from __future__ import annotations

from .animation_controller import AnimationController
from .asset_loader import AnimationManifest


class StateCoordinator:
    """Coordinate persistent states and higher-priority transient animations."""

    def __init__(
        self,
        manifest: AnimationManifest,
        controller: AnimationController,
        base_state: str,
    ):
        if not manifest.states[base_state].is_persistent:
            raise ValueError(f"Base state must be persistent: {base_state}")
        self.manifest = manifest
        self.controller = controller
        self.base_state = base_state
        self.mode: str | None = None
        self._last_configured_process: str | None = None
        self._diagnostic_state: str | None = None

    @property
    def is_transient(self) -> bool:
        return self.mode is not None

    def start(self) -> None:
        self.controller.start(self.base_state)

    def play_startup(self) -> bool:
        self.mode = "startup"
        if self.controller.play_trigger("startup"):
            return True
        self.mode = None
        self.start()
        return False

    def select_user_state(self, state_name: str) -> None:
        state = self.manifest.states[state_name]
        if state.is_persistent:
            self.base_state = state_name
            self.mode = None
            self.controller.set_state(state_name)
            return
        if state.role == "action":
            self.mode = "action"
            self.controller.set_state(state_name)

    def apply_foreground_state(
        self,
        process_name: str,
        state_name: str,
        *,
        force: bool = False,
    ) -> bool:
        state = self.manifest.states.get(state_name)
        if state is None or not state.is_persistent:
            return False
        normalized_process = process_name.casefold()
        if not force and normalized_process == self._last_configured_process:
            return False
        self._last_configured_process = normalized_process
        self.base_state = state_name
        if self.mode is None:
            self.controller.set_state(state_name)
        return True

    def begin_drag(self) -> None:
        current = self.manifest.states[self.controller.state_name]
        if current.is_persistent:
            self.base_state = current.name
        else:
            self.controller.stop()
        self.mode = "drag"

    def update_drag(self, trigger: str) -> bool:
        if self.mode != "drag":
            return False
        target = self.manifest.state_for_trigger(trigger)
        if target is None:
            return False
        if target != self.controller.state_name:
            self.controller.set_state(target)
        return True

    def finish_drag(self) -> None:
        if self.mode == "drag":
            self.mode = None
            self.controller.set_state(self.base_state)

    def can_play_ambient(self) -> bool:
        return (
            self.mode is None
            and self.base_state == self.manifest.default_state
            and self.controller.state_name == self.manifest.default_state
        )

    def play_ambient(self) -> bool:
        if not self.can_play_ambient():
            return False
        self.mode = "ambient"
        if self.controller.play_trigger("startup"):
            return True
        self.mode = None
        return False

    def begin_exit(self) -> bool:
        self.mode = "exit"
        return self.controller.play_trigger("exit")

    def play_diagnostic(self, trigger: str) -> bool:
        state_name = self.manifest.state_for_trigger(trigger)
        if state_name is None:
            return False
        self.mode = "diagnostic"
        self._diagnostic_state = state_name
        self.controller.set_state(state_name)
        return True

    def animation_finished(self, state_name: str) -> str | None:
        expected_trigger = {
            "startup": "startup",
            "ambient": "startup",
            "exit": "exit",
        }.get(self.mode)
        if expected_trigger is not None:
            expected_state = self.manifest.state_for_trigger(expected_trigger)
            if state_name != expected_state:
                return None

        if self.mode == "diagnostic" and state_name != self._diagnostic_state:
            return None

        completed_mode = self.mode
        if completed_mode in {"startup", "ambient", "action", "diagnostic"}:
            self.mode = None
            self._diagnostic_state = None
            self.controller.set_state(self.base_state)
        return completed_mode
