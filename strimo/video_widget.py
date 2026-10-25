"""Video surfaces.

GLVideoWidget  - default. mpv draws into a Qt OpenGL widget (libmpv render API),
                 so mouse, keyboard and overlays all behave like normal Qt widgets.
NativeVideoWidget - compatibility mode. mpv gets its own native child window (wid).
NullVideoWidget  - used by the automated self-test (no video output).
"""

from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QOpenGLContext, QPainter, QPainterPath
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from . import theme
from .player import LOG


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


# ---------------------------------------------------------------------------
def _make_proc_address_getter():
    """Return fn(name: bytes) -> int address of an OpenGL function."""
    if os.name == "nt":
        opengl32 = ctypes.WinDLL("opengl32")
        kernel32 = ctypes.WinDLL("kernel32")
        wgl = opengl32.wglGetProcAddress
        wgl.restype = ctypes.c_void_p
        wgl.argtypes = [ctypes.c_char_p]
        gpa = kernel32.GetProcAddress
        gpa.restype = ctypes.c_void_p
        gpa.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        handle = ctypes.c_void_p(opengl32._handle)

        def get(name: bytes) -> int:
            addr = wgl(name)
            if addr in (None, 0, 1, 2, 3, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
                addr = gpa(handle, name)
            return int(addr or 0)

        return get

    def get_qt(name: bytes) -> int:
        ctx = QOpenGLContext.currentContext()
        if ctx is None:
            return 0
        try:
            addr = ctx.getProcAddress(name)
        except TypeError:
            addr = ctx.getProcAddress(name.decode())
        try:
            return int(addr or 0)
        except TypeError:
            return 0

    return get_qt


class GLVideoWidget(_MouseForwarder, _PlaceholderState, QOpenGLWidget):
    frame_ready = Signal()
    gl_failed = Signal(str)

    def __init__(self, host, parent=None):
        QOpenGLWidget.__init__(self, parent)
        self._setup_mouse(host)
        self.player = None
        self.ctx = None
        self.has_video = False
        self.frames = 0
        self._get_proc = None
        self._proc_cb = None
        self.frame_ready.connect(self._repaint, Qt.ConnectionType.QueuedConnection)
        self._watched_context = None

    def attach(self, player) -> None:
        self.player = player

    def _repaint(self):
        self.update()

    def _proc_address(self, _ctx, name):
        try:
            return self._get_proc(name)
        except Exception:
            return 0

    def initializeGL(self):
        if self.player is None:
            return
        # free mpv's renderer before Qt destroys this GL context (e.g. window re-created)
        try:
            glctx = self.context()
            if glctx is not None and glctx is not self._watched_context:
                glctx.aboutToBeDestroyed.connect(self.free_context)
                self._watched_context = glctx
        except Exception as exc:  # noqa: BLE001
            LOG.write(f"could not watch GL context: {exc}")
        try:
            import mpv

            self._get_proc = _make_proc_address_getter()
            self._proc_cb = mpv.MpvGlGetProcAddressFn(self._proc_address)
            self.ctx = mpv.MpvRenderContext(
                self.player.m, "opengl", opengl_init_params={"get_proc_address": self._proc_cb}
            )
            self.ctx.update_cb = self._on_mpv_update
            LOG.write("OpenGL render context created")
            if self.has_video:
                # context was re-created while a file was open: wake the video track up again
                vid = self.player.get("vid")
                self.player.set("vid", "no")
                self.player.set("vid", vid if vid not in (None, False, "no") else "auto")
        except Exception as exc:  # noqa: BLE001
            self.ctx = None
            LOG.write(f"OpenGL render context failed: {exc}")
            self.gl_failed.emit(str(exc))

    def _on_mpv_update(self):
        # called from an mpv thread
        self.frame_ready.emit()

    def paintGL(self):
        if self.ctx is not None and self.has_video and not self.show_placeholder:
            ratio = self.devicePixelRatioF()
            w = max(1, int(self.width() * ratio))
            h = max(1, int(self.height() * ratio))
            try:
                self.ctx.render(flip_y=True, opengl_fbo={"w": w, "h": h, "fbo": self.defaultFramebufferObject()})
                self.frames += 1
            except Exception as exc:  # noqa: BLE001
                LOG.write(f"render failed: {exc}")
            return
        p = QPainter(self)
        paint_placeholder(self, p, self.message, self.sub)
        p.end()

    def free_context(self):
        if self.ctx is not None:
            try:
                self.makeCurrent()
                self.ctx.free()
            except Exception as exc:  # noqa: BLE001
                LOG.write(f"free render context: {exc}")
            finally:
                self.ctx = None
                try:
                    self.doneCurrent()
                except Exception:  # noqa: BLE001
                    pass


class NativeVideoWidget(_MouseForwarder, _PlaceholderState, QWidget):
    gl_failed = Signal(str)  # unused, keeps the interface identical

    def __init__(self, host, parent=None):
        QWidget.__init__(self, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._setup_mouse(host)
        self.player = None
        self.has_video = False
        self.frames = 0

    def wid(self) -> int:
        return int(self.winId())

    def attach(self, player) -> None:
        self.player = player

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.show_placeholder or not self.has_video:
            paint_placeholder(self, p, self.message, self.sub)
        else:
            p.fillRect(self.rect(), QColor("black"))
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
