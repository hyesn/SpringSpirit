from __future__ import annotations

import os
import random
from collections.abc import Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QContextMenuEvent,
    QMouseEvent,
    QPixmap,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox, QWidget

from .animation_controller import AnimationController
from .asset_loader import AnimationManifest
from .autostart import AutostartError, AutostartManager
from .foreground_monitor import ForegroundMonitor
from .foreground_rules import ForegroundRuleError, ForegroundRuleStore
from .hardware_bubble import HardwareStatusBubble
from .hardware_monitor import HardwareMonitorService, HardwareSnapshot
from .interaction import DragDirectionTracker
from .settings import PetSettings
from .state_coordinator import StateCoordinator


class PetWindow(QWidget):
    MIN_SCALE = 0.5
    MAX_SCALE = 2.5
    SCALE_STEP = 0.1
    SCALE_PRESETS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5)

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
        self._ambient_interval_provider = ambient_interval_provider or (
            lambda: random.SystemRandom().randint(
                8 * 60 * 1000,
                20 * 60 * 1000,
            )
        )
        self._ambient_timer = QTimer(self)
        self._ambient_timer.setSingleShot(True)
        self._ambient_timer.timeout.connect(self._play_idle_special)

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
        self._interaction_enabled = False
        if not self.state_coordinator.play_startup():
            self._interaction_enabled = True
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
        # Render at the screen's physical pixel density. Otherwise Windows DPI
        # scaling enlarges an already-scaled logical bitmap a second time and
        # makes the character look unnecessarily soft.
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

        # QWidget masks use logical coordinates. Keep a separate logical-size
        # alpha mask without touching or repositioning the production PNG.
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
            if self.state_coordinator.can_play_ambient():
                self._schedule_idle_special()

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
        self.move(
            self.frameGeometry().topLeft()
            + (old_center - self.frameGeometry().center())
        )
        if not self._source_pixmap.isNull():
            self._show_frame(self._source_pixmap)
        if self.hardware_bubble.isVisible():
            self.hardware_bubble.reposition()

    def set_animation_state(self, state_name: str) -> None:
        if not self._interaction_enabled:
            return
        self._cancel_hardware_diagnostic()
        self.state_coordinator.select_user_state(state_name)

    def set_scale(self, scale: float) -> None:
        if not self._interaction_enabled:
            return
        new_scale = min(self.MAX_SCALE, max(self.MIN_SCALE, round(scale, 2)))
        if new_scale == self.scale:
            return
        old_center = self.frameGeometry().center()
        self.scale = new_scale
        self._resize_canvas()
        self.move(self.frameGeometry().topLeft() + (old_center - self.frameGeometry().center()))
        self.move(
            self.settings.clamp_position(self.pos(), self.width(), self.height())
        )
        if not self._source_pixmap.isNull():
            self._show_frame(self._source_pixmap)
        if self.hardware_bubble.isVisible():
            self.hardware_bubble.reposition()
        self.settings.save_scale(self.scale)
        self.settings.save_position(self.pos())

    def build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu._spring_submenus = []
        menu._spring_action_groups = []
        for group_name in ("状态", "动作"):
            states = self.manifest.menu_states(group_name)
            if not states:
                continue
            submenu = QMenu(group_name, menu)
            menu.addMenu(submenu)
            menu._spring_submenus.append(submenu)
            for state in states:
                action = QAction(state.label, submenu)
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

        scale_menu = QMenu("缩放", menu)
        menu.addMenu(scale_menu)
        menu._spring_submenus.append(scale_menu)
        scale_group = QActionGroup(scale_menu)
        scale_group.setExclusive(True)
        menu._spring_action_groups.append(scale_group)
        for preset in self.SCALE_PRESETS:
            action = QAction(f"{round(preset * 100)}%", scale_menu)
            action.setCheckable(True)
            action.setData(preset)
            action.setChecked(abs(self.scale - preset) < 0.001)
            action.triggered.connect(
                lambda checked=False, value=preset: self.set_scale(value)
            )
            scale_group.addAction(action)
            scale_menu.addAction(action)

        menu.addSeparator()
        try:
            status = self.autostart.status()
        except AutostartError as exc:
            self._autostart_error = str(exc)
            status = None
        autostart_action = menu.addAction("开机自启动")
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

        menu.addSeparator()
        hardware_menu = QMenu("硬件状态感知", menu)
        menu.addMenu(hardware_menu)
        menu._spring_submenus.append(hardware_menu)
        hardware_available = self.hardware_monitor_service is not None
        hardware_busy = (
            self.hardware_monitor_service.busy
            if self.hardware_monitor_service is not None
            else False
        )
        overview_action = hardware_menu.addAction("系统概览")
        overview_action.setEnabled(hardware_available and not hardware_busy)
        overview_action.triggered.connect(
            lambda: self.request_hardware_diagnostic("overview")
        )
        vitals_action = hardware_menu.addAction("硬件体征")
        vitals_action.setEnabled(hardware_available and not hardware_busy)
        vitals_action.triggered.connect(
            lambda: self.request_hardware_diagnostic("vitals")
        )
        if not hardware_available:
            hardware_menu.setToolTip("硬件监控服务不可用")

        menu.addSeparator()
        follow_action = menu.addAction("跟随前台应用")
        follow_action.setCheckable(True)
        follow_action.setChecked(self._foreground_follow_enabled)
        follow_action.setEnabled(
            self.foreground_rules is not None
            and self.foreground_monitor is not None
            and self.foreground_monitor.available
        )
        if not follow_action.isEnabled():
            follow_action.setToolTip("仅 Windows 系统支持前台应用联动")
        follow_action.toggled.connect(self._set_foreground_follow_enabled)

        status_action = menu.addAction(self._foreground_status_text())
        status_action.setEnabled(False)

        edit_rules_action = menu.addAction("编辑应用规则")
        edit_rules_action.setEnabled(self.foreground_rules is not None)
        edit_rules_action.triggered.connect(self._edit_foreground_rules)

        reload_rules_action = menu.addAction("重新加载应用规则")
        reload_rules_action.setEnabled(self.foreground_rules is not None)
        reload_rules_action.triggered.connect(self._reload_foreground_rules)

        menu.addSeparator()
        exit_action = menu.addAction("退出")
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
            QMessageBox.warning(self, "开机自启动", str(exc))
            action = self.sender()
            if isinstance(action, QAction):
                action.blockSignals(True)
                try:
                    action.setChecked(self.autostart.status().enabled)
                except AutostartError:
                    action.setChecked(False)
                action.blockSignals(False)

    def _set_foreground_follow_enabled(self, enabled: bool) -> None:
        self._foreground_follow_enabled = enabled
        self.settings.save_foreground_follow_enabled(enabled)
        if enabled and self.foreground_monitor is not None:
            self.foreground_monitor.check_now()
            self._apply_current_foreground(force=True)

    def _foreground_status_text(self) -> str:
        if self._foreground_process is None:
            return "当前应用：尚未识别"
        if self._foreground_match_label is None:
            return f"当前应用：{self._foreground_process}（无规则）"
        state_label = self.manifest.states[self._foreground_match_state].label
        return f"当前应用：{self._foreground_match_label} → {state_label}"

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
        self._apply_current_foreground(force=force)

    def _apply_current_foreground(self, *, force: bool = False) -> None:
        if (
            not self._foreground_follow_enabled
            or self._foreground_process is None
            or self._foreground_match_state is None
        ):
            return
        self.state_coordinator.apply_foreground_state(
            self._foreground_process,
            self._foreground_match_state,
            force=force,
        )

    def _edit_foreground_rules(self) -> None:
        if self.foreground_rules is None:
            return
        try:
            startfile = getattr(os, "startfile")
            startfile(str(self.foreground_rules.path))
        except (AttributeError, OSError) as exc:
            QMessageBox.warning(self, "编辑应用规则", f"无法打开规则文件：{exc}")

    def _reload_foreground_rules(self) -> None:
        if self.foreground_rules is None:
            return
        try:
            config = self.foreground_rules.load()
        except ForegroundRuleError as exc:
            QMessageBox.warning(
                self,
                "重新加载应用规则",
                f"{exc}\n\n已继续使用上一次有效规则。",
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
            "overview": ("hardware-overview", "系统概览"),
            "vitals": ("hardware-vitals", "硬件体征"),
        }
        if kind not in configuration:
            raise ValueError(f"Unknown hardware diagnostic: {kind}")
        trigger, title = configuration[kind]
        self._cancel_hardware_diagnostic()
        self._diagnostic_kind = kind
        if not self.state_coordinator.play_diagnostic(trigger):
            self._diagnostic_kind = None
            return
        self.hardware_bubble.show_loading(title, self)
        self.hardware_monitor_service.request(kind)

    def _on_hardware_snapshot(self, snapshot: HardwareSnapshot) -> None:
        if snapshot.kind != self._diagnostic_kind or self._exit_requested:
            return
        title = "系统概览" if snapshot.kind == "overview" else "硬件体征"
        self.hardware_bubble.show_snapshot(title, snapshot, self)

    def _on_hardware_collection_failed(self, message: str) -> None:
        if self._diagnostic_kind is None or self._exit_requested:
            return
        title = "系统概览" if self._diagnostic_kind == "overview" else "硬件体征"
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
        trigger = self._drag_tracker.update(global_position.x())
        if trigger is None:
            return
        self._drag_animation_active = self.state_coordinator.update_drag(trigger)

    def _finish_drag(self) -> None:
        self._drag_offset = None
        self._drag_tracker.reset()
        self.move(
            self.settings.clamp_position(
                self.pos(), self.width(), self.height()
            )
        )
        self.settings.save_position(self.pos())
        self.state_coordinator.finish_drag()
        self._drag_animation_active = False

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
        self._drag_offset = None
        self._drag_tracker.reset()
        self._save_settings()
        self._cancel_hardware_diagnostic()
        if not self.state_coordinator.begin_exit():
            self._allow_close = True
            self.close()

    def force_exit_for_session_end(self) -> None:
        self._force_exit = True
        self._interaction_enabled = False
        self._ambient_timer.stop()
        self._save_settings()
        self._cancel_hardware_diagnostic()
        if self.foreground_monitor is not None:
            self.foreground_monitor.stop()
        self.controller.stop()
        if self.hardware_monitor_service is not None:
            self.hardware_monitor_service.shutdown()
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _save_settings(self) -> None:
        self.settings.save_position(self.pos())
        self.settings.save_scale(self.scale)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._force_exit or self._allow_close:
            self._save_settings()
            if self.foreground_monitor is not None:
                self.foreground_monitor.stop()
            self._cancel_hardware_diagnostic()
            if self.hardware_monitor_service is not None:
                self.hardware_monitor_service.shutdown()
            self.controller.stop()
            event.accept()
            return
        event.ignore()
        self.request_exit()
