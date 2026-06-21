from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .asset_loader import AssetValidationError, load_animation_manifest, resource_path
from .foreground_monitor import ForegroundMonitor
from .foreground_rules import ForegroundRuleError, ForegroundRuleStore
from .pet_window import PetWindow
from .settings import PetSettings


def create_application(argv: list[str] | None = None) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Spring")
    app.setOrganizationName("SpringPet")
    app.setWindowIcon(QIcon(str(resource_path("icon/pig.ico"))))
    app.setQuitOnLastWindowClosed(True)
    return app


def main(argv: list[str] | None = None) -> int:
    app = create_application(argv)
    try:
        manifest = load_animation_manifest()
    except AssetValidationError as exc:
        QMessageBox.critical(None, "Spring 启动失败", str(exc))
        return 1

    persistent_states = {
        name for name, state in manifest.states.items() if state.is_persistent
    }
    foreground_rules = ForegroundRuleStore(persistent_states)
    try:
        foreground_config = foreground_rules.load()
    except ForegroundRuleError as exc:
        foreground_config = foreground_rules.use_defaults()
        QMessageBox.warning(
            None,
            "Spring 应用规则",
            f"{exc}\n\n本次运行将使用内置默认规则。",
        )
    foreground_monitor = ForegroundMonitor(
        debounce_ms=foreground_config.debounce_ms,
        reconcile_interval_ms=foreground_config.reconcile_interval_ms,
    )

    window = PetWindow(
        manifest,
        PetSettings(),
        foreground_rules=foreground_rules,
        foreground_monitor=foreground_monitor,
    )
    app.commitDataRequest.connect(
        lambda _session_manager: window.force_exit_for_session_end()
    )
    window.show()
    return app.exec()
