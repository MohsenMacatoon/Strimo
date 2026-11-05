"""One Strimo at a time - the fast part that runs before anything heavy is loaded.

Selecting many files in File Explorer starts one Strimo per file, all at once (100
files = 100 copies). So the check happens in the first milliseconds, before Qt or the
playback engine load: a copy that finds Strimo already running just drops its file
names into a small "inbox" folder and exits. The running Strimo picks them up
(see inbox.py) and builds one playlist.

No Qt imports here on purpose - this must stay tiny and quick.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import time

from . import paths

_mutex = None  # kept open for as long as the main Strimo runs


def inbox_dir() -> str:
    d = os.path.join(paths.data_dir(), "inbox")
    os.makedirs(d, exist_ok=True)
    return d


def _mutex_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "Local\\Strimo-" + hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:12]


def _already_running() -> bool:
    """Claim the 'Strimo is running' flag. True if another Strimo already holds it."""
    global _mutex
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    handle = k32.CreateMutexW(None, False, _mutex_name())
    exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    if not handle:
        return False
    if exists:
        k32.CloseHandle(handle)
        return True
    _mutex = handle  # we are the main Strimo; Windows frees this when we exit (even on a crash)
    return False


def write_to_inbox(files: list[str], enqueue: bool) -> None:
    files = [f if f.lower().startswith(("http://", "https://")) else os.path.abspath(f) for f in files]
    data = json.dumps({"files": files, "enqueue": enqueue, "t": time.time()})
    name = f"{time.time_ns():020d}-{os.getpid()}"
    folder = inbox_dir()
    tmp = os.path.join(folder, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, os.path.join(folder, name + ".json"))  # appears complete, never half-written


def hand_over_if_running(argv: list[str]) -> bool:
    """Call first thing. True = another Strimo has our files now; this copy should exit."""
    if "--selftest" in argv:
        return False
    try:
        if not _already_running():
            return False
        write_to_inbox([a for a in argv if not a.startswith("--")], "--enqueue" in argv)
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # let it come to the front
        return True
    except Exception:  # noqa: BLE001 - if anything goes wrong, just run normally
        return False
