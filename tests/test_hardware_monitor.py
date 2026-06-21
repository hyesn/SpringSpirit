from __future__ import annotations

import io
import json
import subprocess

from spring_pet.hardware_monitor import (
    HardwareCollector,
    HardwareMetric,
    classify_metric,
    snapshot_commentary,
)


def test_metric_thresholds_are_conservative() -> None:
    assert classify_metric("cpu_usage", 69.9) == "normal"
    assert classify_metric("cpu_usage", 70) == "busy"
    assert classify_metric("cpu_usage", 90) == "critical"
    assert classify_metric("memory_usage", 75) == "warning"
    assert classify_metric("cpu_temperature", 90) == "critical"
    assert classify_metric("gpu_temperature", 80) == "warning"
    assert classify_metric("battery_level", 10, charging=False) == "critical"
    assert classify_metric("battery_level", 5, charging=True) == "normal"


def test_commentary_uses_highest_available_severity() -> None:
    metrics = (
        HardwareMetric("cpu_usage", "CPU", 95, "%", "test", True, "critical"),
        HardwareMetric("memory_usage", "Memory", 30, "%", "test", True, "normal"),
    )
    severity, commentary = snapshot_commentary(metrics, ())
    assert severity == "critical"
    assert "撑不住" in commentary


def test_nvidia_smi_parser_handles_optional_values() -> None:
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            "42, 67, N/A, 25.5\n10, 55, 35, 12.0\n",
            "",
        )

    collector = HardwareCollector("http://localhost", command_runner=runner)
    result = collector._collect_nvidia()

    assert result["gpu_usage"] == 42
    assert result["gpu_temperature"] == 67
    assert result["fan_percent"] == 35
    assert result["gpu_power"] == 37.5


def test_libre_hardware_monitor_tree_is_flattened() -> None:
    payload = {
        "Text": "Machine",
        "Children": [
            {
                "Text": "CPU",
                "Children": [
                    {"Text": "CPU Package", "Value": "72.0 °C"},
                    {"Text": "CPU Fan", "Value": "1350 RPM"},
                ],
            },
            {
                "Text": "GPU",
                "Children": [
                    {"Text": "GPU Core", "Value": "61.0 °C"},
                    {"Text": "GPU Power", "Value": "88.5 W"},
                ],
            },
        ],
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    collector = HardwareCollector(
        "http://localhost",
        url_opener=lambda *_args, **_kwargs: Response(
            json.dumps(payload).encode("utf-8")
        ),
    )
    result = collector._collect_libre_hardware_monitor()

    assert result == {
        "cpu_temperature": 72.0,
        "gpu_temperature": 61.0,
        "fan_speed": 1350.0,
        "gpu_power": 88.5,
    }


def test_missing_optional_backends_return_no_fake_values() -> None:
    def failed_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "not available")

    def failed_url(*_args, **_kwargs):
        raise OSError("offline")

    collector = HardwareCollector(
        "http://localhost",
        command_runner=failed_runner,
        url_opener=failed_url,
    )

    assert collector._collect_nvidia() == {}
    assert collector._collect_libre_hardware_monitor() == {}

