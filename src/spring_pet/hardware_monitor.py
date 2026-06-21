from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, Signal

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is included in production.
    psutil = None


SEVERITY_ORDER = {
    "unavailable": -1,
    "normal": 0,
    "busy": 1,
    "warning": 2,
    "critical": 3,
}


@dataclass(frozen=True)
class HardwareMetric:
    metric_id: str
    label: str
    value: float | int | str | None
    unit: str
    source: str
    available: bool
    severity: str = "normal"
    detail: str | None = None

    @property
    def display_value(self) -> str:
        if not self.available or self.value is None:
            return "Unavailable"
        if isinstance(self.value, float):
            value = f"{self.value:.1f}".rstrip("0").rstrip(".")
        else:
            value = str(self.value)
        return f"{value}{self.unit}"


@dataclass(frozen=True)
class HardwareSnapshot:
    kind: str
    collected_at: datetime
    metrics: tuple[HardwareMetric, ...]
    unavailable_reasons: tuple[str, ...]
    overall_severity: str
    commentary: str


def classify_metric(
    metric_id: str,
    value: float | int | None,
    *,
    charging: bool = False,
) -> str:
    if value is None:
        return "unavailable"
    numeric = float(value)
    if metric_id in {"cpu_usage", "gpu_usage"}:
        return "critical" if numeric >= 90 else "busy" if numeric >= 70 else "normal"
    if metric_id == "memory_usage":
        return "critical" if numeric >= 90 else "warning" if numeric >= 75 else "normal"
    if metric_id == "cpu_temperature":
        return "critical" if numeric >= 90 else "warning" if numeric >= 75 else "normal"
    if metric_id == "gpu_temperature":
        return "critical" if numeric >= 90 else "warning" if numeric >= 80 else "normal"
    if metric_id == "battery_level" and not charging:
        return "critical" if numeric <= 10 else "warning" if numeric <= 20 else "normal"
    return "normal"


def snapshot_commentary(
    metrics: tuple[HardwareMetric, ...],
    unavailable_reasons: tuple[str, ...],
) -> tuple[str, str]:
    available = [metric for metric in metrics if metric.available]
    if not available:
        return (
            "unavailable",
            "有些秘密它不肯说。启动 LibreHardwareMonitor 后我再审它一次。",
        )
    highest = max(
        available,
        key=lambda metric: SEVERITY_ORDER.get(metric.severity, -1),
    )
    if highest.severity == "critical":
        return (
            "critical",
            "这次不是装忙，它真的有点撑不住了。先给它降降温吧。",
        )
    if highest.severity == "warning":
        if "temperature" in highest.metric_id:
            return (
                "warning",
                "有一点热情过头了，让散热器喘口气吧。",
            )
        return (
            "warning",
            "状态还行，不过已经开始悄悄举白旗了。",
        )
    if highest.severity == "busy":
        return (
            "busy",
            "它正在努力工作，希望不是在偷偷编译整个宇宙。",
        )
    if unavailable_reasons and len(available) <= 1:
        return (
            "normal",
            "能看到的不多，但至少它还没有当场装死。",
        )
    return (
        "normal",
        "状态挺稳，看来今天还不用我拿听诊器吓它。",
    )


class HardwareCollector:
    def __init__(
        self,
        libre_hardware_monitor_url: str,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        url_opener: Callable[..., object] | None = None,
    ):
        self.libre_hardware_monitor_url = libre_hardware_monitor_url
        self.command_runner = command_runner or subprocess.run
        self.url_opener = url_opener or urllib.request.urlopen

    def collect(self, kind: str) -> HardwareSnapshot:
        if kind not in {"overview", "vitals"}:
            raise ValueError(f"Unknown hardware snapshot kind: {kind}")
        metrics: list[HardwareMetric] = []
        reasons: list[str] = []
        if kind == "overview":
            metrics.extend(self._collect_overview(reasons))
        else:
            metrics.extend(self._collect_vitals(reasons))
        metric_tuple = tuple(metrics)
        reason_tuple = tuple(dict.fromkeys(reasons))
        severity, commentary = snapshot_commentary(metric_tuple, reason_tuple)
        return HardwareSnapshot(
            kind=kind,
            collected_at=datetime.now(),
            metrics=metric_tuple,
            unavailable_reasons=reason_tuple,
            overall_severity=severity,
            commentary=commentary,
        )

    def _collect_overview(self, reasons: list[str]) -> list[HardwareMetric]:
        metrics: list[HardwareMetric] = []
        if psutil is None:
            reasons.append("System performance counters are unavailable.")
        else:
            before = psutil.net_io_counters()
            cpu_usage = float(psutil.cpu_percent(interval=0.25))
            after = psutil.net_io_counters()
            metrics.append(self._percent_metric("cpu_usage", "CPU usage", cpu_usage, "psutil"))
            memory = psutil.virtual_memory()
            memory_detail = (
                f"{self._format_bytes(memory.used)} / "
                f"{self._format_bytes(memory.total)}"
            )
            metrics.append(
                HardwareMetric(
                    "memory_usage",
                    "Memory",
                    float(memory.percent),
                    "%",
                    "psutil",
                    True,
                    classify_metric("memory_usage", memory.percent),
                    memory_detail,
                )
            )
            battery = psutil.sensors_battery()
            if battery is None:
                reasons.append("No system battery was detected.")
            else:
                charging = bool(battery.power_plugged)
                seconds = battery.secsleft
                detail = "Charging" if charging else "On battery"
                if (
                    not charging
                    and isinstance(seconds, (int, float))
                    and seconds > 0
                    and seconds < 10**8
                ):
                    hours, remainder = divmod(int(seconds), 3600)
                    minutes = remainder // 60
                    detail += f" · {hours}h {minutes}m remaining"
                metrics.append(
                    HardwareMetric(
                        "battery_level",
                        "Battery",
                        float(battery.percent),
                        "%",
                        "psutil",
                        True,
                        classify_metric(
                            "battery_level",
                            battery.percent,
                            charging=charging,
                        ),
                        detail,
                    )
                )
            active_interfaces = [
                name
                for name, stats in psutil.net_if_stats().items()
                if stats.isup and not name.casefold().startswith("loopback")
            ]
            elapsed = 0.25
            upload = max(0.0, (after.bytes_sent - before.bytes_sent) / elapsed)
            download = max(0.0, (after.bytes_recv - before.bytes_recv) / elapsed)
            metrics.append(
                HardwareMetric(
                    "network",
                    "Network",
                    "Connected" if active_interfaces else "Disconnected",
                    "",
                    "psutil",
                    True,
                    "normal" if active_interfaces else "warning",
                    (
                        f"↓ {self._format_rate(download)} · "
                        f"↑ {self._format_rate(upload)}"
                        if active_interfaces
                        else None
                    ),
                )
            )

        nvidia = self._collect_nvidia()
        gpu_usage = nvidia.get("gpu_usage")
        if gpu_usage is None:
            gpu_usage = self._collect_windows_gpu_usage()
        if gpu_usage is None:
            reasons.append("GPU utilization is unavailable.")
        else:
            metrics.append(self._percent_metric("gpu_usage", "GPU usage", gpu_usage, nvidia.get("source", "Windows performance counters")))

        volume = self._collect_volume()
        if volume is None:
            reasons.append("Master volume is unavailable.")
        else:
            level, muted = volume
            metrics.append(
                HardwareMetric(
                    "volume",
                    "Volume",
                    level,
                    "%",
                    "Windows Core Audio",
                    True,
                    "normal",
                    "Muted" if muted else "Active",
                )
            )
        brightness = self._collect_brightness()
        if brightness is None:
            reasons.append("Display brightness is not exposed by this monitor.")
        else:
            metrics.append(
                HardwareMetric(
                    "brightness",
                    "Brightness",
                    brightness,
                    "%",
                    "WmiMonitorBrightness",
                    True,
                )
            )
        return metrics

    def _collect_vitals(self, reasons: list[str]) -> list[HardwareMetric]:
        metrics: list[HardwareMetric] = []
        libre = self._collect_libre_hardware_monitor()
        nvidia = self._collect_nvidia()

        cpu_temp = libre.get("cpu_temperature")
        if cpu_temp is None:
            reasons.append(
                "CPU temperature requires a compatible LibreHardwareMonitor sensor."
            )
        else:
            metrics.append(
                self._temperature_metric(
                    "cpu_temperature",
                    "CPU temperature",
                    cpu_temp,
                    "LibreHardwareMonitor",
                )
            )

        gpu_temp = nvidia.get("gpu_temperature")
        gpu_temp_source = nvidia.get("source", "NVIDIA SMI")
        if gpu_temp is None:
            gpu_temp = libre.get("gpu_temperature")
            gpu_temp_source = "LibreHardwareMonitor"
        if gpu_temp is None:
            reasons.append("GPU temperature is unavailable.")
        else:
            metrics.append(
                self._temperature_metric(
                    "gpu_temperature",
                    "GPU temperature",
                    gpu_temp,
                    gpu_temp_source,
                )
            )

        fan_speed = libre.get("fan_speed")
        fan_unit = " RPM"
        fan_source = "LibreHardwareMonitor"
        if fan_speed is None:
            fan_speed = nvidia.get("fan_percent")
            fan_unit = "%"
            fan_source = nvidia.get("source", "NVIDIA SMI")
        if fan_speed is None:
            reasons.append("Fan speed is unavailable.")
        else:
            metrics.append(
                HardwareMetric(
                    "fan_speed",
                    "Fan speed",
                    fan_speed,
                    fan_unit,
                    fan_source,
                    True,
                )
            )

        gpu_power = nvidia.get("gpu_power")
        if gpu_power is None:
            gpu_power = libre.get("gpu_power")
        if gpu_power is None:
            reasons.append("GPU board power is unavailable.")
        else:
            metrics.append(
                HardwareMetric(
                    "gpu_power",
                    "GPU power",
                    gpu_power,
                    " W",
                    nvidia.get("source", "LibreHardwareMonitor"),
                    True,
                )
            )
        return metrics

    @staticmethod
    def _percent_metric(
        metric_id: str,
        label: str,
        value: float,
        source: str,
    ) -> HardwareMetric:
        return HardwareMetric(
            metric_id,
            label,
            value,
            "%",
            source,
            True,
            classify_metric(metric_id, value),
        )

    @staticmethod
    def _temperature_metric(
        metric_id: str,
        label: str,
        value: float,
        source: str,
    ) -> HardwareMetric:
        return HardwareMetric(
            metric_id,
            label,
            value,
            " °C",
            source,
            True,
            classify_metric(metric_id, value),
        )

    def _collect_nvidia(self) -> dict[str, float | str]:
        command = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,temperature.gpu,fan.speed,power.draw",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = self._run_command(command, timeout=2.5)
        except (OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0:
            return {}
        rows = []
        for line in result.stdout.splitlines():
            values = [part.strip() for part in line.split(",")]
            if len(values) != 4:
                continue
            rows.append([self._number_or_none(value) for value in values])
        if not rows:
            return {}
        output: dict[str, float | str] = {"source": "NVIDIA SMI"}
        for key, index, reducer in (
            ("gpu_usage", 0, max),
            ("gpu_temperature", 1, max),
            ("fan_percent", 2, max),
            ("gpu_power", 3, sum),
        ):
            readings = [row[index] for row in rows if row[index] is not None]
            if readings:
                output[key] = float(reducer(readings))
        return output

    def _collect_windows_gpu_usage(self) -> float | None:
        script = (
            "$samples=(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' "
            "-SampleInterval 1 -MaxSamples 1 -ErrorAction Stop).CounterSamples;"
            "($samples|Measure-Object CookedValue -Sum).Sum"
        )
        try:
            result = self._run_powershell(script, timeout=3.5)
        except (OSError, subprocess.SubprocessError):
            return None
        value = (
            self._number_or_none(result.stdout.strip())
            if result.returncode == 0
            else None
        )
        return min(100.0, max(0.0, value)) if value is not None else None

    def _collect_volume(self) -> tuple[float, bool] | None:
        if sys.platform != "win32":
            return None
        try:
            from pycaw.pycaw import AudioUtilities

            endpoint = AudioUtilities.GetSpeakers().EndpointVolume
            return (
                round(float(endpoint.GetMasterVolumeLevelScalar()) * 100, 1),
                bool(endpoint.GetMute()),
            )
        except Exception:
            return None

    def _collect_brightness(self) -> float | None:
        script = (
            "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
            "-ErrorAction Stop | Where-Object Active | "
            "Select-Object -First 1 -ExpandProperty CurrentBrightness"
        )
        try:
            result = self._run_powershell(script, timeout=2.5)
        except (OSError, subprocess.SubprocessError):
            return None
        return self._number_or_none(result.stdout.strip()) if result.returncode == 0 else None

    def _collect_libre_hardware_monitor(self) -> dict[str, float]:
        try:
            response = self.url_opener(
                self.libre_hardware_monitor_url,
                timeout=0.8,
            )
            with response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return {}
        sensors: list[tuple[str, float, str]] = []
        self._flatten_lhm(payload, (), sensors)
        output: dict[str, float] = {}
        cpu_temps = [
            value
            for path, value, unit in sensors
            if "°c" in unit.casefold()
            and "cpu" in path.casefold()
            and any(token in path.casefold() for token in ("package", "core max", "cpu"))
        ]
        gpu_temps = [
            value
            for path, value, unit in sensors
            if "°c" in unit.casefold() and "gpu" in path.casefold()
        ]
        fan_speeds = [
            value
            for path, value, unit in sensors
            if "rpm" in unit.casefold() or "fan" in path.casefold() and "rpm" in unit.casefold()
        ]
        gpu_powers = [
            value
            for path, value, unit in sensors
            if unit.strip().casefold() == "w" and "gpu" in path.casefold()
        ]
        if cpu_temps:
            output["cpu_temperature"] = max(cpu_temps)
        if gpu_temps:
            output["gpu_temperature"] = max(gpu_temps)
        if fan_speeds:
            output["fan_speed"] = max(fan_speeds)
        if gpu_powers:
            output["gpu_power"] = sum(gpu_powers)
        return output

    def _flatten_lhm(
        self,
        node: object,
        path: tuple[str, ...],
        output: list[tuple[str, float, str]],
    ) -> None:
        if isinstance(node, list):
            for child in node:
                self._flatten_lhm(child, path, output)
            return
        if not isinstance(node, dict):
            return
        label = str(node.get("Text") or node.get("Name") or "").strip()
        current_path = path + ((label,) if label else ())
        raw_value = node.get("Value")
        if isinstance(raw_value, (int, float)):
            output.append((" / ".join(current_path), float(raw_value), ""))
        elif isinstance(raw_value, str):
            parsed = self._number_or_none(raw_value)
            if parsed is not None:
                unit = raw_value.replace(str(parsed), "").strip()
                output.append((" / ".join(current_path), parsed, unit))
        for key in ("Children", "children", "Hardware", "Sensors"):
            children = node.get(key)
            if children is not None:
                self._flatten_lhm(children, current_path, output)

    def _run_powershell(
        self,
        script: str,
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        return self._run_command(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            timeout=timeout,
        )

    def _run_command(
        self,
        command: list[str],
        *,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        return self.command_runner(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
            check=False,
        )

    @staticmethod
    def _number_or_none(value: str) -> float | None:
        match = re.search(r"-?\d+(?:[.,]\d+)?", value)
        if match is None:
            return None
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _format_bytes(value: float) -> str:
        gib = value / (1024**3)
        return f"{gib:.1f} GB"

    @staticmethod
    def _format_rate(value: float) -> str:
        if value >= 1024**2:
            return f"{value / 1024**2:.1f} MB/s"
        return f"{value / 1024:.1f} KB/s"


class HardwareMonitorService(QObject):
    snapshot_ready = Signal(object)
    collection_failed = Signal(str)
    busy_changed = Signal(bool)
    _completed = Signal(int, object, object)

    def __init__(
        self,
        collector: HardwareCollector,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.collector = collector
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="spring-hardware",
        )
        self._generation = 0
        self._busy = False
        self._completed.connect(self._deliver)

    @property
    def busy(self) -> bool:
        return self._busy

    def request(self, kind: str) -> None:
        self._generation += 1
        generation = self._generation
        self._set_busy(True)
        future = self._executor.submit(self.collector.collect, kind)

        def finished(completed_future: object) -> None:
            try:
                snapshot = completed_future.result()
                error = None
            except Exception as exc:  # pragma: no cover - delivered and tested via fakes.
                snapshot = None
                error = exc
            self._completed.emit(generation, snapshot, error)

        future.add_done_callback(finished)

    def cancel(self) -> None:
        self._generation += 1
        self._set_busy(False)

    def shutdown(self) -> None:
        self.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _deliver(
        self,
        generation: int,
        snapshot: HardwareSnapshot | None,
        error: Exception | None,
    ) -> None:
        if generation != self._generation:
            return
        self._set_busy(False)
        if error is not None:
            self.collection_failed.emit(str(error))
        elif snapshot is not None:
            self.snapshot_ready.emit(snapshot)

    def _set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        self.busy_changed.emit(busy)
