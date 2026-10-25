"""Application start-up."""

from __future__ import annotations

import os
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, __version__, paths, theme


def _log_exception(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        with open(paths.log_path(), "a", encoding="utf-8") as f:
            f.write("UNCAUGHT ERROR\n" + text + "\n")
    except OSError:
        pass
    if sys.stderr:
        sys.stderr.write(text)


def _dark_palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: theme.BG,
        QPalette.ColorRole.WindowText: theme.TEXT,
        QPalette.ColorRole.Base: theme.BG,
        QPalette.ColorRole.AlternateBase: theme.BG_PANEL,
        QPalette.ColorRole.ToolTipBase: theme.BG_RAISED,
        QPalette.ColorRole.ToolTipText: theme.TEXT,
        QPalette.ColorRole.Text: theme.TEXT,
        QPalette.ColorRole.Button: theme.BG_RAISED,
        QPalette.ColorRole.ButtonText: theme.TEXT,
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: theme.ACCENT,
        QPalette.ColorRole.HighlightedText: "#08110f",
        QPalette.ColorRole.Link: theme.ACCENT,
        QPalette.ColorRole.PlaceholderText: "#6b7280",
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor("#5d6472"))
    return p


def _option(argv: list[str], name: str):
    prefix = f"--{name}="
    for a in argv:
        if a.startswith(prefix):
            return a[len(prefix):]
    return None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest = "--selftest" in argv
    files = [a for a in argv if not a.startswith("--")]
    sys.excepthook = _log_exception

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(theme.STYLE)
    icon_path = paths.asset("strimo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    try:
        import mpv  # noqa: F401  (loads libmpv-2.dll)
    except (OSError, ImportError) as exc:
        _log_exception(type(exc), exc, exc.__traceback__)
        QMessageBox.critical(
            None, APP_NAME,
            "Strimo's playback engine (libmpv-2.dll) could not be loaded.\n\n"
            "Please reinstall Strimo.\n\nDetails: " + str(exc))
        return 1

    from .config import Config
    from .mainwindow import MainWindow

    if selftest:
        report = _option(argv, "selftest-report") or os.path.join(paths.data_dir(), "selftest.txt")
        work = os.path.dirname(os.path.abspath(report))
        cfg = Config(os.path.join(work, "selftest-config.json"))
        cfg.set("download_dir", os.path.join(work, "selftest-downloads"))
        cfg.set("screenshot_dir", os.path.join(work, "selftest-shots"))
        win = MainWindow(cfg, [], selftest=True)
        win.show()
        from .selftest import SelfTest

        test = SelfTest(win, report, _option(argv, "selftest-media"), _option(argv, "selftest-url"))
        test.start()
        return app.exec()

    cfg = Config()
    win = MainWindow(cfg, files)
    win.show()
    return app.exec()
