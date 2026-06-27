from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .recipe_menu import recipe_font
from . import ui_theme as theme


class DisciplineDisplay(QWidget):
    pause_toggled = Signal()
    switch_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setFont(recipe_font())
        self._pet_window: QWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 10)
        card = QFrame(self)
        card.setObjectName("disciplineCard")
        root.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(92, 54, 48, 54))
        card.setGraphicsEffect(shadow)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(9)
        binding = QFrame(card)
        binding.setObjectName("disciplineBinding")
        binding.setFixedWidth(3)
        layout.addWidget(binding)
        text_layout = QGridLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setHorizontalSpacing(8)
        text_layout.setVerticalSpacing(10)
        self.text_layout = text_layout
        self.phase_label = QLabel("专注中")
        self.phase_label.setObjectName("disciplinePhase")
        self.progress_label = QLabel("00:00")
        self.progress_label.setObjectName("disciplineProgress")
        self.switch_button = QPushButton("切换")
        self.switch_button.setObjectName("disciplineSwitch")
        self.switch_button.setFixedSize(38, 22)
        self.switch_button.clicked.connect(self.switch_requested)
        self.pause_button = QPushButton("暂停")
        self.pause_button.setObjectName("disciplinePause")
        self.pause_button.setFixedSize(38, 22)
        self.pause_button.clicked.connect(self.pause_toggled)
        text_layout.addWidget(self.phase_label, 0, 0, Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(self.switch_button, 0, 1, Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(self.progress_label, 1, 0, Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(self.pause_button, 1, 1, Qt.AlignmentFlag.AlignVCenter)
        text_layout.setColumnStretch(0, 1)
        layout.addLayout(text_layout, 1)

        self.setStyleSheet(
            f"""
            QWidget {{
                color: {theme.COCOA_TEXT};
            }}
            #disciplineCard {{
                background: {theme.CREAM_PAPER};
                border: 1px solid {theme.PINK_BORDER};
                border-radius: {theme.BUBBLE_RADIUS}px;
            }}
            #disciplineBinding {{
                background: {theme.LABEL_PINK};
                border-radius: 1px;
            }}
            #disciplinePhase {{
                color: {theme.COCOA_DEEP};
                font-weight: 700;
            }}
            #disciplineProgress {{
                color: {theme.COCOA_TEXT};
            }}
            #disciplinePause, #disciplineSwitch {{
                color: {theme.COCOA_DEEP};
                background: {theme.PETAL_BLUSH};
                border: 1px solid {theme.PINK_BORDER};
                border-radius: {theme.BUTTON_RADIUS}px;
            }}
            #disciplinePause:hover, #disciplineSwitch:hover {{
                background: {theme.PETAL_BLUSH_DEEP};
            }}
            #disciplineSwitch:disabled {{
                color: {theme.MUTED_COCOA};
                background: {theme.CREAM_PAPER};
            }}
            """
        )
        self.setFixedWidth(176)

    def show_for_pet(self, pet_window: QWidget) -> None:
        self._pet_window = pet_window
        self.adjustSize()
        self.reposition()
        self.show()

    def update_status(
        self,
        *,
        phase: str,
        elapsed_ms: int,
        target_ms: int,
        paused: bool,
        cycle_count: int = 0,
    ) -> None:
        if phase == "focus_ready":
            self.phase_label.setText("待继续")
            self.switch_button.setEnabled(False)
            self.pause_button.setText("继续")
            self.progress_label.setText(f"周目 {cycle_count}")
            self.adjustSize()
            self.reposition()
            return
        if paused:
            self.phase_label.setText("暂停中")
            self.pause_button.setText("继续")
        else:
            self.phase_label.setText("专注中" if phase == "focus" else "放松中")
            self.pause_button.setText("暂停")
        self.switch_button.setEnabled(True)
        remaining_ms = max(0, target_ms - elapsed_ms)
        minutes = remaining_ms // 60_000
        seconds = (remaining_ms % 60_000) // 1000
        self.progress_label.setText(f"剩余 {minutes:02}:{seconds:02}")
        self.adjustSize()
        self.reposition()

    def reposition(self) -> None:
        pet = self._pet_window
        if pet is None:
            return
        pet_rect = pet.frameGeometry()
        screen = QGuiApplication.screenAt(pet_rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        gap = 4
        x = pet_rect.center().x() - self.width() // 2
        y = pet_rect.bottom() + gap
        if y + self.height() > available.bottom():
            y = pet_rect.top() - self.height() - gap
        x = min(max(x, available.left()), available.right() - self.width() + 1)
        y = min(max(y, available.top()), available.bottom() - self.height() + 1)
        self.move(QPoint(x, y))
