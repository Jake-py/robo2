"""Custom Qt widgets used by the control center."""

import math

from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QConicalGradient, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .theme import C


class RadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self._objects = []
        self._sweep = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def update_objects(self, detections, frame_w=640, frame_h=480):
        objs = []
        for detection in detections:
            box = detection.get("box", [0, 0, 0, 0])
            cx = (box[0] + box[2]) / 2 / frame_w
            cy = (box[1] + box[3]) / 2 / frame_h
            angle = (cx - 0.5) * 160
            dist = 1.0 - cy
            objs.append((angle, dist, detection.get("class_name", "?")))
        self._objects = objs

    def _tick(self):
        self._sweep = (self._sweep + 2.0) % 360.0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 8

        painter.fillRect(0, 0, width, height, QColor(C["void"]))

        pen = QPen(QColor(C["border"]))
        pen.setWidth(1)
        painter.setPen(pen)
        for i in range(1, 5):
            rr = radius * i / 4
            painter.drawEllipse(QPointF(cx, cy), rr, rr)

        painter.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))
        painter.drawLine(QPointF(cx, cy - radius), QPointF(cx, cy + radius))

        sweep_rad = math.radians(-self._sweep)
        grad = QConicalGradient(QPointF(cx, cy), -self._sweep)
        grad.setColorAt(0.0, QColor(0, 229, 255, 90))
        grad.setColorAt(0.12, QColor(0, 229, 255, 0))
        grad.setColorAt(1.0, QColor(0, 229, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        lx = cx + radius * math.cos(sweep_rad)
        ly = cy - radius * math.sin(sweep_rad)
        painter.setPen(QPen(QColor(C["cyan"]), 1))
        painter.drawLine(QPointF(cx, cy), QPointF(lx, ly))

        for angle, dist, label in self._objects:
            a_rad = math.radians(90 - angle)
            ox = cx + radius * dist * math.cos(a_rad)
            oy = cy - radius * dist * math.sin(a_rad)
            painter.setBrush(QBrush(QColor(C["green"])))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(ox, oy), 5, 5)
            glow = QColor(C["green"])
            glow.setAlpha(40)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(ox, oy), 11, 11)
            painter.setPen(QPen(QColor(C["green"])))
            painter.setFont(QFont("Courier New", 7))
            painter.drawText(QPointF(ox + 7, oy - 3), label[:8])

        painter.setBrush(QBrush(QColor(C["cyan"])))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 4, 4)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(C["cyan_dim"]), 1))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.end()


class Led(QWidget):
    def __init__(self, size=10, parent=None):
        super().__init__(parent)
        self.setFixedSize(size + 6, size + 6)
        self._sz = size
        self._color = C["text3"]
        self._blink = False
        self._state = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tog)
        self._timer.start(500)

    def set(self, color, blink=False):
        self._color = color
        self._blink = blink
        self.update()

    def _tog(self):
        self._state = not self._state
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = (self.width() - self._sz) // 2
        y = (self.height() - self._sz) // 2
        show = self._state if self._blink else True
        color = QColor(self._color if show else C["deep"])
        if show and self._color != C["text3"]:
            glow = QColor(self._color)
            glow.setAlpha(35)
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x - 4, y - 4, self._sz + 8, self._sz + 8)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x, y, self._sz, self._sz)
        painter.end()
