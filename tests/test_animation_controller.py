from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from spring_pet.animation_controller import AnimationController
from spring_pet.asset_loader import load_animation_manifest


ROOT = Path(__file__).resolve().parents[1]


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_controller_uses_one_reusable_timer() -> None:
    _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    controller = AnimationController(manifest)
    timer = controller.timer
    controller.set_state("waiting")
    controller.set_state("review")
    assert controller.timer is timer
    assert controller.timer.interval() == 317


def test_one_shot_returns_to_idle() -> None:
    _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    controller = AnimationController(manifest)
    controller.set_state("jumping")
    for _ in range(5):
        controller._advance()
    assert controller.state_name == "idle"
    assert controller.frame_index == 0
    controller.stop()


def test_trigger_and_completion_are_manifest_driven() -> None:
    _app()
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    controller = AnimationController(manifest)
    finished = []
    controller.animation_finished.connect(finished.append)

    assert controller.play_trigger("exit")
    assert controller.state_name == "waving"
    for _ in range(4):
        controller._advance()

    assert finished == ["waving"]
    assert controller.state_name == "waving"
    assert not controller.timer.isActive()
    assert not controller.play_trigger("unknown-trigger")
