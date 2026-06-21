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
