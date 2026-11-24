"""Active NVRAM document session, mutations, draft tracking, and persistence."""

from __future__ import annotations

import os
from pathlib import Path
import uuid
from typing import Callable

from .document import BiosSetting, NvramDocument, NvramValidationError
from .parser import BiosParser, validate_nvram_content, validate_settings


def load_text_file(filepath: str) -> str:
    """Load a text file with fallback encodings (utf-8, cp1252)."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Файл не найден: {filepath}")
    for encoding in ("utf-8", "cp1252"):
        try:
            with open(filepath, encoding=encoding) as source_file:
                return source_file.read()
        except UnicodeDecodeError:
            continue
    with open(filepath, encoding="utf-8", errors="replace") as source_file:
        return source_file.read()


class BiosDocumentSession:
    """Manages an active NVRAM document, setting changes, drafts, and persistence."""

    def __init__(
        self,
        filepath: str,
        document: NvramDocument,
        parser: BiosParser | None = None,
    ) -> None:
        self.filepath = filepath
        self.document = document
        self.document_id = uuid.uuid4().hex
        self.parser = parser or BiosParser()
        self._saved_values = self._compute_values()
        self._drafts: set[int] = set()

    @classmethod
    def open_file(
        cls,
        filepath: str,
        parser: BiosParser | None = None,
        load_fn: Callable[[str], str] | None = None,
    ) -> BiosDocumentSession:
        p = Path(filepath).resolve()
        if not p.is_file():
            raise NvramValidationError(f"Файл не найден: {filepath}")
        if p.suffix.lower() not in {".txt", ".nvram"}:
            raise NvramValidationError("Поддерживаются только .txt и .nvram файлы")
        if p.stat().st_size > 20 * 1024 * 1024:
            raise NvramValidationError("Размер NVRAM-файла превышает 20 МБ")

        active_parser = parser or BiosParser()
        if load_fn:
            content = load_fn(str(p))
        else:
            content = load_text_file(str(p))
        if not content.strip():
            raise NvramValidationError("NVRAM-файл пуст")

        doc = active_parser.parse_file(content)
        validate_settings(doc.settings)
        return cls(filepath=str(p), document=doc, parser=active_parser)

    def _compute_values(self) -> tuple:
        return tuple((s.current_value, s.current_option_id) for s in self.document.settings)

    @property
    def is_dirty(self) -> bool:
        return bool(self._drafts) or self._compute_values() != self._saved_values

    @property
    def modified_count(self) -> int:
        return sum(s.is_modified for s in self.document.settings)

    def get_setting(self, setting_id: int) -> BiosSetting:
        if type(setting_id) is not int or not 0 <= setting_id < len(self.document.settings):
            raise ValueError("Invalid setting ID")
        return self.document.settings[setting_id]

    def edit(self, setting_id: int, value: str) -> BiosSetting:
        setting = self.get_setting(setting_id)
        if not isinstance(value, str):
            raise ValueError("Invalid setting value")
        if setting.options:
            setting.set_option(value)
        elif setting.is_numeric:
            setting.set_value(f"<{value.strip().strip('<>')}>")
        else:
            raise ValueError("Параметр доступен только для чтения")
        self._drafts.discard(setting_id)
        return setting

    def set_draft(self, setting_id: int, dirty: bool) -> bool:
        setting = self.get_setting(setting_id)
        if not setting.is_numeric or type(dirty) is not bool:
            raise ValueError("Invalid numeric draft")
        if dirty:
            self._drafts.add(setting_id)
        else:
            self._drafts.discard(setting_id)
        return self.is_dirty

    def reset_setting(self, setting_id: int, mode: str) -> BiosSetting:
        setting = self.get_setting(setting_id)
        if mode == "default":
            setting.reset_to_default()
        elif mode == "initial":
            setting.reset_to_initial()
        else:
            raise ValueError("Unknown reset mode")
        self._drafts.discard(setting_id)
        return setting

    def generate_changes(self) -> str:
        if not any(s.is_modified for s in self.document.settings):
            raise ValueError("Нет изменённых параметров для сохранения")
        content = self.parser.generate_changes(self.document)
        validate_nvram_content(content)
        return content

    def generate_content(self) -> str:
        content = self.parser.generate_content(self.document)
        validate_nvram_content(content)
        return content

    def mark_saved(self) -> None:
        self._drafts.clear()
        self._saved_values = self._compute_values()

    def save_changes(self, target_path: str, write_fn: Callable[[str, str], None]) -> str:
        content = self.generate_changes()
        write_fn(target_path, content)
        self.mark_saved()
        return target_path

    def save_as(
        self,
        target_path: str,
        write_fn: Callable[[str, str], None],
        protected_paths: tuple[str, ...] = (),
    ) -> str:
        resolved_target = str(Path(target_path).resolve())
        for protected in protected_paths:
            if Path(protected).resolve() == Path(resolved_target):
                raise ValueError("Нельзя перезаписывать базовый файл экспорта NVRAM")
        content = self.generate_content()
        write_fn(resolved_target, content)
        new_session = self.open_file(resolved_target, parser=self.parser)
        self.filepath = new_session.filepath
        self.document = new_session.document
        self.document_id = new_session.document_id
        self._saved_values = new_session._saved_values
        self._drafts.clear()
        return resolved_target
