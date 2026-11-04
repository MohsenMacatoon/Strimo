"""One Strimo at a time (like VLC's "allow only one instance").

When several files are selected in File Explorer and opened, Windows starts one Strimo
per file, all at once. The first one becomes the main instance; every other copy hands
its files to it through a local pipe and exits. The main instance gathers everything
that arrives within a moment into one playlist.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import time

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import paths

GATHER_MS = 450   # files arriving this close together form one playlist


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "Strimo-" + hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:12]


def _allow_foreground() -> None:
    """Let the main instance bring its window to the front when it gets our files."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:  # noqa: BLE001
            pass


def _send(files: list[str], enqueue: bool, timeout_ms: int) -> bool:
    payload = (json.dumps({"files": files, "enqueue": enqueue}) + "\n").encode("utf-8")
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        sock = QLocalSocket()
        sock.connectToServer(_server_name())
        if sock.waitForConnected(250):
            sock.write(payload)
            sock.flush()
            ok = sock.waitForBytesWritten(1500)
            sock.disconnectFromServer()
            if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                sock.waitForDisconnected(500)
            return ok
        time.sleep(0.08)  # the main instance may still be starting up
    return False


class Instance(QObject):
    """Decides whether this process is the main Strimo, and receives files sent to it."""

    files_received = Signal(list, bool)  # paths, enqueue

    def __init__(self):
        super().__init__()
        self.lock = QLockFile(os.path.join(paths.data_dir(), "instance.lock"))
        self.lock.setStaleLockTime(0)  # a crashed Strimo's lock is detected by its dead process id
        self.server = None
        self._batch: list[str] = []
        self._batch_enqueue = False
        self._gather = QTimer(self)
        self._gather.setSingleShot(True)
        self._gather.setInterval(GATHER_MS)
        self._gather.timeout.connect(self._flush)

    def become_main_or_hand_over(self, files: list[str], enqueue: bool) -> bool:
        """True: we are the main Strimo. False: our files went to the running one; exit."""
        files = [os.path.abspath(f) if not f.lower().startswith(("http://", "https://")) else f for f in files]
        for _attempt in range(3):
            if self.lock.tryLock(0):
                self._listen()
                return True
            _allow_foreground()
            if _send(files, enqueue, timeout_ms=4000):
                return False
            # the lock's owner isn't answering (closing or crashed): try to take over
            self.lock.removeStaleLockFile()
        return True  # couldn't reach it: run on our own rather than doing nothing

    def _listen(self) -> None:
        QLocalServer.removeServer(_server_name())  # clean up after a crash
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(_server_name())

    def _on_connection(self) -> None:
        while self.server is not None and self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            buf = bytearray()

            def read(s=sock, b=buf):
                b.extend(s.readAll().data())
                while b"\n" in b:
                    line, _, rest = bytes(b).partition(b"\n")
                    b[:] = rest
                    self._message(line)

            sock.readyRead.connect(read)
            sock.disconnected.connect(sock.deleteLater)
            if sock.bytesAvailable():
                read()

    def _message(self, line: bytes) -> None:
        try:
            msg = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            return
        self.add(list(msg.get("files") or []), bool(msg.get("enqueue")))

    def add(self, files: list[str], enqueue: bool = False) -> None:
        """Collect files; they are delivered together once no more arrive for a moment."""
        self._batch.extend(f for f in files if f not in self._batch)
        self._batch_enqueue = self._batch_enqueue or enqueue
        self._gather.start()

    def _flush(self) -> None:
        files, self._batch = self._batch, []
        enqueue, self._batch_enqueue = self._batch_enqueue, False
        self.files_received.emit(files, enqueue)

    def release(self) -> None:
        if self.server is not None:
            self.server.close()
            self.server = None
        self.lock.unlock()
