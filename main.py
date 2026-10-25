"""Strimo entry point (also used by PyInstaller)."""

import os
import sys


def _prepare_dll_search_path() -> None:
    """Make sure libmpv-2.dll (shipped next to Strimo.exe) can be found by python-mpv."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    dirs = [base, os.path.join(base, "_internal"), os.path.join(base, "lib")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
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
