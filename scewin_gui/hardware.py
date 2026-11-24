"""Vendor SCEWIN execution, cryptographic validation, DriverGuard, and safety backups."""

from __future__ import annotations

from contextlib import contextmanager, suppress
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable, NamedTuple, Protocol

from .config import APP_CONFIG, AppConfig
from .logging_config import get_logger
from .nvram.document import BiosSetting, NvramDocument, NvramValidationError
from .nvram.parser import validate_nvram_content, validate_settings
from .nvram.session import load_text_file
from .vault import BackupVault

logger = get_logger("hardware")

EXPECTED_BINARY_HASHES: dict[str, str] = {
    "SCEWIN_64.exe": "2d78e7bb62fcab44c54fe853f51e8836ada45ea374027423bcb6d7a5db46502b",
    "amifldrv64.sys": "e7cbfb16261de1c7f009431d374d90e9eb049ba78246e38bc4c8b9e06f324b6f",
    "amigendrv64.sys": "ffc72f0bde21ba20aa97bee99d9e96870e5aa40cce9884e44c612757f939494f",
}


class DependencyStatus(NamedTuple):
    """Result of dependency presence, readability, integrity and HVCI check."""

    ok: bool
    missing: list[str]
    unreadable: list[str]
    tampered: list[str]
    hvci_active: bool


def calculate_sha256(filepath: str) -> str:
    """Calculate the SHA-256 hash of a file for integrity verification."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest().lower()


def is_hvci_active() -> bool:
    """Check whether Windows Hypervisor-Enforced Code Integrity (HVCI) is active."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "Enabled")
            return bool(val)
    except (OSError, ImportError):
        return False


class SafetyBackupError(RuntimeError):
    """Raised when a mandatory pre-import backup cannot be created."""


class BiosExecutionError(RuntimeError):
    """Base exception for SCEWIN process execution failures."""


class BiosTimeoutError(BiosExecutionError):
    """Raised when SCEWIN process exceeds the configured timeout."""


class BiosPermissionError(BiosExecutionError):
    """Raised when process lacks administrative privileges."""


@dataclass(frozen=True, slots=True)
class BiosCommand:
    """A validated SCEWIN command prepared by the service layer."""

    executable: str
    arguments: tuple[str, ...]
    description: str
    action: str
    dangerous: bool = False
    requires_backup: bool = False


@dataclass(frozen=True, slots=True)
class BiosOperationResult:
    """Structured result emitted by a background SCEWIN worker or BiosExecutor."""

    success: bool
    description: str
    action: str
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    backup_path: str = ""
    error_kind: str = ""

    @property
    def detail(self) -> str:
        """Return the most useful diagnostic text for the UI and logs."""
        if self.success:
            return self.stdout.strip()
        return self.stderr.strip() or self.error_kind


# Backwards compatibility alias
CommandResult = BiosOperationResult


class ProcessRunner(Protocol):
    """Callable runner protocol for executing system commands."""

    def __call__(
        self,
        command: list[str],
        timeout: int,
    ) -> BiosOperationResult:
        ...


def default_process_runner(
    command: list[str],
    timeout: int,
) -> BiosOperationResult:
    """Execute a system command using Windows-safe subprocess settings."""
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=timeout,
            creationflags=creationflags,
        )
        return BiosOperationResult(
            success=proc.returncode == 0,
            description=" ".join(command),
            action="",
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            return_code=proc.returncode,
            error_kind="" if proc.returncode == 0 else (proc.stderr.strip() or proc.stdout.strip() or f"Process error {proc.returncode}"),
        )
    except subprocess.TimeoutExpired as exc:
        raise BiosTimeoutError("Таймаут операции SCEWIN") from exc
    except PermissionError as exc:
        raise BiosPermissionError("Требуются права администратора для доступа к BIOS") from exc


class DriverGuard:
    """Guarantees vendor driver service teardown and file unlock upon process completion."""

    @staticmethod
    @contextmanager
    def guard(driver_names: tuple[str, ...] = ("amifldrv64", "amigendrv64")):
        try:
            yield
        finally:
            if sys.platform == "win32":
                for drv in driver_names:
                    try:
                        subprocess.run(
                            ["sc", "stop", drv],
                            capture_output=True,
                            check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=2,
                        )
                    except Exception:
                        pass


class BiosHardware:
    """Coordinates vendor SCEWIN binary validation, safety backups, and hardware execution."""

    def __init__(
        self,
        config: AppConfig = APP_CONFIG,
        vault: BackupVault | None = None,
        runner: ProcessRunner | None = None,
        base_dir: str | Path | None = None,
        scewin_path: str | None = None,
    ) -> None:
        self.config = config
        self.base_dir = str(Path(base_dir).resolve()) if base_dir else str(config.app_dir)
        self.scewin_path = scewin_path or config.scewin_executable
        self.vault = vault or BackupVault(config.backup_directory, resolve_fn=self.resolve_path)
        self.runner = runner or default_process_runner

    def resolve_path(self, path: str) -> str:
        """Resolve relative paths against the application directory."""
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_dir, path)

    def get_required_files(self) -> list[str]:
        return [self.scewin_path, "amifldrv64.sys", "amigendrv64.sys"]

    def check_dependencies(self) -> DependencyStatus:
        """Verify required SCEWIN files are present, readable, and authentic."""
        missing: list[str] = []
        unreadable: list[str] = []
        tampered: list[str] = []
        for relative_name in self.get_required_files():
            abs_path = self.resolve_path(relative_name)
            if not os.path.exists(abs_path):
                missing.append(relative_name)
                continue
            try:
                with open(abs_path, "rb") as binary_file:
                    if not binary_file.read(64):
                        unreadable.append(relative_name)
                        continue
            except OSError:
                unreadable.append(relative_name)
                continue

            expected_hash = EXPECTED_BINARY_HASHES.get(relative_name)
            if expected_hash:
                try:
                    actual_hash = calculate_sha256(abs_path)
                    if actual_hash != expected_hash:
                        logger.error(
                            "Integrity check failed for %s: expected %s, got %s",
                            relative_name,
                            expected_hash,
                            actual_hash,
                        )
                        tampered.append(relative_name)
                except OSError:
                    unreadable.append(relative_name)

        hvci = is_hvci_active()
        if hvci:
            logger.warning(
                "Windows HVCI (Memory Integrity) is active; vulnerable drivers may be blocked"
            )

        ok = len(missing) == 0 and len(unreadable) == 0 and len(tampered) == 0
        return DependencyStatus(
            ok=ok,
            missing=missing,
            unreadable=unreadable,
            tampered=tampered,
            hvci_active=hvci,
        )

    def _ensure_dependencies_ok(self) -> None:
        status = self.check_dependencies()
        if not status.ok:
            faults = status.missing + status.unreadable + status.tampered
            raise RuntimeError(
                f"Операция SCEWIN отклонена: файлы не прошли проверку безопасности ({', '.join(faults)})"
            )

    def create_safety_backup(self) -> str:
        """Create the mandatory backup required before every BIOS import."""
        source = self.resolve_path(self.config.nvram_file)
        if not os.path.isfile(source):
            raise SafetyBackupError(
                "Нельзя записывать BIOS без актуального nvram.txt. Сначала выполните экспорт."
            )
        try:
            BiosService.validate_nvram_file_path(source, resolve_fn=self.resolve_path)
            return self.vault.create_backup(source)
        except (OSError, NvramValidationError) as error:
            raise SafetyBackupError(f"Не удалось создать обязательный бэкап: {error}") from error

    def execute_export(self, description: str = "Экспорт BIOS") -> BiosOperationResult:
        self._ensure_dependencies_ok()
        exe = self.resolve_path(self.scewin_path)
        out_file = self.resolve_path(self.config.nvram_file)
        cmd = [exe, "/o", "/s", out_file]

        logger.info("Executing BIOS export: %s", cmd)
        with DriverGuard.guard():
            cmd_result = self.runner(cmd, self.config.subprocess_timeout_seconds)
        if not cmd_result.success:
            raise BiosExecutionError(cmd_result.detail or f"SCEWIN exited with code {cmd_result.return_code}")

        # Invariant: Auto-backup on successful export
        backup_path = self.vault.create_backup(out_file)
        return BiosOperationResult(
            success=True,
            description=description,
            action="export",
            stdout=cmd_result.stdout,
            stderr=cmd_result.stderr,
            return_code=cmd_result.return_code,
            backup_path=backup_path,
        )

    def execute_import(
        self,
        nvram_path: str,
        description: str = "Импорт BIOS",
        action: str = "import",
    ) -> BiosOperationResult:
        self._ensure_dependencies_ok()
        resolved_file = BiosService.validate_nvram_file_path(nvram_path, resolve_fn=self.resolve_path)

        # Invariant: Mandatory safety backup before writing to BIOS
        safety_backup_path = self.create_safety_backup()

        exe = self.resolve_path(self.scewin_path)
        cmd = [exe, "/i", "/s", resolved_file]

        logger.info("Executing BIOS import (%s): %s", action, cmd)
        with DriverGuard.guard():
            cmd_result = self.runner(cmd, self.config.subprocess_timeout_seconds)
        if not cmd_result.success:
            raise BiosExecutionError(cmd_result.detail or f"SCEWIN exited with code {cmd_result.return_code}")

        return BiosOperationResult(
            success=True,
            description=description,
            action=action,
            stdout=cmd_result.stdout,
            stderr=cmd_result.stderr,
            return_code=cmd_result.return_code,
            backup_path=safety_backup_path,
        )


class BiosExecutor(BiosHardware):
    """Backwards compatibility adapter for BiosHardware."""

    def __init__(
        self,
        service: BiosService | None = None,
        runner: ProcessRunner | None = None,
        vault: BackupVault | None = None,
        config: AppConfig | None = None,
        base_dir: str | Path | None = None,
        scewin_path: str | None = None,
    ) -> None:
        effective_config = config or (service.config if service else APP_CONFIG)
        effective_base_dir = base_dir or (service.base_dir if service else None)
        effective_scewin_path = scewin_path or (service.scewin_path if service else None)
        effective_vault = vault or (service.vault if service else None)
        super().__init__(
            config=effective_config,
            vault=effective_vault,
            runner=runner,
            base_dir=effective_base_dir,
            scewin_path=effective_scewin_path,
        )
        self.service = service or BiosService(config=effective_config, base_dir=effective_base_dir)


class BiosService:
    """Validate files and prepare safe SCEWIN operations."""

    def __init__(
        self,
        scewin_path: str | None = None,
        config: AppConfig = APP_CONFIG,
        base_dir: str | Path | None = None,
    ) -> None:
        self.config = config
        self.base_dir = str(Path(base_dir).resolve()) if base_dir else str(config.app_dir)
        self.scewin_path = scewin_path or config.scewin_executable
        self.vault = BackupVault(config.backup_directory, resolve_fn=self.resolve_path)

    def resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_dir, path)

    def get_required_files(self) -> list[str]:
        return [self.scewin_path, "amifldrv64.sys", "amigendrv64.sys"]

    def _ensure_dependencies_ok(self) -> None:
        status = self.check_dependencies()
        if not status.ok:
            faults = status.missing + status.unreadable + status.tampered
            raise RuntimeError(
                f"Операция SCEWIN отклонена: файлы не прошли проверку безопасности ({', '.join(faults)})"
            )

    def create_export_operation(self, description: str) -> BiosCommand:
        self._ensure_dependencies_ok()
        return BiosCommand(
            executable=self.resolve_path(self.scewin_path),
            arguments=(
                "/o",
                "/s",
                self.resolve_path(self.config.nvram_file),
            ),
            description=description,
            action="export",
        )

    def create_import_operation(
        self,
        filepath: str,
        description: str,
        action: str = "import",
    ) -> BiosCommand:
        self._ensure_dependencies_ok()
        resolved_path = self.validate_nvram_file(filepath)
        return BiosCommand(
            executable=self.resolve_path(self.scewin_path),
            arguments=("/i", "/s", resolved_path),
            description=description,
            action=action,
            dangerous=True,
            requires_backup=True,
        )

    @staticmethod
    def validate_nvram_file_path(
        filepath: str,
        resolve_fn: Callable[[str], str] | None = None,
    ) -> str:
        resolved_path = resolve_fn(filepath) if resolve_fn else str(Path(filepath).resolve())
        path = Path(resolved_path)
        if not path.is_file():
            raise NvramValidationError(f"Файл не найден: {filepath}")
        if path.suffix.lower() not in {".txt", ".nvram"}:
            raise NvramValidationError("Поддерживаются только .txt и .nvram файлы")
        if path.stat().st_size > 20 * 1024 * 1024:
            raise NvramValidationError("Размер NVRAM-файла превышает 20 МБ")
        content = load_text_file(resolved_path)
        validate_nvram_content(content)
        return resolved_path

    def validate_nvram_file(self, filepath: str) -> str:
        return self.validate_nvram_file_path(filepath, resolve_fn=self.resolve_path)

    @staticmethod
    def validate_nvram_content(content: str) -> NvramDocument:
        return validate_nvram_content(content)

    @staticmethod
    def validate_settings(settings: list[BiosSetting]) -> None:
        validate_settings(settings)

    def create_safety_backup(self) -> str:
        source = self.resolve_path(self.config.nvram_file)
        if not os.path.isfile(source):
            raise SafetyBackupError(
                "Нельзя записывать BIOS без актуального nvram.txt. Сначала выполните экспорт."
            )
        try:
            BiosService.validate_nvram_file_path(source, resolve_fn=self.resolve_path)
            return self.vault.create_backup(source)
        except (OSError, NvramValidationError) as error:
            raise SafetyBackupError(f"Не удалось создать обязательный бэкап: {error}") from error

    def check_dependencies(self) -> DependencyStatus:
        hw = BiosHardware(config=self.config, base_dir=self.base_dir, scewin_path=self.scewin_path)
        return hw.check_dependencies()

    def create_backup(self, source: str, backup_dir: str | None = None) -> str:
        if backup_dir and backup_dir != self.config.backup_directory:
            vault = BackupVault(backup_dir, resolve_fn=self.resolve_path)
            return vault.create_backup(source)
        return self.vault.create_backup(source)

    def list_backups(self) -> list[tuple[str, float, int]]:
        return [(b.path, b.mtime, b.size) for b in self.vault.list_all()]

    def delete_backup(self, filepath: str) -> None:
        self.vault.delete(filepath)

    def atomic_write(self, filepath: str, content: str) -> None:
        target_path = self.resolve_path(filepath)
        dir_path = os.path.dirname(target_path) or self.base_dir
        temp_fd, temp_path = tempfile.mkstemp(
            dir=dir_path,
            prefix=".tmp_nvram_",
            suffix=".txt",
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
                temp_file.write(content)
            os.replace(temp_path, target_path)
            logger.info("File written atomically: %s", target_path)
        except OSError:
            if os.path.exists(temp_path):
                with suppress(OSError):
                    os.unlink(temp_path)
            raise

    @staticmethod
    def load_text_file(filepath: str) -> str:
        return load_text_file(filepath)

    def load_file(self, filepath: str) -> str:
        resolved_path = self.resolve_path(filepath)
        return self.load_text_file(resolved_path)
