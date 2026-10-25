"""yt-dlp command building and output parsing. No Qt dependency.

Strimo runs the standalone yt-dlp.exe as a separate process. That keeps the player
responsive and lets "Update link support" refresh yt-dlp (yt-dlp -U) without
reinstalling Strimo.
"""

from __future__ import annotations

import json
import os

from . import paths

PROGRESS_TAG = "STRIMO|"
FILE_TAG = "STRIMOFILE|"
TITLE_TAG = "STRIMOTITLE|"

QUALITIES = [
    ("best", "Best available"),
    ("2160", "4K (2160p)"),
    ("1440", "1440p"),
    ("1080", "1080p"),
    ("720", "720p"),
    ("480", "480p"),
    ("360", "360p"),
    ("240", "240p (data saver)"),
    ("audio_m4a", "Audio only (M4A)"),
    ("audio_mp3", "Audio only (MP3)"),
]
STREAM_QUALITIES = [q for q in QUALITIES if q[0] != "audio_mp3"]


def ytdlp_path() -> str | None:
    return paths.find_tool("yt-dlp")


def ffmpeg_path() -> str | None:
    return paths.find_tool("ffmpeg")


def _height(q: str):
    return int(q) if q.isdigit() else None


# ---------------------------------------------------------------- formats
def stream_format(quality: str) -> str:
    """Format for playback: separate video+audio links are fine (mpv joins them)."""
    if quality.startswith("audio"):
        return "bestaudio/best"
    h = _height(quality)
    if h:
        return f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
    return "bestvideo+bestaudio/best"


def single_file_format(quality: str) -> str:
    """Format that is one file with both picture and sound (needed for Play & Save)."""
    if quality.startswith("audio"):
        return "bestaudio/best"
    h = _height(quality)
    if h:
        return f"best[height<={h}][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/best"
    return "best[vcodec!=none][acodec!=none]/best"


def download_format_args(quality: str, has_ffmpeg: bool) -> list[str]:
    if quality == "audio_mp3":
        if has_ffmpeg:
            return ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", "0"]
        quality = "audio_m4a"
    if quality == "audio_m4a":
        return ["-f", "bestaudio[ext=m4a]/bestaudio/best"]
    h = _height(quality)
    if has_ffmpeg:
        sort = f"res:{h},ext:mp4:m4a" if h else "ext:mp4:m4a"
        return ["-f", "bv*+ba/b", "-S", sort, "--merge-output-format", "mp4"]
    if h:
        return ["-f", f"b[height<={h}]/b", "-S", f"res:{h},ext:mp4"]
    return ["-f", "b", "-S", "ext:mp4"]


# ---------------------------------------------------------------- commands
def base_args() -> list[str]:
    return ["--no-colors", "--no-playlist", "--no-warnings", "--encoding", "utf-8"]


def info_args(url: str, fmt: str | None = None) -> list[str]:
    args = base_args() + ["-J", "--socket-timeout", "20"]
    if fmt:
        args += ["-f", fmt]
    return args + ["--", url]


def download_args(
    url: str,
    quality: str,
    out_dir: str,
    temp_dir: str,
    ffmpeg: str | None,
    speed_limit_kb: int = 0,
    subs: bool = False,
    sub_langs: str = "en.*",
) -> list[str]:
    progress = (
        "download:" + PROGRESS_TAG
        + "%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|"
        + "%(progress.speed)s|%(progress.eta)s|%(progress.status)s"
    )
    args = base_args() + [
        "--newline",
        "--progress",
        "--no-simulate",
        "--continue",
        "--no-mtime",
        "--windows-filenames",
        "-R", "15",
        "--fragment-retries", "15",
        "--retry-sleep", "3",
        "--socket-timeout", "30",
        "-P", out_dir,
        "-P", f"temp:{temp_dir}",
        "-o", "%(title).150B [%(id)s].%(ext)s",
        "--progress-template", progress,
        "--print", "before_dl:" + TITLE_TAG + "%(title)s",
        "--print", "after_move:" + FILE_TAG + "%(filepath)s",
    ]
    args += download_format_args(quality, bool(ffmpeg))
    if ffmpeg:
        args += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    if speed_limit_kb and speed_limit_kb > 0:
        args += ["-r", f"{int(speed_limit_kb)}K"]
    if subs and not quality.startswith("audio"):
        args += ["--write-subs", "--write-auto-subs", "--sub-langs", sub_langs or "en.*"]
        if ffmpeg:
            args += ["--convert-subs", "srt"]
    return args + ["--", url]


def update_args() -> list[str]:
    return ["-U"]


# ---------------------------------------------------------------- parsing
def _num(text: str):
    text = (text or "").strip()
    if not text or text in ("NA", "None", "none"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_progress(line: str):
    """Return a dict for a progress line, else None."""
    idx = line.find(PROGRESS_TAG)
    if idx < 0:
        return None
    parts = line[idx + len(PROGRESS_TAG):].strip().split("|")
    if len(parts) < 6:
        return None
    downloaded, total, estimate, speed, eta = (_num(p) for p in parts[:5])
    return {
        "downloaded": downloaded,
        "total": total or estimate,
        "speed": speed,
        "eta": eta,
        "status": parts[5].strip(),
    }


def parse_tagged(line: str, tag: str):
    idx = line.find(tag)
    if idx < 0:
        return None
    return line[idx + len(tag):].strip()


def last_error(stderr_text: str) -> str:
    lines = [ln.strip() for ln in (stderr_text or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("ERROR:"):
            msg = ln[len("ERROR:"):].strip()
            return friendly_error(msg)
    return friendly_error(lines[-1]) if lines else "Unknown error"


def friendly_error(msg: str) -> str:
    low = msg.lower()
    if "unsupported url" in low:
        return "This site isn't supported. Try a direct video link instead."
    if "getaddrinfo" in low or "name resolution" in low or "unable to download webpage" in low and "urlopen" in low:
        return "No internet connection (or the site can't be reached)."
    if "sign in" in low or "login" in low or "private" in low:
        return "This video needs a login or is private."
    if "requested format is not available" in low:
        return "That quality isn't available for this video. Try another quality."
    if "http error 403" in low:
        return "The site refused the request (HTTP 403). Updating link support may help."
    if "http error 404" in low:
        return "The link was not found (HTTP 404)."
    return msg[:300]


def parse_info(json_text: str) -> dict:
    """Reduce yt-dlp -J output to what Strimo needs."""
    info = json.loads(json_text)
    if info.get("_type") == "playlist" and info.get("entries"):
        first = next((e for e in info["entries"] if e), None)
        if first:
            info = first
    headers = dict(info.get("http_headers") or {})
    video_url = None
    audio_url = None
    req = info.get("requested_formats")
    if req:
        for f in req:
            if f.get("vcodec") not in (None, "none") and not video_url:
                video_url = f.get("url")
                headers.update(f.get("http_headers") or {})
            elif f.get("acodec") not in (None, "none") and not audio_url:
                audio_url = f.get("url")
        if not video_url and req:
            video_url = req[0].get("url")
            audio_url = None
    else:
        video_url = info.get("url")
    heights = sorted(
        {int(f["height"]) for f in info.get("formats") or [] if isinstance(f.get("height"), (int, float)) and f.get("vcodec") not in (None, "none")},
        reverse=True,
    )
    return {
        "title": info.get("title") or info.get("id") or "",
        "id": info.get("id") or "",
        "ext": info.get("ext") or "mp4",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel") or "",
        "extractor": info.get("extractor_key") or info.get("extractor") or "",
        "is_live": bool(info.get("is_live")),
        "video_url": video_url,
        "audio_url": audio_url,
        "headers": headers,
        "heights": heights,
        "webpage_url": info.get("webpage_url") or "",
        "filesize": info.get("filesize") or info.get("filesize_approx"),
    }
