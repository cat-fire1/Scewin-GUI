"""Logging configuration used by both services and GUI widgets."""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "scewin_gui"


def configure_logging(log_directory: Path) -> logging.Logger:
    """Configure console and UTF-8 file logging once."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    log_directory.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(
        log_directory / "scewin_gui.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def get_logger(component: str) -> logging.Logger:
    """Return a namespaced application logger."""
    return logging.getLogger(f"{LOGGER_NAME}.{component}")
