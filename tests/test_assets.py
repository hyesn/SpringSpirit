from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys

from PIL import Image

from spring_pet.asset_loader import load_animation_manifest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_2x_frames import (
    CORE_PROFILES,
    FRAME_COUNTS,
    core_metrics,
    extract_slot,
)


def test_manifest_validates_all_production_frames() -> None:
    manifest = load_animation_manifest(ROOT / "assets" / "animation_manifest.json")
    assert manifest.canvas == (192, 208)
    assert manifest.asset_scale == 2
    assert manifest.playback_rate == 0.6
    assert set(manifest.states) == {
        "idle",
        "running-right",
        "running-left",
        "waving",
        "jumping",
        "failed",
        "waiting",
        "running",
        "review",
        "sleeping",
        "heart",
        "listening",
        "noting",
    }
    assert sum(len(state.frame_paths) for state in manifest.states.values()) == 81
    assert manifest.state_for_trigger("drag-left") == "running-left"
    assert manifest.state_for_trigger("drag-right") == "running-right"
    assert manifest.state_for_trigger("exit") == "waving"
    assert manifest.state_for_trigger("startup") == "heart"
    assert [state.name for state in manifest.menu_states("状态")] == [
        "idle",
        "waiting",
        "running",
        "review",
        "sleeping",
        "listening",
        "noting",
    ]
    assert [state.name for state in manifest.menu_states("动作")] == [
        "jumping",
        "failed",
    ]
    for state in manifest.states.values():
        for frame_path in state.frame_paths:
            with Image.open(frame_path) as image:
                assert image.size == (384, 416)
                assert image.mode == "RGBA"


def test_new_state_frames_are_clean_and_complete() -> None:
    for scale_root, expected_size in (
        ("animations", (192, 208)),
        ("animations@2x", (384, 416)),
    ):
        for state in ("heart", "sleeping", "listening", "noting"):
            paths = sorted((ROOT / "assets" / scale_root / state).glob("*.png"))
            assert len(paths) == 6
            for path in paths:
                with Image.open(path) as image:
                    assert image.size == expected_size
                    assert image.mode == "RGBA"
                    assert image.getchannel("A").getbbox() is not None
                    greenish_visible = sum(
                        1
                        for red, green, blue, alpha in image.get_flattened_data()
                        if alpha > 32
                        and green > 180
                        and green > red * 1.8
                        and green > blue * 1.8
                    )
                    assert greenish_visible == 0


def test_jumping_keeps_low_high_low_canvas_trajectory() -> None:
    tops = []
    bottoms = []
    for path in sorted((ROOT / "assets" / "animations" / "jumping").glob("*.png")):
        with Image.open(path) as image:
            bbox = image.getchannel("A").getbbox()
        assert bbox is not None
        tops.append(bbox[1])
        bottoms.append(bbox[3])
    assert tops == [62, 31, 6, 25, 62]
    assert bottoms == [202, 190, 163, 181, 202]


def test_running_left_preserves_framewise_mirror_structure() -> None:
    right_dir = ROOT / "assets" / "animations@2x" / "running-right"
    left_dir = ROOT / "assets" / "animations@2x" / "running-left"
    for index in range(8):
        with Image.open(right_dir / f"{index:02}.png") as right:
            mirrored = right.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        with Image.open(left_dir / f"{index:02}.png") as left:
            assert mirrored.tobytes() == left.tobytes()


def test_high_resolution_state_frames_keep_consistent_subject_coverage() -> None:
    for state in ("waiting", "running", "review"):
        source_dir = ROOT / "assets" / "animations" / state
        high_resolution_dir = ROOT / "assets" / "animations@2x" / state
        for source_path in sorted(source_dir.glob("*.png")):
            with Image.open(source_path) as source:
                source_pixels = sum(
                    1
                    for value in source.getchannel("A").get_flattened_data()
                    if value
                )
            with Image.open(high_resolution_dir / source_path.name) as detailed:
                detailed_pixels = sum(
                    1
                    for value in detailed.getchannel("A").get_flattened_data()
                    if value
                )
            ratio = detailed_pixels / source_pixels
            assert 3.8 < ratio < 4.4


def test_high_resolution_frames_use_one_uniform_scale_per_state() -> None:
    for state, frame_count in FRAME_COUNTS.items():
        if state == "running-left" or state in CORE_PROFILES:
            continue
        with Image.open(ROOT / "decoded-clean" / f"{state}.png") as opened:
            strip = opened.convert("RGBA")
            scales = []
            for index in range(frame_count):
                sprite = extract_slot(strip, index, frame_count)
                with Image.open(
                    ROOT
                    / "assets"
                    / "animations@2x"
                    / state
                    / f"{index:02}.png"
                ) as output:
                    bbox = output.getchannel("A").getbbox()
                assert bbox is not None
                scales.append(
                    (
                        (bbox[2] - bbox[0]) / sprite.width,
                        (bbox[3] - bbox[1]) / sprite.height,
                    )
                )
        width_scales = [scale[0] for scale in scales]
        height_scales = [scale[1] for scale in scales]
        assert max(width_scales) - min(width_scales) < 0.006
        assert max(height_scales) - min(height_scales) < 0.003


def test_all_action_frames_match_approved_character_core_geometry() -> None:
    for state, (start_fraction, end_fraction) in CORE_PROFILES.items():
        source_paths = sorted(
            (ROOT / "assets" / "animations" / state).glob("*.png")
        )
        detailed_paths = sorted(
            (ROOT / "assets" / "animations@2x" / state).glob("*.png")
        )
        assert len(source_paths) == len(detailed_paths)
        for source_path, detailed_path in zip(source_paths, detailed_paths):
            with Image.open(source_path) as source:
                source_core = core_metrics(
                    source.convert("RGBA"),
                    start_fraction,
                    end_fraction,
                )
            with Image.open(detailed_path) as detailed:
                detailed_core = core_metrics(
                    detailed.convert("RGBA"),
                    start_fraction,
                    end_fraction,
                )
            assert abs(detailed_core[0] - source_core[0] * 2) <= 2
            assert abs(detailed_core[1] - source_core[1] * 2) <= 2
            assert abs(detailed_core[2] - source_core[2] * 2) <= 1


def test_new_menu_action_is_discovered_from_manifest(tmp_path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    source_manifest = ROOT / "assets" / "animation_manifest.json"
    data = json.loads(source_manifest.read_text(encoding="utf-8"))
    data["states"]["celebrate"] = {
        "label": "庆祝",
        "frames": 1,
        "durations_ms": [500],
        "behavior": "once",
        "role": "action",
        "menu_group": "动作",
        "persist": False,
        "return_to": "idle",
        "trigger": None,
        "menu_order": 15,
    }
    (assets / "animation_manifest.json").write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )

    source_frames = ROOT / "assets" / "animations@2x"
    target_frames = assets / "animations@2x"
    for state_name, config in data["states"].items():
        state_dir = target_frames / state_name
        state_dir.mkdir(parents=True)
        source_state = (
            source_frames / "idle"
            if state_name == "celebrate"
            else source_frames / state_name
        )
        for index in range(config["frames"]):
            shutil.copy2(source_state / f"{index:02}.png", state_dir)

    manifest = load_animation_manifest(assets / "animation_manifest.json")
    assert [state.name for state in manifest.menu_states("动作")] == [
        "jumping",
        "celebrate",
        "failed",
    ]
