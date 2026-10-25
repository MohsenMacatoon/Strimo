"""Settings and per-file memory, stored as JSON in %APPDATA%\\Strimo. No Qt dependency."""

from __future__ import annotations

import copy
import json
import os
import time

from . import paths
from .util import media_key

DEFAULTS: dict = {
    # playback
    "volume": 100,
    "muted": False,
    "skip_seconds": 5,
    "long_skip_seconds": 30,
    "pitch_correction": True,
    "resume": True,
    "remember_speed": True,
    "hold_to_boost": True,
    "boost_speed": 2.0,
    "loop_mode": "none",          # none | one | all
    "hwdec": True,
    "video_backend": "opengl",    # opengl | native
    # streaming / downloads
    "cache_mb": 150,
    "readahead_secs": 60,
    "stream_quality": "720",
    "download_quality": "720",
    "download_dir": "",
    "speed_limit_kb": 0,
    "download_subs": False,
    "sub_langs": "en.*",
    "show_thumbnails": True,
    # interface
    "autohide_windowed": False,
    "wheel_gestures": True,
    "show_frame_counter": False,
    "always_on_top": False,
    "panel_visible": False,
    "panel_tab": 0,
    "show_remaining": False,
    "window_geometry": "",
    "screenshot_dir": "",
    "sub_scale": 1.0,
    # memory
    "recent": [],
    "link_history": [],
    "media": {},
    "intro_rules": {},
    "downloads": [],
}

MAX_MEDIA_ENTRIES = 1500
MAX_RECENT = 15
MAX_LINKS = 30


class Config:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(paths.data_dir(), "config.json")
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.dirty = False
        self.load()

    # ---- basic -------------------------------------------------------
    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if k in DEFAULTS and type(v) is not type(DEFAULTS[k]) and not (
                        isinstance(DEFAULTS[k], float) and isinstance(v, int)
                    ):
                        continue  # ignore values of the wrong type
                    self.data[k] = v
        except (OSError, ValueError):
            pass
        if not self.data.get("download_dir"):
            self.data["download_dir"] = paths.default_download_dir()
        if not self.data.get("screenshot_dir"):
            self.data["screenshot_dir"] = paths.default_screenshot_dir()

    def save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass

    def get(self, key: str, default=None):
        if key in self.data:
            return self.data[key]
        return DEFAULTS.get(key, default)

    def set(self, key: str, value) -> None:
        if self.data.get(key) != value:
            self.data[key] = value
            self.dirty = True

    # ---- per-file memory ---------------------------------------------
    def media(self, entry: str, create: bool = False) -> dict | None:
        key = media_key(entry)
        store = self.data.setdefault("media", {})
        rec = store.get(key)
        if rec is None and create:
            rec = {}
            store[key] = rec
            self._prune_media()
        if rec is not None:
            rec["ts"] = int(time.time())
        return rec

    def _prune_media(self) -> None:
        store = self.data["media"]
        if len(store) <= MAX_MEDIA_ENTRIES:
            return
        keep = sorted(store.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)[: MAX_MEDIA_ENTRIES - 100]
        self.data["media"] = dict(keep)

    def _clean_media(self, entry: str) -> None:
        key = media_key(entry)
        rec = self.data.get("media", {}).get(key)
        if rec is not None and not any(k for k in rec if k != "ts"):
            del self.data["media"][key]

    def get_position(self, entry: str):
        rec = self.media(entry)
        return rec.get("pos") if rec else None

    def set_position(self, entry: str, pos) -> None:
        if pos is None:
            rec = self.media(entry)
            if rec and "pos" in rec:
                del rec["pos"]
                self._clean_media(entry)
                self.dirty = True
            return
        self.media(entry, create=True)["pos"] = round(float(pos), 2)
        self.dirty = True

    def get_speed(self, entry: str):
        rec = self.media(entry)
        return rec.get("speed") if rec else None

    def set_speed(self, entry: str, speed) -> None:
        if speed is None or abs(float(speed) - 1.0) < 1e-6:
            rec = self.media(entry)
            if rec and "speed" in rec:
                del rec["speed"]
                self._clean_media(entry)
                self.dirty = True
            return
        self.media(entry, create=True)["speed"] = round(float(speed), 2)
        self.dirty = True

    def get_list(self, entry: str, name: str) -> list:
        rec = self.media(entry)
        return list(rec.get(name, [])) if rec else []

    def set_list(self, entry: str, name: str, items: list) -> None:
        items = sorted(items, key=lambda x: x.get("t", 0))
        if items:
            self.media(entry, create=True)[name] = items
        else:
            rec = self.media(entry)
            if rec and name in rec:
                del rec[name]
                self._clean_media(entry)
        self.dirty = True

    # ---- intro skip rules (per folder) ---------------------------------
    @staticmethod
    def _folder_key(entry: str) -> str | None:
        if not entry or "://" in entry:
            return None
        return os.path.normcase(os.path.dirname(os.path.abspath(entry)))

    def get_intro(self, entry: str):
        key = self._folder_key(entry)
        if key is None:
            return None
        rule = self.data.get("intro_rules", {}).get(key)
        if isinstance(rule, list) and len(rule) == 2:
            return float(rule[0]), float(rule[1])
        return None

    def set_intro(self, entry: str, start, end) -> None:
        key = self._folder_key(entry)
        if key is None:
            return
        rules = self.data.setdefault("intro_rules", {})
        if start is None or end is None or end <= start:
            rules.pop(key, None)
        else:
            rules[key] = [round(float(start), 2), round(float(end), 2)]
        self.dirty = True

    # ---- recent / history ----------------------------------------------
    def _push(self, key: str, value: str, limit: int) -> None:
        items = [x for x in self.data.get(key, []) if x != value]
        items.insert(0, value)
        self.data[key] = items[:limit]
        self.dirty = True

    def add_recent(self, entry: str) -> None:
        self._push("recent", entry, MAX_RECENT)

    def add_link(self, url: str) -> None:
        self._push("link_history", url, MAX_LINKS)
