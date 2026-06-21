from __future__ import annotations

import sys

import pytest

from spring_pet.autostart import AutostartError, AutostartManager, VALUE_NAME


class FakeKey:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    REG_SZ = 1
    KEY_READ = 2
    KEY_SET_VALUE = 4

    def __init__(self):
        self.values = {}

    def CreateKey(self, _root, _path):
        return FakeKey(self)

    def OpenKey(self, _root, _path, *_args):
        return FakeKey(self)

    def SetValueEx(self, _key, name, _reserved, _kind, value):
        self.values[name] = value

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry behavior")
def test_packaged_autostart_enable_disable_and_path_sync() -> None:
    registry = FakeRegistry()
    manager = AutostartManager(
        executable=r"C:\Program Files\Spring Pet\Spring.exe",
        frozen=True,
        registry=registry,
    )

    assert manager.status().available
    assert not manager.status().enabled
    manager.set_enabled(True)
    assert registry.values[VALUE_NAME] == (
        '"C:\\Program Files\\Spring Pet\\Spring.exe"'
    )

    registry.values[VALUE_NAME] = r'"C:\Old Spring\Spring.exe"'
    manager.sync_path_if_enabled()
    assert registry.values[VALUE_NAME] == manager.command

    manager.set_enabled(False)
    assert not manager.status().enabled


def test_source_mode_autostart_is_unavailable() -> None:
    manager = AutostartManager(frozen=False, registry=FakeRegistry())
    status = manager.status()
    assert not status.available
    assert "打包版" in status.reason
    with pytest.raises(AutostartError):
        manager.set_enabled(True)
