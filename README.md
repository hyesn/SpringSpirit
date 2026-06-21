# Spring Spirit

An environment-aware desktop companion for Windows.

Spring Spirit models desktop animation as an event-driven state orchestration problem. Native Win32 foreground hooks are resolved into process-level context, stabilized through debouncing and reconciliation, then routed through a deterministic priority system spanning persistent states, transient actions, drag feedback, startup sequences, and shutdown choreography.

[Download the latest Windows build](https://github.com/hyesn/SpringSpirit/releases/latest)

## Engineering

- Native `SetWinEventHook` integration with resilient process resolution
- Deterministic arbitration of asynchronous animation states
- Declarative animation topology driven by validated manifests
- DPI-aware RGBA rendering with per-frame alpha hit testing
- Hot-reloadable application rules with last-known-good recovery
- On-demand hardware telemetry with asynchronous, non-blocking diagnostics
- Multi-monitor persistence, session handling, and self-healing autostart

The renderer preserves full transparent canvases and character anchors; production frames are never cropped, recentered, re-keyed, or converted to GIF.

## Stack

`Python · PySide6 · Win32 API · PyInstaller · pytest`

## Build

```powershell
python -m pip install -r requirements.txt
pytest
pyinstaller --noconfirm --clean spring_pet.spec
```

Application-aware behavior is configured at:

```text
%APPDATA%\SpringPet\foreground_rules.json
```

## Hardware Diagnostics

The **Hardware Awareness** menu exposes two on-demand snapshots:

- **System Overview** — CPU/GPU load, memory, battery, audio, brightness, and network activity
- **Hardware Vitals** — CPU/GPU temperature, fan telemetry, and GPU board power when available

General metrics use Windows interfaces and `psutil`; NVIDIA telemetry uses `nvidia-smi`.
CPU temperature and motherboard fan sensors are optional: run the
[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
web server on `127.0.0.1:8085` to expose compatible sensors. Missing sensors are
reported as unavailable—Spring Spirit never invents zero readings or installs hardware drivers.
