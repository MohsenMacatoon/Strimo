"""Playback engine: libVLC (the engine inside the VLC app), driven through python-vlc.

The rest of Strimo talks to this class with a small mpv-style vocabulary
(get("time-pos"), set("pause", True), cmd("seek", ...), prop_changed signals),
so the window code didn't have to change when the engine did.

Threading rule: libVLC event callbacks arrive on VLC's own threads. They only
post a Qt signal; every call back into libVLC happens on the GUI thread.
"""

from __future__ import annotations

import os
import threading
import time
from urllib.parse import quote

from PySide6.QtCore import QObject, QTimer, Signal

import vlc  # python-vlc; needs libvlc.dll + plugins (bundled in the "vlc" folder)

from . import paths
from .util import is_url, round_speed

OPT_TRUSTED = 0x2     # libvlc_media_option_trusted: allows filter / sout options per file
OPT_UNIQUE = 0x100    # libvlc_media_option_unique

# VLC "transform" filter types for every rotate/flip combination.
# Each transform is a 2x2 matrix acting on (x, y) with y pointing down.
_MATRICES = {
    "": (1, 0, 0, 1),
    "90": (0, -1, 1, 0),
    "180": (-1, 0, 0, -1),
    "270": (0, 1, -1, 0),
    "hflip": (-1, 0, 0, 1),
    "vflip": (1, 0, 0, -1),
    "transpose": (0, 1, 1, 0),
    "antitranspose": (0, -1, -1, 0),
}


def _mul(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3])


def transform_type(rotation: int, flip_h: bool, flip_v: bool) -> str:
    """VLC transform-type for: flip first, then rotate clockwise by `rotation`."""
    m = _MATRICES[""]
    if flip_h:
        m = _mul(_MATRICES["hflip"], m)
    if flip_v:
        m = _mul(_MATRICES["vflip"], m)
    rot = {0: "", 90: "90", 180: "180", 270: "270"}[int(rotation) % 360]
    m = _mul(_MATRICES[rot], m)
    for name, mat in _MATRICES.items():
        if mat == m:
            return name
    return ""


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

# event ids we listen to
_EV = vlc.EventType
_EVENTS = {
    "opening": _EV.MediaPlayerOpening,
    "buffering": _EV.MediaPlayerBuffering,
    "playing": _EV.MediaPlayerPlaying,
    "paused": _EV.MediaPlayerPaused,
    "stopped": _EV.MediaPlayerStopped,
    "ended": _EV.MediaPlayerEndReached,
    "error": _EV.MediaPlayerEncounteredError,
    "length": _EV.MediaPlayerLengthChanged,
    "vout": _EV.MediaPlayerVout,
}
for _key, _name in (("es_added", "MediaPlayerESAdded"), ("es_deleted", "MediaPlayerESDeleted")):
    if hasattr(_EV, _name):
        _EVENTS[_key] = getattr(_EV, _name)


def _state(name: str):
    return getattr(vlc.State, name)


class Player(QObject):
    prop_changed = Signal(str, object)
    file_started = Signal()
    file_loaded = Signal()
    load_failed = Signal(str)
    render_error = Signal(str)
    _vlc_event = Signal(str, object)  # internal: VLC thread -> GUI thread

    def __init__(self, cfg, backend: str = "native", wid: int | None = None, null_output: bool = False):
        super().__init__()
        self.cfg = cfg
        self.backend = backend
        self.null_output = null_output
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.night_mode = False
        self._closed = False

        # remembered state (VLC can't report some of these, or reports them late)
        self._volume = int(cfg.get("volume"))
        self._muted = bool(cfg.get("muted"))
        self._speed = 1.0
        self._paused = False
        self._loop_file = False
        self._target = None
        self._title = ""
        self._extra = {}            # audio_url, headers, record_path for the current file
        self._loaded = False        # file_loaded already sent for this file
        self._reloading = None      # dict while re-opening the same file (rotation, night mode)
        self._pending_seek = None   # seconds, applied once playback starts
        self._ab = [None, None]
        self._adjust = {"brightness": 0, "contrast": 0, "saturation": 0, "gamma": 0, "hue": 0}
        self._audio_delay = 0.0
        self._sub_delay = 0.0
        self._zoom = 0.0
        self._pan = [0.0, 0.0]
        self._aspect = "auto"
        self._buffering = False
        self._sub_scale = float(cfg.get("sub_scale") or 1.0)

        args = [
            "--quiet", "--no-video-title-show", "--no-snapshot-preview", "--no-stats",
            "--ignore-config", "--http-reconnect", "--file-caching=300",
            f"--network-caching={int(max(1, min(30, int(cfg.get('network_cache_s') or 2))) * 1000)}",
            "--avcodec-hw=" + ("any" if cfg.get("hwdec") else "none"),
            "--sub-autodetect-fuzzy=3",
            "--audio-time-stretch" if cfg.get("pitch_correction") else "--no-audio-time-stretch",
        ]
        if null_output:
            args += ["--vout=dummy", "--aout=dummy"]
        self.inst = vlc.Instance(args)
        if self.inst is None:
            # an option this libVLC doesn't know makes start-up fail: retry with the essentials
            LOG.write("libVLC refused the options; starting with defaults")
            basic = ["--quiet", "--no-video-title-show"] + (["--vout=dummy", "--aout=dummy"] if null_output else [])
            self.inst = vlc.Instance(basic)
        if self.inst is None:
            raise OSError("libVLC could not start (vlc.Instance returned nothing)")
        try:
            self.inst.set_user_agent("Strimo", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Strimo")
        except Exception:  # noqa: BLE001
            pass
        self.mp = self.inst.media_player_new()
        if wid and not null_output:
            if os.name == "nt":
                self.mp.set_hwnd(int(wid))
            else:
                self.mp.set_xwindow(int(wid))
        # let clicks, double-clicks, wheel and keys reach Strimo's window instead of VLC's
        self.mp.video_set_mouse_input(False)
        self.mp.video_set_key_input(False)

        self._vlc_event.connect(self._on_vlc_event)
        self._callbacks = {}
        em = self.mp.event_manager()
        for name, ev in _EVENTS.items():
            cb = self._make_cb(name)
            self._callbacks[name] = cb
            try:
                em.event_attach(ev, cb)
            except Exception as exc:  # noqa: BLE001
                LOG.write(f"event {name} not available: {exc}")

        self._ab_timer = QTimer(self)
        self._ab_timer.setInterval(40)
        self._ab_timer.timeout.connect(self._check_ab)
        self._osd_timer = QTimer(self)
        self._osd_timer.setSingleShot(True)
        self._osd_timer.timeout.connect(self._hide_osd)
        self._reopen_timer = QTimer(self)   # pressing R several times re-opens only once
        self._reopen_timer.setSingleShot(True)
        self._reopen_timer.setInterval(220)
        self._reopen_timer.timeout.connect(self._reopen)
        LOG.write(f"libVLC {self.version()} started")

    # ================================================================ events
    def _make_cb(self, name):
        def cb(event, _name=name):
            if self._closed:
                return
            data = None
            try:
                if _name == "buffering":
                    data = float(event.u.new_cache)
                elif _name == "vout":
                    data = int(event.u.new_count)
            except Exception:  # noqa: BLE001
                data = None
            self._vlc_event.emit(_name, data)
        return cb

    def _emit(self, name, value) -> None:
        if not self._closed:
            self.prop_changed.emit(name, value)

    def _state_is(self, *names) -> bool:
        try:
            st = self.mp.get_state()
        except Exception:  # noqa: BLE001
            return False
        return any(st == _state(n) for n in names)

    def _on_vlc_event(self, name: str, data) -> None:  # noqa: C901 - event dispatch
        if self._closed:
            return
        if name == "opening":
            if self._reloading is None:
                self.file_started.emit()
        elif name == "playing":
            if not self._state_is("Playing"):
                return
            self._paused = False
            self._apply_player_settings()
            if self._pending_seek is not None:
                target, self._pending_seek = self._pending_seek, None
                self._seek_ms(target)
            if self._reloading is not None:
                restore, self._reloading = self._reloading, None
                if restore.get("paused"):
                    self.mp.set_pause(1)
                    self._paused = True
            self._emit("idle-active", False)
            self._emit("eof-reached", False)
            self._emit("pause", self._paused)
            self._emit("duration", self._duration())
            if not self._loaded:
                self._loaded = True
                self.file_loaded.emit()
        elif name == "paused":
            if self._state_is("Paused"):
                self._paused = True
                self._emit("pause", True)
        elif name == "length":
            self._emit("duration", self._duration())
        elif name == "vout":
            if data:
                self._emit("video-params", self._video_params())
                self._emit("vid", 1)
                self._layout_changed()
        elif name in ("es_added", "es_deleted"):
            self._emit("track-list", self.tracks("audio") + self.tracks("sub"))
        elif name == "buffering":
            busy = data is not None and data < 100 and self._target is not None and is_url(self._target)
            if busy != self._buffering:
                self._buffering = busy
                self._emit("paused-for-cache", busy)
        elif name == "ended":
            if not self._state_is("Ended"):
                return
            if self._loop_file:
                self._restart(0.0)
                return
            self._paused = True
            self._emit("pause", True)
            self._emit("eof-reached", True)
        elif name == "stopped":
            if self._reloading is not None or not self._state_is("Stopped", "NothingSpecial"):
                return
            self._emit("idle-active", True)
            self._emit("vid", False)
        elif name == "error":
            if self._state_is("Error"):
                self._reloading = None
                self.load_failed.emit("Strimo couldn't open this file or link.")
                self._emit("idle-active", True)

    # ================================================================ helpers
    @staticmethod
    def version() -> str:
        try:
            v = vlc.libvlc_get_version()
            return v.decode(errors="replace") if isinstance(v, bytes) else str(v)
        except Exception:  # noqa: BLE001
            return "?"

    def _duration(self):
        try:
            ms = self.mp.get_length()
        except Exception:  # noqa: BLE001
            return None
        return ms / 1000.0 if ms and ms > 0 else None

    def _time(self):
        if self._target is None or self._state_is("NothingSpecial", "Stopped", "Error", "Opening"):
            return None
        try:
            ms = self.mp.get_time()
        except Exception:  # noqa: BLE001
            return None
        if ms is None or ms < 0:
            return None
        return ms / 1000.0

    def _fps(self):
        try:
            fps = float(self.mp.get_fps())
        except Exception:  # noqa: BLE001
            fps = 0.0
        if fps <= 0:
            info = self._track_info()
            fps = info.get("fps") or 0.0
        return fps or None

    def _video_size(self):
        try:
            w, h = self.mp.video_get_size(0)
            if w and h:
                return int(w), int(h)
        except Exception:  # noqa: BLE001
            pass
        info = self._track_info()
        if info.get("width") and info.get("height"):
            return int(info["width"]), int(info["height"])
        return None

    def _video_params(self):
        size = self._video_size()
        if not size:
            return {}
        return {"w": size[0], "h": size[1], "dw": size[0], "dh": size[1], "rotate": 0}

    def _has_video(self) -> bool:
        try:
            if self.mp.has_vout() > 0:
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            return self.mp.video_get_track_count() > 0
        except Exception:  # noqa: BLE001
            return False

    def _track_info(self) -> dict:
        out: dict = {}
        media = self.mp.get_media()
        if media is None:
            return out
        try:
            tracks = list(media.tracks_get() or [])
        except Exception:  # noqa: BLE001
            return out
        def part(t, name):
            p = getattr(t, name, None)
            if p is None and hasattr(t, "u"):
                p = getattr(t.u, name, None)
            return p.contents if hasattr(p, "contents") else p

        for t in tracks:
            try:
                t = t.contents if hasattr(t, "contents") else t
                kind = t.type
                codec = self._codec_name(kind, t.codec)
                if kind == vlc.TrackType.video and "width" not in out:
                    v = part(t, "video")
                    out.update(width=v.width, height=v.height, video_codec=codec, video_bitrate=t.bitrate or None)
                    if v.frame_rate_den:
                        out["fps"] = v.frame_rate_num / v.frame_rate_den
                elif kind == vlc.TrackType.audio and "audio_codec" not in out:
                    a = part(t, "audio")
                    out.update(audio_codec=codec, samplerate=a.rate, channels=a.channels,
                               audio_bitrate=t.bitrate or None)
            except Exception:  # noqa: BLE001
                continue
        return out

    @staticmethod
    def _codec_name(kind, fourcc) -> str:
        try:
            d = vlc.libvlc_media_get_codec_description(kind, fourcc)
            if isinstance(d, bytes):
                d = d.decode(errors="replace")
            if d:
                return str(d)
        except Exception:  # noqa: BLE001
            pass
        try:
            return int(fourcc).to_bytes(4, "little").decode("ascii", "replace").strip()
        except Exception:  # noqa: BLE001
            return ""

    # ================================================================ opening files
    def _media_options(self) -> list[str]:
        opts = []
        ex = self._extra
        headers = ex.get("headers") or {}
        for k, v in headers.items():
            if k.lower() == "user-agent":
                opts.append(f":http-user-agent={v}")
            elif k.lower() == "referer":
                opts.append(f":http-referrer={v}")
        if ex.get("audio_url"):
            opts.append(f":input-slave={ex['audio_url']}")
        if ex.get("record_path"):
            dst = ex["record_path"].replace("\\", "/").replace('"', "")
            opts.append(f':sout=#duplicate{{dst=display,dst=std{{access=file,mux=mkv,dst="{dst}"}}}}')
            opts.append(":sout-keep")
        t = transform_type(self.rotation, self.flip_h, self.flip_v)
        if t:
            opts.append(":video-filter=transform")
            opts.append(f":transform-type={t}")
        if self.night_mode:
            opts += [":audio-filter=compressor", ":compressor-threshold=-24", ":compressor-ratio=8",
                     ":compressor-makeup-gain=12", ":compressor-knee=4"]
        opts.append(f":sub-text-scale={int(round(self._sub_scale * 100))}")
        return opts

    def _make_media(self):
        target = self._target
        if is_url(target):
            media = self.inst.media_new(target)
        else:
            media = self.inst.media_new_path(target)
        for opt in self._media_options():
            try:
                media.add_option_flag(opt, OPT_TRUSTED | OPT_UNIQUE)
            except Exception:  # noqa: BLE001
                media.add_option(opt)
        if self._title:
            try:
                media.set_meta(vlc.Meta.Title, self._title)
            except Exception:  # noqa: BLE001
                pass
        return media

    def play(self, target: str, audio_url=None, headers=None, title=None, record_path=None) -> None:
        self._reopen_timer.stop()
        self._target = target
        self._title = title or ""
        self._extra = {"audio_url": audio_url, "headers": headers or {}, "record_path": record_path}
        self._loaded = False
        self._reloading = None
        self._pending_seek = None
        self._buffering = False
        # per-file settings start fresh (like VLC/mpv)
        self._ab = [None, None]
        self._ab_timer.stop()
        self._emit("ab-loop-a", None)
        self._emit("ab-loop-b", None)
        self._audio_delay = 0.0
        self._sub_delay = 0.0
        self._zoom = 0.0
        self._pan = [0.0, 0.0]
        self.mp.set_media(self._make_media())
        self._paused = False
        self.mp.play()
        self._emit("eof-reached", False)

    def _reopen(self) -> None:
        """Open the current file again with new options (rotation, flips, night mode)."""
        if self._target is None or self._state_is("NothingSpecial", "Stopped", "Error"):
            return
        if self._reloading is not None and self._pending_seek is not None:
            pos = self._pending_seek        # still re-opening from a moment ago
        else:
            pos = self._time() or 0.0
        if self._extra.get("record_path"):
            self._extra["record_path"] = None  # re-opening would overwrite the saved copy
            LOG.write("Play & Save stopped because the video was re-opened")
        paused = self._reloading["paused"] if self._reloading is not None else self._paused
        self._reloading = {"paused": paused}
        self._pending_seek = pos
        self.mp.set_media(self._make_media())
        self.mp.play()

    def _restart(self, seconds: float) -> None:
        """Play again after the end was reached (VLC can't seek once it has ended)."""
        self._pending_seek = seconds if seconds > 0.05 else None
        self._reloading = {"paused": False}
        self.mp.stop()
        self.mp.play()

    def _apply_player_settings(self) -> None:
        """Settings that VLC keeps per playback, re-applied whenever playback (re)starts."""
        self.mp.audio_set_volume(int(self._volume))
        self.mp.audio_set_mute(bool(self._muted))
        self.mp.set_rate(float(self._speed))
        self.mp.audio_set_delay(int(self._audio_delay * 1_000_000))
        self.mp.video_set_spu_delay(int(self._sub_delay * 1_000_000))
        self._apply_adjust()
        self._layout_changed()

    def stop(self) -> None:
        self._reloading = None
        self._pending_seek = None
        self._ab_timer.stop()
        self.mp.stop()
        self._emit("idle-active", True)
        self._emit("vid", False)

    # ================================================================ generic access
    def get(self, name: str, default=None):  # noqa: C901 - property table
        try:
            value = self._get(name)
        except Exception:  # noqa: BLE001
            return default
        return default if value is None else value

    def _get(self, name: str):  # noqa: C901
        if name == "time-pos":
            return self._time()
        if name == "duration":
            return self._duration()
        if name == "pause":
            if self._state_is("Ended"):
                return True
            return self._paused
        if name == "speed":
            return self._speed
        if name == "volume":
            return self._volume
        if name == "mute":
            return self._muted
        if name == "idle-active":
            return self._target is None or self._state_is("NothingSpecial", "Stopped", "Error")
        if name == "eof-reached":
            return self._state_is("Ended")
        if name == "vid":
            return 1 if self._has_video() else False
        if name == "video-params":
            return self._video_params() or None
        if name == "container-fps":
            return self._fps()
        if name == "estimated-frame-number":
            t, fps = self._time(), self._fps()
            return int(t * fps) if t is not None and fps else None
        if name == "demuxer-cache-time":
            return None
        if name == "video-rotate":
            return self.rotation
        if name == "vf":
            return transform_type(self.rotation, self.flip_h, self.flip_v)
        if name == "af":
            return "compressor" if self.night_mode else ""
        if name in self._adjust:
            return self._adjust[name]
        if name == "video-zoom":
            return self._zoom
        if name == "video-pan-x":
            return self._pan[0]
        if name == "video-pan-y":
            return self._pan[1]
        if name == "audio-delay":
            return self._audio_delay
        if name == "sub-delay":
            return self._sub_delay
        if name == "loop-file":
            return "inf" if self._loop_file else False
        if name == "path":
            return self._target
        if name == "media-title":
            return self._title or (os.path.basename(self._target) if self._target else "")
        if name == "stream-record":
            return self._extra.get("record_path") or ""
        if name == "ab-loop-a":
            return self._ab[0]
        if name == "ab-loop-b":
            return self._ab[1]
        if name == "track-list":
            return self.tracks("audio") + self.tracks("sub")
        return None

    def set(self, name: str, value) -> bool:  # noqa: C901 - property table
        try:
            if name == "pause":
                self._set_pause(bool(value))
            elif name == "speed":
                self.set_speed(float(value))
            elif name == "volume":
                self.set_volume(float(value))
            elif name == "mute":
                self._muted = bool(value)
                self.mp.audio_set_mute(self._muted)
                self._emit("mute", self._muted)
            elif name == "loop-file":
                self._loop_file = value in ("inf", True, "yes")
            elif name == "audio-pitch-correction":
                pass  # libVLC sets this at start-up; applied the next time Strimo starts
            elif name == "sub-scale":
                self._sub_scale = float(value)  # applied when the next file opens
            elif name in self._adjust:
                self._adjust[name] = int(value)
                self._apply_adjust()
            elif name == "video-zoom":
                self._zoom = max(0.0, float(value))
                self._layout_changed()
            elif name == "video-pan-x":
                self._pan[0] = float(value)
                self._layout_changed()
            elif name == "video-pan-y":
                self._pan[1] = float(value)
                self._layout_changed()
            elif name == "audio-delay":
                self._audio_delay = float(value)
                self.mp.audio_set_delay(int(self._audio_delay * 1_000_000))
            elif name == "sub-delay":
                self._sub_delay = float(value)
                self.mp.video_set_spu_delay(int(self._sub_delay * 1_000_000))
            elif name == "aid":
                self.mp.audio_set_track(-1 if value in ("no", None, False) else int(value))
            elif name == "sid":
                self.mp.video_set_spu(-1 if value in ("no", None, False) else int(value))
            else:
                return True  # options that don't apply to VLC are accepted and ignored
            return True
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"set {name}={value!r} failed: {exc}")
            return False

    def cmd(self, *args) -> bool:
        name = str(args[0]) if args else ""
        rest = list(args[1:])
        try:
            if name == "seek":
                mode = str(rest[1]) if len(rest) > 1 else "relative"
                self.seek(float(rest[0]), "absolute" if mode.startswith("absolute") else "relative",
                          exact="exact" in mode)
            elif name == "show-text":
                self.osd(str(rest[0]) if rest else "", int(rest[1]) if len(rest) > 1 else 1300)
            elif name == "stop":
                self.stop()
            elif name == "frame-step":
                self.frame_step(False)
            elif name == "frame-back-step":
                self.frame_step(True)
            elif name == "ab-loop":
                self._cycle_ab()
            elif name == "sub-add":
                path = str(rest[0])
                uri = path if is_url(path) else "file:///" + quote(os.path.abspath(path).replace("\\", "/"))
                self.mp.add_slave(vlc.MediaSlaveType.subtitle, uri, True)
            elif name == "screenshot-to-file":
                path = str(rest[0])
                return self.mp.video_take_snapshot(0, path, 0, 0) == 0
            elif name == "loadfile":
                self.play(str(rest[0]))
            return True
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"command {args!r} failed: {exc}")
            return False

    # ================================================================ on-screen text (VLC marquee)
    def osd(self, text: str, ms: int = 1300) -> None:
        if self.null_output:
            return
        try:
            if not text:
                self._hide_osd()
                return
            size = self._video_size()
            h = size[1] if size else 720
            if self.rotation % 180 == 90 and size:
                h = size[0]
            M = vlc.VideoMarqueeOption
            self.mp.video_set_marquee_int(M.Enable, 1)
            self.mp.video_set_marquee_int(M.Size, max(16, int(h * 0.045)))
            self.mp.video_set_marquee_int(M.Position, 5)  # top-left
            for key in ("marquee_X", "X", "marquee_Y", "Y"):
                opt = getattr(M, key, None)
                if opt is not None:
                    self.mp.video_set_marquee_int(opt, max(10, int(h * 0.025)))
            self.mp.video_set_marquee_int(M.Opacity, 255)
            self.mp.video_set_marquee_int(M.Color, 0xFFFFFF)
            self.mp.video_set_marquee_int(M.Timeout, 0)
            self.mp.video_set_marquee_string(M.Text, text)
            self._osd_timer.start(max(200, int(ms)))
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"osd failed: {exc}")

    def _hide_osd(self) -> None:
        try:
            self.mp.video_set_marquee_string(vlc.VideoMarqueeOption.Text, "")
            self.mp.video_set_marquee_int(vlc.VideoMarqueeOption.Enable, 0)
        except Exception:  # noqa: BLE001
            pass

    # ================================================================ playback
    def _set_pause(self, paused: bool) -> None:
        if self._state_is("Ended"):
            if not paused:
                self._restart(0.0)
            return
        self._paused = paused
        self.mp.set_pause(1 if paused else 0)
        self._emit("pause", paused)

    def toggle_pause(self) -> None:
        if self.get("idle-active", True):
            return
        if self._state_is("Ended"):
            self._restart(0.0)
            return
        self._set_pause(not self._paused)

    def _seek_ms(self, seconds: float) -> None:
        dur = self._duration()
        if dur:
            seconds = min(seconds, max(0.0, dur - 0.05))
        self.mp.set_time(int(max(0.0, seconds) * 1000))

    def seek(self, seconds: float, mode: str = "relative", exact: bool = True) -> None:
        cur = self._time() or 0.0
        target = seconds if mode == "absolute" else cur + seconds
        dur = self._duration()
        if dur:
            target = max(0.0, min(dur, target))
        else:
            target = max(0.0, target)
        if self._state_is("Ended"):
            if dur is None or target < dur - 0.05:
                self._restart(target)
            return
        if self._state_is("Opening", "Buffering") and not self._loaded:
            self._pending_seek = target
            return
        self._seek_ms(target)

    def frame_step(self, back: bool = False) -> None:
        if self._state_is("Ended", "Stopped", "NothingSpecial"):
            return
        if not back:
            self._paused = True
            self.mp.next_frame()
            self._emit("pause", True)
            return
        fps = self._fps() or 30.0
        cur = self._time() or 0.0
        self._set_pause(True)
        self._seek_ms(max(0.0, cur - 1.0 / fps))

    def set_speed(self, speed: float) -> float:
        s = round_speed(speed)
        self._speed = s
        self.mp.set_rate(float(s))
        self._emit("speed", s)
        return s

    def set_volume(self, vol: float) -> int:
        v = int(max(0, min(200, round(vol))))
        self._volume = v
        self.mp.audio_set_volume(v)
        self._emit("volume", v)
        return v

    # ================================================================ A-B repeat
    def _cycle_ab(self) -> None:
        t = self._time() or 0.0
        a, b = self._ab
        if a is None:
            self._ab = [t, None]
        elif b is None:
            if t <= a + 0.05:
                t = a + 0.5
            self._ab = [a, t]
            self._ab_timer.start()
        else:
            self._ab = [None, None]
            self._ab_timer.stop()
        self._emit("ab-loop-a", self._ab[0])
        self._emit("ab-loop-b", self._ab[1])

    def _check_ab(self) -> None:
        a, b = self._ab
        if a is None or b is None:
            self._ab_timer.stop()
            return
        if self._state_is("Ended"):
            self._restart(a)
            return
        t = self._time()
        if t is not None and t >= b:
            self._seek_ms(a)

    # ================================================================ picture
    def _apply_adjust(self) -> None:
        a = self._adjust
        try:
            A = vlc.VideoAdjustOption
            if not any(a.values()):
                self.mp.video_set_adjust_int(A.Enable, 0)
                return
            self.mp.video_set_adjust_int(A.Enable, 1)
            self.mp.video_set_adjust_float(A.Brightness, 1.0 + a["brightness"] / 100.0)
            self.mp.video_set_adjust_float(A.Contrast, 1.0 + a["contrast"] / 100.0)
            sat = a["saturation"] / 100.0
            self.mp.video_set_adjust_float(A.Saturation, 1.0 + (sat * 2.0 if sat > 0 else sat))
            self.mp.video_set_adjust_float(A.Gamma, 2.0 ** (a["gamma"] / 100.0))
            self.mp.video_set_adjust_float(A.Hue, a["hue"] * 1.8)
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"picture adjust failed: {exc}")

    def _layout_changed(self, window_size=None) -> None:
        """Aspect ratio, zoom and pan."""
        if window_size is not None:
            self._window_size = window_size
        try:
            if self._aspect == "stretch":
                ws = getattr(self, "_window_size", None)
                self.mp.video_set_aspect_ratio(f"{ws[0]}:{ws[1]}" if ws else None)
            elif self._aspect in ("auto", "fill"):
                self.mp.video_set_aspect_ratio(None)
            else:
                self.mp.video_set_aspect_ratio(self._aspect)
            crop = None
            if self._aspect == "fill":
                ws = getattr(self, "_window_size", None)
                if ws and ws[0] and ws[1]:
                    crop = f"{ws[0]}:{ws[1]}"
            elif self._zoom > 0.001:
                size = self._video_size()
                if size:
                    w, h = size
                    f = 2.0 ** self._zoom
                    cw, ch = max(16, int(w / f)), max(16, int(h / f))
                    x = int((w - cw) / 2 + self._pan[0] * 2 * (w - cw) / 2)
                    y = int((h - ch) / 2 + self._pan[1] * 2 * (h - ch) / 2)
                    x = max(0, min(w - cw, x))
                    y = max(0, min(h - ch, y))
                    crop = f"{cw}x{ch}+{x}+{y}"
            self.mp.video_set_crop_geometry(crop)
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"layout failed: {exc}")

    def window_resized(self, w: int, h: int) -> None:
        self._window_size = (int(w), int(h))
        if self._aspect in ("stretch", "fill"):
            self._layout_changed()

    def set_aspect(self, choice: str) -> None:
        self._aspect = choice
        self._layout_changed()

    def set_rotation(self, degrees: int) -> int:
        new = int(degrees) % 360
        if new != self.rotation:
            self.rotation = new
            self._reopen_timer.start()
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
            self._reopen_timer.start()

    def reset_orientation(self) -> None:
        if self.rotation or self.flip_h or self.flip_v:
            self.rotation = 0
            self.flip_h = self.flip_v = False
            self._reopen_timer.start()

    def set_night_mode(self, on: bool) -> None:
        if bool(on) != self.night_mode:
            self.night_mode = bool(on)
            self._reopen_timer.start()

    # ================================================================ tracks
    def tracks(self, kind: str) -> list[dict]:
        try:
            if kind == "audio":
                desc = self.mp.audio_get_track_description() or []
                current = self.mp.audio_get_track()
            elif kind == "sub":
                desc = self.mp.video_get_spu_description() or []
                current = self.mp.video_get_spu()
            else:
                return []
        except Exception:  # noqa: BLE001
            return []
        out = []
        for item in desc:
            try:
                tid, name = item[0], item[1]
            except (TypeError, IndexError):
                continue
            if tid == -1:
                continue  # VLC's own "Disable" entry; the menus add "Off" themselves
            if isinstance(name, bytes):
                name = name.decode(errors="replace")
            out.append({"id": tid, "type": kind, "title": name, "selected": tid == current})
        return out

    @staticmethod
    def track_label(t: dict) -> str:
        return f"{t.get('id')}. {t.get('title') or 'Track'}"

    # ================================================================ info
    def media_info(self) -> dict:
        info = self._track_info()
        size = None
        if self._target and not is_url(self._target):
            try:
                size = os.path.getsize(self._target)
            except OSError:
                size = None
        vs = self._video_size()
        ext = os.path.splitext(self._target or "")[1].lstrip(".").lower()
        return {
            "title": self.get("media-title", ""),
            "path": self._target or "",
            "format": ext,
            "size": size,
            "duration": self._duration(),
            "video_codec": info.get("video_codec", ""),
            "width": vs[0] if vs else info.get("width"),
            "height": vs[1] if vs else info.get("height"),
            "fps": self._fps(),
            "video_bitrate": info.get("video_bitrate"),
            "audio_codec": info.get("audio_codec", ""),
            "samplerate": info.get("samplerate"),
            "channels": info.get("channels"),
            "audio_bitrate": info.get("audio_bitrate"),
            "hwdec": "auto" if self.cfg.get("hwdec") else "off",
        }

    def terminate(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._ab_timer.stop()
        self._osd_timer.stop()
        try:
            em = self.mp.event_manager()
            for ev in _EVENTS.values():
                try:
                    em.event_detach(ev)
                except Exception:  # noqa: BLE001
                    pass
            self.mp.stop()
            self.mp.release()
            self.inst.release()
        except Exception:  # noqa: BLE001
            pass
