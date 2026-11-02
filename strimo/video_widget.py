"""Video surfaces.

NativeVideoWidget - libVLC draws the video straight into this native window (like the VLC app).
NullVideoWidget   - used by the automated self-test (no video output).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from . import theme


def paint_placeholder(widget: QWidget, painter: QPainter, message: str, sub: str) -> None:
    r = QRectF(widget.rect())
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    grad = QLinearGradient(r.topLeft(), r.bottomRight())
    grad.setColorAt(0.0, QColor("#0d0f13"))
    grad.setColorAt(1.0, QColor("#151922"))
    painter.fillRect(r, grad)
    cx, cy = r.center().x(), r.center().y() - 30
    # logo: ring + play triangle
    painter.setPen(Qt.PenStyle.NoPen)
    ring = QPainterPath()
    ring.addEllipse(QPointF(cx, cy), 46, 46)
    hole = QPainterPath()
    hole.addEllipse(QPointF(cx, cy), 38, 38)
    painter.setBrush(QColor(theme.ACCENT))
    painter.drawPath(ring.subtracted(hole))
    tri = QPainterPath()
    tri.moveTo(cx - 12, cy - 18)
    tri.lineTo(cx + 20, cy)
    tri.lineTo(cx - 12, cy + 18)
    tri.closeSubpath()
    painter.setBrush(QColor(theme.TEXT))
    painter.drawPath(tri)
    f = QFont(widget.font())
    f.setPointSizeF(15)
    f.setBold(True)
    painter.setFont(f)
    painter.setPen(QColor(theme.TEXT))
    painter.drawText(QRectF(r.left() + 20, cy + 60, r.width() - 40, 30), int(Qt.AlignmentFlag.AlignHCenter.value), message)
    f.setPointSizeF(10)
    f.setBold(False)
    painter.setFont(f)
    painter.setPen(QColor(theme.TEXT_DIM))
    painter.drawText(QRectF(r.left() + 20, cy + 94, r.width() - 40, 60),
                     int(Qt.AlignmentFlag.AlignHCenter.value) | int(Qt.TextFlag.TextWordWrap.value), sub)


class _MouseForwarder:
    """Shared mouse handling: everything is forwarded to the main window."""

    host = None

    def _setup_mouse(self, host):
        self.host = host
        self.setMouseTracking(True)
        self.setAcceptDrops(False)  # the main window handles drops
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, e):
        if self.host:
            self.host.video_mouse_press(e)

    def mouseReleaseEvent(self, e):
        if self.host:
            self.host.video_mouse_release(e)

    def mouseDoubleClickEvent(self, e):
        if self.host:
            self.host.video_double_click(e)

    def mouseMoveEvent(self, e):
        if self.host:
            self.host.video_mouse_move(e)

    def wheelEvent(self, e):
        if self.host:
            self.host.video_wheel(e, self.width())

    def contextMenuEvent(self, e):
        if self.host:
            self.host.video_context_menu(e.globalPos())


class _PlaceholderState:
    message = "Drop a video here"
    sub = "Ctrl+O to open a file  ·  Ctrl+U to open a link"
    show_placeholder = True

    def set_placeholder(self, show: bool, message: str | None = None, sub: str | None = None):
        changed = show != self.show_placeholder
        self.show_placeholder = show
        if message is not None:
            changed = changed or message != self.message
            self.message = message
        if sub is not None:
            changed = changed or sub != self.sub
            self.sub = sub
        if changed:
            self.update()


class NativeVideoWidget(_MouseForwarder, _PlaceholderState, QWidget):
    gl_failed = Signal(str)  # unused, keeps the interface identical

    def __init__(self, host, parent=None):
        QWidget.__init__(self, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._setup_mouse(host)
        self.player = None
        self.has_video = False
        self.frames = 0

    def wid(self) -> int:
        return int(self.winId())

    def attach(self, player) -> None:
        self.player = player

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.player is not None and hasattr(self.player, "window_resized"):
            self.player.window_resized(self.width(), self.height())

    def paintEvent(self, _e):
        # while a video plays, VLC draws into its own child window here; painting
        # over it would cause flicker, so Qt only draws the start/placeholder screen
        if self.has_video and not self.show_placeholder:
            return
        p = QPainter(self)
        paint_placeholder(self, p, self.message, self.sub)
        p.end()

    def free_context(self):
        pass


class NullVideoWidget(NativeVideoWidget):
    """For the self-test: behaves like the native widget without a real window handle."""

    def __init__(self, host, parent=None):
        QWidget.__init__(self, parent)
        self._setup_mouse(host)
        self.player = None
        self.has_video = False
        self.frames = 0
