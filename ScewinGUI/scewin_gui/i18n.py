"""JSON-backed interface localization."""

from __future__ import annotations

import json
from pathlib import Path

from .config import APP_CONFIG, AppConfig
from .logging_config import get_logger
from .qt_compat import QObject, QSettings, pyqtSignal

logger = get_logger("i18n")

LANG_OPTIONS = (
    ("en", "English"),
    ("uk", "Українська"),
    ("ru", "Русский"),
)


class TranslationCatalog:
    """Load and cache language dictionaries stored as UTF-8 JSON."""

    def __init__(self, directory: Path, fallback_language: str = "ru") -> None:
        self.directory = directory
        self.fallback_language = fallback_language
        self._cache: dict[str, dict[str, str]] = {}

    def load(self, language: str) -> dict[str, str]:
        """Return one language map, falling back to an empty dictionary."""
        if language in self._cache:
            return self._cache[language]
        path = self.directory / f"{language}.json"
        try:
            with path.open("r", encoding="utf-8") as source:
                data = json.load(source)
            if not isinstance(data, dict):
                raise ValueError("translation root must be an object")
            catalog = {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError, json.JSONDecodeError) as error:
            logger.error("Cannot load translations from %s: %s", path, error)
            catalog = {}
        self._cache[language] = catalog
        return catalog

    def translate(self, language: str, key: str, **kwargs: object) -> str:
        """Resolve and format a translation with fallback-language support."""
        text = self.load(language).get(key) or self.load(self.fallback_language).get(key) or key
        if not kwargs:
            return text
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError) as error:
            logger.warning("Invalid translation format for %s: %s", key, error)
            return text


CATALOG = TranslationCatalog(
    APP_CONFIG.translation_dir,
    APP_CONFIG.default_language,
)


class LanguageManager(QObject):
    """Track current language and notify widgets when it changes."""

    language_changed = pyqtSignal(str)

    def __init__(
        self,
        default_language: str = APP_CONFIG.default_language,
        catalog: TranslationCatalog = CATALOG,
    ) -> None:
        super().__init__()
        self.catalog = catalog
        supported = {code for code, _ in LANG_OPTIONS}
        self._language = (
            default_language if default_language in supported else APP_CONFIG.default_language
        )

    def language(self) -> str:
        """Return the active ISO language code."""
        return self._language

    def set_language(self, language: str) -> None:
        """Switch to a supported language and emit a change notification."""
        supported = {code for code, _ in LANG_OPTIONS}
        if language == self._language or language not in supported:
            return
        self._language = language
        self.language_changed.emit(language)

    def tr(self, key: str, **kwargs: object) -> str:  # type: ignore[override]
        """Translate one interface key."""
        return self.catalog.translate(self._language, key, **kwargs)


_CACHED_LANGUAGE: str | None = None


def tr_global(key: str, **kwargs: object) -> str:
    """Translate early-startup dialogs before a manager is created."""
    language = load_language_setting()
    return CATALOG.translate(language, key, **kwargs)


def load_language_setting(config: AppConfig = APP_CONFIG) -> str:
    """Load the selected language from the application INI file."""
    global _CACHED_LANGUAGE
    if _CACHED_LANGUAGE is not None:
        return _CACHED_LANGUAGE
    settings = QSettings(str(config.config_path), QSettings.Format.IniFormat)
    language = settings.value("ui/language", config.default_language)
    supported = {code for code, _ in LANG_OPTIONS}
    if isinstance(language, str) and language in supported:
        _CACHED_LANGUAGE = language
    else:
        _CACHED_LANGUAGE = config.default_language
    return _CACHED_LANGUAGE


def save_language_setting(
    language: str,
    config: AppConfig = APP_CONFIG,
) -> None:
    """Persist the active language code."""
    global _CACHED_LANGUAGE
    _CACHED_LANGUAGE = language
    settings = QSettings(str(config.config_path), QSettings.Format.IniFormat)
    settings.setValue("ui/language", language)
