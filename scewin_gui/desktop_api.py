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
import webbrowser

from .config import APP_CONFIG, AppConfig
from .core import (
    BackupVault,
    BiosDocumentSession,
    BiosExecutionError,
    BiosExecutor,
    BiosOperationResult,
    BiosParser,
    BiosPermissionError,
    BiosService,
    BiosSetting,
    BiosTimeoutError,
    NvramDocument,
    ProcessRunner,
    default_process_runner,
)
from .logging_config import get_logger

logger = get_logger("desktop")
LANGUAGES = {"ru", "en", "uk"}


class DesktopApi:
    """Serialize requests and bridge desktop operations to webview."""

    def __init__(
        self,
        config: AppConfig = APP_CONFIG,
        base_dir: str | Path | None = None,
        runner: ProcessRunner | None = None,
    ):
        self._config = config
        self._service = BiosService(config=config, base_dir=base_dir)
        self._vault = BackupVault(config.backup_directory, resolve_fn=self._service.resolve_path)

        # Delegate execution through the runner port, supporting monkey-patched subprocess.run for tests
        actual_runner = runner
        if actual_runner is None:
            def compat_runner(cmd: list[str], timeout: int) -> BiosOperationResult:
                sub = getattr(sys.modules.get("scewin_gui.desktop_api"), "subprocess", subprocess)
                creationflags = sub.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                try:
                    proc = sub.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        errors="replace",
                        check=False,
                        timeout=timeout,
                        creationflags=creationflags,
                    )
                    return BiosOperationResult(
                        success=proc.returncode == 0,
                        description=" ".join(cmd),
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

            actual_runner = compat_runner

        self._executor = BiosExecutor(self._service, runner=actual_runner, vault=self._vault)
        self._session: BiosDocumentSession | None = None
        self._parser = BiosParser()
        self._window = None
        self._lock = threading.Lock()
        self._logs: list[str] = []
        self._language = self._read_language()
        self._catalogs = {}
        for language in LANGUAGES:
            path = config.translation_dir / f"{language}.json"
            self._catalogs[language] = json.loads(path.read_text(encoding="utf-8"))
            extras = config.translation_dir / f"desktop_{language}.json"
            self._catalogs[language].update(json.loads(extras.read_text(encoding="utf-8")))
        self._initialized = False

    @property
    def _document(self) -> NvramDocument | None:
        """Backwards compatibility property exposing active document."""
        return self._session.document if self._session else None

    @property
    def _document_id(self) -> str:
        """Backwards compatibility property exposing active document session ID."""
        return self._session.document_id if self._session else ""

    @property
    def _filepath(self) -> str:
        """Backwards compatibility property exposing active file path."""
        return self._session.filepath if self._session else ""

    def _dirty(self) -> bool:
        """Backwards compatibility dirty calculation delegated to session."""
        return self._session.is_dirty if self._session else False

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
        items = self._session.document.settings if self._session else []
        result = {
            "document_id": self._document_id,
            "filepath": self._filepath,
            "dirty": self._dirty(),
            "modified_count": self._session.modified_count if self._session else 0,
            "logs": self._logs[:],
            "language": self._language,
        }
        if settings:
            result["settings"] = [self._setting_data(i, s) for i, s in enumerate(items)]
        if backups:
            result["backups"] = [
                {"path": b.path, "name": b.name, "mtime": b.mtime, "size": b.size}
                for b in self._vault.list_all()
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
            resolved_nvram = self._service.resolve_path(self._config.nvram_file)
            if Path(resolved_nvram).is_file():
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
        resolved = self._service.resolve_path(filepath)
        self._session = BiosDocumentSession.open_file(
            resolved,
            parser=self._parser,
            load_fn=self._service.load_file,
        )
        self._log(self._t("log.loaded", count=len(self._session.document.settings)))

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
        if self._session is None or payload.get("document_id") != self._document_id:
            raise ValueError(self._t("desktop.stale_document"))
        index = payload.get("id")
        if type(index) is not int or not 0 <= index < len(self._session.document.settings):
            raise ValueError("Invalid setting ID")
        return index, self._session.get_setting(index)

    def _edit(self, payload: dict) -> dict:
        index, _ = self._get_setting(payload)
        value = payload.get("value")
        try:
            setting = self._session.edit(index, value)
        except ValueError as err:
            if "Параметр доступен только для чтения" in str(err):
                raise ValueError(self._t("desktop.readonly")) from err
            raise
        self._log(self._t("log.changed", name=setting.name, value=setting.current_value))
        return {**self._snapshot(), "setting": self._setting_data(index, setting)}

    def _draft(self, payload: dict) -> dict:
        index, _ = self._get_setting(payload)
        dirty = payload.get("dirty")
        is_dirty = self._session.set_draft(index, dirty)
        return {"dirty": is_dirty}

    def _reset(self, payload: dict) -> dict:
        index, _ = self._get_setting(payload)
        mode = payload.get("mode")
        setting = self._session.reset_setting(index, mode)
        if mode == "default":
            self._log(self._t("log.reset", name=setting.name))
        return {**self._snapshot(), "setting": self._setting_data(index, setting)}

    def _save_changes(self, _payload: dict) -> dict:
        if self._session is None or self._session.modified_count == 0:
            raise ValueError(self._t("infobar.no_changes_content"))
        path = self._service.resolve_path(self._config.nvram_new_file)
        self._session.save_changes(path, write_fn=self._service.atomic_write)
        count = self._session.modified_count
        self._log(self._t("apply.saved", count=count, file=path))
        return {**self._snapshot(), "message": self._t("infobar.ready_import_content", file=path)}

    def _save_as(self, _payload: dict) -> dict:
        import webview

        if self._session is None:
            raise ValueError(self._t("infobar.no_loaded_file"))
        paths = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="nvram_edited.txt",
            file_types=("NVRAM (*.txt)",),
        )
        if not paths:
            return {"cancelled": True}
        target = Path(paths[0]).resolve()
        live_export = Path(self._service.resolve_path(self._config.nvram_file)).resolve()
        try:
            self._session.save_as(
                str(target),
                write_fn=self._service.atomic_write,
                protected_paths=(str(live_export),),
            )
        except ValueError as err:
            if "базовый файл" in str(err):
                raise ValueError(self._t("desktop.protected_export")) from err
            raise
        self._log(self._t("desktop.saved", path=str(target)))
        return {**self._snapshot(settings=True), "message": self._t("desktop.saved", path=str(target))}

    def _backups(self, _payload: dict) -> dict:
        return self._snapshot(backups=True)

    def _create_backup(self, _payload: dict) -> dict:
        self._service.validate_nvram_file(self._config.nvram_file)
        path = self._vault.create_backup(self._config.nvram_file)
        self._log(self._t("backup.created", path=path))
        return {**self._snapshot(backups=True), "message": self._t("backup.saved", path=path)}

    def _backup_path(self, payload: dict) -> str:
        path = payload.get("path")
        if not isinstance(path, str):
            raise ValueError("Invalid backup path")
        try:
            return str(self._vault.validate_backup_path(path))
        except ValueError as err:
            raise ValueError(self._t("backup.file_missing")) from err

    def _delete_backup(self, payload: dict) -> dict:
        path = self._backup_path(payload)
        if not self._confirm(self._t("backup.delete_title"),
                             self._t("backup.delete_text", name=Path(path).name)):
            return {"cancelled": True}
        self._vault.delete(path)
        self._log(self._t("backup.deleted", path=path))
        return self._snapshot(backups=True)

    def _open_backup_folder(self, _payload: dict) -> dict:
        self._vault.open_in_explorer()
        return {}

    def _bios(self, payload: dict) -> dict:
        action = payload.get("operation")
        if action == "export":
            if not self._confirm_discard():
                return {"cancelled": True}
            self._log(self._t("log.started", desc=self._t("action.export")))
            try:
                result = self._executor.execute_export(description=self._t("action.export"))
            except BiosTimeoutError as error:
                raise RuntimeError(self._t("bios.timeout")) from error
            except BiosPermissionError as error:
                raise RuntimeError(self._t("bios.permission")) from error
            except BiosExecutionError as error:
                raise RuntimeError(str(error)) from error

            if result.stdout.strip():
                self._log(result.stdout.strip())
            self._load(self._config.nvram_file)
            self._log(self._t("backup.auto_created", path=result.backup_path))
            self._log(self._t("infobar.success_content"))
            return {**self._snapshot(settings=True, backups=True),
                    "message": self._t("infobar.success_content")}

        elif action in {"import", "import_loaded", "restore"}:
            if action == "import_loaded":
                if not self._filepath:
                    raise ValueError(self._t("infobar.no_loaded_file"))
                path = self._filepath
            elif action == "restore":
                path = self._backup_path(payload)
            else:
                path = self._service.resolve_path(self._config.nvram_new_file)

            desc = self._t("action.import_loaded" if action == "import_loaded" else "action.import")
            message = self._t("bios.confirm_text", action=desc) + "\n\n" + str(path)
            if action == "import_loaded" and self._dirty():
                message += "\n\n" + self._t("desktop.import_disk")
            if not self._confirm(self._t("bios.confirm_title"), message):
                return {"cancelled": True}

            self._log(self._t("log.started", desc=desc))
            try:
                result = self._executor.execute_import(path, description=desc, action=action)
            except BiosTimeoutError as error:
                raise RuntimeError(self._t("bios.timeout")) from error
            except BiosPermissionError as error:
                raise RuntimeError(self._t("bios.permission")) from error
            except BiosExecutionError as error:
                raise RuntimeError(str(error)) from error

            if result.backup_path:
                self._log(self._t("bios.backup_created", path=result.backup_path))
            if result.stdout.strip():
                self._log(result.stdout.strip())
            self._log(self._t("infobar.success_content"))
            return {**self._snapshot(settings=False, backups=True),
                    "message": self._t("infobar.success_content")}

        raise ValueError("Unknown BIOS operation")

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
