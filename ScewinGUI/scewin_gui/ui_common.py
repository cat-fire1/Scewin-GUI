"""Reusable GUI components and protected BIOS-command workflow."""

from __future__ import annotations

import datetime
import time
from contextlib import suppress

from .config import APP_CONFIG, AppConfig
from .core import BiosCommand, BiosService, CommandResult, SafetyBackupError
from .i18n import LanguageManager
from .logging_config import get_logger
from .qt_compat import (
    TEXT_CURSOR_END,
    InfoBar,
    QEvent,
    QMessageBox,
    QObject,
    QPoint,
    QTimer,
    QToolTip,
    QWidget,
    TextEdit,
)
from .workers import BiosOperationCoordinator, BiosWorker

logger = get_logger("ui")


class DelayedToolTipEventFilter(QObject):
    """Delay tooltip display to reduce visual noise while moving the pointer."""

    def __init__(self, delay_ms: int = APP_CONFIG.tooltip_delay_ms) -> None:
        super().__init__()
        self.delay_ms = delay_ms
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._show_tooltip)
        self.current_widget: QWidget | None = None
        self.original_tooltip = ""

    def eventFilter(
        self,
        obj: QObject | None,
        event: QEvent | None,
    ) -> bool:
        if isinstance(obj, QWidget) and event is not None:
            tooltip = obj.toolTip()
            if event.type() == QEvent.Type.Enter and tooltip:
                self.current_widget = obj
                self.original_tooltip = tooltip
                obj.setToolTip("")
                self.timer.start(self.delay_ms)
            elif event.type() == QEvent.Type.Leave:
                self.timer.stop()
                self._restore_tooltip()
        return super().eventFilter(obj, event)

    def _show_tooltip(self) -> None:
        if self.current_widget is None or not self.original_tooltip:
            return
        self.current_widget.setToolTip(self.original_tooltip)
        QToolTip.showText(
            self.current_widget.mapToGlobal(QPoint(0, self.current_widget.height())),
            self.original_tooltip,
            self.current_widget,
        )

    def _restore_tooltip(self) -> None:
        if self.current_widget is not None and self.original_tooltip:
            self.current_widget.setToolTip(self.original_tooltip)
        self.current_widget = None
        self.original_tooltip = ""


class LocalizedInterface(QWidget):
    """Base widget that owns a language manager and translation shortcut."""

    def __init__(
        self,
        parent: QWidget | None = None,
        lang_manager: LanguageManager | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.lang_manager = lang_manager or LanguageManager()
        self.lang_manager.language_changed.connect(self.apply_language)

    def t(self, key: str, **kwargs: object) -> str:
        """Translate one key with the active language manager."""
        return self.lang_manager.tr(key, **kwargs)

    def apply_language(self) -> None:
        """Update translated widget text in subclasses."""


class BiosCommandInterface(LocalizedInterface):
    """Shared, serialized, and backup-protected SCEWIN worker lifecycle."""

    txt_log: TextEdit

    def __init__(
        self,
        parent: QWidget | None = None,
        lang_manager: LanguageManager | None = None,
        coordinator: BiosOperationCoordinator | None = None,
        config: AppConfig = APP_CONFIG,
    ) -> None:
        super().__init__(parent=parent, lang_manager=lang_manager)
        self.config = config
        self.service = BiosService(config=config)
        self.coordinator = coordinator or BiosOperationCoordinator()
        self.worker: BiosWorker | None = None

    def log(self, message: str) -> None:
        """Write a message to both the standard logger and the visible log."""
        logger.info(message)
        timestamp = time.strftime("%H:%M:%S")
        self.txt_log.append(f"[{timestamp}] {message}")
        self.txt_log.moveCursor(TEXT_CURSOR_END)

    def run_operation(self, operation: BiosCommand) -> None:
        """Confirm, back up, serialize, and start one BIOS operation."""
        if operation.dangerous and not self._confirm_operation(operation):
            return
        if not self.coordinator.try_acquire(operation.description):
            InfoBar.warning(
                self.t("infobar.warning"),
                self.t("bios.busy", action=self.coordinator.description),
                parent=self,
            )
            return

        try:
            if operation.requires_backup:
                backup_path = self.service.create_safety_backup()
                self.log(self.t("bios.backup_created", path=backup_path))
            self.log(self.t("log.started", desc=operation.description))
            self.worker = BiosWorker(operation, self.config)
            self.worker.result_ready.connect(self.on_worker_finished)
            self.worker.start()
        except SafetyBackupError as error:
            logger.error("Mandatory backup failed: %s", error)
            self.coordinator.release()
            InfoBar.error(
                self.t("infobar.error"),
                self.t("bios.backup_required"),
                parent=self,
            )
            return
        except (OSError, RuntimeError, ValueError) as error:
            logger.exception("Cannot start BIOS operation")
            self.coordinator.release()
            InfoBar.error(
                self.t("infobar.error"),
                str(error),
                parent=self,
            )
            return

        InfoBar.info(
            self.t("infobar.loading_title"),
            self.t("infobar.loading_content", desc=operation.description),
            parent=self,
        )

    def on_worker_finished(self, result: CommandResult) -> None:
        """Display a structured result and release the global operation lock."""
        try:
            if result.success:
                self.log(self.t("log.success", detail=result.detail))
                InfoBar.success(
                    result.description,
                    self.t("infobar.success_content"),
                    parent=self,
                )
                self._after_worker_success(result)
            else:
                detail = self._translated_error(result)
                self.log(self.t("log.error", detail=detail))
                InfoBar.error(
                    result.description,
                    detail,
                    parent=self,
                )
        finally:
            self._dispose_worker()
            self.coordinator.release()

    def _confirm_operation(self, operation: BiosCommand) -> bool:
        reply = QMessageBox.question(
            self,
            self.t("bios.confirm_title"),
            self.t("bios.confirm_text", action=operation.description),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,  # type: ignore[arg-type]
        )
        return reply == QMessageBox.StandardButton.Yes

    def _translated_error(self, result: CommandResult) -> str:
        if result.error_kind == "timeout":
            return self.t("bios.timeout")
        if result.error_kind == "permission":
            return self.t("bios.permission")
        return result.detail or self.t("infobar.see_logs")

    def _after_worker_success(self, result: CommandResult) -> None:
        """Run interface-specific work after a successful command."""

    def _dispose_worker(self) -> None:
        if self.worker is None:
            return
        with suppress(TypeError):
            self.worker.result_ready.disconnect(self.on_worker_finished)
        self.worker.deleteLater()
        self.worker = None
