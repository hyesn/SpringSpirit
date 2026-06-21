from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .hardware_monitor import HardwareMetric, HardwareSnapshot


SEVERITY_COLORS = {
    "normal": "#65D692",
    "busy": "#F1C75B",
    "warning": "#F29A58",
    "critical": "#F26D78",
    "unavailable": "#9BA3B4",
}


class HardwareStatusBubble(QWidget):
    def __init__(
        self,
        auto_close_ms: int = 12_000,
        parent: QWidget | None = None,
    ):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setFixedWidth(330)
        self.auto_close_ms = auto_close_ms
        self._pet_window: QWidget | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.card = QFrame(self)
        self.card.setObjectName("hardwareCard")
        root.addWidget(self.card)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("hardwareTitle")
        header.addWidget(self.title_label, 1)
        close_button = QPushButton("×")
        close_button.setObjectName("hardwareClose")
        close_button.setFixedSize(24, 24)
        close_button.clicked.connect(self.hide)
        header.addWidget(close_button)
        layout.addLayout(header)

        self.metric_layout = QVBoxLayout()
        self.metric_layout.setSpacing(5)
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
            """
            QWidget {
                font-family: "Microsoft YaHei UI", "Segoe UI";
            }
            #hardwareCard {
                background: rgba(26, 29, 38, 242);
                border: 1px solid rgba(255, 255, 255, 42);
                border-radius: 16px;
            }
            #hardwareTitle {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: 700;
            }
            #hardwareClose {
                color: #D9DCE5;
                background: transparent;
                border: none;
                font-size: 18px;
            }
            #hardwareClose:hover {
                color: #FFFFFF;
                background: rgba(255, 255, 255, 24);
                border-radius: 12px;
            }
            #hardwareMetricLabel {
                color: #BFC5D2;
                font-size: 12px;
            }
            #hardwareMetricValue {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
            }
            #hardwareMetricDetail {
                color: #8F97A8;
                font-size: 10px;
            }
            #hardwareCommentary {
                color: #F4C2D7;
                font-size: 12px;
                padding-top: 5px;
            }
            #hardwareNotes {
                color: #848C9D;
                font-size: 10px;
            }
            """
        )

    def show_loading(self, title: str, pet_window: QWidget) -> None:
        self._pet_window = pet_window
        self._timer.stop()
        self.title_label.setText(title)
        self._clear_metrics()
        loading = QLabel("正在检查…")
        loading.setObjectName("hardwareMetricLabel")
        self.metric_layout.addWidget(loading)
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
        self.title_label.setText(title)
        self._clear_metrics()
        for metric in snapshot.metrics:
            if metric.available:
                self._add_metric(metric)
        if not snapshot.metrics:
            unavailable = QLabel("No readable metrics")
            unavailable.setObjectName("hardwareMetricLabel")
            self.metric_layout.addWidget(unavailable)
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
        self.title_label.setText(title)
        self._clear_metrics()
        error = QLabel("Hardware inspection failed")
        error.setObjectName("hardwareMetricLabel")
        self.metric_layout.addWidget(error)
        self.commentary_label.setText("它拒绝配合体检。很有个性，可惜没有数据。")
        self.notes_label.setText(message)
        self.notes_label.setVisible(True)
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
        left_position = QPoint(
            pet_rect.left() - self.width() - gap,
            pet_rect.center().y() - self.height() // 2,
        )
        right_position = QPoint(
            pet_rect.right() + gap,
            pet_rect.center().y() - self.height() // 2,
        )
        position = (
            left_position
            if left_position.x() >= available.left()
            else right_position
        )
        x = min(max(position.x(), available.left()), available.right() - self.width() + 1)
        y = min(max(position.y(), available.top()), available.bottom() - self.height() + 1)
        self.move(x, y)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _add_metric(self, metric: HardwareMetric) -> None:
        row = QHBoxLayout()
        labels = QVBoxLayout()
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
        color = SEVERITY_COLORS.get(metric.severity, "#FFFFFF")
        value.setStyleSheet(f"color: {color};")
        row.addWidget(value)
        self.metric_layout.addLayout(row)

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
