from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from .asset_loader import AnimationManifest


class AnimationController(QObject):
    frame_changed = Signal(QPixmap)
    state_changed = Signal(str)
    animation_finished = Signal(str)

    def __init__(self, manifest: AnimationManifest, parent: QObject | None = None):
        super().__init__(parent)
        self.manifest = manifest
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance)
        self._state_name = manifest.default_state
        self._frame_index = 0
        self._pixmaps = {
            name: tuple(QPixmap(str(path)) for path in state.frame_paths)
            for name, state in manifest.states.items()
        }

    @property
    def state_name(self) -> str:
        return self._state_name

    @property
    def frame_index(self) -> int:
        return self._frame_index

    @property
    def current_pixmap(self) -> QPixmap:
        return self._pixmaps[self._state_name][self._frame_index]

    def start(self, state_name: str | None = None) -> None:
        self.set_state(state_name or self._state_name)

    def set_state(self, state_name: str) -> None:
        if state_name not in self.manifest.states:
            raise KeyError(f"Unknown animation state: {state_name}")
        self.timer.stop()
        self._state_name = state_name
        self._frame_index = 0
        self.state_changed.emit(state_name)
        self._emit_current_frame()

    def play_trigger(self, trigger: str) -> bool:
        state_name = self.manifest.state_for_trigger(trigger)
        if state_name is None:
            return False
        self.set_state(state_name)
        return True

    def stop(self) -> None:
        self.timer.stop()

    def _emit_current_frame(self) -> None:
        self.frame_changed.emit(self.current_pixmap)
        duration = self.manifest.states[self._state_name].durations_ms[
            self._frame_index
        ]
        self.timer.start(round(duration / self.manifest.playback_rate))

    def _advance(self) -> None:
        state = self.manifest.states[self._state_name]
        next_index = self._frame_index + 1
        if next_index >= len(state.frame_paths):
            if state.is_looping:
                self._frame_index = 0
                self._emit_current_frame()
            else:
                finished_state = self._state_name
                self.timer.stop()
                self.animation_finished.emit(finished_state)
                if (
                    self._state_name == finished_state
                    and state.return_to is not None
                ):
                    self.set_state(state.return_to)
            return
        self._frame_index = next_index
        self._emit_current_frame()
