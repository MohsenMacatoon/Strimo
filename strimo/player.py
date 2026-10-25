"""Wrapper around libmpv (python-mpv) that talks to the Qt UI through signals."""

from __future__ import annotations

import locale
import os
import threading
import time

from PySide6.QtCore import QObject, Signal

import mpv  # python-mpv; needs libmpv-2.dll next to Strimo.exe

from . import paths
from .util import round_speed

# mpv event ids (stable across mpv versions)
EV_START_FILE = 6
EV_END_FILE = 7
EV_FILE_LOADED = 8
END_REASON_ERROR = 4

OBSERVED = [
    "time-pos", "duration", "pause", "volume", "mute", "speed", "path", "media-title",
    "eof-reached", "idle-active", "demuxer-cache-time", "paused-for-cache",
    "cache-buffering-state", "video-params", "track-list", "ab-loop-a", "ab-loop-b",
    "estimated-frame-number", "container-fps", "vid", "seeking", "loop-file",
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

    def __init__(self, cfg, backend: str = "opengl", wid: int | None = None, null_output: bool = False):
        super().__init__()
        self.cfg = cfg
        self.backend = backend
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.night_mode = False
        self._closed = False

        # libmpv requires the C numeric locale
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except locale.Error:
            pass

        hwdec = "auto-copy" if cfg.get("hwdec") else "no"
        opts = {
            "osc": False,
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            "input_cursor": False,
            "cursor_autohide": "no",
            "keep_open": "yes",
            "idle": "yes",
            "ytdl": False,
            "volume_max": 200,
            "volume": int(cfg.get("volume")),
            "mute": bool(cfg.get("muted")),
            "hr_seek": "yes",
            "cache": "yes",
            "demuxer_max_bytes": f"{int(cfg.get('cache_mb'))}MiB",
            "demuxer_max_back_bytes": "64MiB",
            "demuxer_readahead_secs": int(cfg.get("readahead_secs")),
            "network_timeout": 30,
            "screenshot_format": "png",
            "sub_auto": "fuzzy",
            "sub_scale": float(cfg.get("sub_scale")),
            "audio_pitch_correction": bool(cfg.get("pitch_correction")),
            "osd_font_size": 34,
            "osd_border_size": 2,
            "osd_duration": 1300,
            "osd_bar": False,
            "hwdec": hwdec,
            "reset_on_next_file": "ab-loop-a,ab-loop-b,audio-delay,sub-delay,video-zoom,video-pan-x,video-pan-y",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Strimo",
        }
        if null_output:
            opts.update(vo="null", ao="null")
        elif backend == "native":
            opts.update(vo="gpu", wid=str(int(wid or 0)))
        else:
            opts.update(vo="libmpv")

        str_opts = {k: _opt(v) for k, v in opts.items()}
        self.m = mpv.MPV(log_handler=self._on_log, loglevel="warn", **str_opts)
        self._default_ua = str_opts["user_agent"]

        if backend == "native" and not null_output:
            # newer mpv: let mouse events pass through to Strimo's window
            self.set("input-cursor-passthrough", True)

        for name in OBSERVED:
            try:
                self.m.observe_property(name, self._on_prop)
            except Exception as exc:  # property missing in an old libmpv
                LOG.write(f"observe {name} failed: {exc}")
        self.m.register_event_callback(self._on_event)

    # ------------------------------------------------------------ callbacks (mpv thread)
    def _on_prop(self, name, value):
        if not self._closed:
            self.prop_changed.emit(name, value)

    def _on_log(self, level, component, message):
        text = f"[{level}] {component}: {message}"
        LOG.write(text)
        if level in ("error", "fatal") and component in ("vo", "libmpv_render", "vo/libmpv", "gpu", "vo/gpu"):
            if not self._closed:
                self.render_error.emit(message.strip())

    @staticmethod
    def _event_info(ev):
        """Return (event_id, end_reason) from a python-mpv event.

        python-mpv has delivered events as objects (1.x) and as dicts (older versions),
        with slightly different shapes, so every known layout is tried.
        """
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

        d = None
        if isinstance(ev, dict):
            d = ev
        eid = as_int(getattr(ev, "event_id", None)) if d is None else None
        if eid is None:
            if d is None and hasattr(ev, "as_dict"):
                try:
                    d = ev.as_dict()
                except Exception:
                    d = None
            if d:
                eid = as_int(d.get("event_id"))
                if eid is None and not isinstance(d.get("event"), dict):
                    eid = as_int(d.get("event"))
        if eid != EV_END_FILE:
            return eid, None

        # find the end-file reason
        try:
            data = ev.data if d is None else None
        except Exception:
            data = None
        if data is not None and hasattr(data, "reason"):
            return eid, norm_reason(data.reason)
        if d is None and hasattr(ev, "as_dict"):
            try:
                d = ev.as_dict()
            except Exception:
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
        except Exception as exc:
            LOG.write(f"event parse failed: {exc}")
            return
        if eid == EV_FILE_LOADED:
            self.file_loaded.emit()
        elif eid == EV_START_FILE:
            self.file_started.emit()
        elif eid == EV_END_FILE and reason == END_REASON_ERROR:
            self.load_failed.emit("Strimo couldn't open this file or link.")

    # ------------------------------------------------------------ basic access
    def get(self, name: str, default=None):
        try:
            value = self.m[name]
        except Exception:
            return default
        return default if value is None else value

    def set(self, name: str, value) -> bool:
        try:
            self.m[name] = value
            return True
        except Exception as exc:
            LOG.write(f"set {name}={value!r} failed: {exc}")
            return False

    def cmd(self, *args) -> bool:
        try:
            self.m.command(*[str(a) for a in args])
            return True
        except Exception as exc:
            LOG.write(f"command {args!r} failed: {exc}")
            return False

    def osd(self, text: str, ms: int = 1300) -> None:
        self.cmd("show-text", text, ms)

    # ------------------------------------------------------------ playback
    def play(self, target: str, audio_url=None, headers=None, title=None, record_path=None) -> None:
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
            elif lk in ("accept-encoding",):
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
        self.set("stream-record", "")
        self.cmd("stop")

    def toggle_pause(self) -> None:
        if self.get("idle-active", True):
            return
        if self.get("eof-reached", False):
            self.cmd("seek", 0, "absolute+exact")
            self.set("pause", False)
            return
        self.set("pause", not self.get("pause", False))

    def seek(self, seconds: float, mode: str = "relative", exact: bool = True) -> None:
        self.cmd("seek", f"{seconds:.3f}", f"{mode}+{'exact' if exact else 'keyframes'}")

    def frame_step(self, back: bool = False) -> None:
        self.cmd("frame-back-step" if back else "frame-step")

    def set_speed(self, speed: float) -> float:
        s = round_speed(speed)
        self.set("speed", s)
        return s

    def set_volume(self, vol: float) -> int:
        v = int(max(0, min(200, round(vol))))
        self.set("volume", v)
        return v

    # ------------------------------------------------------------ picture
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
        if horizontal is not None:
            self.flip_h = bool(horizontal)
        if vertical is not None:
            self.flip_v = bool(vertical)
        self._apply_vf()

    def reset_orientation(self) -> None:
        self.flip_h = self.flip_v = False
        self._apply_vf()
        self.set_rotation(0)

    def set_aspect(self, choice: str) -> None:
        self.set("panscan", 1.0 if choice == "fill" else 0.0)
        self.set("keepaspect", choice != "stretch")
        if choice in ("auto", "stretch", "fill"):
            self.set("video-aspect-override", "-1")
        else:
            self.set("video-aspect-override", choice)

    def set_night_mode(self, on: bool) -> None:
        self.night_mode = bool(on)
        self.set("af", NIGHT_MODE_FILTER if on else "")

    # ------------------------------------------------------------ tracks
    def tracks(self, kind: str) -> list[dict]:
        out = []
        for t in self.get("track-list", []) or []:
            if t.get("type") == kind:
                out.append(t)
        return out

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
        label = " · ".join(bits) if bits else "Track"
        return f"{t.get('id')}. {label}"

    # ------------------------------------------------------------ info
    def media_info(self) -> dict:
        vp = self.get("video-params", {}) or {}
        ap = self.get("audio-params", {}) or {}
        return {
            "title": self.get("media-title", ""),
            "path": self.get("path", ""),
            "format": self.get("file-format", ""),
            "size": self.get("file-size"),
            "duration": self.get("duration"),
            "video_codec": self.get("video-codec", "") or self.get("video-format", ""),
            "width": vp.get("w"),
            "height": vp.get("h"),
            "fps": self.get("container-fps"),
            "video_bitrate": self.get("video-bitrate"),
            "audio_codec": self.get("audio-codec-name", "") or self.get("audio-codec", ""),
            "samplerate": ap.get("samplerate"),
            "channels": ap.get("channel-count") or ap.get("channels"),
            "audio_bitrate": self.get("audio-bitrate"),
            "hwdec": self.get("hwdec-current", ""),
        }

    def terminate(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.m.terminate()
        except Exception:
            pass
