"""Small helpers with no Qt dependency (unit-tested in tests/test_logic.py)."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse, unquote

VIDEO_EXTS = {
    "mp4", "m4v", "mkv", "webm", "avi", "mov", "wmv", "flv", "f4v", "mpg", "mpeg",
    "m2v", "ts", "m2ts", "mts", "3gp", "3g2", "ogv", "vob", "divx", "xvid", "rm",
    "rmvb", "asf", "y4m", "mxf", "hevc", "h264", "h265", "av1", "ivf",
}
AUDIO_EXTS = {
    "mp3", "m4a", "aac", "flac", "wav", "ogg", "oga", "opus", "wma", "alac", "aiff",
    "aif", "ape", "mka", "ac3", "dts", "amr", "mid", "midi", "wv",
}
SUB_EXTS = {"srt", "ass", "ssa", "vtt", "sub", "idx", "sup", "smi", "txt"}
STREAM_EXTS = {"m3u8", "mpd"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS

URL_SCHEMES = ("http://", "https://", "rtmp://", "rtmps://", "rtsp://", "mms://", "udp://", "rtp://", "srt://")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ext_of(path: str) -> str:
    """Lower-case extension without the dot. Works for paths and URLs."""
    if is_url(path):
        path = unquote(urlparse(path).path)
    return os.path.splitext(path)[1].lower().lstrip(".")


def is_media_file(path: str) -> bool:
    return ext_of(path) in MEDIA_EXTS


def is_sub_file(path: str) -> bool:
    return ext_of(path) in SUB_EXTS - {"txt"}


def is_url(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return t.startswith(URL_SCHEMES)


def normalize_url(text: str) -> str:
    """Turn user input like 'www.site.com/v.mp4' into a full URL. Returns '' if it is not a link."""
    t = (text or "").strip().strip('"').strip("'")
    if not t:
        return ""
    if is_url(t):
        return t
    if t.lower().startswith("www.") or re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/|$)", t, re.I):
        if " " not in t:
            return "https://" + t
    return ""


def is_direct_media_url(url: str) -> bool:
    """True when the link points straight at a media file or stream manifest."""
    if not is_url(url):
        return False
    low = url.lower()
    if low.startswith(("rtmp", "rtsp", "mms", "udp", "rtp", "srt:")):
        return True
    e = ext_of(url)
    return e in MEDIA_EXTS or e in STREAM_EXTS


def fmt_time(seconds, show_hours: bool = False) -> str:
    """12.3 -> '0:12', 3725 -> '1:02:05'. None -> '--:--'."""
    if seconds is None:
        return "--:--"
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "--:--"
    neg = s < 0
    s = int(abs(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h or show_hours:
        out = f"{h}:{m:02d}:{sec:02d}"
    else:
        out = f"{m}:{sec:02d}"
    return "-" + out if neg else out


def fmt_time_precise(seconds) -> str:
    """Like fmt_time but with tenths, e.g. '1:02.4'."""
    if seconds is None:
        return "--:--"
    s = max(0.0, float(seconds))
    whole = int(s)
    tenth = int((s - whole) * 10)
    return f"{fmt_time(whole)}.{tenth}"


def parse_time(text: str):
    """Parse '83', '1:23', '01:02:03', '1m30s', '1h2m', '90.5'. Returns seconds or None."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if not t:
        return None
    try:
        if ":" in t:
            parts = [float(p) for p in t.split(":")]
            if len(parts) > 3 or any(p < 0 for p in parts):
                return None
            total = 0.0
            for p in parts:
                total = total * 60 + p
            return total
        m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?\s*(?:(\d+(?:\.\d+)?)m)?\s*(?:(\d+(?:\.\d+)?)s?)?", t)
        if m and any(m.groups()):
            h, mi, s = (float(g) if g else 0.0 for g in m.groups())
            return h * 3600 + mi * 60 + s
        return float(t)
    except ValueError:
        return None


def natural_key(text: str):
    """Sort 'ep2' before 'ep10'."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]


def folder_media_files(folder: str) -> list[str]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    files = [os.path.join(folder, n) for n in names if is_media_file(n) and os.path.isfile(os.path.join(folder, n))]
    files.sort(key=lambda p: natural_key(os.path.basename(p)))
    return files


def human_size(num) -> str:
    if num is None:
        return "?"
    n = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_speed(bps) -> str:
    if not bps:
        return ""
    return human_size(bps) + "/s"


def human_bitrate(bps) -> str:
    if not bps:
        return "?"
    b = float(bps)
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} Mbps"
    return f"{b / 1000:.0f} kbps"


def safe_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip(" .")
    if not name:
        name = "video"
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if name.upper() in reserved:
        name = "_" + name
    return name[:max_len].rstrip(" .")


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def display_name(entry: str) -> str:
    """Friendly name for a playlist entry (file path or URL)."""
    if is_url(entry):
        p = urlparse(entry)
        tail = unquote(p.path.rstrip("/").split("/")[-1]) if p.path else ""
        if tail and len(tail) < 80 and "." in tail:
            return tail
        return p.netloc + (p.path if len(p.path) < 40 else p.path[:37] + "...")
    return os.path.basename(entry) or entry


def media_key(entry: str) -> str:
    """Stable key for remembering per-file data (position, speed, bookmarks)."""
    if is_url(entry):
        return entry.strip()
    return os.path.normcase(os.path.abspath(entry))


def round_speed(speed: float) -> float:
    return round(clamp(float(speed), 0.05, 8.0), 2)


def fmt_speed(speed) -> str:
    try:
        return f"{float(speed):.2f}×"
    except (TypeError, ValueError):
        return "1.00×"


ASPECT_CHOICES = [
    ("auto", "Auto (original)"),
    ("16:9", "16:9"),
    ("4:3", "4:3"),
    ("21:9", "21:9 (cinema)"),
    ("1:1", "1:1 (square)"),
    ("9:16", "9:16 (vertical)"),
    ("stretch", "Stretch to window"),
    ("fill", "Crop to fill"),
]
