"""The main Strimo's side of instance.py: collects files handed over by other copies."""

from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .instance import inbox_dir

QUIET_MS = 450     # deliver once no new files arrived for this long ...
MAX_WAIT_MS = 1000  # ... or at most this long after the first one, so playback starts promptly
STALE_S = 120       # leftovers older than this (e.g. after a crash) are thrown away


class Inbox(QObject):
    files_received = Signal(list, bool)  # paths, enqueue

    def __init__(self):
        super().__init__()
        self._batch: list[str] = []
        self._enqueue = False
        self._first_at = None
        self._last_at = 0.0
        self._poll = QTimer(self)
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._check)

    def start(self) -> None:
        self._check()
        self._poll.start()

    def add(self, files: list[str], enqueue: bool = False) -> None:
        now = time.monotonic()
        if self._first_at is None:
            self._first_at = now
        self._last_at = now
        seen = set(self._batch)
        self._batch.extend(f for f in files if f not in seen)
        self._enqueue = self._enqueue or enqueue

    def _check(self) -> None:
        try:
            names = sorted(n for n in os.listdir(inbox_dir()) if n.endswith(".json"))
        except OSError:
            names = []
        arrived = False
        for name in names:
            path = os.path.join(inbox_dir(), name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    msg = json.load(f)
                os.remove(path)
            except (OSError, ValueError):
                continue
            if time.time() - float(msg.get("t") or 0) > STALE_S:
                continue
            self.add(list(msg.get("files") or []), bool(msg.get("enqueue")))
            arrived = True
            if not msg.get("files"):
                self._batch.append("")  # Strimo opened again with no file: bring the window forward
        if not arrived and self._first_at is None:
            return
        now = time.monotonic()
        if self._first_at is not None and (now - self._last_at >= QUIET_MS / 1000 or now - self._first_at >= MAX_WAIT_MS / 1000):
            files, self._batch = self._batch, []
            enqueue, self._enqueue = self._enqueue, False
            self._first_at = None
            self.files_received.emit(files, enqueue)
