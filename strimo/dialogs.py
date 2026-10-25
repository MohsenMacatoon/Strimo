"""Dialogs: Open Link, Sleep timer, Intro skip, Settings, Shortcuts, countdown."""

from __future__ import annotations

import os
import threading
import urllib.request

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__, paths, ytdl
from .procs import LinkResolver
from .util import fmt_time, is_direct_media_url, normalize_url, parse_time


def _hline() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    return f


# ============================================================== Open link
class OpenLinkDialog(QDialog):
    thumb_loaded = Signal(bytes)

    def __init__(self, cfg, parent=None, url: str = "", mode: str = "play"):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Open a link")
        self.setMinimumWidth(560)
        self.action = None
        self.info = None
        self._resolver = None
        self.mode = mode

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel("Paste a video link")
        head.setObjectName("title")
        lay.addWidget(head)
        sub = QLabel("Direct links (.mp4, .mkv, .m3u8 …) and many video sites are supported.")
        sub.setObjectName("dim")
        lay.addWidget(sub)

        self.url = QComboBox()
        self.url.setEditable(True)
        self.url.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.url.addItems(cfg.get("link_history", []))
        self.url.lineEdit().setPlaceholderText("https://…")
        if not url:
            clip = normalize_url(QGuiApplication.clipboard().text() or "")
            url = clip
        self.url.setCurrentText(url)
        self.url.lineEdit().selectAll()
        self.url.currentTextChanged.connect(self._url_changed)

        url_row = QHBoxLayout()
        url_row.addWidget(self.url, 1)
        self.check_btn = QPushButton("Check link")
        self.check_btn.setToolTip("Show the title, length and available qualities (uses a little data)")
        self.check_btn.clicked.connect(self.check_link)
        url_row.addWidget(self.check_btn)
        lay.addLayout(url_row)

        # preview card
        self.card = QFrame()
        self.card.setObjectName("card")
        card_lay = QHBoxLayout(self.card)
        self.thumb = QLabel()
        self.thumb.setFixedSize(QSize(160, 90))
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet("background:#0d0f13; border-radius:6px;")
        card_lay.addWidget(self.thumb)
        meta = QVBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.title_label.setObjectName("title")
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("dim")
        self.meta_label.setWordWrap(True)
        meta.addWidget(self.title_label)
        meta.addWidget(self.meta_label)
        meta.addStretch(1)
        card_lay.addLayout(meta, 1)
        self.card.hide()
        lay.addWidget(self.card)

        form = QFormLayout()
        self.quality = QComboBox()
        for key, label in ytdl.QUALITIES:
            self.quality.addItem(label, key)
        default_q = cfg.get("download_quality" if mode == "download" else "stream_quality")
        idx = self.quality.findData(default_q)
        self.quality.setCurrentIndex(idx if idx >= 0 else self.quality.findData("720"))
        form.addRow("Quality", self.quality)
        self.subs = QCheckBox("Also download subtitles (if the site has them)")
        self.subs.setChecked(bool(cfg.get("download_subs")))
        form.addRow("", self.subs)
        lay.addLayout(form)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        note = QLabel("<b>Play &amp; Save</b> keeps a copy of exactly what you watch — no extra data. "
                      "Skipping around leaves gaps in the copy; use <b>Download</b> for a complete file.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addWidget(_hline())

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Play && Save")
        self.dl_btn = QPushButton("Download")
        self.play_btn = QPushButton("Play")
        primary = self.dl_btn if mode == "download" else self.play_btn
        primary.setObjectName("primary")
        primary.setDefault(True)
        for b in (cancel, self.save_btn, self.dl_btn, self.play_btn):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.play_btn.clicked.connect(lambda: self._finish("play"))
        self.save_btn.clicked.connect(lambda: self._finish("record"))
        self.dl_btn.clicked.connect(lambda: self._finish("download"))
        self.thumb_loaded.connect(self._set_thumb)

        if not ytdl.ytdlp_path():
            self.dl_btn.setEnabled(False)
            self.check_btn.setEnabled(False)
            self.status.setText("Link support (yt-dlp) wasn't found, so only direct links can be played.")
        self._url_changed(self.url.currentText())

    # ---- behaviour --------------------------------------------------------
    def current_url(self) -> str:
        return normalize_url(self.url.currentText())

    def _url_changed(self, _text: str) -> None:
        url = self.current_url()
        ok = bool(url)
        for b in (self.play_btn, self.save_btn):
            b.setEnabled(ok)
        self.dl_btn.setEnabled(ok and bool(ytdl.ytdlp_path()))
        self.check_btn.setEnabled(ok and bool(ytdl.ytdlp_path()))
        self.card.hide()
        self.info = None
        if url and is_direct_media_url(url):
            self.status.setText("Direct media link — it will play right away.")
        elif url:
            self.status.setText("")

    def check_link(self) -> None:
        url = self.current_url()
        if not url:
            return
        if self._resolver is not None:
            self._resolver.cancel()
        self.status.setText("Checking link…")
        self.check_btn.setEnabled(False)
        self._resolver = LinkResolver(url, None, self, timeout_ms=45000)
        self._resolver.resolved.connect(self._show_info)
        self._resolver.failed.connect(self._show_error)
        self._resolver.start()

    def _show_error(self, msg: str) -> None:
        self.check_btn.setEnabled(True)
        self.status.setText("⚠ " + msg)

    def _show_info(self, info: dict) -> None:
        self.check_btn.setEnabled(True)
        self.info = info
        self.card.show()
        self.title_label.setText(info.get("title") or "")
        bits = []
        if info.get("is_live"):
            bits.append("LIVE")
        if info.get("duration"):
            bits.append(fmt_time(info["duration"]))
        if info.get("uploader"):
            bits.append(info["uploader"])
        if info.get("extractor"):
            bits.append(info["extractor"])
        if info.get("heights"):
            bits.append("Qualities: " + ", ".join(f"{h}p" for h in info["heights"][:7]))
        self.meta_label.setText("  ·  ".join(bits))
        self.status.setText("")
        self.thumb.setText("…")
        if info.get("thumbnail") and self.cfg.get("show_thumbnails"):
            threading.Thread(target=self._fetch_thumb, args=(info["thumbnail"],), daemon=True).start()
        else:
            self.thumb.setText("")

    def _fetch_thumb(self, url: str) -> None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read(600_000)
            self.thumb_loaded.emit(data)
        except Exception:  # noqa: BLE001 - thumbnail is optional
            try:
                self.thumb_loaded.emit(b"")
            except RuntimeError:
                pass

    def _set_thumb(self, data: bytes) -> None:
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.thumb.setPixmap(pm.scaled(self.thumb.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        else:
            self.thumb.setText("")

    def _finish(self, action: str) -> None:
        if not self.current_url():
            return
        self.action = action
        q = self.quality.currentData()
        if action == "download":
            self.cfg.set("download_quality", q)
        elif q != "audio_mp3":
            self.cfg.set("stream_quality", q)
        self.cfg.set("download_subs", self.subs.isChecked())
        if self._resolver is not None:
            self._resolver.cancel()
        self.accept()

    def reject(self) -> None:
        if self._resolver is not None:
            self._resolver.cancel()
        super().reject()

    @property
    def chosen_quality(self) -> str:
        return self.quality.currentData()


# ============================================================== Sleep timer
class SleepTimerDialog(QDialog):
    ACTIONS = [("pause", "Pause playback"), ("stop", "Stop playback"), ("quit", f"Close {APP_NAME}"),
               ("sleep", "Put the PC to sleep"), ("shutdown", "Shut down the PC")]

    def __init__(self, active_text: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sleep timer")
        self.result_data = None
        self.turn_off = False
        lay = QVBoxLayout(self)
        head = QLabel("Sleep timer")
        head.setObjectName("title")
        lay.addWidget(head)
        if active_text:
            cur = QLabel(f"Currently: {active_text}")
            cur.setObjectName("badge")
            lay.addWidget(cur)
        form = QFormLayout()
        self.action = QComboBox()
        for key, label in self.ACTIONS:
            self.action.addItem(label, key)
        form.addRow("What to do", self.action)
        lay.addLayout(form)

        self.group = QButtonGroup(self)
        self.r_minutes = QRadioButton("After")
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 600)
        self.minutes.setValue(30)
        self.minutes.setSuffix(" minutes")
        row = QHBoxLayout()
        row.addWidget(self.r_minutes)
        row.addWidget(self.minutes)
        row.addStretch(1)
        lay.addLayout(row)
        self.r_file = QRadioButton("When this video ends")
        self.r_list = QRadioButton("When the playlist ends")
        lay.addWidget(self.r_file)
        lay.addWidget(self.r_list)
        for i, r in enumerate((self.r_minutes, self.r_file, self.r_list)):
            self.group.addButton(r, i)
        self.r_minutes.setChecked(True)
        quick = QHBoxLayout()
        for m in (15, 30, 45, 60, 90):
            b = QPushButton(f"{m} min")
            b.setProperty("chip", True)
            b.clicked.connect(lambda _=False, v=m: (self.minutes.setValue(v), self.r_minutes.setChecked(True)))
            quick.addWidget(b)
        lay.addLayout(quick)
        note = QLabel("Sleep and shut down give you 30 seconds to cancel first.")
        note.setObjectName("dim")
        lay.addWidget(note)
        lay.addWidget(_hline())
        btns = QHBoxLayout()
        if active_text:
            off = QPushButton("Turn off timer")
            off.clicked.connect(self._off)
            btns.addWidget(off)
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        start = QPushButton("Start")
        start.setObjectName("primary")
        start.setDefault(True)
        start.clicked.connect(self._start)
        btns.addWidget(cancel)
        btns.addWidget(start)
        lay.addLayout(btns)

    def _off(self) -> None:
        self.turn_off = True
        self.accept()

    def _start(self) -> None:
        mode = {0: "minutes", 1: "file", 2: "playlist"}[self.group.checkedId()]
        self.result_data = {"action": self.action.currentData(), "mode": mode, "minutes": self.minutes.value()}
        self.accept()


class CountdownDialog(QDialog):
    """'Shutting down in 30 s' with a Cancel button. Accepts automatically at zero."""

    def __init__(self, what: str, seconds: int = 30, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.what = what
        self.left = seconds
        lay = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setObjectName("title")
        lay.addWidget(self.label)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._update()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    def _update(self) -> None:
        self.label.setText(f"{self.what} in {self.left} seconds…")

    def _tick(self) -> None:
        self.left -= 1
        if self.left <= 0:
            self.timer.stop()
            self.accept()
        else:
            self._update()


# ============================================================== Intro skip
class IntroSkipDialog(QDialog):
    def __init__(self, current: float, rule, folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-skip intro")
        self.current = current or 0.0
        self.result_rule = None
        self.remove = False
        lay = QVBoxLayout(self)
        head = QLabel("Auto-skip intro")
        head.setObjectName("title")
        lay.addWidget(head)
        info = QLabel(f"Every video in this folder will jump past this part:\n{folder}")
        info.setObjectName("dim")
        info.setWordWrap(True)
        lay.addWidget(info)
        grid = QGridLayout()
        self.start = QLineEdit(fmt_time(rule[0]) if rule else "0:00")
        self.end = QLineEdit(fmt_time(rule[1]) if rule else fmt_time(self.current))
        for row, (label, edit) in enumerate((("Intro starts at", self.start), ("Intro ends at", self.end))):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(edit, row, 1)
            b = QPushButton("Use current time")
            b.setProperty("chip", True)
            b.clicked.connect(lambda _=False, e=edit: e.setText(fmt_time(self.current)))
            grid.addWidget(b, row, 2)
        lay.addLayout(grid)
        self.err = QLabel("")
        self.err.setObjectName("dim")
        lay.addWidget(self.err)
        btns = QHBoxLayout()
        if rule:
            rem = QPushButton("Remove for this folder")
            rem.clicked.connect(self._remove)
            btns.addWidget(rem)
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

    def _remove(self) -> None:
        self.remove = True
        self.accept()

    def _save(self) -> None:
        s, e = parse_time(self.start.text()), parse_time(self.end.text())
        if s is None or e is None or e <= s:
            self.err.setText("Please enter times like 0:00 and 1:30 (end after start).")
            return
        self.result_rule = (s, e)
        self.accept()


# ============================================================== Settings
class SettingsDialog(QDialog):
    RESTART_KEYS = {"video_backend", "hwdec", "cache_mb", "readahead_secs"}

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.changed: set[str] = set()
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        self._w: dict = {}

        def page():
            w = QWidget()
            f = QFormLayout(w)
            f.setVerticalSpacing(9)
            f.setContentsMargins(12, 12, 12, 12)
            return w, f

        # Playback
        w, f = page()
        self._spin(f, "skip_seconds", "Arrow-key skip", 1, 60, " s")
        self._spin(f, "long_skip_seconds", "Shift + arrow skip", 5, 600, " s")
        self._check(f, "resume", "Continue videos where I left off")
        self._check(f, "remember_speed", "Remember the speed for each file")
        self._check(f, "hold_to_boost", "Hold → to play faster (like YouTube)")
        self._dspin(f, "boost_speed", "Hold-→ speed", 1.25, 8.0, 0.25, "×")
        self._check(f, "pitch_correction", "Keep voices natural when changing speed")
        tabs.addTab(w, "Playback")

        # Links & downloads
        w, f = page()
        self._combo(f, "stream_quality", "Streaming quality", ytdl.STREAM_QUALITIES)
        self._combo(f, "download_quality", "Download quality", ytdl.QUALITIES)
        self._spin(f, "cache_mb", "Buffer size", 20, 2000, " MB",
                   "Bigger = smoother playback on slow or unstable internet")
        self._spin(f, "readahead_secs", "Preload ahead", 5, 3600, " s",
                   "How many seconds of video to load ahead of the current spot")
        self._check(f, "download_subs", "Download subtitles by default")
        self._line(f, "sub_langs", "Subtitle languages", "e.g. en.*  or  en.*,fil  or  all")
        self._check(f, "show_thumbnails", "Show thumbnails when checking links")
        dir_row = QHBoxLayout()
        self.dl_dir = QLineEdit(cfg.get("download_dir"))
        b = QPushButton("Browse…")
        b.clicked.connect(lambda: self._pick_dir(self.dl_dir))
        dir_row.addWidget(self.dl_dir, 1)
        dir_row.addWidget(b)
        f.addRow("Download folder", dir_row)
        tabs.addTab(w, "Links & downloads")

        # Interface
        w, f = page()
        self._check(f, "autohide_windowed", "Hide controls when the mouse is idle (also in a window)")
        self._check(f, "wheel_gestures", "Mouse wheel: left half = brightness, right half = volume")
        shot_row = QHBoxLayout()
        self.shot_dir = QLineEdit(cfg.get("screenshot_dir"))
        b2 = QPushButton("Browse…")
        b2.clicked.connect(lambda: self._pick_dir(self.shot_dir))
        shot_row.addWidget(self.shot_dir, 1)
        shot_row.addWidget(b2)
        f.addRow("Screenshot folder", shot_row)
        tabs.addTab(w, "Interface")

        # Advanced
        w, f = page()
        self._check(f, "hwdec", "Hardware decoding (uses the graphics card, saves battery)")
        self._combo(f, "video_backend", "Video output",
                    [("opengl", "Standard (OpenGL)"), ("native", "Compatibility")],
                    "Try Compatibility if the picture stays black")
        log_btn = QPushButton("Open log file")
        log_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(paths.log_path())))
        f.addRow("Troubleshooting", log_btn)
        data_btn = QPushButton("Open settings folder")
        data_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(paths.data_dir())))
        f.addRow("", data_btn)
        tabs.addTab(w, "Advanced")

        note = QLabel("Buffer, hardware decoding and video output changes apply after restarting Strimo.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        lay.addWidget(note)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Save")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    # ---- builders ---------------------------------------------------------
    def _check(self, f, key, label):
        w = QCheckBox(label)
        w.setChecked(bool(self.cfg.get(key)))
        f.addRow(w)
        self._w[key] = ("check", w)

    def _spin(self, f, key, label, lo, hi, suffix="", tip=""):
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setValue(int(self.cfg.get(key)))
        w.setSuffix(suffix)
        if tip:
            w.setToolTip(tip)
        f.addRow(label, w)
        self._w[key] = ("spin", w)

    def _dspin(self, f, key, label, lo, hi, step, suffix=""):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(2)
        w.setValue(float(self.cfg.get(key)))
        w.setSuffix(suffix)
        f.addRow(label, w)
        self._w[key] = ("dspin", w)

    def _combo(self, f, key, label, choices, tip=""):
        w = QComboBox()
        for k, text in choices:
            w.addItem(text, k)
        idx = w.findData(self.cfg.get(key))
        w.setCurrentIndex(max(0, idx))
        if tip:
            w.setToolTip(tip)
        f.addRow(label, w)
        self._w[key] = ("combo", w)

    def _line(self, f, key, label, placeholder=""):
        w = QLineEdit(str(self.cfg.get(key) or ""))
        w.setPlaceholderText(placeholder)
        f.addRow(label, w)
        self._w[key] = ("line", w)

    def _pick_dir(self, edit: QLineEdit) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text())
        if d:
            edit.setText(d)

    def _save(self) -> None:
        for key, (kind, w) in self._w.items():
            if kind == "check":
                v = w.isChecked()
            elif kind == "spin":
                v = int(w.value())
            elif kind == "dspin":
                v = float(w.value())
            elif kind == "combo":
                v = w.currentData()
            else:
                v = w.text().strip()
            if self.cfg.get(key) != v:
                self.cfg.set(key, v)
                self.changed.add(key)
        for key, edit in (("download_dir", self.dl_dir), ("screenshot_dir", self.shot_dir)):
            v = edit.text().strip()
            if v and v != self.cfg.get(key):
                self.cfg.set(key, v)
                self.changed.add(key)
        self.accept()


# ============================================================== Shortcuts
SHORTCUTS = [
    ("Playback", [
        ("Space", "Play / pause"),
        ("← / →", "Back / forward 5 s"),
        ("Shift + ← / →", "Back / forward 30 s"),
        ("Hold →", "Play at 2× while held"),
        ("0 – 9", "Jump to 0% … 90%"),
        (". / ,", "Next / previous frame"),
        ("L", "A-B repeat (set A, set B, clear)"),
        ("Page Up / Page Down", "Previous / next file"),
        ("Ctrl + G", "Jump to a time"),
        ("Ctrl + B", "Bookmark this moment"),
    ]),
    ("Speed", [
        ("] / [", "Faster / slower by 0.1×"),
        ("} / {  (Shift + ] / [)", "Faster / slower by 0.01×"),
        ("Backspace", "Back to 1×"),
    ]),
    ("Sound", [
        ("↑ / ↓", "Volume up / down"),
        ("M", "Mute"),
        ("N", "Night mode"),
        ("Mouse wheel", "Volume (left half of the video: brightness)"),
    ]),
    ("Picture", [
        ("R", "Rotate 90°"),
        ("H / V", "Flip horizontal / vertical"),
        ("P", "Portrait mode"),
        ("Ctrl + Shift + R", "Reset orientation"),
        ("Ctrl + = / Ctrl + - / Ctrl + 0", "Zoom in / out / reset"),
        ("S", "Screenshot"),
        ("Z / X", "Subtitles earlier / later"),
    ]),
    ("Window", [
        ("F or double-click", "Fullscreen"),
        ("Esc", "Leave fullscreen / mini player"),
        ("Ctrl + M", "Mini player"),
        ("T", "Always on top"),
        ("Ctrl + P", "Side panel"),
        ("I", "Media information"),
    ]),
    ("Files & links", [
        ("Ctrl + O", "Open file"),
        ("Ctrl + U", "Open link"),
        ("Ctrl + V", "Play a copied link or file path"),
        ("Ctrl + D", "Downloads"),
        ("Ctrl + T", "Sleep timer"),
    ]),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)
        row = 0
        for section, items in SHORTCUTS:
            h = QLabel(section)
            h.setObjectName("title")
            grid.addWidget(h, row, 0, 1, 2)
            row += 1
            for keys, what in items:
                k = QLabel(keys)
                k.setObjectName("badge")
                grid.addWidget(k, row, 0)
                grid.addWidget(QLabel(what), row, 1)
                row += 1
        grid.setRowStretch(row, 1)
        scroll.setWidget(inner)
        lay.addWidget(scroll)
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)


def about_text() -> str:
    tools = []
    for name in ("yt-dlp", "ffmpeg"):
        tools.append(f"{name}: {'found' if paths.find_tool(name) else 'not found'}")
    return (
        f"<h3>{APP_NAME} {__version__}</h3>"
        "<p>An ad-free video player with precise speed control, rotation, link playback and downloads.</p>"
        "<p>Built with mpv (playback), Qt / PySide6 (interface), yt-dlp (links) and FFmpeg.</p>"
        f"<p style='color:#9AA2B1'>{' · '.join(tools)}<br>Settings: {os.path.normpath(paths.data_dir())}</p>"
    )
