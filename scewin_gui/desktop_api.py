"""Thread-safe, Qt-free API exposed only to the bundled desktop interface."""

from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import webbrowser

from .config import APP_CONFIG, AppConfig
from .core import BiosParser, BiosService, BiosSetting, NvramDocument
from .logging_config import get_logger

logger = get_logger("desktop")
LANGUAGES = {"ru", "en", "uk"}


class DesktopApi:
    """Serialize requests, keep document ownership in Python, and guard BIOS writes."""

    def __init__(self, config: AppConfig = APP_CONFIG, base_dir: str | Path | None = None):
        self._config = config
        self._service = BiosService(config=config, base_dir=base_dir)
        self._parser = BiosParser()
        self._window = None
        self._lock = threading.Lock()
        self._document: NvramDocument | None = None
        self._document_id = ""
        self._filepath = ""
        self._saved_values: tuple = ()
        self._drafts: set[int] = set()
        self._logs: list[str] = []
        self._language = self._read_language()
        self._catalogs = {}
        for language in LANGUAGES:
            path = config.translation_dir / f"{language}.json"
            self._catalogs[language] = json.loads(path.read_text(encoding="utf-8"))
            extras = config.translation_dir / f"desktop_{language}.json"
            self._catalogs[language].update(json.loads(extras.read_text(encoding="utf-8")))
        self._initialized = False

    def request(self, action: str, payload: dict | None = None) -> dict:
        """The only JS entry point: a closed action list and structured failures."""
        handlers = {
            "bootstrap": self._bootstrap,
            "open_file": self._open_file,
            "edit": self._edit,
            "draft": self._draft,
            "reset": self._reset,
            "save_changes": self._save_changes,
            "save_as": self._save_as,
            "backups": self._backups,
            "create_backup": self._create_backup,
            "delete_backup": self._delete_backup,
            "open_backup_folder": self._open_backup_folder,
            "bios": self._bios,
            "language": self._set_language,
            "external_link": self._external_link,
        }
        if not isinstance(action, str) or action not in handlers:
            return {"ok": False, "error": "Unknown desktop action"}
        if payload is not None and not isinstance(payload, dict):
            return {"ok": False, "error": "Invalid request payload"}
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": self._t("desktop.busy")}
        try:
            return {"ok": True, "data": handlers[action](payload or {})}
        except Exception as error:
            logger.exception("Desktop action %s failed", action)
            self._log(str(error))
            return {"ok": False, "error": str(error), "data": self._snapshot()}
        finally:
            self._lock.release()

    def _t(self, key: str, **values) -> str:
        text = self._catalogs.get(self._language, {}).get(key, key)
        return text.format(**values) if values else text

    def _log(self, message: str) -> None:
        logger.info(message)
        self._logs.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        self._logs = self._logs[-200:]

    def _values(self) -> tuple:
        if self._document is None:
            return ()
        return tuple((s.current_value, s.current_option_id) for s in self._document.settings)

    def _dirty(self) -> bool:
        return bool(self._drafts) or self._values() != self._saved_values

    def _setting_data(self, index: int, setting: BiosSetting) -> dict:
        return {
            "id": index, "name": setting.name, "help": setting.help_string,
            "token": setting.token, "offset": setting.offset, "width": setting.width,
            "value": setting.current_value, "option_id": setting.current_option_id,
            "options": setting.options, "default": setting.bios_default,
            "numeric": setting.is_numeric, "modified": setting.is_modified,
            "register": setting.is_system_register, "active": setting.is_active_profile,
            "differs_default": setting.differs_from_default,
            "context": setting.surrounding_context[:4],
        }

    def _snapshot(self, *, settings: bool = False, backups: bool = False) -> dict:
        items = self._document.settings if self._document else []
        result = {
            "document_id": self._document_id, "filepath": self._filepath,
            "dirty": self._dirty(), "modified_count": sum(s.is_modified for s in items),
            "logs": self._logs[:], "language": self._language,
        }
        if settings:
            result["settings"] = [self._setting_data(i, s) for i, s in enumerate(items)]
        if backups:
            result["backups"] = [
                {"path": path, "name": Path(path).name, "mtime": mtime, "size": size}
                for path, mtime, size in self._service.list_backups()
            ]
        return result

    def _bootstrap(self, _payload: dict) -> dict:
        status = self._service.check_dependencies()
        if not self._initialized:
            self._initialized = True
            if status.ok:
                self._log(self._t("deps.ready"))
            else:
                self._log(self._t("deps.missing", files=", ".join(
                    status.missing + status.unreadable + status.tampered)))
            if Path(self._service.resolve_path(self._config.nvram_file)).is_file():
                try:
                    self._load(self._config.nvram_file)
                except (OSError, ValueError) as error:
                    self._log(str(error))
        return {
            **self._snapshot(settings=True, backups=True),
            "app_name": self._config.app_name, "version": self._config.app_version,
            "dependencies": status._asdict(),
        }

    def _load(self, filepath: str) -> None:
        path = self._service.validate_nvram_file(filepath)
        document = self._service.validate_nvram_content(self._service.load_file(path))
        self._document = document
        self._filepath = path
        self._document_id = uuid.uuid4().hex
        self._drafts.clear()
        self._saved_values = self._values()
        self._log(self._t("log.loaded", count=len(document.settings)))

    def _confirm(self, title: str, message: str) -> bool:
        if self._window is None:
            raise RuntimeError("Desktop window is not ready")
        return bool(self._window.create_confirmation_dialog(title, message))

    def _confirm_discard(self) -> bool:
        return not self._dirty() or self._confirm(
            self._t("desktop.unsaved_title"), self._t("desktop.unsaved_text"))

    def _open_file(self, _payload: dict) -> dict:
        import webview

        paths = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("NVRAM (*.txt;*.nvram)", "All files (*.*)"),
        )
        if paths and self._confirm_discard():
            self._load(paths[0])
            return self._snapshot(settings=True)
        return {"cancelled": True}

    def _get_setting(self, payload: dict) -> tuple[int, BiosSetting]:
        if self._document is None or payload.get("document_id") != self._document_id:
            raise ValueError(self._t("desktop.stale_document"))
        index = payload.get("id")
        if type(index) is not int or not 0 <= index < len(self._document.settings):
            raise ValueError("Invalid setting ID")
        return index, self._document.settings[index]

    def _edit(self, payload: dict) -> dict:
        index, setting = self._get_setting(payload)
        value = payload.get("value")
        if not isinstance(value, str):
            raise ValueError("Invalid setting value")
        if setting.options:
            setting.set_option(value)
        elif setting.is_numeric:
            setting.set_value(f"<{value.strip().strip('<>')}>")
        else:
            raise ValueError(self._t("desktop.readonly"))
        self._drafts.discard(index)
        self._log(self._t("log.changed", name=setting.name, value=setting.current_value))
        return {**self._snapshot(), "setting": self._setting_data(index, setting)}

    def _draft(self, payload: dict) -> dict:
        index, setting = self._get_setting(payload)
        dirty = payload.get("dirty")
        if not setting.is_numeric or type(dirty) is not bool:
            raise ValueError("Invalid numeric draft")
        if dirty:
            self._drafts.add(index)
        else:
            self._drafts.discard(index)
        return {"dirty": self._dirty()}

    def _reset(self, payload: dict) -> dict:
        index, setting = self._get_setting(payload)
        if payload.get("mode") == "default":
            setting.reset_to_default()
            self._log(self._t("log.reset", name=setting.name))
        elif payload.get("mode") == "initial":
            setting.reset_to_initial()
        else:
            raise ValueError("Unknown reset mode")
        self._drafts.discard(index)
        return {**self._snapshot(), "setting": self._setting_data(index, setting)}

    def _save_changes(self, _payload: dict) -> dict:
        if self._document is None or not any(s.is_modified for s in self._document.settings):
            raise ValueError(self._t("infobar.no_changes_content"))
        content = self._parser.generate_changes(self._document)
        self._service.validate_nvram_content(content)
        path = self._service.resolve_path(self._config.nvram_new_file)
        self._service.atomic_write(path, content)
        self._saved_values = self._values()
        count = sum(s.is_modified for s in self._document.settings)
        self._log(self._t("apply.saved", count=count, file=path))
        return {**self._snapshot(), "message": self._t("infobar.ready_import_content", file=path)}

    def _save_as(self, _payload: dict) -> dict:
        import webview

        if self._document is None:
            raise ValueError(self._t("infobar.no_loaded_file"))
        paths = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="nvram_edited.txt",
            file_types=("NVRAM (*.txt)",),
        )
        if not paths:
            return {"cancelled": True}
        target = Path(paths[0]).resolve()
        # Preserve the live export used for mandatory pre-import backups.
        if target == Path(self._service.resolve_path(self._config.nvram_file)).resolve():
            raise ValueError(self._t("desktop.protected_export"))
        content = self._parser.generate_content(self._document)
        self._service.validate_nvram_content(content)
        self._service.atomic_write(str(target), content)
        self._load(str(target))
        self._log(self._t("desktop.saved", path=str(target)))
        return {**self._snapshot(settings=True), "message": self._t("desktop.saved", path=str(target))}

    def _backups(self, _payload: dict) -> dict:
        return self._snapshot(backups=True)

    def _create_backup(self, _payload: dict) -> dict:
        self._service.validate_nvram_file(self._config.nvram_file)
        path = self._service.create_backup(self._config.nvram_file, self._config.backup_directory)
        self._log(self._t("backup.created", path=path))
        return {**self._snapshot(backups=True), "message": self._t("backup.saved", path=path)}

    def _backup_path(self, payload: dict) -> str:
        path = payload.get("path")
        if not isinstance(path, str):
            raise ValueError("Invalid backup path")
        target = Path(path).resolve()
        directory = Path(self._service.resolve_path(self._config.backup_directory)).resolve()
        if target.parent != directory or not target.is_file():
            raise ValueError(self._t("backup.file_missing"))
        return str(target)

    def _delete_backup(self, payload: dict) -> dict:
        path = self._backup_path(payload)
        if not self._confirm(self._t("backup.delete_title"),
                             self._t("backup.delete_text", name=Path(path).name)):
            return {"cancelled": True}
        self._service.delete_backup(path)
        self._log(self._t("backup.deleted", path=path))
        return self._snapshot(backups=True)

    def _open_backup_folder(self, _payload: dict) -> dict:
        path = self._service.resolve_path(self._config.backup_directory)
        os.makedirs(path, exist_ok=True)
        os.startfile(path)
        return {}

    def _bios(self, payload: dict) -> dict:
        action = payload.get("operation")
        if action == "export":
            if not self._confirm_discard():
                return {"cancelled": True}
            operation = self._service.create_export_operation(self._t("action.export"))
        elif action in {"import", "import_loaded", "restore"}:
            if action == "import_loaded":
                if not self._filepath:
                    raise ValueError(self._t("infobar.no_loaded_file"))
                path = self._filepath
            elif action == "restore":
                path = self._backup_path(payload)
            else:
                path = self._config.nvram_new_file
            operation = self._service.create_import_operation(
                path, self._t("action.import_loaded" if action == "import_loaded" else "action.import"),
                action=action,
            )
        else:
            raise ValueError("Unknown BIOS operation")
        if operation.dangerous:
            message = self._t("bios.confirm_text", action=operation.description)
            message += "\n\n" + str(operation.arguments[-1])
            if action == "import_loaded" and self._dirty():
                message += "\n\n" + self._t("desktop.import_disk")
            if not self._confirm(self._t("bios.confirm_title"), message):
                return {"cancelled": True}
        if operation.requires_backup:
            backup = self._service.create_safety_backup()
            self._log(self._t("bios.backup_created", path=backup))
        self._log(self._t("log.started", desc=operation.description))
        try:
            result = subprocess.run(
                [operation.executable, *operation.arguments], capture_output=True,
                text=True, errors="replace", check=False,
                timeout=self._config.subprocess_timeout_seconds,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(self._t("bios.timeout")) from error
        except PermissionError as error:
            raise RuntimeError(self._t("bios.permission")) from error
        if result.stdout.strip():
            self._log(result.stdout.strip())
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip()
                               or f"SCEWIN: {result.returncode}")
        self._log(self._t("infobar.success_content"))
        if action == "export":
            self._load(self._config.nvram_file)
            backup = self._service.create_backup(self._config.nvram_file, self._config.backup_directory)
            self._log(self._t("backup.auto_created", path=backup))
        return {**self._snapshot(settings=action == "export", backups=True),
                "message": self._t("infobar.success_content")}

    def _read_language(self) -> str:
        settings = configparser.ConfigParser(interpolation=None)
        try:
            settings.read(self._service.resolve_path(self._config.settings_file), encoding="utf-8")
            language = settings.get("ui", "language", fallback=self._config.default_language)
            return language if language in LANGUAGES else self._config.default_language
        except (OSError, configparser.Error):
            return self._config.default_language

    def _set_language(self, payload: dict) -> dict:
        language = payload.get("language")
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")
        path = self._service.resolve_path(self._config.settings_file)
        settings = configparser.ConfigParser(interpolation=None)
        settings.read(path, encoding="utf-8")
        if not settings.has_section("ui"):
            settings.add_section("ui")
        settings.set("ui", "language", language)
        from io import StringIO

        output = StringIO()
        settings.write(output)
        self._service.atomic_write(path, output.getvalue())
        self._language = language
        return self._snapshot()

    def _external_link(self, payload: dict) -> dict:
        if payload.get("link") != "coffee":
            raise ValueError("Unknown external link")
        webbrowser.open("https://buymeacoffee.com/cat_fire")
        return {}

    def _on_closing(self, *_args) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        try:
            # Drafts are reported while typing. Never call evaluate_js here:
            # Windows invokes closing on the GUI thread, which must stay unblocked.
            return self._confirm_discard()
        finally:
            self._lock.release()
