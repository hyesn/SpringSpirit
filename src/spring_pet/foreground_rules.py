from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RULES_VERSION = 2

LEGACY_RULE_METADATA = {
    "edge": ("microsoft_edge", "Microsoft Edge"),
    "development": ("development_tools", "Development Tools"),
    "documents": ("productivity", "Productivity and Research"),
    "chat": ("messaging", "Messaging"),
    "media": ("media_entertainment", "Media and Entertainment"),
    "games": ("gaming", "Gaming"),
}

SHELL_PROCESSES = [
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "openconsole.exe",
]


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
        "version": RULES_VERSION,
        "debounce_ms": 400,
        "reconcile_interval_ms": 5000,
        "rules": [
            {
                "id": "microsoft_edge",
                "label": "Microsoft Edge",
                "processes": ["msedge.exe"],
                "state": "noting",
            },
            {
                "id": "development_tools",
                "label": "Development Tools",
                "processes": ["code.exe", "pycharm64.exe", "codex.exe"],
                "state": "running",
            },
            {
                "id": "command_line_shells",
                "label": "Command-Line Shells",
                "processes": SHELL_PROCESSES,
                "state": "running",
            },
            {
                "id": "productivity",
                "label": "Productivity and Research",
                "processes": ["zotero.exe", "wps.exe", "et.exe", "wpp.exe"],
                "state": "noting",
            },
            {
                "id": "messaging",
                "label": "Messaging",
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
                "id": "media_entertainment",
                "label": "Media and Entertainment",
                "processes": [
                    "哔哩哔哩.exe",
                    "bilibili.exe",
                    "douyin.exe",
                    "cloudmusic.exe",
                ],
                "state": "listening",
            },
            {
                "id": "gaming",
                "label": "Gaming",
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
            raise ForegroundRuleError(
                f"Unable to read foreground application rules: {exc}"
            ) from exc
        data, migrated = self._migrate(data)
        config = self._validate(data)
        if migrated:
            self._write_data(data)
        self._config = config
        return config

    def use_defaults(self) -> ForegroundRuleConfig:
        self._config = self._validate(default_rules_data())
        return self._config

    def match(self, process_name: str) -> ForegroundMatch | None:
        return self._config.matches.get(Path(process_name).name.casefold())

    def _write_defaults(self) -> None:
        self._write_data(default_rules_data())

    def _write_data(self, data: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            raise ForegroundRuleError(
                f"Unable to write foreground application rules: {exc}"
            ) from exc

    def _migrate(self, data: object) -> tuple[object, bool]:
        if not isinstance(data, dict) or data.get("version") != 1:
            return data, False
        rules = data.get("rules")
        if not isinstance(rules, list):
            return data, False

        migrated_rules: list[object] = []
        claimed_processes: set[str] = set()
        for entry in rules:
            if not isinstance(entry, dict):
                migrated_rules.append(entry)
                continue
            migrated = dict(entry)
            legacy_id = migrated.get("id")
            metadata = LEGACY_RULE_METADATA.get(legacy_id)
            if metadata is not None:
                migrated["id"], migrated["label"] = metadata
            processes = migrated.get("processes")
            if isinstance(processes, list):
                claimed_processes.update(
                    Path(process).name.casefold()
                    for process in processes
                    if isinstance(process, str)
                )
            migrated_rules.append(migrated)

        available_shells = [
            process
            for process in SHELL_PROCESSES
            if process.casefold() not in claimed_processes
        ]
        if available_shells:
            migrated_rules.insert(
                2,
                {
                    "id": "command_line_shells",
                    "label": "Command-Line Shells",
                    "processes": available_shells,
                    "state": "running",
                },
            )

        migrated_data = dict(data)
        migrated_data["version"] = RULES_VERSION
        migrated_data["rules"] = migrated_rules
        return migrated_data, True

    def _validate(self, data: object) -> ForegroundRuleConfig:
        if not isinstance(data, dict) or data.get("version") != RULES_VERSION:
            raise ForegroundRuleError(
                f"Foreground rule version must be {RULES_VERSION}."
            )
        debounce_ms = data.get("debounce_ms", 400)
        reconcile_ms = data.get("reconcile_interval_ms", 5000)
        if not isinstance(debounce_ms, int) or not 50 <= debounce_ms <= 5000:
            raise ForegroundRuleError(
                "debounce_ms must be an integer between 50 and 5000."
            )
        if not isinstance(reconcile_ms, int) or not 1000 <= reconcile_ms <= 60000:
            raise ForegroundRuleError(
                "reconcile_interval_ms must be an integer between 1000 and 60000."
            )
        rules = data.get("rules")
        if not isinstance(rules, list):
            raise ForegroundRuleError("rules must be an array.")

        matches: dict[str, ForegroundMatch] = {}
        rule_ids: set[str] = set()
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ForegroundRuleError(f"Rule {index + 1} must be an object.")
            rule_id = rule.get("id")
            label = rule.get("label")
            state = rule.get("state")
            processes = rule.get("processes")
            if not isinstance(rule_id, str) or not rule_id.strip():
                raise ForegroundRuleError(f"Rule {index + 1} requires an id.")
            if rule_id in rule_ids:
                raise ForegroundRuleError(f"Duplicate rule id: {rule_id}")
            rule_ids.add(rule_id)
            if not isinstance(label, str) or not label.strip():
                raise ForegroundRuleError(f"Rule {rule_id} requires a label.")
            if not isinstance(state, str) or state not in self.persistent_states:
                raise ForegroundRuleError(
                    f"Rule {rule_id} targets an unknown or non-persistent state: {state}"
                )
            if not isinstance(processes, list) or not processes:
                raise ForegroundRuleError(
                    f"Rule {rule_id} requires at least one process."
                )
            for process in processes:
                if not isinstance(process, str) or not process.strip():
                    raise ForegroundRuleError(
                        f"Rule {rule_id} contains an invalid process name."
                    )
                normalized = Path(process.strip()).name.casefold()
                if normalized in matches:
                    raise ForegroundRuleError(f"Duplicate process name: {process}")
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
