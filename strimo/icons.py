"""Vector icons drawn with QPainter, so Strimo needs no icon files or fonts."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

FG = "#E7EAF0"
DISABLED = "#5d6472"
_SIZE = 64
_cache: dict = {}


def _pen(color, width=5.0):
    p = QPen(QColor(color))
    p.setWidthF(width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _draw(name: str, p: QPainter, c: str) -> None:  # noqa: C901 - one branch per icon
    fill = QColor(c)
    p.setPen(_pen(c))
    p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "play":
        p.setPen(_pen(c, 3))
        p.setBrush(fill)
        p.drawPolygon(_poly((20, 12), (52, 32), (20, 52)))
    elif name == "pause":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(16, 12, 11, 40), 3, 3)
        p.drawRoundedRect(QRectF(37, 12, 11, 40), 3, 3)
    elif name == "stop":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(15, 15, 34, 34), 4, 4)
    elif name in ("prev", "next"):
        p.setPen(_pen(c, 3))
        p.setBrush(fill)
        if name == "next":
            p.drawPolygon(_poly((14, 14), (40, 32), (14, 50)))
            p.drawRoundedRect(QRectF(44, 14, 6, 36), 2, 2)
        else:
            p.drawPolygon(_poly((50, 14), (24, 32), (50, 50)))
            p.drawRoundedRect(QRectF(14, 14, 6, 36), 2, 2)
    elif name in ("volume", "volume_low", "mute"):
        p.setPen(_pen(c, 3))
        p.setBrush(fill)
        p.drawPolygon(_poly((8, 24), (20, 24), (34, 12), (34, 52), (20, 40), (8, 40)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(c, 4.5))
        if name == "mute":
            p.drawLine(QPointF(42, 24), QPointF(56, 40))
            p.drawLine(QPointF(56, 24), QPointF(42, 40))
        else:
            p.drawArc(QRectF(30, 22, 16, 20), -50 * 16, 100 * 16)
            if name == "volume":
                p.drawArc(QRectF(28, 13, 28, 38), -50 * 16, 100 * 16)
    elif name in ("rotate", "rotate_ccw"):
        p.setPen(_pen(c, 5))
        p.drawArc(QRectF(13, 13, 38, 38), 100 * 16, 270 * 16 if name == "rotate" else -270 * 16)
        p.setPen(_pen(c, 3))
        p.setBrush(fill)
        if name == "rotate":
            p.drawPolygon(_poly((26, 4), (38, 13), (26, 21)))
        else:
            p.drawPolygon(_poly((38, 4), (26, 13), (38, 21)))
    elif name == "fullscreen":
        p.setPen(_pen(c, 5))
        for (x, y, dx, dy) in ((12, 12, 1, 1), (52, 12, -1, 1), (12, 52, 1, -1), (52, 52, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 13 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 13 * dy))
    elif name == "fullscreen_exit":
        p.setPen(_pen(c, 5))
        for (x, y, dx, dy) in ((26, 26, -1, -1), (38, 26, 1, -1), (26, 38, -1, 1), (38, 38, 1, 1)):
            p.drawLine(QPointF(x, y), QPointF(x + 13 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 13 * dy))
    elif name == "speed":
        p.setPen(_pen(c, 5))
        p.drawArc(QRectF(8, 14, 48, 48), 0, 180 * 16)
        p.setPen(_pen(c, 4))
        p.drawLine(QPointF(32, 38), QPointF(46, 24))
        p.setBrush(fill)
        p.drawEllipse(QPointF(32, 38), 4, 4)
    elif name == "loop":
        p.setPen(_pen(c, 5))
        p.drawLine(QPointF(14, 20), QPointF(50, 20))
        p.drawLine(QPointF(14, 44), QPointF(50, 44))
        p.setPen(_pen(c, 4))
        p.drawLine(QPointF(14, 12), QPointF(14, 52))
        p.drawLine(QPointF(50, 12), QPointF(50, 52))
        f = p.font()
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(14, 20, 36, 24), int(Qt.AlignmentFlag.AlignCenter.value), "AB")
    elif name == "camera":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(8, 18, 48, 34), 6, 6)
        p.drawLine(QPointF(22, 18), QPointF(26, 11))
        p.drawLine(QPointF(26, 11), QPointF(38, 11))
        p.drawLine(QPointF(38, 11), QPointF(42, 18))
        p.drawEllipse(QPointF(32, 35), 9, 9)
    elif name == "panel":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(8, 12, 48, 40), 5, 5)
        p.drawLine(QPointF(38, 12), QPointF(38, 52))
        p.drawLine(QPointF(43, 22), QPointF(51, 22))
        p.drawLine(QPointF(43, 30), QPointF(51, 30))
        p.drawLine(QPointF(43, 38), QPointF(51, 38))
    elif name == "link":
        p.setPen(_pen(c, 5))
        p.translate(32, 32)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-26, -8, 26, 16), 8, 8)
        p.drawRoundedRect(QRectF(0, -8, 26, 16), 8, 8)
        p.resetTransform()
    elif name == "download":
        p.setPen(_pen(c, 5))
        p.drawLine(QPointF(32, 8), QPointF(32, 40))
        p.drawLine(QPointF(19, 28), QPointF(32, 41))
        p.drawLine(QPointF(45, 28), QPointF(32, 41))
        p.drawLine(QPointF(12, 46), QPointF(12, 54))
        p.drawLine(QPointF(12, 54), QPointF(52, 54))
        p.drawLine(QPointF(52, 54), QPointF(52, 46))
    elif name == "folder":
        p.setPen(_pen(c, 4.5))
        path = QPainterPath()
        path.moveTo(8, 50)
        path.lineTo(8, 14)
        path.lineTo(26, 14)
        path.lineTo(31, 20)
        path.lineTo(56, 20)
        path.lineTo(56, 50)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "file":
        p.setPen(_pen(c, 4.5))
        path = QPainterPath()
        path.moveTo(16, 8)
        path.lineTo(38, 8)
        path.lineTo(50, 20)
        path.lineTo(50, 56)
        path.lineTo(16, 56)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(fill)
        p.drawPolygon(_poly((26, 26), (42, 36), (26, 46)))
    elif name == "gear":
        p.setPen(_pen(c, 4.5))
        p.drawEllipse(QPointF(32, 32), 8, 8)
        p.drawEllipse(QPointF(32, 32), 18, 18)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(32 + 18 * math.cos(a), 32 + 18 * math.sin(a)),
                       QPointF(32 + 25 * math.cos(a), 32 + 25 * math.sin(a)))
    elif name == "bookmark":
        p.setPen(_pen(c, 4.5))
        p.drawPolygon(_poly((18, 8), (46, 8), (46, 56), (32, 44), (18, 56)))
    elif name == "note":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(12, 8, 40, 48), 5, 5)
        for y in (22, 32, 42):
            p.drawLine(QPointF(20, y), QPointF(44, y))
    elif name == "info":
        p.setPen(_pen(c, 4.5))
        p.drawEllipse(QPointF(32, 32), 23, 23)
        p.drawLine(QPointF(32, 29), QPointF(32, 45))
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(32, 20), 3.5, 3.5)
    elif name == "mini":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(6, 12, 52, 40), 5, 5)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(32, 32, 20, 14), 2, 2)
    elif name == "list":
        p.setPen(_pen(c, 5))
        for y in (18, 32, 46):
            p.drawLine(QPointF(24, y), QPointF(54, y))
            p.drawPoint(QPointF(12, y))
    elif name == "shuffle":
        p.setPen(_pen(c, 4.5))
        p.drawLine(QPointF(8, 18), QPointF(20, 18))
        p.drawLine(QPointF(20, 18), QPointF(40, 46))
        p.drawLine(QPointF(40, 46), QPointF(54, 46))
        p.drawLine(QPointF(8, 46), QPointF(20, 46))
        p.drawLine(QPointF(20, 46), QPointF(40, 18))
        p.drawLine(QPointF(40, 18), QPointF(54, 18))
        p.drawLine(QPointF(48, 12), QPointF(54, 18))
        p.drawLine(QPointF(48, 24), QPointF(54, 18))
        p.drawLine(QPointF(48, 40), QPointF(54, 46))
        p.drawLine(QPointF(48, 52), QPointF(54, 46))
    elif name == "repeat":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(10, 18, 44, 28), 10, 10)
        p.setBrush(fill)
        p.drawPolygon(_poly((30, 11), (40, 18), (30, 25)))
    elif name == "plus":
        p.setPen(_pen(c, 5))
        p.drawLine(QPointF(32, 12), QPointF(32, 52))
        p.drawLine(QPointF(12, 32), QPointF(52, 32))
    elif name in ("close", "x"):
        p.setPen(_pen(c, 5))
        p.drawLine(QPointF(16, 16), QPointF(48, 48))
        p.drawLine(QPointF(48, 16), QPointF(16, 48))
    elif name == "trash":
        p.setPen(_pen(c, 4.5))
        p.drawLine(QPointF(10, 16), QPointF(54, 16))
        p.drawLine(QPointF(25, 16), QPointF(27, 9))
        p.drawLine(QPointF(27, 9), QPointF(37, 9))
        p.drawLine(QPointF(37, 9), QPointF(39, 16))
        path = QPainterPath()
        path.moveTo(16, 16)
        path.lineTo(19, 56)
        path.lineTo(45, 56)
        path.lineTo(48, 16)
        p.drawPath(path)
    elif name == "moon":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        outer = QPainterPath()
        outer.addEllipse(QPointF(30, 34), 22, 22)
        inner = QPainterPath()
        inner.addEllipse(QPointF(42, 24), 18, 18)
        p.drawPath(outer.subtracted(inner))
    elif name == "pin":
        p.setPen(_pen(c, 4.5))
        p.drawLine(QPointF(32, 40), QPointF(32, 58))
        p.drawRoundedRect(QRectF(20, 8, 24, 10), 3, 3)
        p.drawPolygon(_poly((24, 18), (40, 18), (46, 40), (18, 40)))
    elif name == "frame":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(8, 12, 48, 40), 4, 4)
        p.setBrush(fill)
        p.drawPolygon(_poly((24, 22), (40, 32), (24, 42)))
    elif name == "sub":
        p.setPen(_pen(c, 4.5))
        p.drawRoundedRect(QRectF(6, 12, 52, 40), 6, 6)
        p.drawLine(QPointF(14, 34), QPointF(28, 34))
        p.drawLine(QPointF(34, 34), QPointF(50, 34))
        p.drawLine(QPointF(14, 43), QPointF(40, 43))
    elif name == "resume":
        p.setPen(_pen(c, 3))
        p.setBrush(fill)
        p.drawPolygon(_poly((22, 14), (48, 32), (22, 50)))
    elif name == "sliders":
        p.setPen(_pen(c, 4.5))
        for x, knob in ((16, 40), (32, 22), (48, 34)):
            p.drawLine(QPointF(x, 10), QPointF(x, 54))
            p.setBrush(fill)
            p.drawEllipse(QPointF(x, knob), 5, 5)
            p.setBrush(Qt.BrushStyle.NoBrush)
    else:
        p.drawEllipse(QPointF(32, 32), 20, 20)


def pixmap(name: str, color: str = FG, size: int = _SIZE) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if size != _SIZE:
        p.scale(size / _SIZE, size / _SIZE)
    _draw(name, p, color)
    p.end()
    return pm


def icon(name: str, color: str = FG) -> QIcon:
    key = (name, color)
    if key not in _cache:
        ic = QIcon()
        for size in (32, 64):
            ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
            ic.addPixmap(pixmap(name, DISABLED, size), QIcon.Mode.Disabled)
        _cache[key] = ic
    return _cache[key]
