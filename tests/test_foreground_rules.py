from __future__ import annotations

import json

import pytest

from spring_pet.foreground_rules import (
    RULES_VERSION,
    ForegroundRuleError,
    ForegroundRuleStore,
)


PERSISTENT_STATES = {
    "idle",
    "waiting",
    "running",
    "review",
    "listening",
    "noting",
}


def test_default_rules_are_created_and_match_case_insensitively(tmp_path) -> None:
    path = tmp_path / "foreground_rules.json"
    store = ForegroundRuleStore(PERSISTENT_STATES, path)
    config = store.load()

    assert path.exists()
    assert config.debounce_ms == 400
    assert store.match("C:/Program Files/Microsoft/Edge/MSEDGE.EXE").state_name == "noting"
    assert store.match("Code.exe").state_name == "running"
    assert store.match("cmd.exe").state_name == "running"
    assert store.match("powershell.exe").state_name == "running"
    assert store.match("pwsh.exe").state_name == "running"
    assert store.match("WindowsTerminal.exe").state_name == "running"
    assert store.match("Weixin.exe").state_name == "waiting"
    assert store.match("cloudmusic.exe").state_name == "listening"
    assert store.match("CS2.EXE").state_name == "review"
    assert store.match("unconfigured.exe") is None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == RULES_VERSION
    assert all(
        rule["label"].isascii()
        for rule in data["rules"]
    )


def test_version_one_rules_are_migrated_to_standard_english_metadata(
    tmp_path,
) -> None:
    path = tmp_path / "foreground_rules.json"
    legacy = {
        "version": 1,
        "debounce_ms": 400,
        "reconcile_interval_ms": 5000,
        "rules": [
            {
                "id": "development",
                "label": "开发工具",
                "processes": ["code.exe"],
                "state": "running",
            },
            {
                "id": "documents",
                "label": "资料与办公",
                "processes": ["zotero.exe"],
                "state": "noting",
            },
        ],
    }
    path.write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )

    store = ForegroundRuleStore(PERSISTENT_STATES, path)
    store.load()
    migrated = json.loads(path.read_text(encoding="utf-8"))

    assert migrated["version"] == RULES_VERSION
    assert migrated["rules"][0]["id"] == "development_tools"
    assert migrated["rules"][0]["label"] == "Development Tools"
    assert migrated["rules"][1]["id"] == "productivity"
    assert migrated["rules"][1]["label"] == "Productivity and Research"
    assert store.match("cmd.exe").state_name == "running"
    assert store.match("pwsh.exe").state_name == "running"


def test_migration_does_not_duplicate_user_defined_shell_processes(
    tmp_path,
) -> None:
    path = tmp_path / "foreground_rules.json"
    legacy = {
        "version": 1,
        "rules": [
            {
                "id": "custom_shell",
                "label": "Custom Shell",
                "processes": ["cmd.exe"],
                "state": "idle",
            }
        ],
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")

    store = ForegroundRuleStore(PERSISTENT_STATES, path)
    store.load()

    assert store.match("cmd.exe").state_name == "idle"
    assert store.match("powershell.exe").state_name == "running"


def test_invalid_reload_keeps_last_known_good_rules(tmp_path) -> None:
    path = tmp_path / "foreground_rules.json"
    store = ForegroundRuleStore(PERSISTENT_STATES, path)
    store.load()
    previous = store.config
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ForegroundRuleError):
        store.load()

    assert store.config is previous
    assert store.match("code.exe").state_name == "running"


def test_duplicate_process_and_unknown_state_are_rejected(tmp_path) -> None:
    path = tmp_path / "foreground_rules.json"
    store = ForegroundRuleStore(PERSISTENT_STATES, path)
    data = {
        "version": RULES_VERSION,
        "rules": [
            {
                "id": "one",
                "label": "One",
                "processes": ["same.exe"],
                "state": "idle",
            },
            {
                "id": "two",
                "label": "Two",
                "processes": ["SAME.EXE"],
                "state": "jumping",
            },
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ForegroundRuleError):
        store.load()
