from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QTimer, Signal


EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH_BUFFER = 32768


@dataclass(frozen=True)
class ForegroundProcess:
    pid: int
    process_name: str


if sys.platform == "win32":
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]


class WindowsForegroundResolver:
    def __init__(self) -> None:
        self.available = sys.platform == "win32"
        if not self.available:
            return
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESSENTRY32W),
        ]
        self.kernel32.Process32FirstW.restype = wintypes.BOOL
        self.kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESSENTRY32W),
        ]
        self.kernel32.Process32NextW.restype = wintypes.BOOL

    def resolve(self) -> ForegroundProcess | None:
        if not self.available:
            return None
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = self._pid_for_window(hwnd)
        if not pid or pid == os.getpid():
            return None
        process_name = self._name_for_pid(pid)
        if process_name and process_name.casefold() == "applicationframehost.exe":
            child_pid = self._hosted_child_pid(hwnd, pid)
            if child_pid:
                child_name = self._name_for_pid(child_pid)
                if child_name:
                    pid, process_name = child_pid, child_name
        if not process_name:
            return None
        return ForegroundProcess(pid=pid, process_name=process_name)

    def _pid_for_window(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def _name_for_pid(self, pid: int) -> str | None:
        handle = self.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            try:
                size = wintypes.DWORD(MAX_PATH_BUFFER)
                buffer = ctypes.create_unicode_buffer(MAX_PATH_BUFFER)
                if self.kernel32.QueryFullProcessImageNameW(
                    handle, 0, buffer, ctypes.byref(size)
                ):
                    return os.path.basename(buffer.value)
            finally:
                self.kernel32.CloseHandle(handle)
        return self._snapshot_name(pid)

    def _snapshot_name(self, pid: int) -> str | None:
        snapshot = self.kernel32.CreateToolhelp32Snapshot(
            TH32CS_SNAPPROCESS, 0
        )
        invalid_handle = ctypes.c_void_p(-1).value
        if not snapshot or snapshot == invalid_handle:
            return None
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        try:
            if not self.kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return None
            while True:
                if int(entry.th32ProcessID) == pid:
                    return str(entry.szExeFile)
                if not self.kernel32.Process32NextW(
                    snapshot, ctypes.byref(entry)
                ):
                    return None
        finally:
            self.kernel32.CloseHandle(snapshot)

    def _hosted_child_pid(self, hwnd: int, host_pid: int) -> int | None:
        result: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        def visit(child_hwnd: int, _lparam: int) -> bool:
            if not self.user32.IsWindowVisible(child_hwnd):
                return True
            child_pid = self._pid_for_window(child_hwnd)
            if child_pid and child_pid != host_pid:
                result.append(child_pid)
                return False
            return True

        callback = callback_type(visit)
        self.user32.EnumChildWindows.argtypes = [
            wintypes.HWND,
            callback_type,
            wintypes.LPARAM,
        ]
        self.user32.EnumChildWindows.restype = wintypes.BOOL
        self.user32.EnumChildWindows(hwnd, callback, 0)
        return result[0] if result else None


class ForegroundMonitor(QObject):
    process_changed = Signal(str)
    _native_event_received = Signal()

    def __init__(
        self,
        *,
        debounce_ms: int = 400,
        reconcile_interval_ms: int = 5000,
        resolver: WindowsForegroundResolver | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.resolver = resolver or WindowsForegroundResolver()
        self._last_process: str | None = None
        self._hook = None
        self._callback = None
        self._user32 = None
        self._running = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self.check_now)
        self._reconcile_timer = QTimer(self)
        self._reconcile_timer.timeout.connect(self.check_now)
        self.configure(debounce_ms, reconcile_interval_ms)
        self._native_event_received.connect(
            self._schedule_debounced_check,
            Qt.ConnectionType.QueuedConnection,
        )

    @property
    def available(self) -> bool:
        return bool(getattr(self.resolver, "available", False))

    @property
    def current_process(self) -> str | None:
        return self._last_process

    def configure(self, debounce_ms: int, reconcile_interval_ms: int) -> None:
        self._debounce_timer.setInterval(debounce_ms)
        self._reconcile_timer.setInterval(reconcile_interval_ms)
        if self._reconcile_timer.isActive():
            self._reconcile_timer.start()

    def start(self) -> bool:
        if self._running:
            return self.available
        self._running = True
        if self.available:
            self._install_hook()
            self._reconcile_timer.start()
            QTimer.singleShot(0, self.check_now)
        return self.available

    def stop(self) -> None:
        self._running = False
        self._debounce_timer.stop()
        self._reconcile_timer.stop()
        if self._hook is not None:
            self._user32.UnhookWinEvent(self._hook)
            self._hook = None
        self._user32 = None
        self._callback = None

    def check_now(self) -> None:
        if not self._running:
            return
        resolved = self.resolver.resolve()
        if resolved is None:
            return
        normalized = resolved.process_name.casefold()
        if normalized == self._last_process:
            return
        self._last_process = normalized
        self.process_changed.emit(resolved.process_name)

    def _schedule_debounced_check(self) -> None:
        if self._running:
            self._debounce_timer.start()

    def _install_hook(self) -> None:
        callback_type = ctypes.WINFUNCTYPE(
            None,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )

        def callback(
            _hook: int,
            _event: int,
            _hwnd: int,
            _object_id: int,
            _child_id: int,
            _thread_id: int,
            _event_time: int,
        ) -> None:
            self._native_event_received.emit()

        self._callback = callback_type(callback)
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SetWinEventHook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            callback_type,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self._user32.SetWinEventHook.restype = wintypes.HANDLE
        self._user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        self._user32.UnhookWinEvent.restype = wintypes.BOOL
        self._hook = self._user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            self._callback,
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
