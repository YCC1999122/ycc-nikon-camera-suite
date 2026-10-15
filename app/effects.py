"""Visual effects: particle field, animated progress bar, hover-lift buttons,
page fade transitions. All vector-drawn, no external assets.
/ 视觉特效：粒子背景、动态进度条、悬浮按钮、页面淡入转场（纯代码绘制，无外部资源）"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import (QEasingCurve, QPropertyAnimation, Qt, QTimer,
                            QVariantAnimation, QRectF)
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import (QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QProgressBar,
                               QPushButton, QWidget)


class ParticleField(QWidget):
    """Drifting constellation particles, transparent for mouse events.
    / 漂浮星座粒子背景，鼠标事件穿透"""

    def __init__(self, parent=None, count: int = 55, color: QColor | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._color = color or QColor("#2563eb")
        self._pts = [
            [random.random(), random.random(),                       # x, y
             random.uniform(-0.0016, 0.0016), random.uniform(-0.0012, 0.0012),  # vx, vy
             random.uniform(1.5, 3.4)]                               # radius
            for _ in range(count)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def setColor(self, color: QColor) -> None:
        self._color = color

    def _tick(self) -> None:
        for p in self._pts:
            p[0] += p[2]
            p[1] += p[3]
            if p[0] < 0 or p[0] > 1:
                p[2] = -p[2]
            if p[1] < 0 or p[1] > 1:
                p[3] = -p[3]
            p[0] = min(max(p[0], 0.0), 1.0)
            p[1] = min(max(p[1], 0.0), 1.0)
        self.update()

    def paintEvent(self, event) -> None:
        w, h = max(self.width(), 1), max(self.height(), 1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        base = self._color
        # link lines between near particles / 近邻粒子连线
        for i in range(len(self._pts)):
            for j in range(i + 1, len(self._pts)):
                dx = (self._pts[i][0] - self._pts[j][0]) * w
                dy = (self._pts[i][1] - self._pts[j][1]) * h
                dist = math.hypot(dx, dy)
                if dist < 110:
                    alpha = int(52 * (1 - dist / 110))
                    pen = QPen(QColor(base.red(), base.green(), base.blue(), alpha))
                    pen.setWidthF(1.0)
                    painter.setPen(pen)
                    painter.drawLine(self._pts[i][0] * w, self._pts[i][1] * h,
                                     self._pts[j][0] * w, self._pts[j][1] * h)
        # glowing dots / 发光粒子点
        painter.setPen(Qt.NoPen)
        for x, y, _vx, _vy, r in self._pts:
            c = QColor(base.red(), base.green(), base.blue(), 110)
            painter.setBrush(c)
            painter.drawEllipse(int(x * w - r), int(y * h - r), int(r * 2), int(r * 2))
        painter.end()


class AnimatedProgressBar(QProgressBar):
    """Gradient progress bar with sliding highlight stripes and glow.
    / 渐变进度条：滑动高光条纹 + 发光边缘"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._grad_start = QColor("#3b82f6")
        self._grad_end = QColor("#2563eb")
        self._track = QColor("#e2e8f0")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def setColors(self, track: QColor, start: QColor, end: QColor) -> None:
        self._track, self._grad_start, self._grad_end = track, start, end

    def _tick(self) -> None:
        self._phase = (self._phase + 1.6) % 24
        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        radius = rect.height() / 2
        # track / 底槽
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.fillPath(path, self._track)

        total = self.maximum() - self.minimum()
        ratio = (self.value() - self.minimum()) / total if total > 0 else 0.0
        if ratio > 0:
            fill_w = max(rect.width() * ratio, rect.height())
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(rect.x(), rect.y(), fill_w, rect.height()),
                                radius, radius)
            grad = QLinearGradient(rect.x(), rect.y(), rect.x() + fill_w, rect.y())
            grad.setColorAt(0, self._grad_start)
            grad.setColorAt(1, self._grad_end)
            painter.fillPath(fill, grad)
            # sliding highlight stripes / 滑动高光条纹
            painter.setClipPath(fill)
            stripe = QColor(255, 255, 255, 46)
            painter.setPen(QPen(stripe, 6))
            offset = -rect.height() * 2 + self._phase
            x = rect.x() + offset
            while x < rect.x() + fill_w + rect.height():
                painter.drawLine(x, rect.y() + rect.height() + 4,
                                 x + rect.height(), rect.y() - 4)
                x += 24
            painter.setClipping(False)
        painter.end()


class HoverButton(QPushButton):
    """Push button with hover lift animation (shadow grows, slight rise).
    / 悬浮按钮：悬停时阴影加深、轻微上浮"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(12)
        self._shadow.setOffset(0, 3)
        self._shadow.setColor(QColor(37, 99, 235, 70))
        self.setGraphicsEffect(self._shadow)
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v) -> None:
        self._shadow.setBlurRadius(12 + v * 16)
        self._shadow.setOffset(0, 3 + v * 4)
        self._shadow.setColor(QColor(37, 99, 235, int(70 + v * 80)))

    def _animate_to(self, end: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._anim.currentValue() or 0.0)
        self._anim.setEndValue(end)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def enterEvent(self, event) -> None:
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_to(0.0)
        super().leaveEvent(event)


def fade_in(widget: QWidget, duration: int = 380) -> None:
    """Fade a widget in via opacity effect. / 控件淡入（页面转场用）"""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim  # keep ref / 持引用防回收
    anim.start()
