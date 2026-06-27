from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .hardware_monitor import HardwareMetric, HardwareSnapshot
from .recipe_menu import recipe_font
from . import ui_theme as theme


class HardwareStatusBubble(QWidget):
    def __init__(
        self,
        auto_close_ms: int = 12_000,
        parent: QWidget | None = None,
    ):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setFont(recipe_font())
        self.setFixedWidth(330)
        self.auto_close_ms = auto_close_ms
        self._pet_window: QWidget | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 12)
        self.card = QFrame(self)
        self.card.setObjectName("hardwareCard")
        root.addWidget(self.card)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(92, 54, 48, 58))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(18, 14, 18, 17)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(9)
        self.header_widget = QWidget()
        self.header_widget.setLayout(header)
        title_mark = QFrame(self.header_widget)
        title_mark.setObjectName("hardwareTitleMark")
        title_mark.setFixedSize(4, 17)
        header.addWidget(title_mark)
        self.title_label = QLabel()
        self.title_label.setObjectName("hardwareTitle")
        header.addWidget(self.title_label, 1)
        close_button = QPushButton("×")
        close_button.setObjectName("hardwareClose")
        close_button.setFixedSize(24, 24)
        close_button.clicked.connect(self.hide)
        self.close_button = close_button
        header.addWidget(self.close_button)
        layout.addWidget(self.header_widget)

        self.metric_layout = QVBoxLayout()
        self.metric_layout.setSpacing(6)
        layout.addLayout(self.metric_layout)
        self.commentary_label = QLabel()
        self.commentary_label.setWordWrap(True)
        self.commentary_label.setObjectName("hardwareCommentary")
        layout.addWidget(self.commentary_label)
        self.notes_label = QLabel()
        self.notes_label.setWordWrap(True)
        self.notes_label.setObjectName("hardwareNotes")
        layout.addWidget(self.notes_label)

        self.setStyleSheet(
            f"""
            QWidget {{
                color: {theme.COCOA_TEXT};
            }}
            #hardwareCard {{
                background: {theme.CREAM_PAPER};
                border: 1px solid {theme.PINK_BORDER};
                border-radius: {theme.BUBBLE_RADIUS}px;
            }}
            #speechBubble {{
                background: {theme.CREAM_PAPER};
                border: 1px solid {theme.PINK_BORDER};
                border-radius: {theme.BUBBLE_RADIUS}px;
            }}
            #hardwareTitleMark {{
                background: {theme.LABEL_PINK};
                border-radius: 2px;
            }}
            #hardwareTitle {{
                color: {theme.COCOA_DEEP};
                font-weight: 700;
            }}
            #hardwareClose {{
                color: {theme.LABEL_PINK_DARK};
                background: transparent;
                border: none;
            }}
            #hardwareClose:hover {{
                color: {theme.COCOA_DEEP};
                background: {theme.PETAL_BLUSH};
                border-radius: 12px;
            }}
            #hardwareMetricRow {{
                background: {theme.PAPER_LIGHT};
                border: 1px solid {theme.HAIRLINE_PINK};
                border-radius: 10px;
            }}
            #hardwareMetricLabel {{
                color: {theme.COCOA_TEXT};
            }}
            #hardwareMetricValue {{
                color: {theme.COCOA_DEEP};
                font-weight: 600;
            }}
            #hardwareMetricDetail {{
                color: {theme.MUTED_COCOA};
            }}
            #hardwareCommentary {{
                color: {theme.COCOA_TEXT};
                background: {theme.PETAL_BLUSH};
                border: 1px solid {theme.HAIRLINE_PINK};
                border-radius: 10px;
                padding: 7px 9px;
            }}
            #hardwareNotes {{
                color: {theme.MUTED_COCOA};
            }}
            """
        )

    def show_loading(self, title: str, pet_window: QWidget) -> None:
        self._pet_window = pet_window
        self._timer.stop()
        self.setFixedWidth(330)
        self.card.setObjectName("hardwareCard")
        self._refresh_card_style()
        self.header_widget.show()
        self.title_label.setText(title)
        self._clear_metrics()
        self._add_plain_row("正在检查…")
        self.commentary_label.setText("别催，我正在让它把体检报告交出来。")
        self.notes_label.clear()
        self.adjustSize()
        self.reposition()
        self.show()

    def show_snapshot(
        self,
        title: str,
        snapshot: HardwareSnapshot,
        pet_window: QWidget,
    ) -> None:
        self._pet_window = pet_window
        self.setFixedWidth(330)
        self.card.setObjectName("hardwareCard")
        self._refresh_card_style()
        self.header_widget.show()
        self.title_label.setText(title)
        self._clear_metrics()
        for metric in snapshot.metrics:
            if metric.available:
                self._add_metric(metric)
        if not snapshot.metrics:
            self._add_plain_row("暂无可读取指标")
        self.commentary_label.setText(snapshot.commentary)
        notes = " · ".join(snapshot.unavailable_reasons[:3])
        self.notes_label.setText(notes)
        self.notes_label.setVisible(bool(notes))
        self.adjustSize()
        self.reposition()
        self.show()
        self._timer.start(max(1000, self.auto_close_ms))

    def show_error(
        self,
        title: str,
        message: str,
        pet_window: QWidget,
    ) -> None:
        self._pet_window = pet_window
        self.setFixedWidth(330)
        self.card.setObjectName("hardwareCard")
        self._refresh_card_style()
        self.header_widget.show()
        self.title_label.setText(title)
        self._clear_metrics()
        self._add_plain_row("检查失败")
        self.commentary_label.setText("它拒绝配合体检。很有个性，可惜没有数据。")
        self.notes_label.setText(message)
        self.notes_label.setVisible(True)
        self.adjustSize()
        self.reposition()
        self.show()
        self._timer.start(max(1000, self.auto_close_ms))

    def show_message(
        self,
        message: str,
        pet_window: QWidget,
    ) -> None:
        self._pet_window = pet_window
        self._timer.stop()
        self.setFixedWidth(230)
        self.card.setObjectName("speechBubble")
        self._refresh_card_style()
        self.header_widget.hide()
        self._clear_metrics()
        self.commentary_label.setText(message)
        self.notes_label.clear()
        self.notes_label.setVisible(False)
        self.adjustSize()
        self.reposition()
        self.show()
        self._timer.start(max(1000, self.auto_close_ms))

    def reposition(self) -> None:
        pet = self._pet_window
        if pet is None or not self.isVisible() and self.size().isEmpty():
            return
        pet_rect = pet.frameGeometry()
        screen = QGuiApplication.screenAt(pet_rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        gap = 12
        right_position = QPoint(
            pet_rect.right() + gap,
            pet_rect.top() - self.height() // 3,
        )
        left_position = QPoint(
            pet_rect.left() - self.width() - gap,
            pet_rect.top() - self.height() // 3,
        )
        bottom_position = QPoint(
            pet_rect.center().x() - self.width() // 2,
            pet_rect.bottom() + gap,
        )
        position = (
            right_position
            if right_position.x() + self.width() <= available.right() + 1
            else left_position
            if left_position.x() >= available.left()
            else bottom_position
        )
        x = min(max(position.x(), available.left()), available.right() - self.width() + 1)
        y = min(max(position.y(), available.top()), available.bottom() - self.height() + 1)
        self.move(x, y)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _add_metric(self, metric: HardwareMetric) -> None:
        row_frame = QFrame(self.card)
        row_frame.setObjectName("hardwareMetricRow")
        row = QHBoxLayout(row_frame)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(9)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        label = QLabel(metric.label)
        label.setObjectName("hardwareMetricLabel")
        labels.addWidget(label)
        if metric.detail:
            detail = QLabel(metric.detail)
            detail.setObjectName("hardwareMetricDetail")
            labels.addWidget(detail)
        row.addLayout(labels, 1)
        value = QLabel(metric.display_value)
        value.setObjectName("hardwareMetricValue")
        color = theme.SEVERITY_COLORS.get(metric.severity, theme.COCOA_DEEP)
        value.setStyleSheet(f"color: {color};")
        row.addWidget(value)
        self.metric_layout.addWidget(row_frame)

    def _add_plain_row(self, text: str) -> None:
        row_frame = QFrame(self.card)
        row_frame.setObjectName("hardwareMetricRow")
        row = QHBoxLayout(row_frame)
        row.setContentsMargins(10, 7, 10, 7)
        label = QLabel(text)
        label.setObjectName("hardwareMetricLabel")
        row.addWidget(label)
        self.metric_layout.addWidget(row_frame)

    def _clear_metrics(self) -> None:
        while self.metric_layout.count():
            item = self.metric_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._delete_layout(child_layout)

    def _delete_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            if item.layout() is not None:
                self._delete_layout(item.layout())

    def _refresh_card_style(self) -> None:
        self.card.style().unpolish(self.card)
        self.card.style().polish(self.card)
