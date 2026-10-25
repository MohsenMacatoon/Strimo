"""Tests for the parts of Strimo that don't need Qt or mpv.  Run: python -m pytest tests  (or python tests/test_logic.py)"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strimo import ytdl  # noqa: E402
from strimo.config import Config  # noqa: E402
from strimo.util import (  # noqa: E402
    display_name, fmt_speed, fmt_time, human_size, is_direct_media_url, is_media_file, is_sub_file,
    is_url, natural_key, normalize_url, parse_time, round_speed, safe_filename, unique_path,
)


def test_fmt_time():
    assert fmt_time(None) == "--:--"
    assert fmt_time(0) == "0:00"
    assert fmt_time(12.9) == "0:12"
    assert fmt_time(75) == "1:15"
    assert fmt_time(3725) == "1:02:05"
    assert fmt_time(65, show_hours=True) == "0:01:05"
    assert fmt_time(-5) == "-0:05"


def test_parse_time():
    assert parse_time("83") == 83
    assert parse_time("1:23") == 83
    assert parse_time("01:02:03") == 3723
    assert parse_time("1m30s") == 90
    assert parse_time("1h2m") == 3720
    assert parse_time("90.5") == 90.5
    assert parse_time("") is None
    assert parse_time("abc") is None
    assert parse_time("1:2:3:4") is None


def test_speed():
    assert round_speed(1.374) == 1.37
    assert round_speed(0.01) == 0.05
    assert round_speed(50) == 8.0
    assert fmt_speed(1.5) == "1.50×"


def test_urls():
    assert is_url("https://x.com/a.mp4")
    assert not is_url("C:\\videos\\a.mp4")
    assert normalize_url("www.example.com/v.mp4") == "https://www.example.com/v.mp4"
    assert normalize_url("example.com/watch?v=1") == "https://example.com/watch?v=1"
    assert normalize_url("hello world") == ""
    assert normalize_url("  https://a.b/c  ") == "https://a.b/c"
    assert is_direct_media_url("https://cdn.site.com/path/movie.MKV?token=1")
    assert is_direct_media_url("https://cdn.site.com/live/index.m3u8")
    assert not is_direct_media_url("https://www.youtube.com/watch?v=abc")
    assert display_name("https://cdn.site.com/path/My%20Movie.mp4") == "My Movie.mp4"


def test_files():
    assert is_media_file("a.MP4") and is_media_file("song.flac")
    assert not is_media_file("notes.txt")
    assert is_sub_file("movie.srt") and not is_sub_file("readme.txt")
    names = ["ep10.mp4", "ep2.mp4", "Ep1.mp4"]
    assert sorted(names, key=natural_key) == ["Ep1.mp4", "ep2.mp4", "ep10.mp4"]
    assert safe_filename('a/b:c*?"<>|') == "a_b_c______"
    assert safe_filename("CON") == "_CON"
    assert human_size(1536) == "2 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.mkv")
        open(p, "w").close()
        assert unique_path(p).endswith("x (2).mkv")


def test_config_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.json")
        c = Config(path)
        f = os.path.join(d, "video.mp4")
        c.set_position(f, 123.456)
        c.set_speed(f, 1.37)
        c.set_list(f, "bookmarks", [{"t": 50, "label": "b"}, {"t": 10, "label": "a"}])
        c.set_intro(f, 0, 90)
        c.add_recent(f)
        c.add_recent("https://x/y.mp4")
        c.add_recent(f)
        c.set("volume", 150)
        c.save()
        c2 = Config(path)
        assert c2.get_position(f) == 123.46
        assert c2.get_speed(f) == 1.37
        assert [b["label"] for b in c2.get_list(f, "bookmarks")] == ["a", "b"]
        assert c2.get_intro(os.path.join(d, "other.mp4")) == (0.0, 90.0)
        assert c2.get("recent")[0] == f and len(c2.get("recent")) == 2
        assert c2.get("volume") == 150
        c2.set_speed(f, 1.0)
        assert c2.get_speed(f) is None
        c2.set_position(f, None)
        c2.set_list(f, "bookmarks", [])
        assert c2.media(f) is None  # empty record removed
        assert c2.get_intro("https://x/y.mp4") is None


def test_config_bad_types_ignored():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.json")
        with open(path, "w") as fh:
            json.dump({"volume": "loud", "boost_speed": 3, "recent": "nope"}, fh)
        c = Config(path)
        assert c.get("volume") == 100
        assert c.get("boost_speed") == 3
        assert c.get("recent") == []


def test_ytdl_formats_and_args():
    assert ytdl.stream_format("720") == "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    assert "acodec!=none" in ytdl.single_file_format("480")
    assert ytdl.download_format_args("audio_mp3", False) == ["-f", "bestaudio[ext=m4a]/bestaudio/best"]
    assert "-x" in ytdl.download_format_args("audio_mp3", True)
    assert ytdl.download_format_args("1080", True)[:2] == ["-f", "bv*+ba/b"]
    assert ytdl.download_format_args("1080", False)[1] == "b[height<=1080]/b"
    args = ytdl.download_args("https://x/v", "720", "/out", "/tmp/p", "/tools/ffmpeg.exe", 300, True, "en.*")
    assert args[-2:] == ["--", "https://x/v"]
    assert "-r" in args and args[args.index("-r") + 1] == "300K"
    assert "--write-subs" in args and "--convert-subs" in args
    assert "--ffmpeg-location" in args
    assert "temp:/tmp/p" in args
    args2 = ytdl.download_args("https://x/v", "audio_m4a", "/out", "/tmp/p", None, 0, True)
    assert "--write-subs" not in args2 and "-r" not in args2 and "--ffmpeg-location" not in args2


def test_ytdl_progress_parsing():
    line = "STRIMO|1048576|10485760|NA|524288.5|17|downloading"
    p = ytdl.parse_progress(line)
    assert p == {"downloaded": 1048576.0, "total": 10485760.0, "speed": 524288.5, "eta": 17.0, "status": "downloading"}
    p = ytdl.parse_progress("STRIMO|100|NA|2000|NA|NA|downloading")
    assert p["total"] == 2000.0 and p["speed"] is None and p["eta"] is None
    assert ytdl.parse_progress("[download] 50% of 10MiB") is None
    assert ytdl.parse_tagged("STRIMOFILE|C:\\Videos\\a [x].mp4", ytdl.FILE_TAG) == "C:\\Videos\\a [x].mp4"
    assert ytdl.parse_tagged("other", ytdl.FILE_TAG) is None


def test_ytdl_errors():
    err = "WARNING: x\nERROR: [generic] Unsupported URL: https://a.b"
    assert "isn't supported" in ytdl.last_error(err)
    assert "403" in ytdl.last_error("ERROR: unable to download video data: HTTP Error 403: Forbidden")
    assert ytdl.last_error("") == "Unknown error"


def test_ytdl_parse_info():
    split = {
        "title": "Clip", "id": "abc", "duration": 61, "thumbnail": "https://t/x.jpg",
        "http_headers": {"User-Agent": "UA"},
        "requested_formats": [
            {"url": "https://v", "vcodec": "avc1", "acodec": "none", "http_headers": {"Referer": "https://r"}},
            {"url": "https://a", "vcodec": "none", "acodec": "mp4a"},
        ],
        "formats": [{"height": 360, "vcodec": "avc1"}, {"height": 720, "vcodec": "avc1"}, {"height": None, "vcodec": "none"}],
    }
    info = ytdl.parse_info(json.dumps(split))
    assert info["video_url"] == "https://v" and info["audio_url"] == "https://a"
    assert info["headers"] == {"User-Agent": "UA", "Referer": "https://r"}
    assert info["heights"] == [720, 360]
    single = {"title": "Direct", "url": "https://file.mp4", "ext": "mp4"}
    info = ytdl.parse_info(json.dumps(single))
    assert info["video_url"] == "https://file.mp4" and info["audio_url"] is None
    playlist = {"_type": "playlist", "entries": [None, single]}
    assert ytdl.parse_info(json.dumps(playlist))["title"] == "Direct"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print("FAIL", name, repr(exc))
    sys.exit(1 if failures else 0)
