from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QFrame, QLabel, QSpinBox, QWidgetAction

from spring_pet.asset_loader import load_animation_manifest
from spring_pet.autostart import AutostartManager
from spring_pet.menu_widgets import ScaleSliderPanel
from spring_pet.pet_window import PetWindow
from spring_pet.recipe_menu import RecipeMenu, recipe_font
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
        "缩放",
        "电脑感知",
        "应用跟随",
        "开机自启动",
        "她律",
        "退出",
    ]

    actions = {action.objectName(): action for action in menu.actions()}
    assert set(actions) == {
        "menu_states",
        "menu_scale",
        "menu_discipline",
        "menu_computer_awareness",
        "menu_foreground_follow",
        "menu_autostart",
        "menu_exit",
    }
    assert menu.sizeHint().width() < 180
    assert max(
        menu.actionGeometry(action).height()
        for action in menu.actions()
    ) <= 30
    state_menu = actions["menu_states"].menu()
    assert [action.text() for action in state_menu.actions()] == [
        "待机中",
        "喝奶茶",
        "工作中",
        "照镜子",
        "听音乐",
        "记笔记",
    ]
    assert "跳跃" not in repr(texts)
    assert "闹别扭" not in repr(texts)
    assert "打瞌睡" not in repr(texts)
    assert "向左跑" not in repr(texts)
    assert "向右跑" not in repr(texts)
    assert "挥手" not in repr(texts)
    discipline_menu = actions["menu_discipline"].menu()
    assert actions["menu_discipline"].isCheckable()
    assert len(discipline_menu.actions()) == 1
    settings_action = discipline_menu.actions()[0]
    assert isinstance(settings_action, QWidgetAction)
    assert settings_action.objectName() == "discipline_settings_panel"
    panel = settings_action.defaultWidget()
    assert panel is not None
    assert panel.font().family() == recipe_font().family()
    assert panel.font().pointSizeF() == recipe_font().pointSizeF()
    assert panel.findChild(QLabel, "disciplineSettingsTitle") is None
    cycle_rows = panel.findChildren(QFrame, "disciplineCycleRow")
    assert len(cycle_rows) == 2
    assert all(row.height() == 28 for row in cycle_rows)
    spin_boxes = panel.findChildren(QSpinBox)
    assert [spin.value() for spin in spin_boxes] == [45, 8]
    assert all(spin.height() == 26 for spin in spin_boxes)
    assert all(spin.suffix() == "" for spin in spin_boxes)
    assert all(
        spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        for spin in spin_boxes
    )
    spin_boxes[0].setValue(30)
    spin_boxes[1].setValue(6)
    assert window._discipline_focus_minutes == 30
    assert window._discipline_relax_minutes == 6
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
    assert window.SCALE_PRESETS == (
        0.25,
        0.5,
        0.75,
        1.0,
        1.25,
        1.5,
        1.75,
        2.0,
        2.25,
        2.5,
    )
    window.set_scale(2.0)
    assert window.scale == 2.0
    menu = window.build_context_menu()
    scale_action = next(
        action
        for action in menu.actions()
        if action.objectName() == "menu_scale"
    )
    scale_menu = scale_action.menu()
    assert len(scale_menu.actions()) == 1
    slider_action = scale_menu.actions()[0]
    assert isinstance(slider_action, QWidgetAction)
    assert slider_action.objectName() == "scale_slider"
    panel = slider_action.defaultWidget()
    assert isinstance(panel, ScaleSliderPanel)
    assert panel.font().family() == recipe_font().family()
    gear_label = panel.findChild(QLabel, "scaleGearLabel")
    assert gear_label is not None
    assert gear_label.text() == "Ⅷ"
    assert gear_label.font().pointSizeF() == recipe_font().pointSizeF()
    assert panel.findChild(QLabel, "scaleCaptionLabel") is None
    assert panel.findChild(QLabel, "scaleValueLabel") is None
    assert panel.height() == 32
    assert panel.slider.height() <= 32
    panel.slider.set_value(2.25)
    assert window.scale == 2.25
    assert gear_label.text() == "Ⅸ"
    panel.slider.set_value(0.25)
    assert window.scale == 0.25
    assert gear_label.text() == "Ⅰ"
    window.force_exit_for_session_end()


def test_drag_release_near_edge_saves_snap_state(tmp_path) -> None:
    window = _window(tmp_path)
    screen = QGuiApplication.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry()
    window.move(
        available.right() - window.width() + 1,
        available.bottom() - window.height() + 1,
    )
    window._begin_drag(window.frameGeometry().center())
    window._finish_drag()
    assert window._edge_snap.horizontal == "right"
    assert window._edge_snap.vertical == "bottom"
    window.set_scale(1.5)
    assert window.frameGeometry().right() == available.right()
    assert window.frameGeometry().bottom() == available.bottom()
    window.force_exit_for_session_end()


def test_startup_heart_resumes_saved_persistent_state(tmp_path) -> None:
    app = _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    backend = QSettings(
        str(tmp_path / "startup.ini"), QSettings.Format.IniFormat
    )
    backend.setValue("looping_state", "waiting")
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
    assert window.controller.state_name == "waiting"
    assert window._interaction_enabled
    window.force_exit_for_session_end()


def test_saved_sleeping_state_falls_back_to_idle(tmp_path) -> None:
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    backend = QSettings(
        str(tmp_path / "saved_sleep.ini"), QSettings.Format.IniFormat
    )
    backend.setValue("looping_state", "sleeping")
    window = PetWindow(
        manifest,
        PetSettings(backend),
        autostart=AutostartManager(frozen=False),
        ambient_interval_provider=lambda: 600_000,
    )
    assert window.state_coordinator.base_state == "idle"
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


def test_discipline_focus_violation_triggers_pouting(tmp_path) -> None:
    app = _app()
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    app.processEvents()

    window._set_discipline_enabled(True)
    window.set_animation_state("running")
    window._advance_discipline(30_000)
    window.set_animation_state("review")
    window._advance_discipline(1000)
    assert window.controller.state_name == "failed"
    assert window.state_coordinator.mode == "scheduled-action"
    assert not window.hardware_bubble.isVisible()
    assert window.speech_bubble.isVisible()
    assert window.speech_bubble.current_kind == "focus_break"
    assert window.speech_bubble.image_label.pixmap() is not None
    assert not window.speech_bubble.image_label.pixmap().isNull()
    assert window.speech_bubble.width() == 170
    assert window.speech_bubble.frameGeometry().center().x() < window.frameGeometry().center().x()
    assert window.speech_bubble.frameGeometry().bottom() <= (
        window.frameGeometry().top() + round(window.frameGeometry().height() * 0.28)
    )
    assert window._discipline_focus_elapsed_ms == 30_000
    window.set_animation_state("running")
    assert not window.speech_bubble.isVisible()
    window._advance_discipline(1000)
    assert window._discipline_focus_elapsed_ms == 31_000
    window.force_exit_for_session_end()


def test_discipline_cycle_completion_triggers_jump(tmp_path) -> None:
    app = _app()
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    app.processEvents()

    window._set_discipline_enabled(True)
    window._discipline_focus_minutes = 1
    window._discipline_relax_minutes = 1
    window.set_animation_state("running")
    window._advance_discipline(60_000)
    assert window._discipline_phase == "relax"
    assert window.controller.state_name == "jumping"
    assert window.speech_bubble.current_kind == "focus_complete"
    assert window.speech_bubble.width() == 150
    window._advance_discipline(60_000)
    assert window._discipline_relax_elapsed_ms == 0
    window.set_animation_state("listening")
    window._advance_discipline(30_000)
    window.set_animation_state("running")
    window._advance_discipline(30_000)
    assert window._discipline_phase == "relax"
    assert window._discipline_relax_elapsed_ms == 30_000
    window.set_animation_state("listening")
    window._advance_discipline(60_000)
    assert window.controller.state_name == "jumping"
    assert window.speech_bubble.current_kind == "cycle_complete"
    assert window.speech_bubble.width() == 150
    assert window._discipline_phase == "focus_ready"
    assert window._discipline_cycle_count == 1
    assert window.discipline_display.phase_label.text() == "待继续"
    assert window.discipline_display.progress_label.text() == "周目 1"
    assert window.discipline_display.pause_button.text() == "继续"
    assert not window.discipline_display.switch_button.isEnabled()
    window._advance_discipline(60_000)
    assert window._discipline_focus_elapsed_ms == 0
    window._toggle_discipline_pause()
    assert window._discipline_phase == "focus"
    assert window._discipline_cycle_count == 1
    window.set_animation_state("running")
    window._advance_discipline(1000)
    assert window._discipline_focus_elapsed_ms == 1000
    window.force_exit_for_session_end()


def test_discipline_pause_stops_progress_and_display_can_resume(tmp_path) -> None:
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    window._set_discipline_enabled(True)
    window.set_animation_state("running")
    assert window.discipline_display.text_layout.verticalSpacing() == 10
    assert window.discipline_display.switch_button.size() == window.discipline_display.pause_button.size()
    assert window.discipline_display.switch_button.text() == "切换"
    window._toggle_discipline_pause()
    window._advance_discipline(60_000)
    assert window._discipline_focus_elapsed_ms == 0
    assert window.discipline_display.pause_button.text() == "继续"
    window._toggle_discipline_pause()
    window._advance_discipline(1000)
    assert window._discipline_focus_elapsed_ms == 1000
    window.force_exit_for_session_end()


def test_discipline_switch_button_changes_phase(tmp_path) -> None:
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    window._set_discipline_enabled(True)

    window.set_animation_state("running")
    window._advance_discipline(10_000)
    window.discipline_display.switch_requested.emit()
    assert window._discipline_phase == "relax"
    assert window._discipline_relax_elapsed_ms == 0
    assert not window._discipline_paused
    assert window.discipline_display.phase_label.text() == "放松中"

    window.set_animation_state("listening")
    window._advance_discipline(10_000)
    window.discipline_display.switch_requested.emit()
    assert window._discipline_phase == "focus"
    assert window._discipline_focus_elapsed_ms == 0
    assert window.discipline_display.phase_label.text() == "专注中"
    window.force_exit_for_session_end()


def test_discipline_disables_old_sleep_timer_until_closed(tmp_path) -> None:
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()
    window.set_animation_state("waiting")
    window._set_discipline_enabled(True)
    window._on_sleep_due()
    assert window.controller.state_name == "waiting"
    window._set_discipline_enabled(False)
    window._on_sleep_due()
    assert window.controller.state_name == "sleeping"
    window.force_exit_for_session_end()


def test_discipline_and_foreground_follow_are_mutually_exclusive(tmp_path) -> None:
    window = _window(tmp_path)
    for _ in range(6):
        window.controller._advance()

    assert window._foreground_follow_enabled
    window._set_discipline_enabled(True)
    assert window._discipline_enabled
    assert not window._foreground_follow_enabled

    window._set_foreground_follow_enabled(True)
    assert window._foreground_follow_enabled
    assert not window._discipline_enabled
    assert not window.discipline_display.isVisible()
    window.force_exit_for_session_end()


def test_discipline_reads_foreground_without_following_animation(tmp_path) -> None:
    from spring_pet.foreground_rules import ForegroundRuleStore

    app = _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    persistent = {
        name for name, state in manifest.states.items() if state.is_persistent
    }
    rules = ForegroundRuleStore(persistent, tmp_path / "rules.json")
    rules.load()
    settings = PetSettings(
        QSettings(str(tmp_path / "discipline_foreground.ini"), QSettings.Format.IniFormat)
    )

    class Monitor:
        available = True
        process_changed = type("SignalLike", (), {"connect": lambda self, callback: None})()

        def __init__(self):
            self.checked = False

        def start(self) -> bool:
            return True

        def stop(self) -> None:
            pass

        def check_now(self) -> None:
            self.checked = True

    monitor = Monitor()
    window = PetWindow(
        manifest,
        settings,
        autostart=AutostartManager(frozen=False),
        foreground_rules=rules,
        foreground_monitor=monitor,
        ambient_interval_provider=lambda: 600_000,
    )
    for _ in range(6):
        window.controller._advance()
    app.processEvents()

    window.set_animation_state("running")
    window._set_discipline_enabled(True)
    assert monitor.checked
    assert not window._foreground_follow_enabled
    assert window.controller.state_name == "running"

    window._advance_discipline(30_000)
    window._on_foreground_process_changed("cloudmusic.exe")
    assert window._foreground_match_state == "listening"
    assert window.state_coordinator.base_state == "running"
    assert window.controller.state_name == "running"

    window._advance_discipline(1000)
    assert window.controller.state_name == "failed"
    assert window.speech_bubble.current_kind == "focus_break"
    assert window._discipline_focus_elapsed_ms == 30_000
    window.force_exit_for_session_end()


def test_long_state_duration_enters_sleep_then_wakes_to_original_base(tmp_path) -> None:
    window = _window(tmp_path)
    window.SLEEP_DURATION_MS = 10
    for _ in range(6):
        window.controller._advance()

    window.set_animation_state("waiting")
    window._on_sleep_due()
    assert window.controller.state_name == "sleeping"
    assert window.state_coordinator.mode == "sleep"
    window._wake_from_sleep()
    assert window.controller.state_name == "waiting"
    assert window.state_coordinator.mode is None
    window.force_exit_for_session_end()


def test_foreground_change_during_sleep_updates_wake_target(tmp_path) -> None:
    from spring_pet.foreground_rules import ForegroundRuleStore

    app = _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    persistent = {
        name for name, state in manifest.states.items() if state.is_persistent
    }
    rules = ForegroundRuleStore(persistent, tmp_path / "rules.json")
    rules.load()
    settings = PetSettings(
        QSettings(str(tmp_path / "foreground_sleep.ini"), QSettings.Format.IniFormat)
    )

    class Monitor:
        available = True
        process_changed = type("SignalLike", (), {"connect": lambda self, callback: None})()

        def start(self) -> bool:
            return True

        def stop(self) -> None:
            pass

        def check_now(self) -> None:
            pass

    window = PetWindow(
        manifest,
        settings,
        autostart=AutostartManager(frozen=False),
        foreground_rules=rules,
        foreground_monitor=Monitor(),
        ambient_interval_provider=lambda: 600_000,
    )
    for _ in range(6):
        window.controller._advance()
    app.processEvents()
    window.set_animation_state("waiting")
    window._on_sleep_due()
    window._on_foreground_process_changed("msedge.exe")
    assert window.controller.state_name == "sleeping"
    window._wake_from_sleep()
    assert window.controller.state_name == "noting"
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
