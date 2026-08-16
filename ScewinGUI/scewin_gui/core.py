"""BIOS data models, NVRAM parser, validation, and filesystem service."""

from __future__ import annotations

import datetime
import os
import re
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from re import Pattern

from .config import APP_CONFIG, AppConfig
from .logging_config import get_logger

logger = get_logger("core")


class NvramValidationError(ValueError):
    """Raised when a selected file is not a valid SCEWIN NVRAM document."""


class SafetyBackupError(RuntimeError):
    """Raised when a mandatory pre-import backup cannot be created."""


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
class CommandResult:
    """Structured result emitted by a background SCEWIN worker."""

    success: bool
    description: str
    action: str
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error_kind: str = ""

    @property
    def detail(self) -> str:
        """Return the most useful diagnostic text for the UI and logs."""
        if self.success:
            return self.stdout.strip()
        return self.stderr.strip() or self.error_kind


@dataclass(slots=True)
class BiosSetting:
    """One editable BIOS setup entry and its original file block."""

    name: str = ""
    help_string: str = ""
    token: str = ""
    offset: str = ""
    width: str = ""
    bios_default: str = ""
    current_value: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)
    raw_value: str = ""
    is_numeric: bool = False
    options_map: dict[str, str] = field(default_factory=dict)
    line_start: int = 0
    line_end: int = 0
    original_lines: list[str] = field(default_factory=list)
    initial_value: str = ""
    is_modified: bool = False

    # Удобное строковое представление для отладки.
    def __repr__(self) -> str:
        return f"<BiosSetting {self.name}: {self.current_value}>"

    # Устанавливает новое значение и фиксирует факт изменения.
    def set_value(self, new_value: str) -> None:
        clean_new = new_value.strip()
        clean_current = self.current_value.strip()

        if clean_current != clean_new:
            self.current_value = clean_new
            self.is_modified = clean_new != self.initial_value

    # Сбрасывает значение на BIOS Default, если доступно.
    def reset_to_default(self) -> None:
        if self.bios_default and self.bios_default != "-":
            self.set_value(self.bios_default)

    # Возвращает значение к исходному состоянию.
    def reset_to_initial(self) -> None:
        self.current_value = self.initial_value
        self.is_modified = False


class BiosParser:
    """Parse SCEWIN NVRAM text and rebuild changed setting blocks."""

    RE_QUESTION = re.compile(r"^\s*Setup Question\s*=\s*(.*)")
    RE_HELP = re.compile(r"^\s*Help String\s*=\s*(.*)")
    RE_TOKEN = re.compile(r"^\s*Token\s*=\s*(.*)")
    RE_OFFSET = re.compile(r"^\s*Offset\s*=\s*(.*)")
    RE_DEFAULT = re.compile(r"^\s*BIOS Default\s*=\s*(.*)")
    RE_VALUE = re.compile(r"^\s*Value\s*=\s*(.*)")
    RE_OPTION = re.compile(r"(\*?)\[([0-9A-Fa-f]+)\]\s*(.*)")
    RE_OPTION_LINE = re.compile(r"^(.*?)(\*?)(\[[0-9A-Fa-f]+\]\s*)(.*)$")
    RE_VALUE_LINE = re.compile(r"^(\s*Value\s*=\s*)(.*)")
    RE_META_FIELD = re.compile(
        r"^(\s*)(Setup Question|Help String|Token|Offset|Width|BIOS Default|Options)"
        r"(\s*=\s*)(.*)",
        re.IGNORECASE,
    )
    META_FIELDS: tuple[tuple[Pattern[str], str], ...] = (
        (RE_HELP, "help_string"),
        (RE_TOKEN, "token"),
        (RE_OFFSET, "offset"),
        (RE_DEFAULT, "bios_default"),
    )
    SPACED_META_KEYS = frozenset(("Setup Question", "Help String"))

    # Подготавливает хранилище заголовка файла.
    def __init__(self) -> None:
        self.header_lines: list[str] = []

    # Основной разбор текстового дампа NVRAM на настройки.
    def parse_file(self, content: str) -> list[BiosSetting]:
        # Parse raw NVRAM text into a list of BiosSetting objects.
        settings: list[BiosSetting] = []
        lines = content.splitlines()
        current_setting: BiosSetting | None = None
        self.header_lines = []

        for i, line in enumerate(lines):
            if "=" not in line and "[" not in line:
                continue
            match_question = self.RE_QUESTION.match(line)
            if match_question:
                if current_setting:
                    self._finalize_setting_block(current_setting, i, lines)
                    settings.append(current_setting)
                else:
                    if i > 0:
                        self.header_lines = lines[0:i]

                current_setting = BiosSetting()
                current_setting.line_start = i
                current_setting.name = match_question.group(1).strip()
                continue

            if current_setting:
                for regex, attribute in self.META_FIELDS:
                    self._parse_line_for_setting(
                        current_setting,
                        line,
                        regex,
                        attribute,
                    )

                match_value = self.RE_VALUE.match(line)
                if match_value:
                    val = match_value.group(1).split("//")[0].strip()
                    current_setting.raw_value = val
                    if not current_setting.current_value:
                        current_setting.current_value = val
                    current_setting.is_numeric = True
                    continue

                if "[" in line and "]" in line:
                    match_opt = self.RE_OPTION.search(line)
                    if match_opt:
                        is_active = match_opt.group(1) == "*"
                        opt_id = match_opt.group(2)
                        remainder = match_opt.group(3)
                        opt_text = remainder.split("//")[0].strip()

                        current_setting.options.append((opt_id, opt_text))
                        current_setting.options_map[opt_text] = opt_id

                        if is_active:
                            current_setting.current_value = opt_text

        if current_setting:
            self._finalize_setting_block(current_setting, len(lines), lines)
            settings.append(current_setting)

        return settings

    # Универсальный разбор метаданных строки по регекспу.
    def _parse_line_for_setting(
        self,
        setting: BiosSetting,
        line: str,
        regex: Pattern[str],
        attribute: str,
    ) -> None:
        # Extract a single metadata field from a line when it matches.
        match = regex.match(line)
        if match:
            val = match.group(1).split("//")[0].strip()
            setattr(setting, attribute, val)

    # Завершает блок настройки и сохраняет исходные строки.
    def _finalize_setting_block(
        self,
        setting: BiosSetting,
        current_line_idx: int,
        lines: list[str],
    ) -> None:
        # Finalize a settings block and capture its original text.
        setting.line_end = current_line_idx - 1
        setting.original_lines = lines[setting.line_start : current_line_idx]
        if setting.bios_default:
            match = re.match(r"(\[.*?\])?(.*)", setting.bios_default)
            if match:
                setting.bios_default = match.group(2).strip()
        setting.initial_value = setting.current_value

    # Собирает новый текст NVRAM с учетом измененных значений.
    def generate_content(self, settings: list[BiosSetting]) -> str:
        # Rebuild the NVRAM file content using current setting values.
        output_lines: list[str] = []
        if self.header_lines:
            output_lines.extend(line for line in self.header_lines if line.strip())
            output_lines.append("")

        for i, setting in enumerate(settings):
            if i > 0:
                output_lines.append("")
            lines = list(setting.original_lines)
            target_value = setting.current_value
            for line in lines:
                match_meta = self.RE_META_FIELD.match(line)
                if match_meta:
                    indent, key, _, val = match_meta.groups()
                    sep = "\t= " if key in self.SPACED_META_KEYS else "\t="
                    line = f"{indent}{key}{sep}{val}"
                if setting.is_numeric:
                    match_val = self.RE_VALUE_LINE.match(line)
                    if match_val:
                        val_str = target_value
                        if setting.raw_value.startswith("<") and not val_str.startswith("<"):
                            val_str = f"<{val_str}>"
                        if setting.raw_value in line:
                            line = line.replace(setting.raw_value, val_str)
                    output_lines.append(line)
                elif setting.options:
                    match_opt = self.RE_OPTION_LINE.match(line)
                    if match_opt and "Setup Question" not in line and "BIOS Default" not in line:
                        prefix, asterisk, bracket_part, remainder = match_opt.groups()
                        opt_text_clean = remainder.split("//")[0].strip()
                        is_target = opt_text_clean == target_value
                        active_marker = "*" if is_target else ""
                        output_lines.append(f"{prefix}{active_marker}{bracket_part}{remainder}")
                    else:
                        output_lines.append(line)
                else:
                    output_lines.append(line)
        return "\n".join(output_lines)


class BiosService:
    """Validate files and prepare safe SCEWIN operations."""

    # Сохраняет путь к исполняемому файлу SCEWIN.
    def __init__(
        self,
        scewin_path: str | None = None,
        config: AppConfig = APP_CONFIG,
        base_dir: str | Path | None = None,
    ) -> None:
        self.config = config
        self.base_dir = str(Path(base_dir).resolve()) if base_dir else str(config.app_dir)
        self.scewin_path = scewin_path or config.scewin_executable

    def resolve_path(self, path: str) -> str:
        # Resolve relative paths against the application directory.
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_dir, path)

    def get_required_files(self) -> list[str]:
        return [self.scewin_path, "amifldrv64.sys", "amigendrv64.sys"]

    def create_export_operation(self, description: str) -> BiosCommand:
        """Prepare an operation that exports the current BIOS configuration."""
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
        """Validate a file and prepare a protected BIOS import operation."""
        resolved_path = self.validate_nvram_file(filepath)
        return BiosCommand(
            executable=self.resolve_path(self.scewin_path),
            arguments=("/i", "/s", resolved_path),
            description=description,
            action=action,
            dangerous=True,
            requires_backup=True,
        )

    def validate_nvram_file(self, filepath: str) -> str:
        """Validate the path, extension, size, and parsed NVRAM structure."""
        resolved_path = self.resolve_path(filepath)
        path = Path(resolved_path)
        if not path.is_file():
            raise NvramValidationError(f"Файл не найден: {filepath}")
        if path.suffix.lower() not in {".txt", ".nvram"}:
            raise NvramValidationError("Поддерживаются только .txt и .nvram файлы")
        if path.stat().st_size > 20 * 1024 * 1024:
            raise NvramValidationError("Размер NVRAM-файла превышает 20 МБ")
        content = self.load_file(resolved_path)
        self.validate_nvram_content(content)
        return resolved_path

    @staticmethod
    def validate_nvram_content(content: str) -> list[BiosSetting]:
        """Parse content and reject empty or structurally invalid documents."""
        if not content.strip():
            raise NvramValidationError("NVRAM-файл пуст")
        settings = BiosParser().parse_file(content)
        BiosService.validate_settings(settings)
        return settings

    @staticmethod
    def validate_settings(settings: list[BiosSetting]) -> None:
        """Reject parsed results that cannot represent a safe import."""
        if not settings:
            raise NvramValidationError("В файле не найдено ни одного параметра Setup Question")
        invalid = [setting for setting in settings if not setting.name.strip()]
        if invalid:
            raise NvramValidationError("Обнаружен параметр без имени")

    def create_safety_backup(self) -> str:
        """Create the mandatory backup required before every BIOS import."""
        source = self.resolve_path(self.config.nvram_file)
        if not os.path.isfile(source):
            raise SafetyBackupError(
                "Нельзя записывать BIOS без актуального nvram.txt. Сначала выполните экспорт."
            )
        try:
            self.validate_nvram_file(source)
            return self.create_backup(
                self.config.nvram_file,
                self.config.backup_directory,
            )
        except (OSError, NvramValidationError) as error:
            raise SafetyBackupError(f"Не удалось создать обязательный бэкап: {error}") from error
    # Проверяет наличие необходимых файлов рядом с приложением.
    def check_dependencies(self) -> tuple[bool, list[str], list[str]]:
        # Verify required SCEWIN files are present and readable.
        missing: list[str] = []
        unreadable: list[str] = []
        for relative_name in self.get_required_files():
            abs_path = self.resolve_path(relative_name)
            if not os.path.exists(abs_path):
                missing.append(relative_name)
                continue
            try:
                with open(abs_path, "rb") as binary_file:
                    if not binary_file.read(64):
                        unreadable.append(relative_name)
            except OSError:
                unreadable.append(relative_name)
        return len(missing) == 0 and len(unreadable) == 0, missing, unreadable

    # Создает резервную копию NVRAM файла с таймстампом.
    def create_backup(self, source: str, backup_dir: str = "backups") -> str:
        """Copy an NVRAM file into a uniquely timestamped backup."""
        source_path = self.resolve_path(source)
        backup_path = self.resolve_path(backup_dir)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Файл не найден: {source}")
        os.makedirs(backup_path, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = os.path.join(backup_path, f"nvram_backup_{timestamp}.txt")
        shutil.copy(source_path, dest)
        logger.info("Backup created: %s", dest)
        return dest

    def list_backups(self) -> list[tuple[str, float, int]]:
        """Return backup path, modification time, and size, newest first."""
        backup_path = Path(self.resolve_path(self.config.backup_directory))
        if not backup_path.exists():
            return []
        items: list[tuple[str, float, int]] = []
        for path in backup_path.iterdir():
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                logger.warning("Cannot stat backup: %s", path)
                continue
            items.append((str(path), stat.st_mtime, stat.st_size))
        return sorted(items, key=lambda item: item[1], reverse=True)

    def delete_backup(self, filepath: str) -> None:
        """Delete only files located directly inside the backup directory."""
        backup_dir = Path(self.resolve_path(self.config.backup_directory)).resolve()
        target = Path(filepath).resolve()
        if target.parent != backup_dir:
            raise ValueError("Удаление разрешено только в папке бэкапов")
        target.unlink()
        logger.info("Backup deleted: %s", target)

    # Пишет файл через временный файл для атомарности.
    def atomic_write(self, filepath: str, content: str) -> None:
        # Write data using a temp file and atomic replace.
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

    # Загружает текстовый файл с запасными кодировками.
    def load_file(self, filepath: str) -> str:
        # Load a text file with fallback encodings.
        resolved_path = self.resolve_path(filepath)
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"Файл не найден: {filepath}")
        for encoding in ("utf-8", "cp1252"):
            try:
                with open(resolved_path, encoding=encoding) as source_file:
                    return source_file.read()
            except UnicodeDecodeError:
                continue
        with open(
            resolved_path,
            encoding="utf-8",
            errors="replace",
        ) as source_file:
            return source_file.read()
