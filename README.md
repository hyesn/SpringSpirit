# Spring Spirit

An environment-aware desktop spirit for Windows.

Spring Spirit is built less like a toy widget and more like a compact real-time interaction system: foreground-process sensing, discipline cycles, edge-aware placement, hardware telemetry, and declarative animation states are coordinated through one deterministic state engine.

## Highlights

- Win32 foreground hooks with debounce and reconciliation
- Manifest-driven animation roles, triggers, transitions, and persistence
- Focus/relax discipline flow with local visual feedback
- Multi-monitor snapping, clamping, and bubble avoidance
- Async hardware snapshots with optional LibreHardwareMonitor support
- DPI-aware RGBA rendering with alpha hit testing

`Python · PySide6 · Win32 API · Core Audio · NVIDIA SMI · LibreHardwareMonitor · PyInstaller`

[Download the latest Windows build](https://github.com/hyesn/SpringSpirit/releases/latest)

## Build

```powershell
python -m pip install -r requirements.txt
pytest
pyinstaller --noconfirm --clean spring_pet.spec
```

Thermal and fan data can be read from an optional local [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) endpoint. Missing sensors stay unavailable; Spring Spirit does not fake readings.
