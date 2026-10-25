"""Download manager (queue, pause/resume, speed limit) and its panel."""

from __future__ import annotations

import os
import shutil
import time
import uuid

from PySide6.QtCore import QObject, QProcess, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from . import icons, paths, ytdl
from .procs import kill_tree, make_process
from .util import display_name, fmt_time, human_size, human_speed


class DownloadItem:
    FIELDS = ("id", "url", "title", "quality", "subs", "status", "downloaded", "total", "filepath", "error", "added")

    def __init__(self, url: str, quality: str = "720", subs: bool = False, title: str = ""):
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.title = title
        self.quality = quality
        self.subs = subs
        self.status = "queued"  # queued | downloading | paused | failed | done | canceled
        self.downloaded = 0.0
        self.total = None
        self.speed = None
        self.eta = None
        self.filepath = ""
        self.error = ""
        self.added = time.time()
        self.part = 1
        self.phase = ""
        self._stop = None
        self._last_dl = 0.0

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.FIELDS}

    @classmethod
    def from_dict(cls, d: dict) -> "DownloadItem":
        item = cls(d.get("url", ""))
        for k in cls.FIELDS:
            if k in d:
                setattr(item, k, d[k])
        return item

    @property
    def name(self) -> str:
        return self.title or display_name(self.url)

    @property
    def fraction(self):
        if self.status == "done":
            return 1.0
        if self.total:
            return max(0.0, min(1.0, (self.downloaded or 0) / self.total))
        return None


class DownloadManager(QObject):
    item_added = Signal(object)
    item_changed = Signal(object)
    item_removed = Signal(object)
    item_done = Signal(object)
    state_changed = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.items: list[DownloadItem] = []
        self.active: DownloadItem | None = None
        self.proc: QProcess | None = None
        self._buf = b""
        self._err = b""
        self._last_emit = 0.0
        for d in cfg.get("downloads", []) or []:
            try:
                item = DownloadItem.from_dict(d)
            except Exception:  # noqa: BLE001
                continue
            if item.status in ("downloading", "queued"):
                item.status = "paused"  # never start using data on its own after a restart
            if item.status != "canceled" and item.url:
                self.items.append(item)

    # ---- public ---------------------------------------------------------
    def add(self, url: str, quality: str, subs: bool = False, title: str = "") -> DownloadItem:
        item = DownloadItem(url, quality, subs, title)
        self.items.append(item)
        self.item_added.emit(item)
        self._save()
        self._pump()
        return item

    def pause(self, item: DownloadItem) -> None:
        if item is self.active and self.proc is not None:
            item._stop = "pause"
            kill_tree(self.proc)
        elif item.status == "queued":
            item.status = "paused"
            self._changed(item, force=True)

    def resume(self, item: DownloadItem) -> None:
        if item.status in ("paused", "failed"):
            item.status = "queued"
            item.error = ""
            self._changed(item, force=True)
            self._pump()

    def cancel(self, item: DownloadItem) -> None:
        if item is self.active and self.proc is not None:
            item._stop = "cancel"
            kill_tree(self.proc)
        else:
            self._discard_parts(item)
            self.remove(item)

    def remove(self, item: DownloadItem) -> None:
        if item is self.active:
            self.cancel(item)
            return
        if item in self.items:
            self.items.remove(item)
            self.item_removed.emit(item)
            self._save()

    def clear_finished(self) -> None:
        for item in [i for i in self.items if i.status in ("done", "canceled")]:
            self.remove(item)

    def has_active(self) -> bool:
        return self.active is not None

    def shutdown(self) -> None:
        """Called when Strimo closes: pause the running download (it resumes later)."""
        if self.active is not None and self.proc is not None:
            item = self.active
            item._stop = "pause"
            try:
                self.proc.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            kill_tree(self.proc)
            self.proc.waitForFinished(3000)
            item.status = "paused"
            self.active = None
        self._save()

    # ---- internals ---------------------------------------------------------
    def _save(self) -> None:
        self.cfg.set("downloads", [i.to_dict() for i in self.items if i.status != "canceled"])
        self.state_changed.emit()

    def _changed(self, item: DownloadItem, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_emit > 0.25:
            self._last_emit = now
            self.item_changed.emit(item)

    def _discard_parts(self, item: DownloadItem) -> None:
        shutil.rmtree(os.path.join(paths.parts_dir(), item.id), ignore_errors=True)

    def _pump(self) -> None:
        if self.active is not None:
            return
        nxt = next((i for i in self.items if i.status == "queued"), None)
        if nxt is not None:
            self._start(nxt)

    def _start(self, item: DownloadItem) -> None:
        exe = ytdl.ytdlp_path()
        if not exe:
            item.status = "failed"
            item.error = "Link support (yt-dlp) is missing. Reinstall Strimo."
            self._changed(item, force=True)
            return
        out_dir = self.cfg.get("download_dir") or paths.default_download_dir()
        temp_dir = os.path.join(paths.parts_dir(), item.id)
        try:
            os.makedirs(out_dir, exist_ok=True)
            os.makedirs(temp_dir, exist_ok=True)
        except OSError as exc:
            item.status = "failed"
            item.error = f"Can't write to the download folder: {exc}"
            self._changed(item, force=True)
            return
        args = ytdl.download_args(
            item.url, item.quality, out_dir, temp_dir, ytdl.ffmpeg_path(),
            int(self.cfg.get("speed_limit_kb") or 0), bool(item.subs), self.cfg.get("sub_langs"),
        )
        self.active = item
        item.status = "downloading"
        item._stop = None
        item.speed = None
        item.eta = None
        item.part = 1
        item.phase = "Starting…"
        item._last_dl = 0.0
        self._buf = b""
        self._err = b""
        proc = make_process(self)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self.proc = proc
        self._changed(item, force=True)
        proc.start(exe, args)

    def _on_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart and self.active is not None:
            item = self.active
            item.status = "failed"
            item.error = "Couldn't start yt-dlp."
            self.active = None
            self.proc = None
            self._changed(item, force=True)
            self._save()
            self._pump()

    def _on_stderr(self) -> None:
        if self.proc is not None:
            self._err = (self._err + self.proc.readAllStandardError().data())[-8000:]

    def _on_stdout(self) -> None:
        if self.proc is None or self.active is None:
            return
        self._buf += self.proc.readAllStandardOutput().data()
        *lines, self._buf = self._buf.replace(b"\r", b"\n").split(b"\n")
        item = self.active
        for raw in lines:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            prog = ytdl.parse_progress(line)
            if prog is not None:
                dl = prog["downloaded"] or 0.0
                if dl < item._last_dl * 0.5 and item._last_dl > 0:
                    item.part += 1
                item._last_dl = dl
                item.downloaded = dl
                item.total = prog["total"]
                item.speed = prog["speed"]
                item.eta = prog["eta"]
                item.phase = "Finishing up…" if prog["status"] == "finished" else ""
                self._changed(item)
                continue
            title = ytdl.parse_tagged(line, ytdl.TITLE_TAG)
            if title:
                item.title = title
                self._changed(item, force=True)
                continue
            fp = ytdl.parse_tagged(line, ytdl.FILE_TAG)
            if fp:
                item.filepath = fp

    def _on_finished(self, code, _status=None) -> None:
        item = self.active
        proc = self.proc
        self.active = None
        self.proc = None
        if item is None:
            return
        if proc is not None:
            self._buf += proc.readAllStandardOutput().data()
            self._buf += b"\n"
            self.active = item
            self.proc = proc
            self._on_stdout()
            self.active = None
            self.proc = None
            self._err += proc.readAllStandardError().data()
        stop = item._stop
        item._stop = None
        item.speed = None
        item.eta = None
        item.phase = ""
        if stop == "pause":
            item.status = "paused"
        elif stop == "cancel":
            item.status = "canceled"
            self._discard_parts(item)
            if item in self.items:
                self.items.remove(item)
            self.item_removed.emit(item)
            self._save()
            self._pump()
            return
        elif code == 0:
            item.status = "done"
            if item.total:
                item.downloaded = item.total
            self._discard_parts(item)
            self.item_done.emit(item)
        else:
            item.status = "failed"
            item.error = ytdl.last_error(self._err.decode("utf-8", "replace"))
        self._changed(item, force=True)
        self._save()
        self._pump()


# =============================================================== panel
class DownloadRow(QFrame):
    def __init__(self, item: DownloadItem, manager: DownloadManager, panel: "DownloadsPanel"):
        super().__init__()
        self.item = item
        self.manager = manager
        self.panel = panel
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(5)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setToolTip(item.url)
        top.addWidget(self.title, 1)
        self.action_btn = self._btn("pause", "Pause")
        self.play_btn = self._btn("play", "Play")
        self.folder_btn = self._btn("folder", "Show in folder")
        self.close_btn = self._btn("close", "Cancel")
        for b in (self.action_btn, self.play_btn, self.folder_btn, self.close_btn):
            top.addWidget(b)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        lay.addWidget(self.bar)
        self.status = QLabel()
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.action_btn.clicked.connect(self._action)
        self.close_btn.clicked.connect(self._close)
        self.play_btn.clicked.connect(lambda: self.panel.play_file.emit(self.item.filepath))
        self.folder_btn.clicked.connect(self._folder)
        self.refresh()

    @staticmethod
    def _btn(name: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setIcon(icons.icon(name))
        b.setIconSize(QSize(15, 15))
        b.setFixedSize(28, 28)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return b

    def _action(self) -> None:
        st = self.item.status
        if st in ("downloading", "queued"):
            self.manager.pause(self.item)
        elif st in ("paused", "failed"):
            self.manager.resume(self.item)

    def _close(self) -> None:
        if self.item.status == "done":
            self.manager.remove(self.item)
        else:
            self.manager.cancel(self.item)

    def _folder(self) -> None:
        fp = self.item.filepath
        if fp and os.path.exists(fp):
            from .panels import _show_in_folder

            _show_in_folder(fp)
        else:
            self.panel.open_folder()

    def refresh(self) -> None:
        it = self.item
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(it.name, Qt.TextElideMode.ElideMiddle, max(120, self.width() - 150)))
        frac = it.fraction
        if frac is None and it.status == "downloading":
            self.bar.setRange(0, 0)  # busy
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int((frac or 0) * 1000))
        state = {"paused": "paused", "failed": "failed"}.get(it.status, "")
        if self.bar.property("state") != state:
            self.bar.setProperty("state", state)
            self.bar.style().unpolish(self.bar)
            self.bar.style().polish(self.bar)

        size = human_size(it.downloaded) if it.downloaded else "0 B"
        total = f" of {human_size(it.total)}" if it.total else ""
        if it.status == "downloading":
            if it.phase:
                text = it.phase
            else:
                bits = [size + total]
                if it.speed:
                    bits.append(human_speed(it.speed))
                if it.eta is not None:
                    bits.append(f"{fmt_time(it.eta)} left")
                if it.part > 1:
                    bits.append(f"part {it.part}")
                text = " · ".join(bits)
        elif it.status == "queued":
            text = "Waiting in queue…"
        elif it.status == "paused":
            text = f"Paused at {size}{total} — press ▶ to continue" if it.downloaded else "Paused — press ▶ to start"
        elif it.status == "failed":
            text = f"Failed: {it.error}  — press ▶ to retry"
        elif it.status == "done":
            text = f"Done · {human_size(it.total)}" if it.total else "Done"
        else:
            text = it.status.capitalize()
        self.status.setText(text)

        active = it.status in ("downloading", "queued")
        self.action_btn.setVisible(it.status != "done")
        self.action_btn.setIcon(icons.icon("pause" if active else "resume"))
        self.action_btn.setToolTip("Pause" if active else ("Retry" if it.status == "failed" else "Resume"))
        self.play_btn.setVisible(it.status == "done" and bool(it.filepath))
        self.close_btn.setToolTip("Remove from list" if it.status == "done" else "Cancel and delete partial file")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.refresh()


class DownloadsPanel(QWidget):
    play_file = Signal(str)
    add_link_requested = Signal()

    def __init__(self, manager: DownloadManager, cfg, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.cfg = cfg
        self.rows: dict[str, DownloadRow] = {}
        self.setObjectName("panelRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        add = QPushButton("  Download a link")
        add.setObjectName("primary")
        add.setIcon(icons.icon("download", "#08110f"))
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add.clicked.connect(self.add_link_requested.emit)
        top.addWidget(add, 1)
        clear = QPushButton("Clear done")
        clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        clear.clicked.connect(self.manager.clear_finished)
        top.addWidget(clear)
        lay.addLayout(top)

        folder_row = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setObjectName("dim")
        self.folder_label.setWordWrap(True)
        change = QPushButton("Change")
        change.setProperty("chip", True)
        change.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        change.clicked.connect(self.change_folder)
        opn = QPushButton("Open")
        opn.setProperty("chip", True)
        opn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        opn.clicked.connect(self.open_folder)
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(change)
        folder_row.addWidget(opn)
        lay.addLayout(folder_row)

        limit_row = QHBoxLayout()
        lim_label = QLabel("Speed limit")
        lim_label.setObjectName("dim")
        self.limit = QSpinBox()
        self.limit.setRange(0, 100000)
        self.limit.setSingleStep(50)
        self.limit.setSuffix(" KB/s")
        self.limit.setSpecialValueText("No limit")
        self.limit.setValue(int(cfg.get("speed_limit_kb") or 0))
        self.limit.setToolTip("Keeps downloads from slowing down the rest of your internet.\n"
                              "Applies when a download starts or resumes.")
        self.limit.valueChanged.connect(lambda v: self.cfg.set("speed_limit_kb", int(v)))
        limit_row.addWidget(lim_label)
        limit_row.addWidget(self.limit, 1)
        lay.addLayout(limit_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        self.rows_layout = QVBoxLayout(holder)
        self.rows_layout.setContentsMargins(0, 0, 4, 0)
        self.rows_layout.setSpacing(6)
        self.empty = QLabel("No downloads yet.\nPaste a link with “Download a link”, or use\nFile → Open Link and choose Download.")
        self.empty.setObjectName("dim")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rows_layout.addWidget(self.empty)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll, 1)

        manager.item_added.connect(self._add_row)
        manager.item_changed.connect(self._update_row)
        manager.item_removed.connect(self._remove_row)
        for item in manager.items:
            self._add_row(item)
        self.refresh_folder()

    def refresh_folder(self) -> None:
        self.folder_label.setText("Save to: " + (self.cfg.get("download_dir") or paths.default_download_dir()))

    def change_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose download folder", self.cfg.get("download_dir") or "")
        if d:
            self.cfg.set("download_dir", d)
            self.refresh_folder()

    def open_folder(self) -> None:
        d = self.cfg.get("download_dir") or paths.default_download_dir()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _add_row(self, item: DownloadItem) -> None:
        row = DownloadRow(item, self.manager, self)
        self.rows[item.id] = row
        self.rows_layout.insertWidget(0, row)
        self.empty.hide()

    def _update_row(self, item: DownloadItem) -> None:
        row = self.rows.get(item.id)
        if row is not None:
            row.refresh()

    def _remove_row(self, item: DownloadItem) -> None:
        row = self.rows.pop(item.id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        self.empty.setVisible(not self.rows)
