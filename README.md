# Spring Spirit

An environment-aware desktop entity for Windows.

Spring Spirit treats a desktop character as a real-time systems problem rather than a sprite player. Native foreground events, process context, user interaction, lifecycle signals, and heterogeneous hardware telemetry are fused into a deterministic state-arbitration engine that drives responsive animation without blocking the UI thread.

## Architecture

- **Context sensing** — Win32 event hooks with debounced process resolution and reconciliation
- **State arbitration** — deterministic coordination of persistent, transient, diagnostic, drag, startup, and shutdown states
- **Hardware introspection** — asynchronous CPU/GPU, memory, power, thermal, audio, display, and network telemetry
- **Declarative motion** — validated manifest topology with extensible roles, triggers, transitions, and persistence
- **Precision rendering** — DPI-aware RGBA composition with per-frame alpha hit testing and stable character geometry
- **Fault tolerance** — optional sensor backends, last-known-good configuration recovery, and graceful capability degradation

`Python · PySide6 · Win32 API · Core Audio · NVIDIA SMI · LibreHardwareMonitor · PyInstaller`

[Download the latest Windows build](https://github.com/hyesn/SpringSpirit/releases/latest)

## Build

```powershell
python -m pip install -r requirements.txt
pytest
pyinstaller --noconfirm --clean spring_pet.spec
```

Optional thermal and fan telemetry is discovered through a local
[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
endpoint. Unsupported sensors remain explicitly unavailable; no kernel driver is installed and no synthetic readings are produced.
