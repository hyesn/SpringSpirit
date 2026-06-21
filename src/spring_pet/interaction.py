from __future__ import annotations


class DragDirectionTracker:
    """Turn horizontal drag movement into stable direction triggers."""

    def __init__(self, threshold: int = 4):
        self.threshold = threshold
        self._anchor_x: int | None = None

    def start(self, x: int) -> None:
        self._anchor_x = x

    def update(self, x: int) -> str | None:
        if self._anchor_x is None:
            self.start(x)
            return None
        delta = x - self._anchor_x
        if abs(delta) < self.threshold:
            return None
        self._anchor_x = x
        return "drag-right" if delta > 0 else "drag-left"

    def reset(self) -> None:
        self._anchor_x = None
