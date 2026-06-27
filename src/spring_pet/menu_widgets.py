from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from .recipe_menu import recipe_font
from . import ui_theme as theme


class SnapScaleSlider(QWidget):
    def __init__(
        self,
        values: tuple[float, ...],
        current: float,
        on_changed: Callable[[float], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.values = values
        self.on_changed = on_changed
        self._index = self._nearest_index(current)
        self.setFixedSize(154, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    @property
    def value(self) -> float:
        return self.values[self._index]

    def set_value(self, value: float) -> None:
        index = self._nearest_index(value)
        if index == self._index:
            return
        self._index = index
        self.update()
        self.on_changed(self.value)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track_left = 9
        track_right = self.width() - 9
        track_y = self.height() // 2
        step = (track_right - track_left) / (len(self.values) - 1)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.SOFT_PINK))
        painter.drawRoundedRect(
            QRectF(track_left, track_y - 2.0, track_right - track_left, 4),
            2,
            2,
        )
        painter.setBrush(QColor(theme.LABEL_PINK))
        knob_x = track_left + step * self._index
        painter.drawRoundedRect(
            QRectF(track_left, track_y - 2.0, knob_x - track_left, 4),
            2,
            2,
        )

        painter.setPen(QPen(QColor(theme.PINK_BORDER), 1.0))
        painter.setBrush(QColor(theme.PAPER_LIGHT))
        for index in range(len(self.values)):
            x = track_left + step * index
            radius = 2.25 if index == self._index else 1.7
            painter.drawEllipse(QPointF(x, track_y), radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.LABEL_PINK))
        painter.drawEllipse(QPointF(knob_x, track_y), 6.4, 6.4)
        painter.setBrush(QColor(theme.CREAM_PAPER))
        painter.drawEllipse(QPointF(knob_x, track_y), 2.2, 2.2)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._update_from_x(event.position().x())
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_x(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._update_from_x(event.position().x())
        event.accept()

    def _update_from_x(self, x: float) -> None:
        track_left = 9
        track_right = self.width() - 9
        ratio = min(1.0, max(0.0, (x - track_left) / (track_right - track_left)))
        index = round(ratio * (len(self.values) - 1))
        self.set_value(self.values[index])

    def _nearest_index(self, value: float) -> int:
        return min(
            range(len(self.values)),
            key=lambda index: abs(self.values[index] - value),
        )


class ScaleSliderPanel(QWidget):
    GEAR_LABELS = ("Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ")

    def __init__(
        self,
        values: tuple[float, ...],
        current: float,
        on_changed: Callable[[float], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("scaleSliderPanel")
        self.setFont(recipe_font())
        self.setFixedSize(210, 32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 10, 4)
        layout.setSpacing(10)

        self._external_on_changed = on_changed
        self.slider = SnapScaleSlider(values, current, self._on_slider_changed, self)
        layout.addWidget(self.slider, 1)

        self.gear_label = QLabel(self._gear_text(), self)
        self.gear_label.setObjectName("scaleGearLabel")
        gear_font = recipe_font()
        gear_font.setPointSizeF(10.0)
        gear_font.setWeight(QFont.Weight.Medium)
        self.gear_label.setFont(gear_font)
        self.gear_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gear_label.setFixedWidth(24)
        layout.addWidget(self.gear_label)
        self.setStyleSheet(
            f"""
            #scaleSliderPanel {{
                background: transparent;
                color: {theme.COCOA_TEXT};
            }}
            #scaleGearLabel {{
                color: {theme.COCOA_TEXT};
            }}
            """
        )

    def _on_slider_changed(self, value: float) -> None:
        self.gear_label.setText(self._gear_text())
        self._external_on_changed(value)

    def _gear_text(self) -> str:
        return self.GEAR_LABELS[self.slider._index]

    def sizeHint(self) -> QSize:
        return QSize(210, 32)
