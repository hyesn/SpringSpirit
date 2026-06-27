from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

from spring_pet.asset_loader import load_animation_manifest
from spring_pet.autostart import AutostartManager
from spring_pet.hardware_monitor import HardwareMetric, HardwareSnapshot
from spring_pet.pet_window import PetWindow
from spring_pet.recipe_menu import recipe_font
from spring_pet.settings import PetSettings


ROOT = Path(__file__).resolve().parents[1]


class FakeHardwareService(QObject):
    snapshot_ready = Signal(object)
    collection_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.busy = False
        self.requests: list[str] = []
        self.cancel_count = 0
        self.shutdown_count = 0

    def request(self, kind: str) -> None:
        self.busy = True
        self.requests.append(kind)

    def cancel(self) -> None:
        self.busy = False
        self.cancel_count += 1

    def shutdown(self) -> None:
        self.shutdown_count += 1
        self.cancel()


def _window(tmp_path) -> tuple[PetWindow, FakeHardwareService]:
    QApplication.instance() or QApplication([])
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    service = FakeHardwareService()
    settings = PetSettings(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    window = PetWindow(
        manifest,
        settings,
        autostart=AutostartManager(frozen=False),
        hardware_monitor_service=service,
        ambient_interval_provider=lambda: 600_000,
    )
    for _ in range(6):
        window.controller._advance()
    return window, service


def test_hardware_menu_and_overview_animation(tmp_path) -> None:
    window, service = _window(tmp_path)
    menu = window.build_context_menu()
    hardware_action = next(
        action
        for action in menu.actions()
        if action.objectName() == "menu_computer_awareness"
    )
    assert [action.text() for action in hardware_action.menu().actions()] == [
        "系统概览",
        "硬件体征",
    ]

    window.request_hardware_diagnostic("overview")

    assert service.requests == ["overview"]
    assert window.controller.state_name == "inspect"
    assert window.state_coordinator.mode == "diagnostic"
    assert window.hardware_bubble.isVisible()
    assert window.hardware_bubble.font().family() == recipe_font().family()
    assert window.hardware_bubble.card.objectName() == "hardwareCard"
    assert window.hardware_bubble.header_widget.isVisible()
    busy_menu = window.build_context_menu()
    busy_hardware = next(
        action
        for action in busy_menu.actions()
        if action.objectName() == "menu_computer_awareness"
    ).menu()
    assert not any(action.isEnabled() for action in busy_hardware.actions())
    window.force_exit_for_session_end()


def test_snapshot_updates_bubble_and_animation_returns_to_base(tmp_path) -> None:
    window, service = _window(tmp_path)
    window.set_animation_state("waiting")
    window.request_hardware_diagnostic("vitals")
    snapshot = HardwareSnapshot(
        kind="vitals",
        collected_at=datetime.now(),
        metrics=(
            HardwareMetric(
                "gpu_temperature",
                "GPU temperature",
                62,
                " °C",
                "test",
                True,
                "normal",
            ),
        ),
        unavailable_reasons=("Fan speed is unavailable.",),
        overall_severity="normal",
        commentary="状态挺稳。",
    )
    service.busy = False
    service.snapshot_ready.emit(snapshot)
    QApplication.processEvents()
    assert window.hardware_bubble.commentary_label.text() == "状态挺稳。"
    assert window.hardware_bubble.card.objectName() == "hardwareCard"
    assert window.hardware_bubble.title_label.styleSheet() == ""

    for _ in range(6):
        window.controller._advance()
    assert window.controller.state_name == "waiting"
    window.force_exit_for_session_end()


def test_drag_cancels_diagnostic_and_closes_bubble(tmp_path) -> None:
    window, service = _window(tmp_path)
    window.request_hardware_diagnostic("overview")
    cancel_before = service.cancel_count

    window._begin_drag(window.pos())

    assert service.cancel_count == cancel_before + 1
    assert not window.hardware_bubble.isVisible()
    window.force_exit_for_session_end()
