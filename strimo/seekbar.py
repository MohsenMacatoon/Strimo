"""Seek bar modelled on VLC's: jump-to-click, instant handle feedback while dragging,
throttled seeks during a drag plus an exact seek on release, and a light time bubble.

Also shows the buffered range, A-B loop markers, bookmark ticks and the intro-skip range.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme
from .util import fmt_time

DRAG_SEEK_MS = 150   # like VLC: at most one seek every 150 ms while dragging


class TimeBubble(QWidget):
    """The small time label above the seek bar (like VLC's time tooltip).

    A plain tool window that is only moved while the mouse moves - no tooltip
    machinery, no fade animation, never takes focus or clicks.
    """

    def __init__(self, owner=None):
        super().__init__(owner, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        f = self.font()
        f.setPointSizeF(9.5)
        f.setBold(True)
        self.setFont(f)
        self._text = ""

    def show_text(self, text: str, center_x: int, bottom_y: int) -> None:
        if text != self._text:
            self._text = text
            fm = QFontMetrics(self.font())
            self.resize(fm.horizontalAdvance(text) + 14, fm.height() + 6)
            self.update()
        self.move(int(center_x - self.width() / 2), int(bottom_y - self.height()))
        if not self.isVisible():
            self.show()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_RAISED))
        p.setPen(QPen(QColor(theme.ACCENT), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.setPen(QColor(theme.TEXT))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter.value), self._text)
        p.end()


class SeekBar(QWidget):
    seek_requested = Signal(float, bool)  # seconds, final (exact) seek

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(26)  # generous click area; the visible bar is thin like VLC's
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.duration = 0.0
        self.position = 0.0
        self.buffered = 0.0
        self.ab = (None, None)
        self.marks: list[float] = []
        self.intro = None
        self._hover_x = None
        self._dragging = False
        self._drag_pos = 0.0
        self._pending = None              # newest drag position not sent yet
        self._limit = QTimer(self)        # spaces out seeks while dragging
        self._limit.setSingleShot(True)
        self._limit.setInterval(DRAG_SEEK_MS)
        self._limit.timeout.connect(self._send_pending)
        self._bubble = TimeBubble(self)

    # ---- state ----------------------------------------------------------
    def set_duration(self, d) -> None:
        d = float(d) if d else 0.0
        if d != self.duration:
            self.duration = d
            self.update()

    def set_position(self, p) -> float:
        """Show the engine's position. Returns the position actually displayed."""
        if self._dragging:
            return self._drag_pos
        p = float(p) if p else 0.0
        if abs(p - self.position) > 1e-3:
            old_x, new_x = self._x_for(self.position), self._x_for(p)
            self.position = p
            if int(old_x) != int(new_x):
                self.update()
        return self.position

    def set_buffered(self, b) -> None:
        b = float(b) if b else 0.0
        if abs(b - self.buffered) > 0.5:
            self.buffered = b
            self.update()

    def set_ab(self, a, b) -> None:
        self.ab = (a, b)
        self.update()

    def set_marks(self, marks) -> None:
        self.marks = list(marks)
        self.update()

    def set_intro(self, rule) -> None:
        self.intro = rule
        self.update()

    def is_dragging(self) -> bool:
        return self._dragging

    # ---- geometry -----------------------------------------------------------
    def _track(self) -> QRectF:
        return QRectF(8, self.height() / 2 - 2, max(1, self.width() - 16), 4)

    def _x_for(self, t: float) -> float:
        tr = self._track()
        if self.duration <= 0:
            return tr.left()
        return tr.left() + tr.width() * max(0.0, min(1.0, t / self.duration))

    def _t_for(self, x: float) -> float:
        tr = self._track()
        frac = (x - tr.left()) / tr.width()
        return max(0.0, min(1.0, frac)) * self.duration

    # ---- painting -----------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tr = self._track()
        active = self._hover_x is not None or self._dragging
        if active:
            tr = tr.adjusted(0, -1.5, 0, 1.5)
        radius = tr.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(tr, radius, radius)

        if self.duration > 0:
            pos = self._drag_pos if self._dragging else self.position
            if self.intro:
                x1, x2 = self._x_for(self.intro[0]), self._x_for(self.intro[1])
                p.setBrush(QColor(245, 185, 66, 70))
                p.drawRect(QRectF(x1, tr.top(), max(1.0, x2 - x1), tr.height()))
            if self.buffered > pos:
                x1, x2 = self._x_for(pos), self._x_for(self.buffered)
                p.setBrush(QColor("#59606e"))
                p.drawRoundedRect(QRectF(x1, tr.top(), max(0.0, x2 - x1), tr.height()), radius, radius)
            a, b = self.ab
            if a is not None:
                xa = self._x_for(a)
                xb = self._x_for(b) if b is not None else xa
                p.setBrush(QColor(245, 185, 66, 110))
                p.drawRect(QRectF(xa, tr.top() - 3, max(2.0, xb - xa), tr.height() + 6))
            xp = self._x_for(pos)
            p.setBrush(QColor(theme.ACCENT))
            p.drawRoundedRect(QRectF(tr.left(), tr.top(), max(0.0, xp - tr.left()), tr.height()), radius, radius)
            p.setBrush(QColor("#ffffff"))
            for m in self.marks:
                xm = self._x_for(m)
                p.drawRect(QRectF(xm - 1, tr.top() - 4, 2, tr.height() + 8))
            if active:
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(QRectF(xp - 7, tr.center().y() - 7, 14, 14))
            if self._hover_x is not None and not self._dragging:
                p.setBrush(QColor(255, 255, 255, 90))
                p.drawRect(QRectF(self._hover_x - 1, tr.top() - 3, 2, tr.height() + 6))
        p.end()

    # ---- time bubble --------------------------------------------------------
    def _show_bubble(self, x: float) -> None:
        if self.duration <= 0:
            self._bubble.hide()
            return
        t = self._t_for(x)
        top_left = self.mapToGlobal(QPoint(0, 0))
        self._bubble.show_text(fmt_time(t, self.duration >= 3600), top_left.x() + int(x), top_left.y() - 2)

    def _hide_bubble(self) -> None:
        if self._bubble.isVisible():
            self._bubble.hide()

    # ---- seeking ------------------------------------------------------------
    def _seek_drag(self, t: float) -> None:
        """Called on every drag movement: seek now, or remember it for the next free slot."""
        if self._limit.isActive():
            self._pending = t
            return
        self._pending = None
        self.seek_requested.emit(t, False)
        self._limit.start()

    def _send_pending(self) -> None:
        if self._dragging and self._pending is not None:
            t, self._pending = self._pending, None
            self.seek_requested.emit(t, False)
            self._limit.start()

    # ---- mouse --------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
            e.ignore()
            return
        x = e.position().x()
        self._dragging = True
        self._hover_x = x
        self._drag_pos = self._t_for(x)          # jump to click, like VLC
        self.update()
        self._show_bubble(x)
        self._limit.stop()
        self._seek_drag(self._drag_pos)
        e.accept()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        self._hover_x = x
        self._show_bubble(x)
        if self._dragging:
            self._drag_pos = self._t_for(x)
            self._seek_drag(self._drag_pos)      # handle moves now; seeks are spaced out
        self.update()

    def mouseReleaseEvent(self, e):
        if not self._dragging or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_pos = self._t_for(e.position().x())
        self._dragging = False
        self._pending = None
        self._limit.stop()
        self.position = self._drag_pos
        self.seek_requested.emit(self._drag_pos, True)   # exact final seek
        if not self.rect().contains(e.position().toPoint()):
            self._hover_x = None
            self._hide_bubble()
        self.update()

    def leaveEvent(self, _e):
        if not self._dragging:
            self._hover_x = None
            self._hide_bubble()
            self.update()

    def hideEvent(self, e):
        self._hide_bubble()
        super().hideEvent(e)

    def wheelEvent(self, e):
        # scrolling over the bar seeks by 5 s per notch
        if self.duration <= 0:
            return
        steps = e.angleDelta().y() / 120
        if steps:
            target = max(0.0, min(self.duration, self.position + 5 * steps))
            self.position = target
            self.update()
            self.seek_requested.emit(target, True)

    def bubble_rect(self) -> QRect:
        return self._bubble.geometry()
