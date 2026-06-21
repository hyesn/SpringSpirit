from __future__ import annotations

import json

import pytest

from spring_pet.foreground_rules import ForegroundRuleError, ForegroundRuleStore


PERSISTENT_STATES = {
    "idle",
    "waiting",
    "running",
    "review",
    "sleeping",
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
    assert store.match("Weixin.exe").state_name == "waiting"
    assert store.match("cloudmusic.exe").state_name == "listening"
    assert store.match("CS2.EXE").state_name == "review"
    assert store.match("unconfigured.exe") is None


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
        "version": 1,
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

