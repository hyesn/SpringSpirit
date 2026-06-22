from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtWidgets import QApplication

from spring_pet.asset_loader import load_animation_manifest
from spring_pet.autostart import AutostartManager
from spring_pet.pet_window import PetWindow
from spring_pet.recipe_menu import RecipeMenu
from spring_pet.settings import PetSettings


ROOT = Path(__file__).resolve().parents[1]


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(tmp_path) -> PetWindow:
    _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    settings = PetSettings(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    return PetWindow(
        manifest,
        settings,
        autostart=AutostartManager(frozen=False),
        ambient_interval_provider=lambda: 600_000,
    )


def test_menu_hides_system_states_and_groups_user_states(tmp_path) -> None:
    window = _window(tmp_path)
    menu = window.build_context_menu()
    texts = [action.text() for action in menu.actions()]
    assert isinstance(menu, RecipeMenu)
    assert texts == [
        "状态",
        "动作",
        "缩放",
        "电脑感知",
        "应用跟随",
        "开机自启动",
        "退出",
    ]

    actions = {action.objectName(): action for action in menu.actions()}
    assert set(actions) == {
        "menu_states",
        "menu_actions",
        "menu_scale",
        "menu_computer_awareness",
        "menu_foreground_follow",
        "menu_autostart",
        "menu_exit",
    }
    state_menu = actions["menu_states"].menu()
    action_menu = actions["menu_actions"].menu()
    assert [action.text() for action in state_menu.actions()] == [
        "待机",
        "喝奶茶",
        "工作中",
        "照镜子",
        "打瞌睡",
        "听音乐",
        "记笔记",
    ]
    assert [action.text() for action in action_menu.actions()] == [
        "跳跃",
        "闹别扭",
    ]
    assert "向左跑" not in repr(texts)
    assert "向右跑" not in repr(texts)
    assert "挥手" not in repr(texts)
    foreground_menu = actions["menu_foreground_follow"].menu()
    assert [action.text() for action in foreground_menu.actions()] == [
        "当前应用：尚未识别",
        "编辑规则",
        "重载规则",
    ]
    assert not actions["menu_autostart"].isEnabled()
    window.force_exit_for_session_end()


def test_drag_switches_direction_and_restores_persistent_state(tmp_path) -> None:
    window = _window(tmp_path)
    window.controller.set_state("waiting")
    window._begin_drag(QPoint(100, 100))
    window._update_drag(QPoint(103, 130))
    assert window.controller.state_name == "waiting"
    window._update_drag(QPoint(104, 130))
    assert window.controller.state_name == "running-right"
    window._update_drag(QPoint(100, 130))
    assert window.controller.state_name == "running-left"
    window._finish_drag()
    assert window.controller.state_name == "waiting"
    window.force_exit_for_session_end()


def test_drag_cancels_interrupted_action_to_idle(tmp_path) -> None:
    window = _window(tmp_path)
    window.controller.set_state("jumping")
    window._begin_drag(QPoint(100, 100))
    window._update_drag(QPoint(104, 100))
    window._finish_drag()
    assert window.controller.state_name == "idle"
    window.force_exit_for_session_end()


def test_exit_plays_farewell_once_and_disables_interaction(tmp_path) -> None:
    window = _window(tmp_path)
    window.request_exit()
    window.request_exit()
    assert window.controller.state_name == "waving"
    assert not window._interaction_enabled
    for _ in range(4):
        window.controller._advance()
    assert window._allow_close


def test_scale_presets_and_wheel_range_are_declared(tmp_path) -> None:
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    assert window.SCALE_PRESETS == (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5)
    window.set_scale(2.0)
    assert window.scale == 2.0
    menu = window.build_context_menu()
    scale_action = next(
        action
        for action in menu.actions()
        if action.objectName() == "menu_scale"
    )
    scale_menu = scale_action.menu()
    checked = [action.text() for action in scale_menu.actions() if action.isChecked()]
    assert checked == ["200%"]
    window.force_exit_for_session_end()


def test_startup_heart_resumes_saved_persistent_state(tmp_path) -> None:
    app = _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    backend = QSettings(
        str(tmp_path / "startup.ini"), QSettings.Format.IniFormat
    )
    backend.setValue("looping_state", "sleeping")
    window = PetWindow(
        manifest,
        PetSettings(backend),
        autostart=AutostartManager(frozen=False),
        ambient_interval_provider=lambda: 600_000,
    )
    assert window.controller.state_name == "heart"
    assert not window._interaction_enabled
    for _ in range(6):
        window.controller._advance()
    app.processEvents()
    assert window.controller.state_name == "sleeping"
    assert window._interaction_enabled
    window.force_exit_for_session_end()


def test_idle_special_heart_returns_to_idle(tmp_path) -> None:
    app = _app()
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    app.processEvents()
    assert window.controller.state_name == "idle"
    assert window._ambient_timer.isActive()

    window._ambient_timer.stop()
    window._play_idle_special()
    assert window.controller.state_name == "heart"
    assert window.state_coordinator.mode == "ambient"
    for _ in range(6):
        window.controller._advance()
    app.processEvents()
    assert window.controller.state_name == "idle"
    assert window._ambient_timer.isActive()
    window.force_exit_for_session_end()


def test_interrupted_idle_special_can_schedule_again(tmp_path) -> None:
    app = _app()
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    app.processEvents()
    window._ambient_timer.stop()
    window._play_idle_special()
    assert window.state_coordinator.mode == "ambient"
    window.set_animation_state("waiting")
    assert window.state_coordinator.mode is None
    window.set_animation_state("idle")
    assert window._ambient_timer.isActive()
    window.force_exit_for_session_end()
