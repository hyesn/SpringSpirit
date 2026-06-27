from __future__ import annotations

from PySide6.QtCore import QSettings

from spring_pet.settings import PetSettings


def test_settings_restore_only_looping_states(tmp_path) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings = PetSettings(backend)
    backend.setValue("scale", 9)
    backend.setValue("looping_state", "jumping")

    restored = settings.load(
        default_scale=1.25,
        default_state="idle",
        persistent_states={"idle", "waiting"},
    )
    assert restored.scale == 2.5
    assert restored.looping_state == "idle"
    assert restored.foreground_follow_enabled
    assert restored.diagnostic_bubble_timeout_ms == 12_000
    assert (
        restored.libre_hardware_monitor_url
        == "http://127.0.0.1:8085/data.json"
    )
    assert not restored.discipline_enabled
    assert not restored.discipline_paused
    assert restored.discipline_focus_minutes == 45
    assert restored.discipline_relax_minutes == 8
    assert restored.discipline_phase == "focus"
    assert restored.discipline_cycle_count == 0
    assert restored.edge_snap_enabled
    assert restored.edge_snap_horizontal == ""
    assert restored.edge_snap_vertical == ""


def test_foreground_follow_setting_is_persisted(tmp_path) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings = PetSettings(backend)
    settings.save_foreground_follow_enabled(False)

    restored = settings.load(
        default_scale=1.25,
        default_state="idle",
        persistent_states={"idle"},
    )
    assert not restored.foreground_follow_enabled


def test_hardware_settings_are_validated(tmp_path) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    backend.setValue("diagnostic_bubble_timeout_ms", 999_999)
    backend.setValue("libre_hardware_monitor_url", "http://localhost:9000/data.json")
    settings = PetSettings(backend)

    restored = settings.load(
        default_scale=1.25,
        default_state="idle",
        persistent_states={"idle"},
    )

    assert restored.diagnostic_bubble_timeout_ms == 60_000
    assert (
        restored.libre_hardware_monitor_url
        == "http://localhost:9000/data.json"
    )


def test_discipline_and_edge_settings_are_validated(tmp_path) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    backend.setValue("discipline_enabled", True)
    backend.setValue("discipline_paused", True)
    backend.setValue("discipline_focus_minutes", 999)
    backend.setValue("discipline_relax_minutes", -2)
    backend.setValue("discipline_phase", "broken")
    backend.setValue("discipline_focus_elapsed_ms", 12_345)
    backend.setValue("discipline_relax_elapsed_ms", 678)
    backend.setValue("discipline_cycle_count", 3)
    backend.setValue("edge_snap_horizontal", "right")
    backend.setValue("edge_snap_vertical", "bottom")
    settings = PetSettings(backend)

    restored = settings.load(
        default_scale=1.25,
        default_state="idle",
        persistent_states={"idle"},
    )

    assert restored.discipline_enabled
    assert restored.discipline_paused
    assert restored.discipline_focus_minutes == 180
    assert restored.discipline_relax_minutes == 1
    assert restored.discipline_phase == "focus"
    assert restored.discipline_focus_elapsed_ms == 12_345
    assert restored.discipline_relax_elapsed_ms == 678
    assert restored.discipline_cycle_count == 3
    assert restored.edge_snap_horizontal == "right"
    assert restored.edge_snap_vertical == "bottom"


def test_discipline_focus_ready_and_cycle_count_are_persisted(tmp_path) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings = PetSettings(backend)

    settings.save_discipline_progress(
        phase="focus_ready",
        focus_elapsed_ms=0,
        relax_elapsed_ms=60_000,
        cycle_count=2,
    )
    restored = settings.load(
        default_scale=1.25,
        default_state="idle",
        persistent_states={"idle"},
    )

    assert restored.discipline_phase == "focus_ready"
    assert restored.discipline_cycle_count == 2

    settings.clear_discipline_progress()
    restored = settings.load(
        default_scale=1.25,
        default_state="idle",
        persistent_states={"idle"},
    )
    assert restored.discipline_phase == "focus"
    assert restored.discipline_cycle_count == 0
