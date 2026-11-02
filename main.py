"""Strimo entry point (also used by PyInstaller)."""

import os
import sys


def _prepare_dll_search_path() -> None:
    """Point python-vlc at the bundled libVLC (the "vlc" folder next to Strimo's files)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    dirs = [base, os.path.join(base, "_internal"), os.path.join(base, "lib")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
    for root in list(dirs):
        vlc_dir = os.path.join(root, "vlc")
        if os.path.isfile(os.path.join(vlc_dir, "libvlc.dll")):
            os.environ["PYTHON_VLC_LIB_PATH"] = os.path.join(vlc_dir, "libvlc.dll")
            os.environ["PYTHON_VLC_MODULE_PATH"] = os.path.join(vlc_dir, "plugins")
            os.environ["VLC_PLUGIN_PATH"] = os.path.join(vlc_dir, "plugins")
            dirs.insert(0, vlc_dir)
            break
    dirs = [d for d in dirs if os.path.isdir(d)]
    os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])
    if hasattr(os, "add_dll_directory"):
        for d in dirs:
            try:
                os.add_dll_directory(d)
            except OSError:
                pass


_prepare_dll_search_path()

from strimo.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
