from spring_pet.interaction import DragDirectionTracker


def test_drag_direction_uses_threshold_and_supports_reversal() -> None:
    tracker = DragDirectionTracker(threshold=4)
    tracker.start(100)

    assert tracker.update(103) is None
    assert tracker.update(104) == "drag-right"
    assert tracker.update(102) is None
    assert tracker.update(100) == "drag-left"
    tracker.reset()
    assert tracker.update(50) is None
