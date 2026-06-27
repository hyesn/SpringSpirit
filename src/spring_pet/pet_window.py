from __future__ import annotations

import os
import random
import time
from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QContextMenuEvent,
    QFont,
    QMouseEvent,
    QPixmap,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox, QWidget
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QSpinBox,
    QVBoxLayout,
    QWidgetAction,
)

from .animation_controller import AnimationController
from .asset_loader import AnimationManifest
from .autostart import AutostartError, AutostartManager
from .discipline_display import DisciplineDisplay
from .foreground_monitor import ForegroundMonitor
from .foreground_rules import ForegroundRuleError, ForegroundRuleStore
from .hardware_bubble import HardwareStatusBubble
from .hardware_monitor import HardwareMonitorService, HardwareSnapshot
from .interaction import DragDirectionTracker
from .menu_widgets import ScaleSliderPanel
from .placement import EdgeSnap, apply_edge_snap, clamp_rect_top_left, detect_edge_snap
from .recipe_menu import RecipeMenu, recipe_font
from .settings import PetSettings
from .speech_bubble import SpeechBubble
from .state_coordinator import StateCoordinator
from . import ui_theme as theme


class PetWindow(QWidget):
    MIN_SCALE = 0.25
    MAX_SCALE = 2.5
    SCALE_STEP = 0.1
    SCALE_PRESETS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5)
    SLEEP_AFTER_MS = 30 * 60 * 1000
    SLEEP_DURATION_MS = 5 * 60 * 1000
    SLEEP_STATE = "sleeping"
    DISCIPLINE_TICK_MS = 1000
    DISCIPLINE_REMINDER_COOLDOWN_MS = 3 * 60 * 1000
    FOCUS_STATES = {"running", "noting"}
    RELAX_STATES = {"listening", "review"}

    def __init__(
        self,
        manifest: AnimationManifest,
        settings: PetSettings,
        autostart: AutostartManager | None = None,
        foreground_rules: ForegroundRuleStore | None = None,
        foreground_monitor: ForegroundMonitor | None = None,
        hardware_monitor_service: HardwareMonitorService | None = None,
        ambient_interval_provider: Callable[[], int] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.manifest = manifest
        self.settings = settings
        self.autostart = autostart or AutostartManager()
        self.foreground_rules = foreground_rules
        self.foreground_monitor = foreground_monitor
        self.hardware_monitor_service = hardware_monitor_service
        self._drag_offset: QPoint | None = None
        self._drag_animation_active = False
        self._drag_tracker = DragDirectionTracker(threshold=4)
        self._source_pixmap = QPixmap()
        self._screen_signal_connected = False
        self._exit_requested = False
        self._allow_close = False
        self._force_exit = False
        self._interaction_enabled = True
        self._autostart_error: str | None = None
        self._foreground_process: str | None = None
        self._foreground_match_label: str | None = None
        self._foreground_match_state: str | None = None
        self._diagnostic_kind: str | None = None
        self._pending_discipline_event: tuple[str, str] | None = None
        self._pending_sleep = False
        self._discipline_enabled = False
        self._discipline_paused = False
        self._discipline_phase = "focus"
        self._discipline_focus_minutes = 45
        self._discipline_relax_minutes = 8
        self._discipline_focus_elapsed_ms = 0
        self._discipline_relax_elapsed_ms = 0
        self._discipline_cycle_count = 0
        self._discipline_focus_break_active = False
        self._discipline_last_tick = time.monotonic()
        self._discipline_cooldowns: dict[str, float] = {}
        self._edge_snap_enabled = True
        self._edge_snap = EdgeSnap()
        self._ambient_interval_provider = ambient_interval_provider or (
            lambda: random.SystemRandom().randint(
                8 * 60 * 1000,
                20 * 60 * 1000,
            )
        )
        self._ambient_timer = QTimer(self)
        self._ambient_timer.setSingleShot(True)
        self._ambient_timer.timeout.connect(self._play_idle_special)
        self._discipline_timer = QTimer(self)
        self._discipline_timer.timeout.connect(self._on_discipline_tick)
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._on_sleep_due)
        self._wake_timer = QTimer(self)
        self._wake_timer.setSingleShot(True)
        self._wake_timer.timeout.connect(self._wake_from_sleep)

        self.setWindowTitle("Spring")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        persistent_states = {
            name for name, state in manifest.states.items() if state.is_persistent
        }
        restored = settings.load(
            default_scale=manifest.default_scale,
            default_state=manifest.default_state,
            persistent_states=persistent_states,
        )
        self.scale = restored.scale
        self._foreground_follow_enabled = restored.foreground_follow_enabled
        self.hardware_bubble = HardwareStatusBubble(
            restored.diagnostic_bubble_timeout_ms
        )
        self.speech_bubble = SpeechBubble()
        self.discipline_display = DisciplineDisplay()
        self.discipline_display.pause_toggled.connect(self._toggle_discipline_pause)
        self.discipline_display.switch_requested.connect(self._switch_discipline_phase)
        self._discipline_enabled = restored.discipline_enabled
        self._discipline_paused = restored.discipline_paused
        self._discipline_focus_minutes = restored.discipline_focus_minutes
        self._discipline_relax_minutes = restored.discipline_relax_minutes
        self._discipline_phase = restored.discipline_phase
        self._discipline_focus_elapsed_ms = restored.discipline_focus_elapsed_ms
        self._discipline_relax_elapsed_ms = restored.discipline_relax_elapsed_ms
        self._discipline_cycle_count = restored.discipline_cycle_count
        self._edge_snap_enabled = restored.edge_snap_enabled
        self._edge_snap = EdgeSnap(
            restored.edge_snap_horizontal,
            restored.edge_snap_vertical,
        )
        self._resize_canvas()

        self.controller = AnimationController(manifest, self)
        self.controller.frame_changed.connect(self._show_frame)
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.animation_finished.connect(self._on_animation_finished)
        self.state_coordinator = StateCoordinator(
            manifest,
            self.controller,
            restored.looping_state,
        )

        start_position = restored.position
        if start_position is None:
            start_position = settings.default_position(self.width(), self.height())
        self.move(
            settings.clamp_position(start_position, self.width(), self.height())
        )
        if self._edge_snap_enabled and not self._edge_snap.is_free:
            self.move(apply_edge_snap(self.frameGeometry(), self._edge_snap))
        self._interaction_enabled = False
        if not self.state_coordinator.play_startup():
            self._interaction_enabled = True
            self._restart_state_timers()
        if self._discipline_enabled:
            self._show_discipline_display()
            if not self._discipline_paused and self._discipline_phase != "focus_ready":
                self._discipline_timer.start(self.DISCIPLINE_TICK_MS)
        if self.foreground_monitor is not None:
            self.foreground_monitor.process_changed.connect(
                self._on_foreground_process_changed
            )
            self.foreground_monitor.start()
        if self.hardware_monitor_service is not None:
            self.hardware_monitor_service.snapshot_ready.connect(
                self._on_hardware_snapshot
            )
            self.hardware_monitor_service.collection_failed.connect(
                self._on_hardware_collection_failed
            )
        try:
            self.autostart.sync_path_if_enabled()
        except AutostartError as exc:
            self._autostart_error = str(exc)

    def _resize_canvas(self) -> None:
        device_pixel_ratio = max(1.0, self.devicePixelRatioF())
        width = round(self.manifest.canvas[0] * self.scale / device_pixel_ratio)
        height = round(self.manifest.canvas[1] * self.scale / device_pixel_ratio)
        self.setFixedSize(width, height)
        self.label.setGeometry(0, 0, width, height)

    def _show_frame(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        # Render once at physical resolution to avoid Windows DPI softening.
        device_pixel_ratio = max(1.0, self.devicePixelRatioF())
        physical_size = QSize(
            round(self.width() * device_pixel_ratio),
            round(self.height() * device_pixel_ratio),
        )
        is_downscaling = (
            physical_size.width() < pixmap.width()
            or physical_size.height() < pixmap.height()
        )
        transformation = (
            Qt.TransformationMode.SmoothTransformation
            if is_downscaling
            else Qt.TransformationMode.FastTransformation
        )
        rendered = pixmap.scaled(
            physical_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            transformation,
        )
        rendered.setDevicePixelRatio(device_pixel_ratio)
        self.label.setPixmap(rendered)

        # QWidget masks use logical coordinates.
        mask_source = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.setMask(mask_source.mask())

    def _on_state_changed(self, state_name: str) -> None:
        state = self.manifest.states[state_name]
        if state.is_persistent:
            self.settings.save_looping_state(state_name)
        if (
            state_name == self.manifest.default_state
            and self.state_coordinator.mode is None
            and self._interaction_enabled
            and not self._exit_requested
        ):
            self._schedule_idle_special()
        else:
            self._ambient_timer.stop()

    def _on_animation_finished(self, state_name: str) -> None:
        exit_state = self.manifest.state_for_trigger("exit")
        if self._exit_requested and state_name == exit_state:
            self._allow_close = True
            self.close()
            application = QApplication.instance()
            if application is not None:
                application.quit()
            return

        completed_mode = self.state_coordinator.animation_finished(state_name)
        if completed_mode == "startup":
            self._interaction_enabled = True
            self._restart_state_timers()
            if self.state_coordinator.can_play_ambient():
                self._schedule_idle_special()
        elif completed_mode == "scheduled-action":
            self._flush_pending_state_timers()
        elif completed_mode in {"ambient", "action", "diagnostic"}:
            self._flush_pending_state_timers()

    def _schedule_idle_special(self) -> None:
        interval = max(1, int(self._ambient_interval_provider()))
        self._ambient_timer.start(interval)

    def _play_idle_special(self) -> None:
        if (
            not self._interaction_enabled
            or self._exit_requested
            or not self.state_coordinator.can_play_ambient()
        ):
            return
        if not self.state_coordinator.play_ambient():
            self._schedule_idle_special()

    def _menu_state_names(self) -> set[str]:
        return {state.name for state in self.manifest.menu_states("\u72b6\u6001")}

    def _current_base_allows_timers(self) -> bool:
        return (
            self._interaction_enabled
            and not self._exit_requested
            and not self._discipline_enabled
            and self.state_coordinator.base_state in self._menu_state_names()
        )

    def _can_play_delayed_effect(self) -> bool:
        return self._current_base_allows_timers() and self.state_coordinator.mode is None

    def _restart_state_timers(self) -> None:
        self._pending_sleep = False
        self._wake_timer.stop()
        if self._current_base_allows_timers():
            self._sleep_timer.start(self.SLEEP_AFTER_MS)
        else:
            self._sleep_timer.stop()

    def _on_sleep_due(self) -> None:
        if not self._current_base_allows_timers():
            return
        if not self._can_play_delayed_effect():
            self._pending_sleep = True
            return
        self._enter_scheduled_sleep()

    def _enter_scheduled_sleep(self) -> None:
        if self.SLEEP_STATE not in self.manifest.states:
            return
        self._pending_sleep = False
        if self.state_coordinator.enter_sleep(self.SLEEP_STATE):
            self._wake_timer.start(self.SLEEP_DURATION_MS)

    def _wake_from_sleep(self) -> None:
        if self.state_coordinator.wake_from_sleep():
            self._restart_state_timers()

    def _flush_pending_state_timers(self) -> None:
        if self._pending_discipline_event is not None:
            self._try_play_discipline_event()
        if not self._can_play_delayed_effect():
            return
        if self._pending_sleep:
            self._enter_scheduled_sleep()

    def _discipline_target_ms(self) -> int:
        minutes = (
            self._discipline_focus_minutes
            if self._discipline_phase == "focus"
            else self._discipline_relax_minutes
        )
        return minutes * 60_000

    def _discipline_elapsed_ms(self) -> int:
        return (
            self._discipline_focus_elapsed_ms
            if self._discipline_phase == "focus"
            else self._discipline_relax_elapsed_ms
        )

    def _show_discipline_display(self) -> None:
        self.discipline_display.update_status(
            phase=self._discipline_phase,
            elapsed_ms=self._discipline_elapsed_ms(),
            target_ms=self._discipline_target_ms(),
            paused=self._discipline_paused,
            cycle_count=self._discipline_cycle_count,
        )
        self.discipline_display.show_for_pet(self)

    def _set_discipline_enabled(self, enabled: bool) -> None:
        self._discipline_enabled = enabled
        self.settings.save_discipline_enabled(enabled)
        if enabled:
            if self._foreground_follow_enabled:
                self._foreground_follow_enabled = False
                self.settings.save_foreground_follow_enabled(False)
            self._discipline_phase = "focus"
            self._discipline_focus_elapsed_ms = 0
            self._discipline_relax_elapsed_ms = 0
            self._discipline_cycle_count = 0
            self._discipline_paused = False
            self.settings.save_discipline_paused(False)
            self._discipline_cooldowns.clear()
            self._discipline_focus_break_active = False
            self._pending_discipline_event = None
            self.speech_bubble.hide_now()
            self._sleep_timer.stop()
            self._wake_timer.stop()
            self._discipline_last_tick = time.monotonic()
            if self.foreground_monitor is not None:
                self.foreground_monitor.check_now()
            self._discipline_timer.start(self.DISCIPLINE_TICK_MS)
            self._show_discipline_display()
            self._save_discipline_progress()
        else:
            self._discipline_timer.stop()
            self._discipline_paused = False
            self._discipline_phase = "focus"
            self._discipline_focus_elapsed_ms = 0
            self._discipline_relax_elapsed_ms = 0
            self._discipline_cycle_count = 0
            self._discipline_cooldowns.clear()
            self._discipline_focus_break_active = False
            self._pending_discipline_event = None
            self.discipline_display.hide()
            self.speech_bubble.hide_now()
            self.settings.save_discipline_paused(False)
            self.settings.clear_discipline_progress()
            self._restart_state_timers()

    def _toggle_discipline_pause(self) -> None:
        if not self._discipline_enabled:
            return
        if self._discipline_phase == "focus_ready":
            self._discipline_phase = "focus"
            self._discipline_paused = False
            self._discipline_focus_elapsed_ms = 0
            self._discipline_relax_elapsed_ms = 0
            self.settings.save_discipline_paused(False)
            self._discipline_last_tick = time.monotonic()
            self._discipline_timer.start(self.DISCIPLINE_TICK_MS)
            self._save_discipline_progress()
            self._show_discipline_display()
            return
        self._discipline_paused = not self._discipline_paused
        self.settings.save_discipline_paused(self._discipline_paused)
        self._discipline_last_tick = time.monotonic()
        if self._discipline_paused:
            self._discipline_timer.stop()
        else:
            self._discipline_timer.start(self.DISCIPLINE_TICK_MS)
        self._show_discipline_display()

    def _switch_discipline_phase(self) -> None:
        if not self._discipline_enabled or self._discipline_phase == "focus_ready":
            return
        self._discipline_paused = False
        self.settings.save_discipline_paused(False)
        self._discipline_cooldowns.clear()
        self._discipline_focus_break_active = False
        self._pending_discipline_event = None
        self.speech_bubble.hide_now()
        if self._discipline_phase == "focus":
            self._discipline_phase = "relax"
            self._discipline_relax_elapsed_ms = 0
        else:
            self._discipline_phase = "focus"
            self._discipline_focus_elapsed_ms = 0
        self._discipline_last_tick = time.monotonic()
        self._discipline_timer.start(self.DISCIPLINE_TICK_MS)
        self._save_discipline_progress()
        self._show_discipline_display()

    def _on_discipline_tick(self) -> None:
        if (
            not self._discipline_enabled
            or self._discipline_paused
            or self._discipline_phase == "focus_ready"
        ):
            return
        now = time.monotonic()
        delta_ms = max(0, min(5_000, round((now - self._discipline_last_tick) * 1000)))
        self._discipline_last_tick = now
        self._advance_discipline(delta_ms)

    def _advance_discipline(self, delta_ms: int) -> None:
        if (
            not self._discipline_enabled
            or self._discipline_paused
            or self._discipline_phase == "focus_ready"
        ):
            return
        state = self._discipline_observed_state()
        if self._discipline_phase == "focus":
            if state in self.FOCUS_STATES:
                if self._discipline_focus_break_active:
                    self._clear_focus_break_notice()
                self._discipline_focus_elapsed_ms = min(
                    self._discipline_focus_elapsed_ms + delta_ms,
                    self._discipline_focus_minutes * 60_000,
                )
                self._discipline_cooldowns.pop("focus_break", None)
                if self._discipline_focus_elapsed_ms >= self._discipline_focus_minutes * 60_000:
                    self._discipline_phase = "relax"
                    self._discipline_relax_elapsed_ms = 0
                    self._queue_discipline_event(
                        "focus_complete",
                        "jumping",
                    )
            elif state in self.RELAX_STATES:
                self._discipline_violation("focus_break")
        else:
            if state in self.RELAX_STATES:
                self._discipline_relax_elapsed_ms = min(
                    self._discipline_relax_elapsed_ms + delta_ms,
                    self._discipline_relax_minutes * 60_000,
                )
                if self._discipline_relax_elapsed_ms >= self._discipline_relax_minutes * 60_000:
                    self._discipline_complete_cycle()
            elif state in self.FOCUS_STATES:
                pass
        self._save_discipline_progress()
        if self.discipline_display.isVisible():
            self._show_discipline_display()

    def _discipline_violation(self, kind: str) -> None:
        now = time.monotonic()
        last = self._discipline_cooldowns.get(kind)
        if last is not None and (now - last) * 1000 < self.DISCIPLINE_REMINDER_COOLDOWN_MS:
            return
        self._discipline_cooldowns[kind] = now
        if kind == "focus_break":
            if self._discipline_focus_break_active:
                return
            self._discipline_focus_break_active = True
            pass
        else:
            return
        self._queue_discipline_event(kind, "failed")

    def _discipline_complete_cycle(self) -> None:
        self._discipline_cycle_count += 1
        self._discipline_phase = "focus_ready"
        self._discipline_focus_elapsed_ms = 0
        self._discipline_relax_elapsed_ms = self._discipline_relax_minutes * 60_000
        self._discipline_cooldowns.clear()
        self._discipline_focus_break_active = False
        self._discipline_timer.stop()
        self.settings.save_discipline_paused(False)
        self._queue_discipline_event("cycle_complete", "jumping")
        self._save_discipline_progress()
        if self.discipline_display.isVisible():
            self._show_discipline_display()

    def _queue_discipline_event(self, kind: str, action_state: str) -> None:
        if not self._discipline_enabled or self._exit_requested:
            return
        self._pending_discipline_event = (kind, action_state)
        self._try_play_discipline_event()

    def _try_play_discipline_event(self) -> None:
        if self._pending_discipline_event is None:
            return
        if self.state_coordinator.mode is not None or self._exit_requested:
            return
        kind, action_state = self._pending_discipline_event
        if not self._discipline_event_still_valid(kind):
            self._pending_discipline_event = None
            return
        if self.state_coordinator.play_scheduled_action(action_state):
            self._pending_discipline_event = None
            self._show_discipline_message(kind)

    def _show_discipline_message(self, kind: str) -> None:
        self.hardware_bubble.hide()
        self.speech_bubble.show_kind(kind, self, duration_ms=5_000)
        if self.discipline_display.isVisible():
            self.discipline_display.reposition()

    def _discipline_event_still_valid(self, kind: str) -> bool:
        state = self._discipline_observed_state()
        if kind == "focus_break":
            return self._discipline_phase == "focus" and state in self.RELAX_STATES
        if kind == "focus_complete":
            return self._discipline_phase == "relax"
        if kind == "cycle_complete":
            return self._discipline_phase == "focus_ready"
        return True

    def _clear_focus_break_notice(self) -> None:
        self._discipline_focus_break_active = False
        self._discipline_cooldowns.pop("focus_break", None)
        if self._pending_discipline_event and self._pending_discipline_event[0] == "focus_break":
            self._pending_discipline_event = None
        if self.speech_bubble.isVisible():
            self.speech_bubble.hide_now()

    def _discipline_observed_state(self) -> str:
        if (
            self._discipline_enabled
            and self._foreground_match_state is not None
        ):
            return self._foreground_match_state
        return self.state_coordinator.base_state

    def _save_discipline_progress(self) -> None:
        self.settings.save_discipline_progress(
            phase=self._discipline_phase,
            focus_elapsed_ms=self._discipline_focus_elapsed_ms,
            relax_elapsed_ms=self._discipline_relax_elapsed_ms,
            cycle_count=self._discipline_cycle_count,
        )

    def _build_discipline_settings_widget(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        panel.setObjectName("disciplineSettingsPanel")
        panel_font = recipe_font()
        panel_font.setPointSizeF(10.0)
        panel_font.setWeight(QFont.Weight.Medium)
        panel.setFont(panel_font)
        panel.setFixedSize(146, 56)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(0)

        focus = QSpinBox(panel)
        focus.setObjectName("disciplineSpin")
        focus.setFont(panel_font)
        focus.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        focus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus.setRange(1, 180)
        focus.setValue(self._discipline_focus_minutes)
        relax = QSpinBox(panel)
        relax.setObjectName("disciplineSpin")
        relax.setFont(panel_font)
        relax.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        relax.setAlignment(Qt.AlignmentFlag.AlignCenter)
        relax.setRange(1, 60)
        relax.setValue(self._discipline_relax_minutes)
        def make_cycle_row(
            title_text: str,
            spin: QSpinBox,
        ) -> QFrame:
            row = QFrame(panel)
            row.setObjectName("disciplineCycleRow")
            row.setFixedHeight(28)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 1, 0, 1)
            row_layout.setSpacing(4)
            row_title = QLabel(title_text, row)
            row_title.setObjectName("disciplineCycleLabel")
            row_title.setFont(panel_font)
            row_title.setFixedWidth(42)
            row_layout.addWidget(row_title)
            spin.setFixedSize(46, 26)
            row_layout.addWidget(spin)
            row_layout.addSpacing(10)
            unit_label = QLabel("min", row)
            unit_label.setObjectName("disciplineUnitLabel")
            unit_label.setFont(panel_font)
            unit_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            unit_label.setFixedWidth(24)
            row_layout.addWidget(unit_label)
            return row

        layout.addWidget(
            make_cycle_row(
                "\u4e13\u6ce8\uff1a",
                focus,
            )
        )
        layout.addWidget(
            make_cycle_row(
                "\u653e\u677e\uff1a",
                relax,
            )
        )
        panel.setStyleSheet(
            f"""
            #disciplineSettingsPanel {{
                background: transparent;
                color: {theme.COCOA_TEXT};
            }}
            #disciplineCycleRow {{
                background: transparent;
                border: none;
            }}
            #disciplineCycleLabel {{
                color: {theme.COCOA_TEXT};
            }}
            #disciplineUnitLabel {{
                color: {theme.COCOA_TEXT};
            }}
            QLabel {{
                color: {theme.COCOA_TEXT};
            }}
            #disciplineSpin {{
                color: {theme.COCOA_TEXT};
                background: {theme.PAPER_LIGHT};
                border: 1px solid {theme.PINK_BORDER};
                border-radius: 4px;
                padding: 1px 3px;
            }}
            #disciplineSpin:focus {{
                border: 1px solid {theme.LABEL_PINK};
                background: {theme.CREAM_PAPER};
            }}
            """
        )
        focus.valueChanged.connect(
            lambda value: self._set_discipline_cycle_minutes(
                focus_minutes=value,
                relax_minutes=relax.value(),
            )
        )
        relax.valueChanged.connect(
            lambda value: self._set_discipline_cycle_minutes(
                focus_minutes=focus.value(),
                relax_minutes=value,
            )
        )
        return panel

    def _set_discipline_cycle_minutes(
        self,
        *,
        focus_minutes: int,
        relax_minutes: int,
    ) -> None:
        focus_minutes = min(180, max(1, int(focus_minutes)))
        relax_minutes = min(60, max(1, int(relax_minutes)))
        if (
            focus_minutes == self._discipline_focus_minutes
            and relax_minutes == self._discipline_relax_minutes
        ):
            return
        self._discipline_focus_minutes = focus_minutes
        self._discipline_relax_minutes = relax_minutes
        self.settings.save_discipline_config(
            self._discipline_focus_minutes,
            self._discipline_relax_minutes,
        )
        self._discipline_phase = "focus"
        self._discipline_focus_elapsed_ms = 0
        self._discipline_relax_elapsed_ms = 0
        self._discipline_focus_break_active = False
        self.speech_bubble.hide_now()
        self._discipline_last_tick = time.monotonic()
        self._save_discipline_progress()
        if self._discipline_enabled:
            if not self._discipline_paused:
                self._discipline_timer.start(self.DISCIPLINE_TICK_MS)
            self._show_discipline_display()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        window_handle = self.windowHandle()
        if window_handle is not None and not self._screen_signal_connected:
            window_handle.screenChanged.connect(self._on_screen_changed)
            self._screen_signal_connected = True
        self._refresh_for_screen_density()

    def _on_screen_changed(self, _screen: object | None = None) -> None:
        self._refresh_for_screen_density()

    def _refresh_for_screen_density(self) -> None:
        old_center = self.frameGeometry().center()
        self._resize_canvas()
        if self._edge_snap_enabled and not self._edge_snap.is_free:
            self.move(apply_edge_snap(self.frameGeometry(), self._edge_snap))
        else:
            self.move(
                self.frameGeometry().topLeft()
                + (old_center - self.frameGeometry().center())
            )
            self.move(clamp_rect_top_left(self.frameGeometry()))
        if not self._source_pixmap.isNull():
            self._show_frame(self._source_pixmap)
        if self.hardware_bubble.isVisible():
            self.hardware_bubble.reposition()
        if self.speech_bubble.isVisible():
            self.speech_bubble.reposition()
        if self.discipline_display.isVisible():
            self.discipline_display.reposition()

    def set_animation_state(self, state_name: str) -> None:
        if not self._interaction_enabled:
            return
        self._cancel_hardware_diagnostic()
        previous_base = self.state_coordinator.base_state
        self.state_coordinator.select_user_state(state_name)
        if self.state_coordinator.base_state != previous_base:
            self._restart_state_timers()
            self._on_discipline_base_state_changed()

    def set_scale(self, scale: float) -> None:
        if not self._interaction_enabled:
            return
        new_scale = min(self.MAX_SCALE, max(self.MIN_SCALE, round(scale, 2)))
        if new_scale == self.scale:
            return
        old_center = self.frameGeometry().center()
        self.scale = new_scale
        self._resize_canvas()
        if self._edge_snap_enabled and not self._edge_snap.is_free:
            self.move(apply_edge_snap(self.frameGeometry(), self._edge_snap))
        else:
            self.move(self.frameGeometry().topLeft() + (old_center - self.frameGeometry().center()))
            self.move(clamp_rect_top_left(self.frameGeometry()))
        if not self._source_pixmap.isNull():
            self._show_frame(self._source_pixmap)
        if self.hardware_bubble.isVisible():
            self.hardware_bubble.reposition()
        if self.speech_bubble.isVisible():
            self.speech_bubble.reposition()
        if self.discipline_display.isVisible():
            self.discipline_display.reposition()
        self.settings.save_scale(self.scale)
        self.settings.save_position(self.pos())

    def build_context_menu(self) -> QMenu:
        menu = RecipeMenu(parent=self)
        menu._spring_submenus = []
        menu._spring_action_groups = []
        for group_name in ("\u72b6\u6001",):
            states = self.manifest.menu_states(group_name)
            if not states:
                continue
            submenu = RecipeMenu(group_name, menu)
            submenu_action = menu.addMenu(submenu)
            menu._spring_submenus.append(submenu)
            submenu_action.setObjectName("menu_states")
            for state in states:
                action = QAction(state.label, submenu)
                action.setObjectName(f"state_{state.name}")
                action.setData(state.name)
                action.setCheckable(state.role == "persistent")
                action.setChecked(
                    state.role == "persistent"
                    and state.name == self.state_coordinator.base_state
                )
                action.triggered.connect(
                    lambda checked=False, state_name=state.name: (
                        self.set_animation_state(state_name)
                    )
                )
                submenu.addAction(action)

        scale_menu = RecipeMenu("\u7f29\u653e", menu)
        scale_action = menu.addMenu(scale_menu)
        menu._spring_submenus.append(scale_menu)
        scale_action.setObjectName("menu_scale")
        scale_slider_action = QWidgetAction(scale_menu)
        scale_slider_action.setObjectName("scale_slider")
        scale_slider_action.setDefaultWidget(
            ScaleSliderPanel(self.SCALE_PRESETS, self.scale, self.set_scale, scale_menu)
        )
        scale_menu.addAction(scale_slider_action)

        hardware_menu = RecipeMenu("\u7535\u8111\u611f\u77e5", menu)
        hardware_action = menu.addMenu(hardware_menu)
        menu._spring_submenus.append(hardware_menu)
        hardware_action.setObjectName("menu_computer_awareness")
        hardware_available = self.hardware_monitor_service is not None
        hardware_busy = (
            self.hardware_monitor_service.busy
            if self.hardware_monitor_service is not None
            else False
        )
        overview_action = hardware_menu.addAction("\u7cfb\u7edf\u6982\u89c8")
        overview_action.setObjectName("computer_overview")
        overview_action.setEnabled(hardware_available and not hardware_busy)
        overview_action.triggered.connect(
            lambda: self.request_hardware_diagnostic("overview")
        )
        vitals_action = hardware_menu.addAction("\u786c\u4ef6\u4f53\u5f81")
        vitals_action.setObjectName("computer_vitals")
        vitals_action.setEnabled(hardware_available and not hardware_busy)
        vitals_action.triggered.connect(
            lambda: self.request_hardware_diagnostic("vitals")
        )
        if not hardware_available:
            hardware_menu.setToolTip("\u786c\u4ef6\u76d1\u63a7\u670d\u52a1\u4e0d\u53ef\u7528")

        foreground_menu = RecipeMenu("\u5e94\u7528\u8ddf\u968f", menu)
        follow_action = menu.addMenu(foreground_menu)
        menu._spring_submenus.append(foreground_menu)
        follow_action.setObjectName("menu_foreground_follow")
        follow_action.setChecked(self._foreground_follow_enabled)
        follow_available = (
            self.foreground_rules is not None
            and self.foreground_monitor is not None
            and self.foreground_monitor.available
        )
        RecipeMenu.make_toggle_submenu_action(
            follow_action,
            available=follow_available,
        )
        if not follow_available:
            follow_action.setToolTip("\u4ec5 Windows \u7cfb\u7edf\u652f\u6301\u524d\u53f0\u5e94\u7528\u8054\u52a8")
        follow_action.toggled.connect(self._set_foreground_follow_enabled)

        status_action = foreground_menu.addAction(self._foreground_status_text())
        status_action.setObjectName("foreground_current")
        status_action.setEnabled(False)

        edit_rules_action = foreground_menu.addAction("\u7f16\u8f91\u89c4\u5219")
        edit_rules_action.setObjectName("foreground_edit_rules")
        edit_rules_action.setEnabled(self.foreground_rules is not None)
        edit_rules_action.triggered.connect(self._edit_foreground_rules)

        reload_rules_action = foreground_menu.addAction("\u91cd\u8f7d\u89c4\u5219")
        reload_rules_action.setObjectName("foreground_reload_rules")
        reload_rules_action.setEnabled(self.foreground_rules is not None)
        reload_rules_action.triggered.connect(self._reload_foreground_rules)

        try:
            status = self.autostart.status()
        except AutostartError as exc:
            self._autostart_error = str(exc)
            status = None
        autostart_action = menu.addAction("\u5f00\u673a\u81ea\u542f\u52a8")
        autostart_action.setObjectName("menu_autostart")
        autostart_action.setCheckable(True)
        autostart_action.setChecked(status.enabled if status else False)
        autostart_action.setEnabled(status.available if status else False)
        if status and status.reason:
            autostart_action.setStatusTip(status.reason)
            autostart_action.setToolTip(status.reason)
        elif self._autostart_error:
            autostart_action.setStatusTip(self._autostart_error)
            autostart_action.setToolTip(self._autostart_error)
        autostart_action.toggled.connect(self._set_autostart)

        discipline_menu = RecipeMenu("\u5979\u5f8b", menu)
        discipline_action = menu.addMenu(discipline_menu)
        menu._spring_submenus.append(discipline_menu)
        discipline_action.setObjectName("menu_discipline")
        discipline_action.setChecked(self._discipline_enabled)
        RecipeMenu.make_toggle_submenu_action(
            discipline_action,
            available=True,
        )
        discipline_action.toggled.connect(self._set_discipline_enabled)
        settings_panel_action = QWidgetAction(discipline_menu)
        settings_panel_action.setObjectName("discipline_settings_panel")
        settings_panel_action.setDefaultWidget(
            self._build_discipline_settings_widget(discipline_menu)
        )
        discipline_menu.addAction(settings_panel_action)

        exit_action = menu.addAction("\u9000\u51fa")
        exit_action.setObjectName("menu_exit")
        exit_action.triggered.connect(self.request_exit)
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if not self._interaction_enabled:
            event.ignore()
            return
        menu = self.build_context_menu()
        menu.exec(event.globalPos())

    def _set_autostart(self, enabled: bool) -> None:
        try:
            self.autostart.set_enabled(enabled)
            self._autostart_error = None
        except AutostartError as exc:
            self._autostart_error = str(exc)
            QMessageBox.warning(self, "\u5f00\u673a\u81ea\u542f\u52a8", str(exc))
            action = self.sender()
            if isinstance(action, QAction):
                action.blockSignals(True)
                try:
                    action.setChecked(self.autostart.status().enabled)
                except AutostartError:
                    action.setChecked(False)
                action.blockSignals(False)

    def _set_foreground_follow_enabled(self, enabled: bool) -> None:
        if enabled and self._discipline_enabled:
            self._set_discipline_enabled(False)
        self._foreground_follow_enabled = enabled
        self.settings.save_foreground_follow_enabled(enabled)
        if enabled and self.foreground_monitor is not None:
            self.foreground_monitor.check_now()
            self._apply_current_foreground(force=True)

    def _foreground_status_text(self) -> str:
        if self._foreground_process is None:
            return "\u5f53\u524d\u5e94\u7528\uff1a\u5c1a\u672a\u8bc6\u522b"
        if self._foreground_match_label is None:
            return f"\u5f53\u524d\u5e94\u7528\uff1a{self._foreground_process}\uff08\u65e0\u89c4\u5219\uff09"
        state_label = self.manifest.states[self._foreground_match_state].label
        return f"\u5f53\u524d\u5e94\u7528\uff1a{self._foreground_match_label} \u2192 {state_label}"

    def _on_foreground_process_changed(
        self, process_name: str, *, force: bool = False
    ) -> None:
        self._foreground_process = process_name
        self._foreground_match_label = None
        self._foreground_match_state = None
        if self.foreground_rules is None:
            return
        match = self.foreground_rules.match(process_name)
        if match is not None:
            self._foreground_match_label = match.label
            self._foreground_match_state = match.state_name
        if self._discipline_enabled:
            self._on_discipline_base_state_changed()
            return
        self._apply_current_foreground(force=force)

    def _apply_current_foreground(self, *, force: bool = False) -> None:
        if (
            not self._foreground_follow_enabled
            or self._foreground_process is None
            or self._foreground_match_state is None
        ):
            return
        changed = self.state_coordinator.apply_foreground_state(
            self._foreground_process,
            self._foreground_match_state,
            force=force,
        )
        if changed and self.state_coordinator.mode != "sleep":
            self._restart_state_timers()
            self._on_discipline_base_state_changed()

    def _on_discipline_base_state_changed(self) -> None:
        if not self._discipline_enabled:
            return
        if (
            self._discipline_phase == "focus"
            and self._discipline_focus_break_active
            and self._discipline_observed_state() in self.FOCUS_STATES
        ):
            self._clear_focus_break_notice()

    def _edit_foreground_rules(self) -> None:
        if self.foreground_rules is None:
            return
        try:
            startfile = getattr(os, "startfile")
            startfile(str(self.foreground_rules.path))
        except (AttributeError, OSError) as exc:
            QMessageBox.warning(self, "\u7f16\u8f91\u5e94\u7528\u89c4\u5219", f"\u65e0\u6cd5\u6253\u5f00\u89c4\u5219\u6587\u4ef6\uff1a{exc}")

    def _reload_foreground_rules(self) -> None:
        if self.foreground_rules is None:
            return
        try:
            config = self.foreground_rules.load()
        except ForegroundRuleError as exc:
            QMessageBox.warning(
                self,
                "\u91cd\u65b0\u52a0\u8f7d\u5e94\u7528\u89c4\u5219",
                f"{exc}\n\n\u5df2\u7ee7\u7eed\u4f7f\u7528\u4e0a\u4e00\u6b21\u6709\u6548\u89c4\u5219\u3002",
            )
            return
        if self.foreground_monitor is not None:
            self.foreground_monitor.configure(
                config.debounce_ms,
                config.reconcile_interval_ms,
            )
        if self._foreground_process is not None:
            self._on_foreground_process_changed(
                self._foreground_process,
                force=True,
            )

    def request_hardware_diagnostic(self, kind: str) -> None:
        if (
            not self._interaction_enabled
            or self._exit_requested
            or self.hardware_monitor_service is None
        ):
            return
        configuration = {
            "overview": ("hardware-overview", "\u7cfb\u7edf\u6982\u89c8"),
            "vitals": ("hardware-vitals", "\u786c\u4ef6\u4f53\u5f81"),
        }
        if kind not in configuration:
            raise ValueError(f"Unknown hardware diagnostic: {kind}")
        trigger, title = configuration[kind]
        self._cancel_hardware_diagnostic()
        self._diagnostic_kind = kind
        if not self.state_coordinator.play_diagnostic(trigger):
            self._diagnostic_kind = None
            return
        self.speech_bubble.hide_now()
        self.hardware_bubble.show_loading(title, self)
        self.hardware_monitor_service.request(kind)

    def _on_hardware_snapshot(self, snapshot: HardwareSnapshot) -> None:
        if snapshot.kind != self._diagnostic_kind or self._exit_requested:
            return
        title = "\u7cfb\u7edf\u6982\u89c8" if snapshot.kind == "overview" else "\u786c\u4ef6\u4f53\u5f81"
        self.hardware_bubble.show_snapshot(title, snapshot, self)

    def _on_hardware_collection_failed(self, message: str) -> None:
        if self._diagnostic_kind is None or self._exit_requested:
            return
        title = "\u7cfb\u7edf\u6982\u89c8" if self._diagnostic_kind == "overview" else "\u786c\u4ef6\u4f53\u5f81"
        self.hardware_bubble.show_error(title, message, self)

    def _cancel_hardware_diagnostic(self) -> None:
        if self.hardware_monitor_service is not None:
            self.hardware_monitor_service.cancel()
        self._diagnostic_kind = None
        self.hardware_bubble.hide()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            self._interaction_enabled
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._begin_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._interaction_enabled
            and
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            global_position = event.globalPosition().toPoint()
            self._update_drag(global_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._finish_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _begin_drag(self, global_position: QPoint) -> None:
        self._cancel_hardware_diagnostic()
        self.speech_bubble.hide_now()
        self._wake_timer.stop()
        self._drag_offset = global_position - self.frameGeometry().topLeft()
        self._drag_animation_active = False
        self.state_coordinator.begin_drag()
        self._drag_tracker.start(global_position.x())

    def _update_drag(self, global_position: QPoint) -> None:
        if self._drag_offset is None:
            return
        self.move(global_position - self._drag_offset)
        if self.hardware_bubble.isVisible():
            self.hardware_bubble.reposition()
        if self.speech_bubble.isVisible():
            self.speech_bubble.reposition()
        if self.discipline_display.isVisible():
            self.discipline_display.reposition()
        trigger = self._drag_tracker.update(global_position.x())
        if trigger is None:
            return
        self._drag_animation_active = self.state_coordinator.update_drag(trigger)

    def _finish_drag(self) -> None:
        self._drag_offset = None
        self._drag_tracker.reset()
        if self._edge_snap_enabled:
            self._edge_snap = detect_edge_snap(self.frameGeometry())
            if self._edge_snap.is_free:
                self.move(clamp_rect_top_left(self.frameGeometry()))
            else:
                self.move(apply_edge_snap(self.frameGeometry(), self._edge_snap))
            self.settings.save_edge_snap(
                enabled=True,
                horizontal=self._edge_snap.horizontal,
                vertical=self._edge_snap.vertical,
            )
        else:
            self.move(clamp_rect_top_left(self.frameGeometry()))
        self.settings.save_position(self.pos())
        self.state_coordinator.finish_drag()
        self._drag_animation_active = False
        self._flush_pending_state_timers()
        if self.hardware_bubble.isVisible():
            self.hardware_bubble.reposition()
        if self.speech_bubble.isVisible():
            self.speech_bubble.reposition()
        if self.discipline_display.isVisible():
            self.discipline_display.reposition()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._interaction_enabled or event.angleDelta().y() == 0:
            return
        direction = 1 if event.angleDelta().y() > 0 else -1
        self.set_scale(self.scale + direction * self.SCALE_STEP)
        event.accept()

    def request_exit(self) -> None:
        if self._exit_requested:
            return
        self._exit_requested = True
        self._interaction_enabled = False
        self._ambient_timer.stop()
        self._discipline_timer.stop()
        self._sleep_timer.stop()
        self._wake_timer.stop()
        self._drag_offset = None
        self._drag_tracker.reset()
        self._save_settings()
        self._cancel_hardware_diagnostic()
        self.speech_bubble.hide_now()
        if not self.state_coordinator.begin_exit():
            self._allow_close = True
            self.close()

    def force_exit_for_session_end(self) -> None:
        self._force_exit = True
        self._interaction_enabled = False
        self._ambient_timer.stop()
        self._discipline_timer.stop()
        self._sleep_timer.stop()
        self._wake_timer.stop()
        self._save_settings()
        self._cancel_hardware_diagnostic()
        self.speech_bubble.hide_now()
        if self.foreground_monitor is not None:
            self.foreground_monitor.stop()
        self.controller.stop()
        if self.hardware_monitor_service is not None:
            self.hardware_monitor_service.shutdown()
        self.discipline_display.hide()
        self.speech_bubble.hide_now()
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _save_settings(self) -> None:
        self.settings.save_position(self.pos())
        self.settings.save_scale(self.scale)
        self.settings.save_discipline_enabled(self._discipline_enabled)
        self.settings.save_discipline_paused(self._discipline_paused)
        self._save_discipline_progress()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._force_exit or self._allow_close:
            self._save_settings()
            if self.foreground_monitor is not None:
                self.foreground_monitor.stop()
            self._cancel_hardware_diagnostic()
            self.speech_bubble.hide_now()
            if self.hardware_monitor_service is not None:
                self.hardware_monitor_service.shutdown()
            self.controller.stop()
            event.accept()
            return
        event.ignore()
        self.request_exit()
