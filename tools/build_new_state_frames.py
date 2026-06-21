from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from build_2x_frames import largest_component


CANVAS = (192, 208)
PADDING = 5


def extract_sprites(strip: Image.Image, frame_count: int) -> list[Image.Image]:
    sprites = []
    slot_width = strip.width / frame_count
    for index in range(frame_count):
        left = round(index * slot_width)
        right = round((index + 1) * slot_width)
        sprites.append(largest_component(strip.crop((left, 0, right, strip.height))))
    return sprites


def compose_frames(sprites: list[Image.Image], scale: int) -> list[Image.Image]:
    max_width = max(sprite.width for sprite in sprites)
    max_height = max(sprite.height for sprite in sprites)
    base_scale = min(
        (CANVAS[0] - PADDING * 2) / max_width,
        (CANVAS[1] - PADDING * 2) / max_height,
    )
    output_size = (CANVAS[0] * scale, CANVAS[1] * scale)
    frames = []
    for sprite in sprites:
        width = max(1, round(sprite.width * base_scale * scale))
        height = max(1, round(sprite.height * base_scale * scale))
        resized = sprite.resize((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", output_size, (0, 0, 0, 0))
        left = (output_size[0] - width) // 2
        bottom = output_size[1] - PADDING * scale
        canvas.alpha_composite(resized, (left, bottom - height))
        frames.append(canvas)
    return frames


def save_frames(frames: list[Image.Image], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        output = output_dir / f"{index:02}.png"
        temporary = output.with_suffix(".tmp.png")
        frame.save(temporary, optimize=True)
        temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build stable 1x and 2x frames for a new transparent row strip."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--assets-root", default="assets")
    args = parser.parse_args()

    with Image.open(args.input) as opened:
        sprites = extract_sprites(opened.convert("RGBA"), args.frames)

    assets_root = Path(args.assets_root).resolve()
    save_frames(
        compose_frames(sprites, 1),
        assets_root / "animations" / args.state,
    )
    save_frames(
        compose_frames(sprites, 2),
        assets_root / "animations@2x" / args.state,
    )


if __name__ == "__main__":
    main()
