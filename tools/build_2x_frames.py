from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from PIL import Image


FRAME_COUNTS = {
    "idle": 6,
    "running-right": 8,
    "running-left": 8,
    "waving": 4,
    "jumping": 5,
    "failed": 8,
    "waiting": 6,
    "running": 6,
    "review": 6,
    "heart": 6,
    "sleeping": 6,
    "listening": 6,
    "noting": 6,
    "inspect": 6,
    "examine": 6,
}
SCALE = 2
CANVAS = (192, 208)
OUTPUT_CANVAS = (CANVAS[0] * SCALE, CANVAS[1] * SCALE)
CORE_PROFILES = {
    # Standing states use the lower body as their stable identity anchor.
    "idle": (0.72, 1.00),
    "waving": (0.72, 1.00),
    "waiting": (0.72, 1.00),
    "running": (0.72, 1.00),
    "review": (0.72, 1.00),
    "sleeping": (0.72, 1.00),
    "heart": (0.72, 1.00),
    "listening": (0.72, 1.00),
    "noting": (0.72, 1.00),
    "inspect": (0.70, 1.00),
    "examine": (0.70, 1.00),
    # Motion states use the body core so limbs do not distort scale.
    "failed": (0.42, 0.68),
    "running-right": (0.30, 0.62),
    "jumping": (0.28, 0.62),
}


def alpha_bbox(path: Path) -> tuple[int, int, int, int]:
    with Image.open(path) as image:
        bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"Frame is empty: {path}")
    return bbox


def core_metrics(
    image: Image.Image,
    start_fraction: float,
    end_fraction: float,
) -> tuple[int, float, int]:
    """Measure a stable body band plus the full-frame vertical baseline."""
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("Frame is empty")
    start_y = round(
        bbox[1] + (bbox[3] - bbox[1]) * start_fraction
    )
    end_y = round(
        bbox[1] + (bbox[3] - bbox[1]) * end_fraction
    )
    hard_alpha = alpha.point(lambda value: 255 if value > 16 else 0)
    region_bbox = hard_alpha.crop(
        (0, start_y, image.width, end_y)
    ).getbbox()
    if region_bbox is None:
        raise ValueError("Frame has no lower-body core")
    left, _top, right, bottom = region_bbox
    return right - left, (left + right) / 2, bbox[3]


def extract_slot(strip: Image.Image, index: int, count: int) -> Image.Image:
    left = round(index * strip.width / count)
    right = round((index + 1) * strip.width / count)
    slot = strip.crop((left, 0, right, strip.height))
    return largest_component(slot)


def largest_component(image: Image.Image, alpha_threshold: int = 16) -> Image.Image:
    """Keep the main sprite and discard neighboring-slot fragments/noise."""
    alpha = image.getchannel("A")
    width, height = image.size
    alpha_data = alpha.tobytes()
    visited = bytearray(width * height)
    largest_pixels: list[int] = []
    largest_bbox: tuple[int, int, int, int] | None = None

    for start, alpha_value in enumerate(alpha_data):
        if alpha_value <= alpha_threshold or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        pixels: list[int] = []
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        while stack:
            current = stack.pop()
            pixels.append(current)
            x = current % width
            y = current // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            for neighbor in (
                current - 1 if x > 0 else -1,
                current + 1 if x + 1 < width else -1,
                current - width if y > 0 else -1,
                current + width if y + 1 < height else -1,
            ):
                if (
                    neighbor >= 0
                    and not visited[neighbor]
                    and alpha_data[neighbor] > alpha_threshold
                ):
                    visited[neighbor] = 1
                    stack.append(neighbor)
        if len(pixels) > len(largest_pixels):
            largest_pixels = pixels
            largest_bbox = (min_x, min_y, max_x + 1, max_y + 1)

    if largest_bbox is None:
        raise ValueError("Strip slot is empty")

    cleaned = Image.new("RGBA", image.size, (0, 0, 0, 0))
    source_pixels = image.load()
    cleaned_pixels = cleaned.load()
    for pixel_index in largest_pixels:
        x = pixel_index % width
        y = pixel_index // width
        cleaned_pixels[x, y] = source_pixels[x, y]
    return cleaned.crop(largest_bbox)


def build_frame(
    sprite: Image.Image,
    output_frame: Path,
    frame_scale: float,
    target_left: int,
    target_top: int,
) -> None:
    width = max(1, round(sprite.width * frame_scale))
    height = max(1, round(sprite.height * frame_scale))
    detailed_sprite = sprite.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", OUTPUT_CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(detailed_sprite, (target_left, target_top))
    output_frame.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_frame.with_suffix(".tmp.png")
    canvas.save(temporary, optimize=True)
    temporary.replace(output_frame)


def build_state(
    state: str,
    strips_root: Path,
    source_root: Path,
    output_root: Path,
) -> None:
    count = FRAME_COUNTS[state]
    with Image.open(strips_root / f"{state}.png") as opened:
        strip = opened.convert("RGBA")
        sprites = [extract_slot(strip, index, count) for index in range(count)]

        source_frames = [
            source_root / state / f"{index:02}.png"
            for index in range(count)
        ]
        if state in CORE_PROFILES:
            start_fraction, end_fraction = CORE_PROFILES[state]
            source_images = [
                Image.open(path).convert("RGBA") for path in source_frames
            ]
            source_cores = [
                core_metrics(image, start_fraction, end_fraction)
                for image in source_images
            ]

            for index, (sprite, source_core) in enumerate(
                zip(sprites, source_cores)
            ):
                core_width, core_center, core_bottom = core_metrics(
                    sprite,
                    start_fraction,
                    end_fraction,
                )
                target_core_width = source_core[0] * SCALE
                target_core_center = source_core[1] * SCALE
                target_core_bottom = source_core[2] * SCALE
                frame_scale = target_core_width / core_width
                width = round(sprite.width * frame_scale)
                height = round(sprite.height * frame_scale)
                target_left = round(
                    target_core_center - core_center * frame_scale
                )
                target_top = round(
                    target_core_bottom - core_bottom * frame_scale
                )
                if (
                    target_left < 0
                    or target_top < 0
                    or target_left + width > OUTPUT_CANVAS[0]
                    or target_top + height > OUTPUT_CANVAS[1]
                ):
                    raise ValueError(
                        f"Stable core placement does not fit {state} frame {index}"
                    )
                build_frame(
                    sprite,
                    output_root / state / f"{index:02}.png",
                    frame_scale,
                    target_left,
                    target_top,
                )
            return

        height_scales = []
        for sprite, source_frame in zip(sprites, source_frames):
            _left, top, _right, bottom = alpha_bbox(source_frame)
            height_scales.append((bottom - top) * SCALE / sprite.height)

        # Uniform state scale prevents frame-to-frame body ballooning.
        state_scale = statistics.median(height_scales)
        max_safe_scale = min(
            (OUTPUT_CANVAS[0] - 10 * SCALE) / max(sprite.width for sprite in sprites),
            (OUTPUT_CANVAS[1] - 10 * SCALE) / max(sprite.height for sprite in sprites),
        )
        state_scale = min(state_scale, max_safe_scale)

        for index, sprite in enumerate(sprites):
            left, _top, right, bottom = alpha_bbox(source_frames[index])
            width = round(sprite.width * state_scale)
            height = round(sprite.height * state_scale)
            target_left = round(
                (left + right) * SCALE / 2 - width / 2
            )
            target_top = bottom * SCALE - height
            build_frame(
                sprite,
                output_root / state / f"{index:02}.png",
                state_scale,
                target_left,
                target_top,
            )


def mirror_running_left(output_root: Path) -> None:
    right_dir = output_root / "running-right"
    left_dir = output_root / "running-left"
    left_dir.mkdir(parents=True, exist_ok=True)
    for index in range(FRAME_COUNTS["running-right"]):
        with Image.open(right_dir / f"{index:02}.png") as right:
            mirrored = right.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            output = left_dir / f"{index:02}.png"
            temporary = output.with_suffix(".tmp.png")
            mirrored.save(temporary, optimize=True)
            temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build 2x frames from approved high-resolution row strips."
    )
    parser.add_argument("--strips-root", default="decoded-clean")
    parser.add_argument("--source-root", default="assets/animations")
    parser.add_argument("--output-root", default="assets/animations@2x")
    args = parser.parse_args()

    strips_root = Path(args.strips_root).resolve()
    source_root = Path(args.source_root).resolve()
    output_root = Path(args.output_root).resolve()

    for state in FRAME_COUNTS:
        if state != "running-left":
            build_state(state, strips_root, source_root, output_root)
    mirror_running_left(output_root)


if __name__ == "__main__":
    main()
