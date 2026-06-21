from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class RestoredSettings:
    position: QPoint | None
    scale: float
    looping_state: str
    foreground_follow_enabled: bool
    diagnostic_bubble_timeout_ms: int
    libre_hardware_monitor_url: str


class PetSettings:
    def __init__(self, backend: QSettings | None = None):
        self.backend = backend or QSettings("SpringPet", "Spring")

    def load(
        self,
        *,
        default_scale: float,
        default_state: str,
        persistent_states: set[str],
    ) -> RestoredSettings:
        scale = self._as_float(self.backend.value("scale"), default_scale)
        scale = min(2.5, max(0.5, scale))

        state = str(self.backend.value("looping_state", default_state))
        if state not in persistent_states:
            state = default_state

        position = None
        if self.backend.contains("x") and self.backend.contains("y"):
            position = QPoint(
                self._as_int(self.backend.value("x"), 0),
                self._as_int(self.backend.value("y"), 0),
            )
        follow_enabled = self._as_bool(
            self.backend.value("foreground_follow_enabled"), True
        )
        bubble_timeout_ms = self._as_int(
            self.backend.value("diagnostic_bubble_timeout_ms"),
            12_000,
        )
        bubble_timeout_ms = min(60_000, max(3_000, bubble_timeout_ms))
        libre_url = str(
            self.backend.value(
                "libre_hardware_monitor_url",
                "http://127.0.0.1:8085/data.json",
            )
        ).strip()
        if not libre_url:
            libre_url = "http://127.0.0.1:8085/data.json"
        return RestoredSettings(
            position=position,
            scale=scale,
            looping_state=state,
            foreground_follow_enabled=follow_enabled,
            diagnostic_bubble_timeout_ms=bubble_timeout_ms,
            libre_hardware_monitor_url=libre_url,
        )

    def save_position(self, position: QPoint) -> None:
        self.backend.setValue("x", position.x())
        self.backend.setValue("y", position.y())
        self.backend.sync()

    def save_scale(self, scale: float) -> None:
        self.backend.setValue("scale", scale)
        self.backend.sync()

    def save_looping_state(self, state_name: str) -> None:
        self.backend.setValue("looping_state", state_name)
        self.backend.sync()

    def save_foreground_follow_enabled(self, enabled: bool) -> None:
        self.backend.setValue("foreground_follow_enabled", enabled)
        self.backend.sync()

    def save_diagnostic_bubble_timeout_ms(self, timeout_ms: int) -> None:
        self.backend.setValue("diagnostic_bubble_timeout_ms", timeout_ms)
        self.backend.sync()

    def save_libre_hardware_monitor_url(self, url: str) -> None:
        self.backend.setValue("libre_hardware_monitor_url", url)
        self.backend.sync()

    @staticmethod
    def clamp_position(position: QPoint, width: int, height: int) -> QPoint:
        screens = QGuiApplication.screens()
        if not screens:
            return position

        candidate = QPoint(position)
        for screen in screens:
            available = screen.availableGeometry()
            if available.intersects(QRect(candidate.x(), candidate.y(), width, height)):
                return candidate

        available = QGuiApplication.primaryScreen().availableGeometry()
        x = min(max(position.x(), available.left()), available.right() - width + 1)
        y = min(max(position.y(), available.top()), available.bottom() - height + 1)
        return QPoint(x, y)

    @staticmethod
    def default_position(width: int, height: int, margin: int = 24) -> QPoint:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(0, 0)
        available = screen.availableGeometry()
        return QPoint(
            available.right() - width - margin + 1,
            available.bottom() - height - margin + 1,
        )

    @staticmethod
    def _as_float(value: object, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _as_int(value: object, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _as_bool(value: object, fallback: bool) -> bool:
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "on"}
