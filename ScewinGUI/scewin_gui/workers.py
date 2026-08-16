"""Background workers and application-wide BIOS-operation coordination."""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass

from .config import APP_CONFIG, AppConfig
from .core import (
    BiosCommand,
    BiosParser,
    BiosService,
    BiosSetting,
    CommandResult,
)
from .logging_config import get_logger
from .qt_compat import QObject, QThread, pyqtSignal

logger = get_logger("workers")


@dataclass(frozen=True, slots=True)
class NvramLoadResult:
    """Result of loading and parsing one NVRAM file."""

    success: bool
    filepath: str
    settings: list[BiosSetting] | None = None
    header_lines: list[str] | None = None
    error: str = ""


class BiosOperationCoordinator(QObject):
    """Prevent overlapping SCEWIN operations across all application pages."""

    state_changed = pyqtSignal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._description = ""

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def description(self) -> str:
        return self._description

    def try_acquire(self, description: str) -> bool:
        """Acquire the process-wide operation slot when it is free."""
        if self._busy:
            return False
        self._busy = True
        self._description = description
        self.state_changed.emit(True, description)
        return True

    def release(self) -> None:
        """Release the operation slot after worker completion or startup error."""
        if not self._busy:
            return
        self._busy = False
        self._description = ""
        self.state_changed.emit(False, "")


class BiosWorker(QThread):
    """Execute one prepared SCEWIN command outside the GUI thread."""

    result_ready = pyqtSignal(object)

    def __init__(
        self,
        operation: BiosCommand,
        config: AppConfig = APP_CONFIG,
    ) -> None:
        super().__init__()
        self.operation = operation
        self.config = config

    def run(self) -> None:
        """Execute SCEWIN and emit a structured result for every outcome."""
        command = [
            self.operation.executable,
            *self.operation.arguments,
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        logger.info("Starting operation %s", self.operation.action)
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=creation_flags,
                timeout=self.config.subprocess_timeout_seconds,
                check=False,
            )
            result = CommandResult(
                success=process.returncode == 0,
                description=self.operation.description,
                action=self.operation.action,
                stdout=process.stdout,
                stderr=process.stderr,
                return_code=process.returncode,
                error_kind="process" if process.returncode else "",
            )
        except subprocess.TimeoutExpired as error:
            result = CommandResult(
                success=False,
                description=self.operation.description,
                action=self.operation.action,
                stdout=_decode_timeout_stream(error.stdout),
                stderr=_decode_timeout_stream(error.stderr),
                error_kind="timeout",
            )
        except FileNotFoundError as error:
            result = _exception_result(self.operation, error, "not_found")
        except PermissionError as error:
            result = _exception_result(self.operation, error, "permission")
        except OSError as error:
            result = _exception_result(self.operation, error, "os_error")

        logger.log(
            logging.INFO if result.success else logging.ERROR,
            "Operation %s finished: %s",
            result.action,
            result.detail,
        )
        self.result_ready.emit(result)


class NVRAMLoadWorker(QThread):
    """Load, validate, and parse an NVRAM file outside the GUI thread."""

    result_ready = pyqtSignal(object)

    def __init__(
        self,
        filepath: str,
        service: BiosService,
    ) -> None:
        super().__init__()
        self.filepath = filepath
        self.service = service

    def run(self) -> None:
        try:
            content = self.service.load_file(self.filepath)
            parser = BiosParser()
            settings = parser.parse_file(content)
            self.service.validate_settings(settings)
            self.result_ready.emit(
                NvramLoadResult(
                    success=True,
                    filepath=self.filepath,
                    settings=settings,
                    header_lines=parser.header_lines,
                )
            )
        except (OSError, ValueError) as error:
            logger.error("Cannot load %s: %s", self.filepath, error)
            self.result_ready.emit(
                NvramLoadResult(
                    success=False,
                    filepath=self.filepath,
                    error=str(error),
                )
            )


def _decode_timeout_stream(value: bytes | str | None) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")


def _exception_result(
    operation: BiosCommand,
    error: OSError,
    error_kind: str,
) -> CommandResult:
    return CommandResult(
        success=False,
        description=operation.description,
        action=operation.action,
        stderr=str(error),
        error_kind=error_kind,
    )
