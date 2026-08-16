"""Application startup, single-instance guard, and Qt configuration."""

from __future__ import annotations

import ctypes
import sys

from .config import APP_CONFIG
from .i18n import tr_global
from .logging_config import configure_logging, get_logger
from .main_window import MainWindow
from .qt_compat import QApplication, QMessageBox, Qt

try:
    import win32api
    import win32event
    import winerror
except ImportError:
    win32api = None
    win32event = None
    winerror = None

logger = get_logger("app")


class SingleInstanceGuard:
    """Use a named Windows mutex to prevent concurrent application instances."""

    def __init__(self, app_name: str = "ScewinGUI_SingleInstance") -> None:
        self.mutex_name = f"Local\\{app_name}"
        self.mutex_handle = None

    def is_already_running(self) -> bool:
        """Create the mutex and report whether it already existed."""
        if win32event is None or win32api is None or winerror is None:
            logger.warning("pywin32 is unavailable; instance guard is disabled")
            return False
        try:
            self.mutex_handle = win32event.CreateMutex(
                None,
                False,
                self.mutex_name,
            )
            return win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        except OSError as error:
            logger.error("Cannot create the instance mutex: %s", error)
            return False

    def release(self) -> None:
        """Close the mutex handle if one was created."""
        if self.mutex_handle is None or win32api is None:
            return
        try:
            win32api.CloseHandle(self.mutex_handle)
        except OSError as error:
            logger.warning("Cannot close the instance mutex: %s", error)
        finally:
            self.mutex_handle = None

    def __enter__(self) -> SingleInstanceGuard:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


def set_windows_app_id() -> None:
    """Register a stable taskbar identity on supported Windows versions."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_CONFIG.app_id)
    except (AttributeError, OSError):
        logger.debug("Windows AppUserModelID is unavailable")


def create_application(arguments: list[str]) -> QApplication:
    """Create and style the shared QApplication instance."""
    if hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy") and hasattr(
        Qt, "HighDpiScaleFactorRoundingPolicy"
    ):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    application = QApplication(arguments)
    application.setStyleSheet(
        application.styleSheet()
        + """
        QToolTip {
            background-color: rgba(50, 50, 50, 240);
            color: white;
            border: 1px solid rgba(100, 100, 100, 180);
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
        }
        """
    )
    return application


def show_already_running_message() -> None:
    """Display the localized duplicate-instance warning."""
    message = QMessageBox()
    message.setIcon(QMessageBox.Icon.Warning)
    message.setWindowTitle(tr_global("single.title"))
    message.setText(tr_global("single.text"))
    message.setInformativeText(tr_global("single.info"))
    message.setStandardButtons(QMessageBox.StandardButton.Ok)
    message.exec()


def main(arguments: list[str] | None = None) -> int:
    """Start the GUI and release the mutex for every exit path."""
    configure_logging(APP_CONFIG.app_dir / "logs")
    app_arguments = arguments if arguments is not None else sys.argv

    with SingleInstanceGuard(APP_CONFIG.app_name) as guard:
        if guard.is_already_running():
            application = create_application(app_arguments)
            show_already_running_message()
            return 0

        set_windows_app_id()
        application = create_application(app_arguments)
        window = MainWindow()
        window.show()
        return application.exec()
