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
    discipline_enabled: bool
    discipline_paused: bool
    discipline_focus_minutes: int
    discipline_relax_minutes: int
    discipline_phase: str
    discipline_focus_elapsed_ms: int
    discipline_relax_elapsed_ms: int
    discipline_cycle_count: int
    edge_snap_enabled: bool
    edge_snap_horizontal: str
    edge_snap_vertical: str


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
        scale = min(2.5, max(0.25, scale))

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
        focus_minutes = min(
            180,
            max(1, self._as_int(self.backend.value("discipline_focus_minutes"), 45)),
        )
        relax_minutes = min(
            60,
            max(1, self._as_int(self.backend.value("discipline_relax_minutes"), 8)),
        )
        phase = str(self.backend.value("discipline_phase", "focus"))
        if phase not in {"focus", "relax", "focus_ready"}:
            phase = "focus"
        horizontal = str(self.backend.value("edge_snap_horizontal", ""))
        if horizontal not in {"", "left", "right"}:
            horizontal = ""
        vertical = str(self.backend.value("edge_snap_vertical", ""))
        if vertical not in {"", "top", "bottom"}:
            vertical = ""
        return RestoredSettings(
            position=position,
            scale=scale,
            looping_state=state,
            foreground_follow_enabled=follow_enabled,
            diagnostic_bubble_timeout_ms=bubble_timeout_ms,
            libre_hardware_monitor_url=libre_url,
            discipline_enabled=self._as_bool(
                self.backend.value("discipline_enabled"), False
            ),
            discipline_paused=self._as_bool(
                self.backend.value("discipline_paused"), False
            ),
            discipline_focus_minutes=focus_minutes,
            discipline_relax_minutes=relax_minutes,
            discipline_phase=phase,
            discipline_focus_elapsed_ms=max(
                0,
                self._as_int(self.backend.value("discipline_focus_elapsed_ms"), 0),
            ),
            discipline_relax_elapsed_ms=max(
                0,
                self._as_int(self.backend.value("discipline_relax_elapsed_ms"), 0),
            ),
            discipline_cycle_count=max(
                0,
                self._as_int(self.backend.value("discipline_cycle_count"), 0),
            ),
            edge_snap_enabled=self._as_bool(
                self.backend.value("edge_snap_enabled"), True
            ),
            edge_snap_horizontal=horizontal,
            edge_snap_vertical=vertical,
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

    def save_discipline_enabled(self, enabled: bool) -> None:
        self.backend.setValue("discipline_enabled", enabled)
        self.backend.sync()

    def save_discipline_paused(self, paused: bool) -> None:
        self.backend.setValue("discipline_paused", paused)
        self.backend.sync()

    def save_discipline_config(self, focus_minutes: int, relax_minutes: int) -> None:
        self.backend.setValue("discipline_focus_minutes", focus_minutes)
        self.backend.setValue("discipline_relax_minutes", relax_minutes)
        self.backend.sync()

    def save_discipline_progress(
        self,
        *,
        phase: str,
        focus_elapsed_ms: int,
        relax_elapsed_ms: int,
        cycle_count: int = 0,
    ) -> None:
        self.backend.setValue("discipline_phase", phase)
        self.backend.setValue("discipline_focus_elapsed_ms", focus_elapsed_ms)
        self.backend.setValue("discipline_relax_elapsed_ms", relax_elapsed_ms)
        self.backend.setValue("discipline_cycle_count", max(0, int(cycle_count)))
        self.backend.sync()

    def clear_discipline_progress(self) -> None:
        self.backend.setValue("discipline_phase", "focus")
        self.backend.setValue("discipline_focus_elapsed_ms", 0)
        self.backend.setValue("discipline_relax_elapsed_ms", 0)
        self.backend.setValue("discipline_cycle_count", 0)
        self.backend.sync()

    def save_edge_snap(
        self,
        *,
        enabled: bool,
        horizontal: str,
        vertical: str,
    ) -> None:
        self.backend.setValue("edge_snap_enabled", enabled)
        self.backend.setValue("edge_snap_horizontal", horizontal)
        self.backend.setValue("edge_snap_vertical", vertical)
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
