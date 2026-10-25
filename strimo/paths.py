"""Where Strimo keeps its files. No Qt dependency."""

from __future__ import annotations

import os
import shutil
import sys

from . import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> str:
    """Folder that holds Strimo.exe (installed) or the project folder (running from source)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundle_dir() -> str:
    """Folder with bundled data files (PyInstaller puts them in _internal)."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", app_root())
    return app_root()


def asset(name: str) -> str:
    return os.path.join(bundle_dir(), "assets", name)


def data_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_NAME)
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        path = os.path.join(base, APP_NAME.lower())
    os.makedirs(path, exist_ok=True)
    return path


def parts_dir() -> str:
    path = os.path.join(data_dir(), "partial-downloads")
    os.makedirs(path, exist_ok=True)
    return path


def _user_folder(*candidates: str) -> str:
    home = os.path.expanduser("~")
    for c in candidates:
        p = os.path.join(home, c)
        if os.path.isdir(p):
            return p
    return home


def default_download_dir() -> str:
    return os.path.join(_user_folder("Videos", "Downloads"), f"{APP_NAME} Downloads")


def default_screenshot_dir() -> str:
    return os.path.join(_user_folder("Pictures"), APP_NAME)


def tools_dirs() -> list[str]:
    """Places to look for yt-dlp / ffmpeg, in order."""
    dirs = [os.path.join(app_root(), "tools"), app_root(), os.path.join(bundle_dir(), "tools")]
    out = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def find_tool(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    for d in tools_dirs():
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def log_path() -> str:
    return os.path.join(data_dir(), "strimo.log")
