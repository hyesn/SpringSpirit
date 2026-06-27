from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .asset_loader import resource_path


class SpeechBubble(QWidget):
    IMAGE_BY_KIND = {
        "focus_break": "violate.png",
        "focus_complete": "focusend.png",
        "cycle_complete": "relaxend.png",
    }
    DISPLAY_WIDTH_BY_KIND = {
        "focus_break": 170,
        "focus_complete": 150,
        "cycle_complete": 150,
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self._pet_window: QWidget | None = None
        self.current_kind: str | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.image_label = QLabel(self)
        self.image_label.setObjectName("speechBubbleImage")
        self.image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.image_label)

    def show_kind(
        self,
        kind: str,
        pet_window: QWidget,
        *,
        duration_ms: int = 5_000,
    ) -> None:
        filename = self.IMAGE_BY_KIND[kind]
        pixmap = QPixmap(str(resource_path("broadcast") / filename))
        if pixmap.isNull():
            return
        self.current_kind = kind
        self._pet_window = pet_window
        self._timer.stop()
        display_width = self.DISPLAY_WIDTH_BY_KIND[kind]
        scaled = pixmap.scaledToWidth(
            display_width,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setFixedSize(scaled.size())
        self.setFixedSize(scaled.size())
        self.reposition()
        self.show()
        self._timer.start(max(1000, duration_ms))

    def hide_now(self) -> None:
        self.current_kind = None
        self._timer.stop()
        self.hide()

    def reposition(self) -> None:
        pet = self._pet_window
        if pet is None:
            return
        pet_rect = pet.frameGeometry()
        screen = QGuiApplication.screenAt(pet_rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        head_target = QPoint(
            pet_rect.left() + round(pet_rect.width() * 0.48),
            pet_rect.top() + round(pet_rect.height() * 0.16),
        )
        tail_offset = QPoint(
            round(self.width() * 0.98),
            round(self.height() * 0.96),
        )
        position = head_target - tail_offset
        x = min(max(position.x(), available.left()), available.right() - self.width() + 1)
        y = min(max(position.y(), available.top()), available.bottom() - self.height() + 1)
        self.move(x, y)
