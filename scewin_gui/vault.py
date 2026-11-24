"""Backup archive repository, rotation, and file boundary validation."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
from typing import Callable

from .logging_config import get_logger

logger = get_logger("vault")


@dataclass(frozen=True, slots=True)
class BackupItem:
    """Metadata for a verified backup file."""

    path: str
    name: str
    mtime: float
    size: int


class BackupVault:
    """Manages timestamped NVRAM backup archives and restoration."""

    def __init__(self, backup_dir: Path | str, resolve_fn: Callable[[str], str] | None = None) -> None:
        self.resolve_fn = resolve_fn or (lambda p: str(Path(p).resolve()))
        self.backup_dir_path = Path(self.resolve_fn(str(backup_dir))).resolve()

    def get_directory(self) -> Path:
        self.backup_dir_path.mkdir(parents=True, exist_ok=True)
        return self.backup_dir_path

    def list_all(self) -> list[BackupItem]:
        if not self.backup_dir_path.exists():
            return []
        items: list[BackupItem] = []
        for path in self.backup_dir_path.iterdir():
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                items.append(
                    BackupItem(
                        path=str(path),
                        name=path.name,
                        mtime=stat.st_mtime,
                        size=stat.st_size,
                    )
                )
            except OSError:
                continue
        return sorted(items, key=lambda item: item.mtime, reverse=True)

    def validate_backup_path(self, filepath: str) -> Path:
        target = Path(self.resolve_fn(filepath)).resolve()
        if target.parent != self.backup_dir_path or not target.is_file():
            raise ValueError("Файл не найден в каталоге резервных копий")
        return target

    def create_backup(self, source_path: str) -> str:
        resolved_source = self.resolve_fn(source_path)
        if not os.path.exists(resolved_source):
            raise FileNotFoundError(f"Файл не найден: {source_path}")
        self.get_directory()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = self.backup_dir_path / f"nvram_backup_{timestamp}.txt"
        shutil.copy(resolved_source, dest)
        logger.info("Backup created: %s", dest)
        return str(dest)

    def delete(self, filepath: str) -> None:
        target = self.validate_backup_path(filepath)
        target.unlink()
        logger.info("Backup deleted: %s", target)

    def open_in_explorer(self) -> None:
        dir_path = self.get_directory()
        if sys.platform == "win32":
            os.startfile(str(dir_path))
