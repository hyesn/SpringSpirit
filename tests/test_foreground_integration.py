from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QSettings, Signal
from PySide6.QtWidgets import QApplication

from spring_pet.asset_loader import load_animation_manifest
from spring_pet.autostart import AutostartManager
from spring_pet.foreground_rules import ForegroundRuleStore
from spring_pet.pet_window import PetWindow
from spring_pet.settings import PetSettings


ROOT = Path(__file__).resolve().parents[1]


class FakeMonitor(QObject):
    process_changed = Signal(str)
    available = True

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = False
        self.configuration: tuple[int, int] | None = None

    def start(self) -> bool:
        self.started = True
        return True

    def stop(self) -> None:
        self.stopped = True

    def check_now(self) -> None:
        pass

    def configure(self, debounce_ms: int, reconcile_interval_ms: int) -> None:
        self.configuration = (debounce_ms, reconcile_interval_ms)


def _window(tmp_path) -> tuple[PetWindow, FakeMonitor]:
    QApplication.instance() or QApplication([])
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    persistent = {
        name for name, state in manifest.states.items() if state.is_persistent
    }
    rules = ForegroundRuleStore(persistent, tmp_path / "rules.json")
    rules.load()
    monitor = FakeMonitor()
    settings = PetSettings(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    window = PetWindow(
        manifest,
        settings,
        autostart=AutostartManager(frozen=False),
        foreground_rules=rules,
        foreground_monitor=monitor,
        ambient_interval_provider=lambda: 600_000,
    )
    return window, monitor


def test_foreground_change_during_startup_applies_after_heart(tmp_path) -> None:
    window, monitor = _window(tmp_path)
    monitor.process_changed.emit("Code.exe")
    assert window.controller.state_name == "heart"

    for _ in range(6):
        window.controller._advance()

    assert window.controller.state_name == "running"
    assert window.state_coordinator.base_state == "running"
    window.force_exit_for_session_end()


def test_manual_state_holds_until_different_configured_process(tmp_path) -> None:
    window, monitor = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    monitor.process_changed.emit("Code.exe")
    assert window.controller.state_name == "running"

    window.set_animation_state("waiting")
    monitor.process_changed.emit("CODE.EXE")
    assert window.controller.state_name == "waiting"

    monitor.process_changed.emit("unconfigured.exe")
    assert window.controller.state_name == "waiting"

    monitor.process_changed.emit("msedge.exe")
    assert window.controller.state_name == "noting"
    window.force_exit_for_session_end()


def test_action_and_drag_restore_latest_foreground_base(tmp_path) -> None:
    window, monitor = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    monitor.process_changed.emit("Code.exe")
    window.set_animation_state("jumping")
    monitor.process_changed.emit("msedge.exe")
    assert window.controller.state_name == "jumping"
    for _ in range(5):
        window.controller._advance()
    assert window.controller.state_name == "noting"

    window._begin_drag(QPoint(100, 100))
    window._update_drag(QPoint(104, 100))
    monitor.process_changed.emit("Weixin.exe")
    window._finish_drag()
    assert window.controller.state_name == "waiting"
    window.force_exit_for_session_end()


def test_foreground_menu_text_toggle_and_submenu_content(tmp_path) -> None:
    window, _monitor = _window(tmp_path)
    menu = window.build_context_menu()
    follow_action = next(
        action
        for action in menu.actions()
        if action.objectName() == "menu_foreground_follow"
    )

    assert follow_action.isChecked()
    checked_size = menu.sizeHint()
    checked_geometry = menu.actionGeometry(follow_action)
    assert menu.activate_text_action(follow_action)
    assert not follow_action.isChecked()
    assert not window._foreground_follow_enabled
    rebuilt = window.build_context_menu()
    rebuilt_follow = next(
        action
        for action in rebuilt.actions()
        if action.objectName() == "menu_foreground_follow"
    )
    assert rebuilt.sizeHint() == checked_size
    assert rebuilt.actionGeometry(rebuilt_follow) == checked_geometry
    assert [action.text() for action in follow_action.menu().actions()] == [
        "当前应用：尚未识别",
        "编辑规则",
        "重载规则",
    ]
    window.force_exit_for_session_end()
