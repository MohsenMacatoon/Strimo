"""Seek bar with buffered range, A-B loop markers, bookmark ticks and a hover time preview."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme
from .util import fmt_time


class SeekBar(QWidget):
    seek_requested = Signal(float, bool)  # seconds, exact

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(22)
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
        self._throttle = QElapsedTimer()
        self._throttle.start()
        self.live = False

    # ---- state ------------------------------------------------------
    def set_duration(self, d) -> None:
        self.duration = float(d) if d else 0.0
        self.update()

    def set_position(self, p) -> None:
        if self._dragging:
            return
        self.position = float(p) if p else 0.0
        self.update()

    def set_buffered(self, b) -> None:
        self.buffered = float(b) if b else 0.0
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

    # ---- geometry ---------------------------------------------------
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

    # ---- painting -------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tr = self._track()
        hovered = self._hover_x is not None or self._dragging
        if hovered:
            tr = tr.adjusted(0, -1.5, 0, 1.5)
        radius = tr.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(tr, radius, radius)

        if self.duration > 0:
            pos = self._drag_pos if self._dragging else self.position
            # intro region
            if self.intro:
                x1, x2 = self._x_for(self.intro[0]), self._x_for(self.intro[1])
                p.setBrush(QColor(245, 185, 66, 70))
                p.drawRect(QRectF(x1, tr.top(), max(1.0, x2 - x1), tr.height()))
            # buffered
            if self.buffered > pos:
                x1, x2 = self._x_for(pos), self._x_for(self.buffered)
                p.setBrush(QColor("#59606e"))
                p.drawRoundedRect(QRectF(x1, tr.top(), max(0.0, x2 - x1), tr.height()), radius, radius)
            # A-B region
            a, b = self.ab
            if a is not None:
                xa = self._x_for(a)
                xb = self._x_for(b) if b is not None else xa
                p.setBrush(QColor(245, 185, 66, 110))
                p.drawRect(QRectF(xa, tr.top() - 3, max(2.0, xb - xa), tr.height() + 6))
            # played
            xp = self._x_for(pos)
            p.setBrush(QColor(theme.ACCENT))
            p.drawRoundedRect(QRectF(tr.left(), tr.top(), max(0.0, xp - tr.left()), tr.height()), radius, radius)
            # bookmarks
            p.setBrush(QColor("#ffffff"))
            for m in self.marks:
                xm = self._x_for(m)
                p.drawRect(QRectF(xm - 1, tr.top() - 4, 2, tr.height() + 8))
            # handle
            if hovered:
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(QRectF(xp - 7, tr.center().y() - 7, 14, 14))
            # hover marker
            if self._hover_x is not None and not self._dragging:
                p.setBrush(QColor(255, 255, 255, 90))
                p.drawRect(QRectF(self._hover_x - 1, tr.top() - 3, 2, tr.height() + 6))
        p.end()

    # ---- mouse ----------------------------------------------------------
    def _show_tip(self, x: float, global_pos: QPoint) -> None:
        if self.duration <= 0:
            return
        t = self._t_for(x)
        text = fmt_time(t, self.duration >= 3600)
        QToolTip.showText(QPoint(global_pos.x() - 18, self.mapToGlobal(QPoint(0, 0)).y() - 42), text, self)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
            return
        self._dragging = True
        self._drag_pos = self._t_for(e.position().x())
        self.seek_requested.emit(self._drag_pos, False)
        self._throttle.restart()
        self.update()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        self._hover_x = x
        self._show_tip(x, e.globalPosition().toPoint())
        if self._dragging:
            self._drag_pos = self._t_for(x)
            if self._throttle.elapsed() > 60:
                self.seek_requested.emit(self._drag_pos, False)
                self._throttle.restart()
        self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging and e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_pos = self._t_for(e.position().x())
            self.position = self._drag_pos
            self.seek_requested.emit(self._drag_pos, True)
            self.update()

    def leaveEvent(self, _e):
        self._hover_x = None
        QToolTip.hideText()
        self.update()

    def wheelEvent(self, e):
        # scrolling over the bar seeks by 5 s per notch
        if self.duration <= 0:
            return
        steps = e.angleDelta().y() / 120
        if steps:
            self.seek_requested.emit(max(0.0, min(self.duration, self.position + 5 * steps)), True)
