"""Bottom control bar and the precise speed popup."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from . import icons
from .seekbar import SeekBar
from .util import fmt_speed, fmt_time, round_speed

SPEED_PRESETS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0]


def tool_button(icon_name: str, tip: str, size: int = 34, icon_px: int = 20) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(icon_px, icon_px))
    b.setFixedSize(size, size)
    b.setToolTip(tip)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setAutoRaise(True)
    return b


class SpeedPopup(QWidget):
    speed_set = Signal(float)
    pitch_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Playback speed")
        title.setObjectName("dim")
        self.value = QLabel("1.00×")
        self.value.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.value)
        lay.addLayout(head)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(5, 800)  # hundredths
        self.slider.setSingleStep(1)
        self.slider.setPageStep(10)
        self.slider.setValue(100)
        self.slider.valueChanged.connect(lambda v: self._emit(v / 100.0))
        lay.addWidget(self.slider)

        row = QHBoxLayout()
        row.setSpacing(4)
        for delta in (-0.1, -0.01):
            b = QPushButton(f"{delta:+.2f}")
            b.setProperty("chip", True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, d=delta: self._emit(self.spin.value() + d))
            row.addWidget(b)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(0.05, 8.0)
        self.spin.setDecimals(2)
        self.spin.setSingleStep(0.01)
        self.spin.setSuffix(" ×")
        self.spin.setValue(1.0)
        self.spin.setKeyboardTracking(False)
        self.spin.setToolTip("Type an exact speed, e.g. 1.37, then press Enter")
        self.spin.valueChanged.connect(self._emit)
        row.addWidget(self.spin, 1)
        for delta in (0.01, 0.1):
            b = QPushButton(f"{delta:+.2f}")
            b.setProperty("chip", True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, d=delta: self._emit(self.spin.value() + d))
            row.addWidget(b)
        lay.addLayout(row)

        grid = QGridLayout()
        grid.setSpacing(4)
        for i, s in enumerate(SPEED_PRESETS):
            b = QPushButton(f"{s:g}×")
            b.setProperty("chip", True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, v=s: self._emit(v))
            grid.addWidget(b, i // 5, i % 5)
        lay.addLayout(grid)

        self.pitch = QCheckBox("Keep voice pitch natural (pitch correction)")
        self.pitch.setChecked(True)
        self.pitch.toggled.connect(self.pitch_toggled.emit)
        lay.addWidget(self.pitch)

        hint = QLabel("Keys: [ ] ±0.1   { } ±0.01   Backspace = 1×")
        hint.setObjectName("dim")
        lay.addWidget(hint)

    def _emit(self, value: float) -> None:
        self.speed_set.emit(round_speed(value))

    def set_speed(self, speed: float) -> None:
        s = round_speed(speed)
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.slider.setValue(int(round(s * 100)))
        self.spin.setValue(s)
        for w in (self.slider, self.spin):
            w.blockSignals(False)
        self.value.setText(fmt_speed(s))

    def set_pitch(self, on: bool) -> None:
        self.pitch.blockSignals(True)
        self.pitch.setChecked(on)
        self.pitch.blockSignals(False)


class ClickLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ControlBar(QWidget):
    play_clicked = Signal()
    prev_clicked = Signal()
    next_clicked = Signal()
    stop_clicked = Signal()
    mute_clicked = Signal()
    volume_changed = Signal(int)
    fullscreen_clicked = Signal()
    panel_clicked = Signal()
    screenshot_clicked = Signal()
    ab_clicked = Signal()
    mini_clicked = Signal()
    sleep_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("controlBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.show_remaining = False
        self._pos = 0.0
        self._dur = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 4, 10, 6)
        root.setSpacing(2)

        # seek row
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self.pos_label = QLabel("0:00")
        self.pos_label.setObjectName("timeLabel")
        self.pos_label.setMinimumWidth(52)
        self.pos_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seekbar = SeekBar()
        self.dur_label = ClickLabel("0:00")
        self.dur_label.setObjectName("timeLabel")
        self.dur_label.setMinimumWidth(56)
        self.dur_label.setToolTip("Click to switch between total and remaining time")
        self.dur_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dur_label.clicked.connect(self._toggle_remaining)
        seek_row.addWidget(self.pos_label)
        seek_row.addWidget(self.seekbar, 1)
        seek_row.addWidget(self.dur_label)
        root.addLayout(seek_row)

        # buttons row
        row = QHBoxLayout()
        row.setSpacing(2)
        self.prev_btn = tool_button("prev", "Previous file (Page Up)")
        self.play_btn = tool_button("play", "Play / Pause (Space)", 38, 18)
        self.play_btn.setObjectName("playButton")
        self.next_btn = tool_button("next", "Next file (Page Down)")
        self.stop_btn = tool_button("stop", "Stop")
        self.prev_btn.clicked.connect(self.prev_clicked.emit)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        self.next_btn.clicked.connect(self.next_clicked.emit)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        for b in (self.prev_btn, self.play_btn, self.next_btn, self.stop_btn):
            row.addWidget(b)
        row.addSpacing(10)

        self.mute_btn = tool_button("volume", "Mute (M)")
        self.mute_btn.clicked.connect(self.mute_clicked.emit)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 200)
        self.volume.setValue(100)
        self.volume.setFixedWidth(110)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.setToolTip("Volume (↑ / ↓, mouse wheel). Goes up to 200%")
        self.volume.valueChanged.connect(self.volume_changed.emit)
        self.vol_label = QLabel("100%")
        self.vol_label.setObjectName("timeLabel")
        self.vol_label.setMinimumWidth(40)
        row.addWidget(self.mute_btn)
        row.addWidget(self.volume)
        row.addWidget(self.vol_label)

        row.addStretch(1)

        self.frame_label = QLabel("")
        self.frame_label.setObjectName("timeLabel")
        self.frame_label.hide()
        row.addWidget(self.frame_label)
        row.addSpacing(6)

        self.sleep_label = ClickLabel("")
        self.sleep_label.setObjectName("badge")
        self.sleep_label.setToolTip("Sleep timer is on — click to change or cancel")
        self.sleep_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sleep_label.clicked.connect(self.sleep_clicked.emit)
        self.sleep_label.hide()
        row.addWidget(self.sleep_label)
        row.addSpacing(6)

        self.speed_btn = QToolButton()
        self.speed_btn.setObjectName("speedButton")
        self.speed_btn.setText("1.00×")
        self.speed_btn.setToolTip("Playback speed")
        self.speed_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.speed_popup = SpeedPopup()
        speed_menu = QMenu(self.speed_btn)
        act = QWidgetAction(speed_menu)
        act.setDefaultWidget(self.speed_popup)
        speed_menu.addAction(act)
        self.speed_btn.setMenu(speed_menu)
        row.addWidget(self.speed_btn)
        row.addSpacing(4)

        self.rotate_btn = tool_button("rotate", "Rotate / flip (R, H, V)")
        self.rotate_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.ab_btn = tool_button("loop", "A-B repeat (L)")
        self.ab_btn.setCheckable(True)
        self.ab_btn.clicked.connect(lambda _=False: self.ab_clicked.emit())
        self.shot_btn = tool_button("camera", "Screenshot (S)")
        self.shot_btn.clicked.connect(self.screenshot_clicked.emit)
        self.mini_btn = tool_button("mini", "Mini player (Ctrl+M)")
        self.mini_btn.clicked.connect(self.mini_clicked.emit)
        self.panel_btn = tool_button("panel", "Side panel: playlist, bookmarks, notes, downloads (Ctrl+P)")
        self.panel_btn.setCheckable(True)
        self.panel_btn.clicked.connect(lambda _=False: self.panel_clicked.emit())
        self.fs_btn = tool_button("fullscreen", "Fullscreen (F / double-click)")
        self.fs_btn.clicked.connect(self.fullscreen_clicked.emit)
        for b in (self.rotate_btn, self.ab_btn, self.shot_btn, self.mini_btn, self.panel_btn, self.fs_btn):
            row.addWidget(b)
        root.addLayout(row)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    # ---- updates ----------------------------------------------------------
    def _toggle_remaining(self) -> None:
        self.show_remaining = not self.show_remaining
        self._refresh_time()

    def _refresh_time(self) -> None:
        hours = self._dur >= 3600
        self.pos_label.setText(fmt_time(self._pos, hours))
        if self.show_remaining and self._dur:
            self.dur_label.setText("-" + fmt_time(max(0.0, self._dur - self._pos), hours))
        else:
            self.dur_label.setText(fmt_time(self._dur, hours) if self._dur else "0:00")

    def set_time(self, pos, dur=None) -> None:
        if pos is not None:
            self._pos = float(pos)
            self.seekbar.set_position(pos)
        if dur is not None:
            self._dur = float(dur)
            self.seekbar.set_duration(dur)
        self._refresh_time()

    def reset_time(self) -> None:
        self._pos = 0.0
        self._dur = 0.0
        self.seekbar.set_duration(0)
        self.seekbar.set_position(0)
        self.seekbar.set_buffered(0)
        self._refresh_time()

    def set_playing(self, playing: bool) -> None:
        self.play_btn.setIcon(icons.icon("pause" if playing else "play", "#08110f"))
        self.play_btn.setIconSize(QSize(18, 18))

    def set_volume(self, vol: int, muted: bool) -> None:
        self.volume.blockSignals(True)
        self.volume.setValue(int(vol))
        self.volume.blockSignals(False)
        self.vol_label.setText("Muted" if muted else f"{int(vol)}%")
        name = "mute" if muted or vol == 0 else ("volume_low" if vol < 50 else "volume")
        self.mute_btn.setIcon(icons.icon(name, "#F5B942" if vol > 100 and not muted else icons.FG))

    def set_speed(self, speed: float) -> None:
        self.speed_btn.setText(fmt_speed(speed))
        changed = abs(float(speed) - 1.0) > 1e-6
        if self.speed_btn.property("changed") != changed:
            self.speed_btn.setProperty("changed", changed)
            self.speed_btn.style().unpolish(self.speed_btn)
            self.speed_btn.style().polish(self.speed_btn)
        self.speed_popup.set_speed(speed)

    def set_fullscreen(self, fs: bool) -> None:
        self.fs_btn.setIcon(icons.icon("fullscreen_exit" if fs else "fullscreen"))

    def set_ab(self, a, b) -> None:
        self.ab_btn.setChecked(a is not None)
        self.seekbar.set_ab(a, b)

    def set_frame_text(self, text: str | None) -> None:
        self.frame_label.setVisible(bool(text))
        self.frame_label.setText(text or "")

    def set_sleep_text(self, text: str | None) -> None:
        self.sleep_label.setVisible(bool(text))
        self.sleep_label.setText(text or "")
