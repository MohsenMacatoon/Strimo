"""Side panel tabs: Playlist, Bookmarks, Notes, Adjust, Info."""

from __future__ import annotations

import os
import random

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QScrollArea, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from . import icons, theme
from .util import ASPECT_CHOICES, display_name, fmt_time, human_bitrate, human_size, is_url

_USER_ROLE = int(Qt.ItemDataRole.UserRole.value)
ROLE_ENTRY = _USER_ROLE
ROLE_CURRENT = _USER_ROLE + 1
ROLE_TIME = _USER_ROLE + 2


def small_button(icon_name: str, tip: str) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(17, 17))
    b.setFixedSize(30, 30)
    b.setToolTip(tip)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def panel_layout(widget: QWidget) -> QVBoxLayout:
    widget.setObjectName("panelRoot")
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QVBoxLayout(widget)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(8)
    return lay


# ============================================================== Playlist
class PlaylistPanel(QWidget):
    play_requested = Signal(int)
    add_files_requested = Signal()
    add_folder_requested = Signal()
    loop_mode_changed = Signal(str)
    changed = Signal()

    LOOP_LABELS = {"none": "Repeat: off", "one": "Repeat: this file", "all": "Repeat: whole list"}

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = panel_layout(self)
        top = QHBoxLayout()
        self.count_label = QLabel("Playlist is empty")
        self.count_label.setObjectName("dim")
        top.addWidget(self.count_label, 1)
        self.add_btn = small_button("plus", "Add files")
        self.folder_btn = small_button("folder", "Add a whole folder")
        self.shuffle_btn = small_button("shuffle", "Shuffle")
        self.loop_btn = small_button("repeat", "Repeat: off")
        self.loop_btn.setCheckable(True)
        self.clear_btn = small_button("trash", "Clear playlist")
        for b in (self.add_btn, self.folder_btn, self.shuffle_btn, self.loop_btn, self.clear_btn):
            top.addWidget(b)
        lay.addLayout(top)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.itemDoubleClicked.connect(lambda it: self.play_requested.emit(self.list.row(it)))
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.model().rowsMoved.connect(lambda *a: self._after_change())
        lay.addWidget(self.list, 1)
        hint = QLabel("Drag to reorder · double-click to play")
        hint.setObjectName("dim")
        lay.addWidget(hint)

        self.loop_mode = "none"
        self.add_btn.clicked.connect(self.add_files_requested.emit)
        self.folder_btn.clicked.connect(self.add_folder_requested.emit)
        self.shuffle_btn.clicked.connect(self.shuffle)
        self.loop_btn.clicked.connect(lambda _=False: self.cycle_loop())
        self.clear_btn.clicked.connect(self.clear)

    # ---- data ----------------------------------------------------------
    def entries(self) -> list[str]:
        return [self.list.item(i).data(ROLE_ENTRY) for i in range(self.list.count())]

    def count(self) -> int:
        return self.list.count()

    def _make_item(self, entry: str) -> QListWidgetItem:
        it = QListWidgetItem(("🌐  " if is_url(entry) else "") + display_name(entry))
        it.setData(ROLE_ENTRY, entry)
        it.setData(ROLE_CURRENT, False)
        it.setToolTip(entry)
        return it

    def set_entries(self, entries: list[str], current: int = -1) -> None:
        self.list.clear()
        for e in entries:
            self.list.addItem(self._make_item(e))
        self.set_current(current)

    def add_entries(self, entries: list[str]) -> int:
        """Append entries that aren't already in the list. Returns index of the first given entry."""
        existing = self.entries()
        first = -1
        for e in entries:
            if e in existing:
                idx = existing.index(e)
            else:
                self.list.addItem(self._make_item(e))
                existing.append(e)
                idx = len(existing) - 1
            if first < 0:
                first = idx
        self._after_change()
        return first

    def index_of(self, entry: str) -> int:
        try:
            return self.entries().index(entry)
        except ValueError:
            return -1

    def current_index(self) -> int:
        for i in range(self.list.count()):
            if self.list.item(i).data(ROLE_CURRENT):
                return i
        return -1

    def current_entry(self):
        i = self.current_index()
        return self.list.item(i).data(ROLE_ENTRY) if i >= 0 else None

    def set_current(self, index: int) -> None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            cur = i == index
            it.setData(ROLE_CURRENT, cur)
            f = QFont(self.list.font())
            f.setBold(cur)
            it.setFont(f)
            it.setForeground(QColor(theme.ACCENT) if cur else QColor(theme.TEXT))
            if cur:
                self.list.scrollToItem(it)
        self._update_count()

    def next_index(self, wrap: bool) -> int:
        i, n = self.current_index(), self.list.count()
        if n == 0:
            return -1
        if i + 1 < n:
            return i + 1
        return 0 if wrap else -1

    def prev_index(self, wrap: bool) -> int:
        i, n = self.current_index(), self.list.count()
        if n == 0:
            return -1
        if i - 1 >= 0:
            return i - 1
        return n - 1 if wrap else -1

    def entry_at(self, index: int):
        it = self.list.item(index)
        return it.data(ROLE_ENTRY) if it else None

    def shuffle(self) -> None:
        entries = self.entries()
        if len(entries) < 2:
            return
        cur = self.current_entry()
        rest = [e for e in entries if e != cur]
        random.shuffle(rest)
        new = ([cur] if cur else []) + rest
        self.set_entries(new, 0 if cur else -1)
        self._after_change()

    def clear(self) -> None:
        cur = self.current_entry()
        self.set_entries([cur] if cur else [], 0 if cur else -1)
        self._after_change()

    def remove_rows(self, rows: list[int]) -> None:
        for r in sorted(rows, reverse=True):
            self.list.takeItem(r)
        self._after_change()

    def cycle_loop(self) -> None:
        order = ["none", "all", "one"]
        self.set_loop_mode(order[(order.index(self.loop_mode) + 1) % 3])
        self.loop_mode_changed.emit(self.loop_mode)

    def set_loop_mode(self, mode: str) -> None:
        self.loop_mode = mode if mode in self.LOOP_LABELS else "none"
        self.loop_btn.setChecked(self.loop_mode != "none")
        self.loop_btn.setToolTip(self.LOOP_LABELS[self.loop_mode] + " (click to change)")

    def _update_count(self) -> None:
        n = self.list.count()
        i = self.current_index()
        if n == 0:
            self.count_label.setText("Playlist is empty")
        elif i >= 0:
            self.count_label.setText(f"{i + 1} of {n}")
        else:
            self.count_label.setText(f"{n} item{'s' if n != 1 else ''}")

    def _after_change(self) -> None:
        self._update_count()
        self.changed.emit()

    def _context_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        menu = QMenu(self)
        if it:
            row = self.list.row(it)
            entry = it.data(ROLE_ENTRY)
            menu.addAction("Play", lambda: self.play_requested.emit(row))
            rows = sorted({self.list.row(x) for x in self.list.selectedItems()} | {row})
            menu.addAction(f"Remove ({len(rows)})" if len(rows) > 1 else "Remove", lambda: self.remove_rows(rows))
            if not is_url(entry):
                menu.addAction("Show in folder", lambda: _show_in_folder(entry))
            else:
                menu.addAction("Copy link", lambda: QGuiApplication.clipboard().setText(entry))
            menu.addSeparator()
        menu.addAction("Add files…", self.add_files_requested.emit)
        menu.addAction("Add folder…", self.add_folder_requested.emit)
        menu.addAction("Shuffle", self.shuffle)
        menu.exec(self.list.mapToGlobal(pos))


def _show_in_folder(path: str) -> None:
    import subprocess

    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


# ============================================================== Bookmarks / Notes
class _TimedListPanel(QWidget):
    jump_requested = Signal(float)
    items_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = panel_layout(self)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda it: self.jump_requested.emit(float(it.data(ROLE_TIME))))
        self._items: list[dict] = []

    def _text(self, item: dict) -> str:
        raise NotImplementedError

    def set_items(self, items: list[dict]) -> None:
        self._items = sorted(items, key=lambda x: x.get("t", 0))
        self.list.clear()
        for item in self._items:
            it = QListWidgetItem(self._text(item))
            it.setData(ROLE_TIME, float(item.get("t", 0)))
            self.list.addItem(it)
        self._empty_changed()

    def items(self) -> list[dict]:
        return list(self._items)

    def _empty_changed(self) -> None:
        pass

    def _delete_selected(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self._items):
            del self._items[row]
            self.set_items(self._items)
            self.items_changed.emit(self.items())


class BookmarksPanel(_TimedListPanel):
    add_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        top = QHBoxLayout()
        self.info = QLabel("Mark important moments (Ctrl+B)")
        self.info.setObjectName("dim")
        top.addWidget(self.info, 1)
        add = small_button("plus", "Bookmark this moment (Ctrl+B)")
        ren = small_button("note", "Rename")
        dele = small_button("trash", "Delete")
        add.clicked.connect(self.add_requested.emit)
        ren.clicked.connect(self._rename)
        dele.clicked.connect(self._delete_selected)
        for b in (add, ren, dele):
            top.addWidget(b)
        self.lay.addLayout(top)
        self.lay.addWidget(self.list, 1)
        hint = QLabel("Double-click a bookmark to jump to it")
        hint.setObjectName("dim")
        self.lay.addWidget(hint)

    def _text(self, item):
        return f"{fmt_time(item.get('t'))}   {item.get('label', '')}"

    def _rename(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self._items):
            return
        text, ok = QInputDialog.getText(self, "Rename bookmark", "Label:", QLineEdit.EchoMode.Normal,
                                        self._items[row].get("label", ""))
        if ok:
            self._items[row]["label"] = text.strip()
            self.set_items(self._items)
            self.items_changed.emit(self.items())


class NotesPanel(_TimedListPanel):
    def __init__(self, time_source, parent=None):
        super().__init__(parent)
        self.time_source = time_source
        self._pending_time = None
        self.title = ""
        top = QHBoxLayout()
        lab = QLabel("Timestamped notes for this video")
        lab.setObjectName("dim")
        top.addWidget(lab, 1)
        copy_btn = small_button("file", "Copy all notes")
        export_btn = small_button("download", "Export notes to a .txt file")
        dele = small_button("trash", "Delete selected note")
        copy_btn.clicked.connect(self._copy)
        export_btn.clicked.connect(self._export)
        dele.clicked.connect(self._delete_selected)
        for b in (copy_btn, export_btn, dele):
            top.addWidget(b)
        self.lay.addLayout(top)
        self.lay.addWidget(self.list, 1)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type a note and press Enter…")
        self.edit.textEdited.connect(self._on_edit)
        self.edit.returnPressed.connect(self._commit)
        self.stamp = QLabel("")
        self.stamp.setObjectName("dim")
        self.lay.addWidget(self.stamp)
        self.lay.addWidget(self.edit)

    def _text(self, item):
        return f"[{fmt_time(item.get('t'))}]  {item.get('text', '')}"

    def _on_edit(self, text: str) -> None:
        if text and self._pending_time is None:
            self._pending_time = self.time_source() or 0.0
            self.stamp.setText(f"Note will be saved at {fmt_time(self._pending_time)}")
        elif not text:
            self._pending_time = None
            self.stamp.setText("")

    def _commit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        t = self._pending_time if self._pending_time is not None else (self.time_source() or 0.0)
        self._items.append({"t": round(float(t), 2), "text": text})
        self.set_items(self._items)
        self.items_changed.emit(self.items())
        self.edit.clear()
        self._pending_time = None
        self.stamp.setText("")

    def as_text(self) -> str:
        lines = [f"Notes — {self.title}" if self.title else "Notes", ""]
        lines += [f"[{fmt_time(i.get('t'))}] {i.get('text', '')}" for i in self._items]
        return "\n".join(lines) + "\n"

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.as_text())

    def _export(self) -> None:
        if not self._items:
            return
        base = (self.title or "notes").rsplit(".", 1)[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export notes", base + " - notes.txt", "Text files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.as_text())


# ============================================================== Adjust
class AdjustPanel(QWidget):
    """Picture, audio and subtitle adjustments. Talks to the player directly."""

    load_sub_requested = Signal()

    EQ = [("brightness", "Brightness"), ("contrast", "Contrast"), ("saturation", "Saturation"),
          ("gamma", "Gamma"), ("hue", "Hue")]
    PRESETS = {
        "Dark video boost": {"brightness": 6, "contrast": 4, "saturation": 0, "gamma": 22, "hue": 0},
        "Vivid": {"brightness": 0, "contrast": 10, "saturation": 28, "gamma": 0, "hue": 0},
        "Reset": {"brightness": 0, "contrast": 0, "saturation": 0, "gamma": 0, "hue": 0},
    }

    def __init__(self, get_player, cfg, parent=None):
        super().__init__(parent)
        self.get_player = get_player
        self.cfg = cfg
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = panel_layout(inner)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # picture
        pic = QGroupBox("Picture")
        grid = QGridLayout(pic)
        grid.setVerticalSpacing(6)
        self.sliders: dict[str, QSlider] = {}
        self.value_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(self.EQ):
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(-100, 100)
            s.setValue(0)
            s.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            v = QLabel("0")
            v.setMinimumWidth(30)
            v.setObjectName("timeLabel")
            s.valueChanged.connect(lambda val, k=key: self._eq(k, val))
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(s, row, 1)
            grid.addWidget(v, row, 2)
            self.sliders[key] = s
            self.value_labels[key] = v
        presets = QHBoxLayout()
        for name in self.PRESETS:
            b = QPushButton(name)
            b.setProperty("chip", True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, n=name: self.apply_preset(n))
            presets.addWidget(b)
        grid.addLayout(presets, len(self.EQ), 0, 1, 3)
        lay.addWidget(pic)

        # view
        view = QGroupBox("View")
        form = QFormLayout(view)
        self.aspect = QComboBox()
        for key, label in ASPECT_CHOICES:
            self.aspect.addItem(label, key)
        self.aspect.currentIndexChanged.connect(lambda _i: self._player_call("set_aspect", self.aspect.currentData()))
        form.addRow("Aspect ratio", self.aspect)
        zoom_row = QHBoxLayout()
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(-100, 200)  # hundredths of log2 zoom
        self.zoom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.zoom.valueChanged.connect(self._zoom_changed)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("timeLabel")
        self.zoom_label.setMinimumWidth(42)
        zoom_reset = QPushButton("Reset")
        zoom_reset.setProperty("chip", True)
        zoom_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        zoom_reset.clicked.connect(self.reset_zoom)
        zoom_row.addWidget(self.zoom, 1)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(zoom_reset)
        form.addRow("Zoom", zoom_row)
        pan_row = QHBoxLayout()
        self.pan_x = QSlider(Qt.Orientation.Horizontal)
        self.pan_y = QSlider(Qt.Orientation.Horizontal)
        for s, prop in ((self.pan_x, "video-pan-x"), (self.pan_y, "video-pan-y")):
            s.setRange(-50, 50)
            s.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            s.valueChanged.connect(lambda v, p=prop: self._set(p, v / 100.0))
        pan_row.addWidget(QLabel("←→"))
        pan_row.addWidget(self.pan_x)
        pan_row.addWidget(QLabel("↑↓"))
        pan_row.addWidget(self.pan_y)
        form.addRow("Pan", pan_row)
        lay.addWidget(view)

        # audio
        audio = QGroupBox("Audio")
        af = QFormLayout(audio)
        self.audio_track = QComboBox()
        self.audio_track.activated.connect(lambda _i: self._set("aid", self.audio_track.currentData()))
        af.addRow("Track", self.audio_track)
        self.audio_delay = QDoubleSpinBox()
        self.audio_delay.setRange(-30, 30)
        self.audio_delay.setDecimals(2)
        self.audio_delay.setSingleStep(0.05)
        self.audio_delay.setSuffix(" s")
        self.audio_delay.setToolTip("Positive = sound later, negative = sound earlier")
        self.audio_delay.valueChanged.connect(lambda v: self._set("audio-delay", v))
        af.addRow("Sync (delay)", self.audio_delay)
        self.night = QCheckBox("Night mode — softer explosions, clearer voices")
        self.night.toggled.connect(lambda on: self._player_call("set_night_mode", on))
        af.addRow(self.night)
        lay.addWidget(audio)

        # subtitles
        subs = QGroupBox("Subtitles")
        sf = QFormLayout(subs)
        self.sub_track = QComboBox()
        self.sub_track.activated.connect(lambda _i: self._set("sid", self.sub_track.currentData()))
        sf.addRow("Track", self.sub_track)
        load = QPushButton("Load subtitle file…")
        load.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        load.clicked.connect(self.load_sub_requested.emit)
        sf.addRow(load)
        self.sub_delay = QDoubleSpinBox()
        self.sub_delay.setRange(-60, 60)
        self.sub_delay.setDecimals(2)
        self.sub_delay.setSingleStep(0.1)
        self.sub_delay.setSuffix(" s")
        self.sub_delay.setToolTip("Keys: Z = earlier, X = later")
        self.sub_delay.valueChanged.connect(lambda v: self._set("sub-delay", v))
        sf.addRow("Delay", self.sub_delay)
        self.sub_scale = QSlider(Qt.Orientation.Horizontal)
        self.sub_scale.setRange(40, 300)
        self.sub_scale.setValue(int(float(cfg.get("sub_scale")) * 100))
        self.sub_scale.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sub_scale.valueChanged.connect(self._sub_scale)
        sf.addRow("Size", self.sub_scale)
        lay.addWidget(subs)
        lay.addStretch(1)

    # ---- helpers ------------------------------------------------------------
    def _set(self, prop, value) -> None:
        p = self.get_player()
        if p is not None and value is not None:
            p.set(prop, value)

    def _player_call(self, method, *args) -> None:
        p = self.get_player()
        if p is not None:
            getattr(p, method)(*args)

    def _eq(self, key: str, val: int) -> None:
        self.value_labels[key].setText(f"{val:+d}" if val else "0")
        self._set(key, val)

    def apply_preset(self, name: str) -> None:
        for key, val in self.PRESETS[name].items():
            self.sliders[key].setValue(val)
        p = self.get_player()
        if p is not None:
            p.osd(f"Picture: {name}")

    def _zoom_changed(self, v: int) -> None:
        z = v / 100.0
        self.zoom_label.setText(f"{int(round(2 ** z * 100))}%")
        self._set("video-zoom", z)

    def reset_zoom(self) -> None:
        self.zoom.setValue(0)
        self.pan_x.setValue(0)
        self.pan_y.setValue(0)

    def step_zoom(self, delta: float) -> None:
        self.zoom.setValue(int(self.zoom.value() + delta * 100))

    def _sub_scale(self, v: int) -> None:
        self.cfg.set("sub_scale", v / 100.0)
        self._set("sub-scale", v / 100.0)

    def step_sub_scale(self, delta: float) -> None:
        self.sub_scale.setValue(int(self.sub_scale.value() + delta * 100))

    def nudge_sub_delay(self, delta: float) -> float:
        self.sub_delay.setValue(round(self.sub_delay.value() + delta, 2))
        return self.sub_delay.value()

    def set_aspect_choice(self, key: str) -> None:
        idx = self.aspect.findData(key)
        if idx >= 0:
            self.aspect.setCurrentIndex(idx)

    def refresh_from_player(self) -> None:
        """Pull current values (after a file loads, delays reset)."""
        p = self.get_player()
        if p is None:
            return
        for w, prop in ((self.audio_delay, "audio-delay"), (self.sub_delay, "sub-delay")):
            w.blockSignals(True)
            w.setValue(float(p.get(prop, 0.0) or 0.0))
            w.blockSignals(False)
        for s in (self.zoom, self.pan_x, self.pan_y):
            s.blockSignals(True)
            s.setValue(0)
            s.blockSignals(False)
        self.zoom_label.setText("100%")
        self.night.blockSignals(True)
        self.night.setChecked(bool(p.night_mode))
        self.night.blockSignals(False)
        self.refresh_tracks()

    def refresh_tracks(self) -> None:
        p = self.get_player()
        if p is None:
            return
        for combo, kind in ((self.audio_track, "audio"), (self.sub_track, "sub")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Off", "no")
            selected = 0
            for t in p.tracks(kind):
                combo.addItem(p.track_label(t), str(t.get("id")))
                if t.get("selected"):
                    selected = combo.count() - 1
            combo.setCurrentIndex(selected)
            combo.blockSignals(False)


# ============================================================== Info
class InfoPanel(QWidget):
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = panel_layout(self)
        top = QHBoxLayout()
        t = QLabel("Media information")
        t.setObjectName("title")
        top.addWidget(t, 1)
        r = QPushButton("Refresh")
        r.setProperty("chip", True)
        r.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        r.clicked.connect(self.refresh_requested.emit)
        top.addWidget(r)
        lay.addLayout(top)
        self.form = QFormLayout()
        self.form.setVerticalSpacing(7)
        lay.addLayout(self.form)
        lay.addStretch(1)
        self._labels: dict[str, QLabel] = {}
        for key in ("Name", "Location", "Container", "File size", "Duration", "Resolution", "Frame rate",
                    "Video codec", "Video bitrate", "Audio codec", "Audio", "Audio bitrate", "HW decoding"):
            v = QLabel("—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            k = QLabel(key)
            k.setObjectName("dim")
            self.form.addRow(k, v)
            self._labels[key] = v

    def show_info(self, info: dict | None) -> None:
        info = info or {}

        def put(key, value):
            self._labels[key].setText(str(value) if value not in (None, "", 0) else "—")

        path = info.get("path") or ""
        put("Name", info.get("title"))
        put("Location", path if is_url(path) else os.path.dirname(path) if path else "")
        put("Container", info.get("format"))
        put("File size", human_size(info["size"]) if info.get("size") else None)
        put("Duration", fmt_time(info.get("duration")) if info.get("duration") else None)
        if info.get("width") and info.get("height"):
            put("Resolution", f"{info['width']} × {info['height']}")
        else:
            put("Resolution", None)
        put("Frame rate", f"{float(info['fps']):.3f} fps" if info.get("fps") else None)
        put("Video codec", info.get("video_codec"))
        put("Video bitrate", human_bitrate(info.get("video_bitrate")) if info.get("video_bitrate") else None)
        put("Audio codec", info.get("audio_codec"))
        if info.get("samplerate"):
            ch = info.get("channels")
            put("Audio", f"{int(info['samplerate']) / 1000:g} kHz" + (f", {ch} ch" if ch else ""))
        else:
            put("Audio", None)
        put("Audio bitrate", human_bitrate(info.get("audio_bitrate")) if info.get("audio_bitrate") else None)
        put("HW decoding", info.get("hwdec") or ("off" if path else None))
