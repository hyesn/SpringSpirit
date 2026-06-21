from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


CANVAS = (192, 208)
FRAME_COUNT = 6
CORE_BAND = (0.70, 1.00)
BOTTOM_MARGIN = 5


def remove_green_screen(
    image: Image.Image,
    *,
    crop: bool = True,
) -> Image.Image:
    source = image.convert("RGBA")
    pixels = []
    for red, green, blue, _alpha in source.get_flattened_data():
        dominance = green - max(red, blue)
        if green >= 175 and dominance >= 65 and green >= red * 1.45:
            alpha = 0
        elif green >= 135 and dominance >= 45 and green >= red * 1.30:
            alpha = max(0, min(255, round((65 - dominance) * 12.75)))
        else:
            alpha = 255
        if alpha:
            green = min(green, max(red, blue) + 24)
        pixels.append((red, green, blue, alpha))
    cleaned = Image.new("RGBA", source.size)
    cleaned.putdata(pixels)
    bbox = cleaned.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("Green-screen removal produced an empty frame")
    return cleaned.crop(bbox) if crop else cleaned


def keep_largest_component(
    image: Image.Image,
    alpha_threshold: int = 24,
) -> Image.Image:
    alpha = image.getchannel("A")
    width, height = image.size
    alpha_data = alpha.tobytes()
    visited = bytearray(width * height)
    largest: list[int] = []
    for start, value in enumerate(alpha_data):
        if value <= alpha_threshold or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            x = current % width
            for neighbor in (
                current - 1 if x else -1,
                current + 1 if x + 1 < width else -1,
                current - width if current >= width else -1,
                current + width if current + width < width * height else -1,
            ):
                if (
                    neighbor >= 0
                    and not visited[neighbor]
                    and alpha_data[neighbor] > alpha_threshold
                ):
                    visited[neighbor] = 1
                    stack.append(neighbor)
        if len(component) > len(largest):
            largest = component
    if not largest:
        raise ValueError("Sprite contains no visible component")
    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    source_pixels = image.load()
    output_pixels = output.load()
    for index in largest:
        x = index % width
        y = index // width
        output_pixels[x, y] = source_pixels[x, y]
    return output


def extract_sprites(strip: Image.Image) -> list[Image.Image]:
    """Extract complete subjects before assigning them to animation frames.

    Generated props can cross a nominal equal-width slot boundary. Segmenting
    the transparent full strip first keeps those connected pixels with their
    owner instead of cutting them into the neighboring frame.
    """
    cleaned = remove_green_screen(strip, crop=False)
    components = connected_components(cleaned)
    substantial = [
        component
        for component in components
        if component[4] >= cleaned.width * cleaned.height * 0.002
    ]
    subjects = sorted(substantial, key=lambda component: component[0])
    if len(subjects) != FRAME_COUNT:
        raise ValueError(
            f"Expected {FRAME_COUNT} complete subjects, found {len(subjects)}"
        )
    sprites = []
    for left, top, right, bottom, _size in subjects:
        sprite = cleaned.crop((left, top, right, bottom))
        sprite = keep_largest_component(sprite)
        bbox = sprite.getchannel("A").getbbox()
        if bbox is None:
            raise ValueError("Extracted subject is empty")
        sprites.append(sprite.crop(bbox))
    return sprites


def connected_components(
    image: Image.Image,
    alpha_threshold: int = 24,
) -> list[tuple[int, int, int, int, int]]:
    alpha = image.getchannel("A")
    width, height = image.size
    alpha_data = alpha.tobytes()
    visited = bytearray(width * height)
    components: list[tuple[int, int, int, int, int]] = []
    for start, value in enumerate(alpha_data):
        if value <= alpha_threshold or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        size = 0
        min_x, min_y = width, height
        max_x = max_y = 0
        while stack:
            current = stack.pop()
            size += 1
            x = current % width
            y = current // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            for neighbor in (
                current - 1 if x else -1,
                current + 1 if x + 1 < width else -1,
                current - width if y else -1,
                current + width if y + 1 < height else -1,
            ):
                if (
                    neighbor >= 0
                    and not visited[neighbor]
                    and alpha_data[neighbor] > alpha_threshold
                ):
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components.append((min_x, min_y, max_x + 1, max_y + 1, size))
    return components


def core_geometry(image: Image.Image) -> tuple[int, float, int]:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("Sprite is empty")
    start_y = round(bbox[1] + (bbox[3] - bbox[1]) * CORE_BAND[0])
    end_y = round(bbox[1] + (bbox[3] - bbox[1]) * CORE_BAND[1])
    hard_alpha = alpha.point(lambda value: 255 if value > 24 else 0)
    core_bbox = hard_alpha.crop((0, start_y, image.width, end_y)).getbbox()
    if core_bbox is None:
        raise ValueError("Sprite has no stable lower-body core")
    left, _top, right, _bottom = core_bbox
    return right - left, (left + right) / 2, bbox[3]


def compose_frames(sprites: list[Image.Image], scale: int) -> list[Image.Image]:
    core_widths = [core_geometry(sprite)[0] for sprite in sprites]
    target_core_width = 74 * scale
    state_scale = target_core_width / (sum(core_widths) / len(core_widths))
    safe_scale = min(
        (CANVAS[0] * scale - 8 * scale) / max(sprite.width for sprite in sprites),
        (CANVAS[1] * scale - 8 * scale) / max(sprite.height for sprite in sprites),
    )
    state_scale = min(state_scale, safe_scale)
    output_size = (CANVAS[0] * scale, CANVAS[1] * scale)
    target_center = output_size[0] / 2
    target_bottom = output_size[1] - BOTTOM_MARGIN * scale
    frames = []
    for sprite in sprites:
        _core_width, core_center, core_bottom = core_geometry(sprite)
        width = max(1, round(sprite.width * state_scale))
        height = max(1, round(sprite.height * state_scale))
        resized = sprite.resize((width, height), Image.Resampling.LANCZOS)
        left = round(target_center - core_center * state_scale)
        top = round(target_bottom - core_bottom * state_scale)
        if left < 0 or top < 0 or left + width > output_size[0] or top + height > output_size[1]:
            raise ValueError("Stable sprite placement exceeds the output canvas")
        frame = Image.new("RGBA", output_size, (0, 0, 0, 0))
        frame.alpha_composite(resized, (left, top))
        frames.append(frame)
    return frames


def save_frames(frames: list[Image.Image], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        output = output_dir / f"{index:02}.png"
        temporary = output.with_suffix(".tmp.png")
        frame.save(temporary, optimize=True)
        temporary.replace(output)


def save_contact_sheet(
    states: dict[str, list[Image.Image]],
    output: Path,
) -> None:
    cell = (192, 208)
    label_height = 28
    sheet = Image.new(
        "RGBA",
        (cell[0] * FRAME_COUNT, (cell[1] + label_height) * len(states)),
        (245, 245, 245, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for row, (state, frames) in enumerate(states.items()):
        y = row * (cell[1] + label_height)
        draw.text((8, y + 6), state, fill=(30, 30, 30, 255))
        for column, frame in enumerate(frames):
            sheet.alpha_composite(frame, (column * cell[0], y + label_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output, quality=95)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded-root", default="decoded")
    parser.add_argument("--assets-root", default="assets")
    parser.add_argument("--qa-output", default="build/hardware-animation-contact-sheet.jpg")
    args = parser.parse_args()

    decoded_root = Path(args.decoded_root)
    assets_root = Path(args.assets_root)
    qa_states: dict[str, list[Image.Image]] = {}
    for state in ("inspect", "examine"):
        with Image.open(decoded_root / f"{state}.png") as opened:
            sprites = extract_sprites(opened)
        frames_1x = compose_frames(sprites, 1)
        frames_2x = compose_frames(sprites, 2)
        save_frames(frames_1x, assets_root / "animations" / state)
        save_frames(frames_2x, assets_root / "animations@2x" / state)
        qa_states[state] = frames_1x
    save_contact_sheet(qa_states, Path(args.qa_output))


if __name__ == "__main__":
    main()
