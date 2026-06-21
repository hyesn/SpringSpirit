from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover - Windows is the production platform.
    winreg = None


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Spring"


class AutostartError(RuntimeError):
    """Raised when the Windows autostart entry cannot be updated."""


@dataclass(frozen=True)
class AutostartStatus:
    available: bool
    enabled: bool
    reason: str | None = None


class AutostartManager:
    def __init__(
        self,
        *,
        executable: str | None = None,
        frozen: bool | None = None,
        registry: Any = None,
        key_path: str = RUN_KEY,
    ):
        self.executable = executable or sys.executable
        self.frozen = (
            bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        )
        self.registry = winreg if registry is None else registry
        self.key_path = key_path

    @property
    def available(self) -> bool:
        return self.frozen and self.registry is not None and sys.platform == "win32"

    @property
    def command(self) -> str:
        return subprocess.list2cmdline([self.executable])

    def status(self) -> AutostartStatus:
        if not self.available:
            return AutostartStatus(
                available=False,
                enabled=False,
                reason="仅打包版可设置开机自启动",
            )
        try:
            value = self._read_value()
        except FileNotFoundError:
            value = None
        except OSError as exc:
            raise AutostartError(f"读取开机自启动设置失败：{exc}") from exc
        return AutostartStatus(available=True, enabled=value is not None)

    def set_enabled(self, enabled: bool) -> None:
        if not self.available:
            raise AutostartError("开机自启动仅支持 Windows 打包版。")
        try:
            if enabled:
                with self.registry.CreateKey(
                    self.registry.HKEY_CURRENT_USER, self.key_path
                ) as key:
                    self.registry.SetValueEx(
                        key,
                        VALUE_NAME,
                        0,
                        self.registry.REG_SZ,
                        self.command,
                    )
            else:
                with self.registry.OpenKey(
                    self.registry.HKEY_CURRENT_USER,
                    self.key_path,
                    0,
                    self.registry.KEY_SET_VALUE,
                ) as key:
                    try:
                        self.registry.DeleteValue(key, VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            raise AutostartError(f"更新开机自启动设置失败：{exc}") from exc

    def sync_path_if_enabled(self) -> None:
        if not self.available:
            return
        try:
            current = self._read_value()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AutostartError(f"读取开机自启动设置失败：{exc}") from exc
        if current != self.command:
            self.set_enabled(True)

    def _read_value(self) -> str:
        with self.registry.OpenKey(
            self.registry.HKEY_CURRENT_USER,
            self.key_path,
            0,
            self.registry.KEY_READ,
        ) as key:
            value, _value_type = self.registry.QueryValueEx(key, VALUE_NAME)
        return str(value)
