from __future__ import annotations

from PySide6.QtWidgets import QApplication

from spring_pet.foreground_monitor import ForegroundMonitor, ForegroundProcess


class FakeResolver:
    available = False

    def __init__(self) -> None:
        self.current: ForegroundProcess | None = None

    def resolve(self) -> ForegroundProcess | None:
        return self.current


def test_monitor_deduplicates_process_names_and_ignores_failures() -> None:
    QApplication.instance() or QApplication([])
    resolver = FakeResolver()
    monitor = ForegroundMonitor(resolver=resolver)
    monitor._running = True
    emitted: list[str] = []
    monitor.process_changed.connect(emitted.append)

    resolver.current = ForegroundProcess(1, "Code.exe")
    monitor.check_now()
    resolver.current = ForegroundProcess(2, "CODE.EXE")
    monitor.check_now()
    resolver.current = None
    monitor.check_now()
    resolver.current = ForegroundProcess(3, "msedge.exe")
    monitor.check_now()

    assert emitted == ["Code.exe", "msedge.exe"]
    monitor.stop()

