# PyInstaller recipe for Strimo.exe  (run:  pyinstaller --noconfirm strimo.spec)
# Expects libmpv-2.dll (or mpv-2.dll) in .\vendor  — build\fetch_tools.ps1 puts it there.
import os

ROOT = os.path.abspath(".")
VENDOR = os.path.join(ROOT, "vendor")

mpv_dlls = [(os.path.join(VENDOR, n), ".") for n in ("libmpv-2.dll", "mpv-2.dll")
            if os.path.exists(os.path.join(VENDOR, n))]
if not mpv_dlls:
    raise SystemExit("libmpv-2.dll not found in vendor\\ - run build\\fetch_tools.ps1 first")

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=mpv_dlls,
    datas=[("assets/strimo.ico", "assets"), ("assets/strimo.png", "assets")],
    hiddenimports=["mpv"],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus"],
    noarchive=False,
)

# leave out large Qt pieces Strimo doesn't use (software OpenGL, translations, QML)
def _keep(entry):
    name = entry[0].replace("\\", "/").lower()
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
