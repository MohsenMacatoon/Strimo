"""Playback engine: libmpv, drawing straight into Strimo's window (no per-frame work in Python).

mpv renders with the graphics card (Direct3D 11 on Windows) into its own child window
inside the video widget - the same way VLC and mpv-based players work. Rotation, flips,
night mode, zoom and subtitle size all change instantly while playing.

The window talks to this class with a small vocabulary (get/set/cmd, prop_changed).
"""

from __future__ import annotations

import locale
import os
import threading
import time

from PySide6.QtCore import QObject, Signal

import mpv  # python-mpv; needs libmpv-2.dll next to Strimo.exe

from . import __version__, paths
from .util import round_speed

# mpv event ids (stable across mpv versions)
EV_START_FILE = 6
EV_END_FILE = 7
EV_FILE_LOADED = 8
END_REASON_ERROR = 4

# Only properties that change occasionally. Position, buffer and frame number are
# read by a 5x-per-second timer in the window instead of being pushed every frame.
OBSERVED = [
    "duration", "pause", "volume", "mute", "speed", "media-title", "eof-reached", "idle-active",
    "paused-for-cache", "video-params", "track-list", "ab-loop-a", "ab-loop-b", "vid",
]

NIGHT_MODE_FILTER = "lavfi=[dynaudnorm=f=200:g=15:p=0.7:m=8]"


def _opt(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


class _LogFile:
    """Tiny thread-safe log writer (keeps the file small)."""

    def __init__(self, path: str, max_bytes: int = 512_000):
        self.path = path
        self.lock = threading.Lock()
        try:
            if os.path.getsize(path) > max_bytes:
                os.replace(path, path + ".old")
        except OSError:
            pass

    def write(self, text: str) -> None:
        with self.lock:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
            except OSError:
                pass


LOG = _LogFile(paths.log_path())


class Player(QObject):
    prop_changed = Signal(str, object)
    file_started = Signal()
    file_loaded = Signal()
    load_failed = Signal(str)
    render_error = Signal(str)

    def __init__(self, cfg, backend: str = "native", wid: int | None = None, null_output: bool = False):
        super().__init__()
        self.cfg = cfg
        self.backend = backend
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.night_mode = False
        self._closed = False
        self._speed = 1.0
        self._seek_target = None   # newest requested seek, until mpv reports it
        self._seek_at = 0.0
        t0 = time.monotonic()

        # libmpv requires the C numeric locale
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except locale.Error:
            pass

        opts = {
            "osc": False,
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            "input_cursor": False,
            "cursor_autohide": "no",       # Strimo hides the cursor itself in fullscreen
            "keep_open": "yes",
            "idle": "yes",
            "ytdl": False,
            "volume_max": 200,
            "volume": int(cfg.get("volume")),
            "mute": bool(cfg.get("muted")),
            "hr_seek": "yes",
            "cache": "yes",
            "demuxer_max_bytes": f"{int(cfg.get('cache_mb') or 150)}MiB",
            "demuxer_max_back_bytes": "64MiB",
            "demuxer_readahead_secs": int(cfg.get("readahead_secs") or 60),
            "cache_pause_wait": max(1, min(30, int(cfg.get("network_cache_s") or 2))),
            "network_timeout": 30,
            "screenshot_format": "png",
            "sub_auto": "fuzzy",
            "sub_scale": float(cfg.get("sub_scale") or 1.0),
            "audio_pitch_correction": bool(cfg.get("pitch_correction")),
            "osd_font_size": 34,
            "osd_border_size": 2,
            "osd_duration": 1300,
            "osd_bar": False,
            "hwdec": "auto-safe" if cfg.get("hwdec") else "no",
            "reset_on_next_file": "ab-loop-a,ab-loop-b,audio-delay,sub-delay,video-zoom,video-pan-x,video-pan-y",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Strimo",
        }
        if null_output:
            opts.update(vo="null", ao="null")
        else:
            opts.update(vo="gpu-next,gpu", wid=str(int(wid or 0)))

        str_opts = {k: _opt(v) for k, v in opts.items()}
        self.m = mpv.MPV(log_handler=self._on_log, loglevel="warn", **str_opts)
        self._default_ua = str_opts["user_agent"]
        if not null_output:
            # newer mpv: let clicks pass through mpv's window to Strimo's
            self.set("input-cursor-passthrough", True)

        for name in OBSERVED:
            try:
                self.m.observe_property(name, self._on_prop)
            except Exception as exc:  # property missing in an old libmpv
                LOG.write(f"observe {name} failed: {exc}")
        self.m.register_event_callback(self._on_event)
        LOG.write(f"Strimo {__version__} started with mpv {self.version()} "
                  f"({(time.monotonic() - t0) * 1000:.0f} ms)")

    # ------------------------------------------------------------ callbacks (mpv thread)
    def _on_prop(self, name, value):
        if not self._closed:
            self.prop_changed.emit(name, value)

    def _on_log(self, level, component, message):
        LOG.write(f"[{level}] {component}: {message}")
        if level in ("error", "fatal") and component.startswith(("vo", "gpu", "d3d11")) and not self._closed:
            self.render_error.emit(message.strip())

    @staticmethod
    def _event_info(ev):
        """Return (event_id, end_reason) from a python-mpv event (object or dict style)."""
        names = {"start-file": EV_START_FILE, "end-file": EV_END_FILE, "file-loaded": EV_FILE_LOADED}

        def as_int(v):
            v = getattr(v, "value", v)
            if isinstance(v, bytes):
                v = v.decode(errors="replace")
            if isinstance(v, str):
                return names.get(v)
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        def norm_reason(r):
            r = getattr(r, "value", r)
            if isinstance(r, bytes):
                r = r.decode(errors="replace")
            if isinstance(r, str):
                return END_REASON_ERROR if r.lower() == "error" else None
            try:
                return int(r)
            except (TypeError, ValueError):
                return None

        d = ev if isinstance(ev, dict) else None
        eid = as_int(getattr(ev, "event_id", None)) if d is None else None
        if eid is None:
            if d is None and hasattr(ev, "as_dict"):
                try:
                    d = ev.as_dict()
                except Exception:  # noqa: BLE001
                    d = None
            if d:
                eid = as_int(d.get("event_id"))
                if eid is None and not isinstance(d.get("event"), dict):
                    eid = as_int(d.get("event"))
        if eid != EV_END_FILE:
            return eid, None
        try:
            data = ev.data if d is None else None
        except Exception:  # noqa: BLE001
            data = None
        if data is not None and hasattr(data, "reason"):
            return eid, norm_reason(data.reason)
        if d is None and hasattr(ev, "as_dict"):
            try:
                d = ev.as_dict()
            except Exception:  # noqa: BLE001
                d = None
        if d:
            for holder in (d, d.get("event"), d.get("data")):
                if isinstance(holder, dict) and "reason" in holder:
                    return eid, norm_reason(holder["reason"])
        return eid, None

    def _on_event(self, ev):
        if self._closed:
            return
        try:
            eid, reason = self._event_info(ev)
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"event parse failed: {exc}")
            return
        if eid == EV_FILE_LOADED:
            self.file_loaded.emit()
        elif eid == EV_START_FILE:
            self.file_started.emit()
        elif eid == EV_END_FILE and reason == END_REASON_ERROR:
            self.load_failed.emit("Strimo couldn't open this file or link.")

    # ------------------------------------------------------------ basic access
    def version(self) -> str:
        return str(self._raw("mpv-version", "?"))

    # NOTE: python-mpv's player["name"] reads/writes mpv's *start-up options*, not the
    # live properties (playback position, pause state, idle state...). Live properties
    # are attributes: player.time_pos, player.pause = True. Always go through these two.
    def _raw(self, name, default=None):
        try:
            value = getattr(self.m, name.replace("-", "_"))
        except Exception:  # noqa: BLE001
            return default
        return default if value is None else value

    def _put(self, name, value) -> None:
        setattr(self.m, name.replace("-", "_"), value)

    def _engine_time(self):
        t = self._raw("time-pos")
        return float(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else None

    def _time(self):
        """Current time - or, for the instant right after a seek, the spot being sought."""
        real = self._engine_time()
        tgt = self._seek_target
        if tgt is not None:
            age = time.monotonic() - self._seek_at
            ahead = (age + 0.3) * max(1.0, float(self._speed)) + 0.5
            if (real is not None and tgt - 0.4 <= real <= tgt + ahead) or age > 1.5:
                self._seek_target = None
            else:
                return tgt
        return real

    def get(self, name: str, default=None):
        if name == "time-pos":
            t = self._time()
            return default if t is None else t
        if name == "video-rotate":
            return self.rotation
        return self._raw(name, default)

    def set(self, name: str, value) -> bool:
        if name == "speed":
            self.set_speed(float(value))
            return True
        try:
            self._put(name, value)
            return True
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"set {name}={value!r} failed: {exc}")
            return False

    def cmd(self, *args) -> bool:
        try:
            self.m.command(*[str(a) for a in args])
            return True
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"command {args!r} failed: {exc}")
            return False

    def osd(self, text: str, ms: int = 1300) -> None:
        self.cmd("show-text", text, ms)

    # ------------------------------------------------------------ playback
    def play(self, target: str, audio_url=None, headers=None, title=None, record_path=None) -> None:
        self._seek_target = None
        self.cmd("change-list", "audio-files", "clr", "")
        if audio_url:
            self.cmd("change-list", "audio-files", "append", audio_url)
        self.cmd("change-list", "http-header-fields", "clr", "")
        ua = None
        ref = None
        for k, v in (headers or {}).items():
            lk = k.lower()
            if lk == "user-agent":
                ua = v
            elif lk == "referer":
                ref = v
            elif lk == "accept-encoding":
                continue
            else:
                self.cmd("change-list", "http-header-fields", "append", f"{k}: {v}")
        self.set("user-agent", ua or self._default_ua)
        self.set("referrer", ref or "")
        self.set("force-media-title", title or "")
        self.set("stream-record", record_path or "")
        self.cmd("loadfile", target, "replace")
        self.set("pause", False)

    def stop(self) -> None:
        self._seek_target = None
        self.set("stream-record", "")
        self.cmd("stop")

    def toggle_pause(self) -> None:
        if self._raw("idle-active", True):
            return
        if self._raw("eof-reached", False):
            self.seek(0, "absolute")
            self.set("pause", False)
            return
        self.set("pause", not self._raw("pause", False))

    def seek(self, seconds: float, mode: str = "relative", exact: bool = True) -> None:
        cur = self._time() or 0.0
        target = float(seconds) if mode == "absolute" else cur + float(seconds)
        dur = self._raw("duration")
        if isinstance(dur, (int, float)) and dur > 0:
            target = min(target, max(0.0, float(dur) - 0.05))
        target = max(0.0, target)
        # absolute seeks to the computed target, so quick repeated skips add up
        self.cmd("seek", f"{target:.3f}", "absolute+exact" if exact else "absolute+keyframes")
        self._seek_target = target
        self._seek_at = time.monotonic()

    def frame_step(self, back: bool = False) -> None:
        self._seek_target = None
        self.cmd("frame-back-step" if back else "frame-step")

    def set_speed(self, speed: float) -> float:
        s = round_speed(speed)
        self._speed = s
        try:
            self._put("speed", s)
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"speed failed: {exc}")
        return s

    def set_volume(self, vol: float) -> int:
        v = int(max(0, min(200, round(vol))))
        self.set("volume", v)
        return v

    # ------------------------------------------------------------ picture (all instant in mpv)
    def _apply_vf(self) -> None:
        filters = []
        if self.flip_h:
            filters.append("lavfi=[hflip]")
        if self.flip_v:
            filters.append("lavfi=[vflip]")
        self.set("vf", ",".join(filters))

    def set_rotation(self, degrees: int) -> int:
        self.rotation = int(degrees) % 360
        self.set("video-rotate", self.rotation)
        return self.rotation

    def set_flip(self, horizontal=None, vertical=None) -> None:
        changed = False
        if horizontal is not None and bool(horizontal) != self.flip_h:
            self.flip_h = bool(horizontal)
            changed = True
        if vertical is not None and bool(vertical) != self.flip_v:
            self.flip_v = bool(vertical)
            changed = True
        if changed:
            self._apply_vf()

    def reset_orientation(self) -> None:
        if self.flip_h or self.flip_v:
            self.flip_h = self.flip_v = False
            self._apply_vf()
        self.set_rotation(0)

    def set_aspect(self, choice: str) -> None:
        self.set("panscan", 1.0 if choice == "fill" else 0.0)
        self.set("keepaspect", choice != "stretch")
        self.set("video-aspect-override", "no" if choice in ("auto", "stretch", "fill") else choice)

    def set_night_mode(self, on: bool) -> None:
        self.night_mode = bool(on)
        self.set("af", NIGHT_MODE_FILTER if on else "")

    # ------------------------------------------------------------ tracks
    def tracks(self, kind: str) -> list[dict]:
        return [t for t in (self._raw("track-list", []) or []) if t.get("type") == kind]

    @staticmethod
    def track_label(t: dict) -> str:
        bits = []
        if t.get("title"):
            bits.append(str(t["title"]))
        if t.get("lang"):
            bits.append(str(t["lang"]).upper())
        if t.get("codec"):
            bits.append(str(t["codec"]))
        if t.get("external"):
            bits.append("external")
        return f"{t.get('id')}. {' · '.join(bits) if bits else 'Track'}"

    # ------------------------------------------------------------ info
    def media_info(self) -> dict:
        vp = self._raw("video-params", {}) or {}
        ap = self._raw("audio-params", {}) or {}
        return {
            "title": self._raw("media-title", ""),
            "path": self._raw("path", ""),
            "format": self._raw("file-format", ""),
            "size": self._raw("file-size"),
            "duration": self._raw("duration"),
            "video_codec": self._raw("video-codec", "") or self._raw("video-format", ""),
            "width": vp.get("w"),
            "height": vp.get("h"),
            "fps": self._raw("container-fps"),
            "video_bitrate": self._raw("video-bitrate"),
            "audio_codec": self._raw("audio-codec-name", "") or self._raw("audio-codec", ""),
            "samplerate": ap.get("samplerate"),
            "channels": ap.get("channel-count") or ap.get("channels"),
            "audio_bitrate": self._raw("audio-bitrate"),
            "hwdec": self._raw("hwdec-current", ""),
        }

    def terminate(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.m.terminate()
        except Exception:  # noqa: BLE001
            pass
