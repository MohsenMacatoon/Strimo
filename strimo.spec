# PyInstaller recipe for Strimo.exe  (run:  pyinstaller --noconfirm strimo.spec)
# Expects the VLC engine in .\vendor\vlc (libvlc.dll, libvlccore.dll, plugins\)
# - build\fetch_tools.ps1 puts it there.
import os

ROOT = os.path.abspath(".")
VLC_DIR = os.path.join(ROOT, "vendor", "vlc")
if not os.path.isfile(os.path.join(VLC_DIR, "libvlc.dll")):
    raise SystemExit("vendor\\vlc\\libvlc.dll not found - run build\\fetch_tools.ps1 first")

# copy the whole VLC folder as-is (PyInstaller must not analyse the ~300 plugin dlls)
vlc_datas = []
for folder, _dirs, files in os.walk(VLC_DIR):
    rel = os.path.relpath(folder, VLC_DIR)
    dest = "vlc" if rel == "." else os.path.join("vlc", rel)
    for f in files:
        vlc_datas.append((os.path.join(folder, f), dest))

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[("assets/strimo.ico", "assets"), ("assets/strimo.png", "assets")] + vlc_datas,
    hiddenimports=["vlc"],
    excludes=["tkinter", "unittest", "pydoc", "mpv", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus"],
    noarchive=False,
)

# leave out large Qt pieces Strimo doesn't use (software OpenGL, translations, QML)
def _keep(entry):
    name = entry[0].replace("\\", "/").lower()
    if name.startswith("vlc/"):
        return True
    drop = ("opengl32sw.dll", "/translations/", "qt6quick", "qt6qml", "qt6pdf", "/qpdf", "qt6virtualkeyboard")
    return not any(d in name for d in drop)

a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Strimo",
    icon="assets/strimo.ico",
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Strimo")
