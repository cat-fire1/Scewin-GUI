"""Application configuration and filesystem locations."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def get_app_dir() -> Path:
    """Return the directory containing the script or packaged executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Immutable runtime configuration shared by all application layers."""

    app_name: str = "Scewin GUI"
    app_version: str = "1.0.0"
    app_id: str = "ScewinGUI.BiosEditor.v1.0"
    default_language: str = "ru"
    scewin_executable: str = "SCEWIN_64.exe"
    nvram_file: str = "nvram.txt"
    nvram_new_file: str = "nvram_new.txt"
    backup_directory: str = "backups"
    settings_file: str = "settings.ini"
    subprocess_timeout_seconds: int = 30
    search_debounce_ms: int = 150
    sort_debounce_ms: int = 50
    auto_load_delay_ms: int = 200
    worker_wait_ms: int = 1000
    tooltip_delay_ms: int = 500
    window_width: int = 1100
    window_height: int = 750
    layout_margin: int = 30
    layout_spacing: int = 15
    border_radius: int = 8
    column_width_parameter: int = 420
    column_width_value: int = 200
    column_width_default: int = 160
    column_width_status: int = 150
    row_height: int = 42
    widget_height: int = 32
    search_bar_width: int = 350
    log_card_height: int = 120
    log_text_width: int = 400

    @property
    def app_dir(self) -> Path:
        return get_app_dir()

    @property
    def config_path(self) -> Path:
        return self.app_dir / self.settings_file

    @property
    def icon_path(self) -> Path:
        return self.app_dir / "icon.ico"

    @property
    def translation_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / "translations"
        return Path(__file__).resolve().parent / "translations"


APP_CONFIG = AppConfig()
