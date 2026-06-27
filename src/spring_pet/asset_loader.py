from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtGui import QImage


class AssetValidationError(RuntimeError):
    """Raised when production animation assets do not match the manifest."""


@dataclass(frozen=True)
class AnimationState:
    name: str
    label: str
    frame_paths: tuple[Path, ...]
    durations_ms: tuple[int, ...]
    behavior: str
    role: str
    menu_group: str | None
    persist: bool
    return_to: str | None
    trigger: str | None
    menu_order: int

    @property
    def is_looping(self) -> bool:
        return self.behavior == "loop"

    @property
    def is_persistent(self) -> bool:
        return self.role == "persistent" and self.persist

    @property
    def is_menu_visible(self) -> bool:
        return self.menu_group is not None


@dataclass(frozen=True)
class AnimationManifest:
    default_state: str
    canvas: tuple[int, int]
    asset_scale: int
    default_scale: float
    playback_rate: float
    states: dict[str, AnimationState]

    def state_for_trigger(self, trigger: str) -> str | None:
        for state in self.states.values():
            if state.trigger == trigger:
                return state.name
        return None

    def menu_states(self, group: str) -> tuple[AnimationState, ...]:
        return tuple(
            sorted(
                (
                    state
                    for state in self.states.values()
                    if state.menu_group == group
                ),
                key=lambda state: (state.menu_order, state.name),
            )
        )


def resource_path(relative_path: str | Path) -> Path:
    """Resolve bundled resources without depending on the working directory."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        base = Path(bundle_root)
    else:
        base = Path(__file__).resolve().parents[2]
    return base / Path(relative_path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetValidationError(message)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssetValidationError(f"找不到动画清单：{path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetValidationError(f"无法读取动画清单：{path}\n{exc}") from exc


def load_animation_manifest(
    manifest_path: Path | None = None,
) -> AnimationManifest:
    path = manifest_path or resource_path("assets/animation_manifest.json")
    data = _read_manifest(path)

    canvas_raw = data.get("canvas")
    _require(
        isinstance(canvas_raw, list)
        and len(canvas_raw) == 2
        and all(isinstance(value, int) and value > 0 for value in canvas_raw),
        "动画清单中的 canvas 必须是两个正整数。",
    )
    canvas = (canvas_raw[0], canvas_raw[1])

    states_raw = data.get("states")
    _require(isinstance(states_raw, dict) and states_raw, "动画清单没有 states。")

    asset_scale = data.get("asset_scale", 1)
    _require(
        isinstance(asset_scale, int) and asset_scale >= 1,
        "asset_scale 必须是大于等于 1 的整数。",
    )

    states: dict[str, AnimationState] = {}
    animations_dir = "animations" if asset_scale == 1 else f"animations@{asset_scale}x"
    animations_root = path.parent / animations_dir
    frame_size = (canvas[0] * asset_scale, canvas[1] * asset_scale)
    for name, config in states_raw.items():
        _require(isinstance(config, dict), f"状态 {name} 配置无效。")
        frame_count = config.get("frames")
        durations = config.get("durations_ms")
        behavior = config.get("behavior")
        label = config.get("label")
        role = config.get("role")
        menu_group = config.get("menu_group")
        persist = config.get("persist", False)
        return_to = config.get("return_to")
        trigger = config.get("trigger")
        menu_order = config.get("menu_order", 0)
        _require(
            isinstance(frame_count, int) and frame_count > 0,
            f"状态 {name} 的 frames 无效。",
        )
        _require(
            isinstance(durations, list)
            and len(durations) == frame_count
            and all(isinstance(value, int) and value > 0 for value in durations),
            f"状态 {name} 的 durations_ms 必须与帧数一致且均为正整数。",
        )
        _require(behavior in {"loop", "once"}, f"状态 {name} 的 behavior 无效。")
        _require(isinstance(label, str) and label, f"状态 {name} 缺少菜单标签。")
        _require(
            role in {"persistent", "action", "system"},
            f"状态 {name} 的 role 无效。",
        )
        _require(
            menu_group is None or menu_group in {"状态", "动作"},
            f"状态 {name} 的 menu_group 无效。",
        )
        _require(isinstance(persist, bool), f"状态 {name} 的 persist 无效。")
        _require(
            return_to is None or isinstance(return_to, str),
            f"状态 {name} 的 return_to 无效。",
        )
        _require(
            trigger is None or isinstance(trigger, str),
            f"状态 {name} 的 trigger 无效。",
        )
        _require(
            isinstance(menu_order, int),
            f"状态 {name} 的 menu_order 无效。",
        )
        _require(
            not (role == "system" and menu_group is not None),
            f"系统状态 {name} 不应显示在菜单中。",
        )
        _require(
            not persist or role == "persistent",
            f"只有 persistent 状态可以持久化：{name}",
        )

        state_dir = animations_root / name
        _require(state_dir.is_dir(), f"找不到状态素材目录：{state_dir}")
        frame_paths = tuple(sorted(state_dir.glob("*.png")))
        expected_names = tuple(f"{index:02}.png" for index in range(frame_count))
        actual_names = tuple(frame.name for frame in frame_paths)
        _require(
            actual_names == expected_names,
            f"状态 {name} 帧文件应为 {expected_names}，实际为 {actual_names}。",
        )

        for frame_path in frame_paths:
            image = QImage(str(frame_path))
            _require(not image.isNull(), f"无法加载动画帧：{frame_path}")
            _require(
                (image.width(), image.height()) == frame_size,
                f"动画帧尺寸错误：{frame_path}，应为 {frame_size[0]}×{frame_size[1]}。",
            )
            _require(
                image.hasAlphaChannel(),
                f"动画帧缺少 alpha 通道：{frame_path}",
            )

        states[name] = AnimationState(
            name=name,
            label=label,
            frame_paths=frame_paths,
            durations_ms=tuple(durations),
            behavior=behavior,
            role=role,
            menu_group=menu_group,
            persist=persist,
            return_to=return_to,
            trigger=trigger,
            menu_order=menu_order,
        )

    triggers = [
        state.trigger for state in states.values() if state.trigger is not None
    ]
    _require(
        len(triggers) == len(set(triggers)),
        "动画清单中的 trigger 必须唯一。",
    )
    for state in states.values():
        _require(
            state.return_to is None or state.return_to in states,
            f"状态 {state.name} 的 return_to 不存在：{state.return_to}",
        )
        _require(
            state.role != "persistent" or state.behavior == "loop",
            f"持续状态必须循环播放：{state.name}",
        )
        _require(
            state.role != "action" or state.behavior == "once",
            f"菜单动作必须单次播放：{state.name}",
        )
        _require(
            state.role != "system" or state.trigger is not None,
            f"系统状态必须声明 trigger：{state.name}",
        )

    default_state = data.get("default_state")
    _require(
        isinstance(default_state, str) and default_state in states,
        "default_state 不存在于 states 中。",
    )
    _require(
        states[default_state].role == "persistent",
        "default_state 必须是 persistent 状态。",
    )
    default_scale = data.get("default_scale")
    _require(
        isinstance(default_scale, (int, float)) and 0.25 <= default_scale <= 2.5,
        "default_scale 必须在 0.25 到 2.5 之间。",
    )

    playback_rate = data.get("playback_rate", 1.0)
    _require(
        isinstance(playback_rate, (int, float)) and 0 < playback_rate <= 4,
        "playback_rate 必须大于 0 且不超过 4。",
    )

    first_frame = QImage(str(states[default_state].frame_paths[0]))
    _require(not first_frame.isNull(), "默认状态首帧无法加载。")

    return AnimationManifest(
        default_state=default_state,
        canvas=canvas,
        asset_scale=asset_scale,
        default_scale=float(default_scale),
        playback_rate=float(playback_rate),
        states=states,
    )
