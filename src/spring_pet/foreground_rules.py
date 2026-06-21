from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ForegroundRuleError(RuntimeError):
    """Raised when foreground application rules cannot be loaded."""


@dataclass(frozen=True)
class ForegroundMatch:
    rule_id: str
    label: str
    process_name: str
    state_name: str


@dataclass(frozen=True)
class ForegroundRuleConfig:
    debounce_ms: int
    reconcile_interval_ms: int
    matches: dict[str, ForegroundMatch]


def default_rules_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SpringPet" / "foreground_rules.json"
    return Path.home() / "AppData" / "Roaming" / "SpringPet" / "foreground_rules.json"


def default_rules_data() -> dict[str, Any]:
    return {
        "version": 1,
        "debounce_ms": 400,
        "reconcile_interval_ms": 5000,
        "rules": [
            {
                "id": "edge",
                "label": "Microsoft Edge",
                "processes": ["msedge.exe"],
                "state": "noting",
            },
            {
                "id": "development",
                "label": "开发工具",
                "processes": ["code.exe", "pycharm64.exe", "codex.exe"],
                "state": "running",
            },
            {
                "id": "documents",
                "label": "资料与办公",
                "processes": ["zotero.exe", "wps.exe", "et.exe", "wpp.exe"],
                "state": "noting",
            },
            {
                "id": "chat",
                "label": "QQ / 微信",
                "processes": [
                    "qq.exe",
                    "qqnt.exe",
                    "qqsclauncher.exe",
                    "weixin.exe",
                    "wechat.exe",
                ],
                "state": "waiting",
            },
            {
                "id": "media",
                "label": "影音应用",
                "processes": [
                    "哔哩哔哩.exe",
                    "bilibili.exe",
                    "douyin.exe",
                    "cloudmusic.exe",
                ],
                "state": "listening",
            },
            {
                "id": "games",
                "label": "游戏平台与游戏",
                "processes": [
                    "steam.exe",
                    "aclos-launcher.exe",
                    "riotclientservices.exe",
                    "valorant-win64-shipping.exe",
                    "battle.net launcher.exe",
                    "battle.net.exe",
                    "cs2.exe",
                ],
                "state": "review",
            },
        ],
    }


class ForegroundRuleStore:
    def __init__(
        self,
        persistent_states: set[str],
        path: Path | None = None,
    ):
        self.persistent_states = persistent_states
        self.path = path or default_rules_path()
        self._config = self._validate(default_rules_data())

    @property
    def config(self) -> ForegroundRuleConfig:
        return self._config

    def load(self) -> ForegroundRuleConfig:
        if not self.path.exists():
            self._write_defaults()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ForegroundRuleError(f"无法读取前台应用规则：{exc}") from exc
        config = self._validate(data)
        self._config = config
        return config

    def use_defaults(self) -> ForegroundRuleConfig:
        self._config = self._validate(default_rules_data())
        return self._config

    def match(self, process_name: str) -> ForegroundMatch | None:
        return self._config.matches.get(Path(process_name).name.casefold())

    def _write_defaults(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(default_rules_data(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            raise ForegroundRuleError(f"无法创建前台应用规则：{exc}") from exc

    def _validate(self, data: object) -> ForegroundRuleConfig:
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ForegroundRuleError("前台应用规则 version 必须为 1。")
        debounce_ms = data.get("debounce_ms", 400)
        reconcile_ms = data.get("reconcile_interval_ms", 5000)
        if not isinstance(debounce_ms, int) or not 50 <= debounce_ms <= 5000:
            raise ForegroundRuleError("debounce_ms 必须是 50 到 5000 之间的整数。")
        if not isinstance(reconcile_ms, int) or not 1000 <= reconcile_ms <= 60000:
            raise ForegroundRuleError(
                "reconcile_interval_ms 必须是 1000 到 60000 之间的整数。"
            )
        rules = data.get("rules")
        if not isinstance(rules, list):
            raise ForegroundRuleError("rules 必须是数组。")

        matches: dict[str, ForegroundMatch] = {}
        rule_ids: set[str] = set()
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ForegroundRuleError(f"第 {index + 1} 条规则必须是对象。")
            rule_id = rule.get("id")
            label = rule.get("label")
            state = rule.get("state")
            processes = rule.get("processes")
            if not isinstance(rule_id, str) or not rule_id.strip():
                raise ForegroundRuleError(f"第 {index + 1} 条规则缺少 id。")
            if rule_id in rule_ids:
                raise ForegroundRuleError(f"规则 id 重复：{rule_id}")
            rule_ids.add(rule_id)
            if not isinstance(label, str) or not label.strip():
                raise ForegroundRuleError(f"规则 {rule_id} 缺少 label。")
            if not isinstance(state, str) or state not in self.persistent_states:
                raise ForegroundRuleError(
                    f"规则 {rule_id} 指向未知或非持续状态：{state}"
                )
            if not isinstance(processes, list) or not processes:
                raise ForegroundRuleError(f"规则 {rule_id} 的 processes 不能为空。")
            for process in processes:
                if not isinstance(process, str) or not process.strip():
                    raise ForegroundRuleError(
                        f"规则 {rule_id} 包含无效进程名。"
                    )
                normalized = Path(process.strip()).name.casefold()
                if normalized in matches:
                    raise ForegroundRuleError(f"进程名重复：{process}")
                matches[normalized] = ForegroundMatch(
                    rule_id=rule_id,
                    label=label.strip(),
                    process_name=Path(process.strip()).name,
                    state_name=state,
                )
        return ForegroundRuleConfig(
            debounce_ms=debounce_ms,
            reconcile_interval_ms=reconcile_ms,
            matches=matches,
        )
