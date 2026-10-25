"""Running yt-dlp as a background process (QProcess) without blocking the window."""

from __future__ import annotations

import os
import subprocess
import uuid

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from . import ytdl

CREATE_NO_WINDOW = 0x08000000


def make_process(parent=None) -> QProcess:
    proc = QProcess(parent)
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", "utf-8")
    env.insert("PYTHONUTF8", "1")
    proc.setProcessEnvironment(env)
    return proc


def kill_tree(proc: QProcess) -> None:
    """Stop a process and its children (yt-dlp.exe starts a child process)."""
    if proc.state() == QProcess.ProcessState.NotRunning:
        return
    pid = proc.processId()
    if os.name == "nt" and pid:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           creationflags=CREATE_NO_WINDOW, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    if proc.state() != QProcess.ProcessState.NotRunning:
        proc.kill()


class LinkResolver(QObject):
    """Runs `yt-dlp -J` for one link and reports the result."""

    resolved = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, fmt: str | None, parent=None, timeout_ms: int = 60000):
        super().__init__(parent)
        self.url = url
        self.fmt = fmt
        self.id = uuid.uuid4().hex
        self._out = bytearray()
        self._err = bytearray()
        self._done = False
        self.proc = make_process(self)
        self.proc.readyReadStandardOutput.connect(self._read_out)
        self.proc.readyReadStandardError.connect(self._read_err)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.timeout_ms = timeout_ms

    def start(self) -> None:
        exe = ytdl.ytdlp_path()
        if not exe:
            self._fail("Link support (yt-dlp) is missing. Reinstall Strimo to restore it.")
            return
        self.proc.start(exe, ytdl.info_args(self.url, self.fmt))
        self.timer.start(self.timeout_ms)

    def cancel(self) -> None:
        self._done = True
        self.timer.stop()
        kill_tree(self.proc)

    def _read_out(self) -> None:
        self._out += self.proc.readAllStandardOutput().data()

    def _read_err(self) -> None:
        self._err += self.proc.readAllStandardError().data()

    def _fail(self, msg: str) -> None:
        if not self._done:
            self._done = True
            self.timer.stop()
            self.failed.emit(msg)

    def _error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._fail("Couldn't start yt-dlp (link support).")

    def _timeout(self) -> None:
        kill_tree(self.proc)
        self._fail("The site took too long to answer. Check your connection and try again.")

    def _finished(self, code, _status=None) -> None:
        if self._done:
            return
        self._read_out()
        self._read_err()
        if code != 0:
            self._fail(ytdl.last_error(self._err.decode("utf-8", "replace")))
            return
        try:
            info = ytdl.parse_info(self._out.decode("utf-8", "replace"))
        except ValueError:
            self._fail("Couldn't read the site's answer.")
            return
        self._done = True
        self.timer.stop()
        self.resolved.emit(info)


class CommandRunner(QObject):
    """Runs a short yt-dlp command (like -U) and reports its text output."""

    done = Signal(int, str)

    def __init__(self, args: list[str], parent=None):
        super().__init__(parent)
        self.args = args
        self._buf = bytearray()
        self.proc = make_process(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(lambda: self._buf.extend(self.proc.readAllStandardOutput().data()))
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)

    def start(self) -> None:
        exe = ytdl.ytdlp_path()
        if not exe:
            self.done.emit(-1, "yt-dlp was not found.")
            return
        self.proc.start(exe, self.args)

    def _error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self.done.emit(-1, "Couldn't start yt-dlp.")

    def _finished(self, code, _status=None) -> None:
        self._buf.extend(self.proc.readAllStandardOutput().data())
        self.done.emit(int(code), self._buf.decode("utf-8", "replace"))
