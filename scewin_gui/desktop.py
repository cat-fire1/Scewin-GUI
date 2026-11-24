"""Native WebView2 host for the locally bundled React application."""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path
import sys

from .config import APP_CONFIG
from .logging_config import configure_logging


class SingleInstanceGuard:
    """Hold a Windows mutex without requiring Qt or pywin32."""

    def __init__(self):
        self._handle = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        self._handle = kernel.CreateMutexW(None, False, "Local\\ScewinGUI_SingleInstance")
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.get_last_error() != 183

    def release(self) -> None:
        if self._handle:
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(self._handle)
            self._handle = None


def _message(text: str) -> None:
    print(text, file=sys.stderr)
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, APP_CONFIG.app_name, 0x10)


def _style_window(window) -> None:
    """Match the dark interface with the Windows title bar."""
    if sys.platform != "win32":
        return
    from ctypes import wintypes

    try:
        handle = wintypes.HWND(window.native.Handle.ToInt64())
        enabled = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled),
        )
    except (AttributeError, OSError):
        pass


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scewin GUI desktop application")
    parser.add_argument("--debug", action="store_true", help="Enable WebView developer tools")
    parser.add_argument("--dev", action="store_true", help="Load the local Vite server with hot reload")
    args = parser.parse_args(arguments)
    root = Path(getattr(sys, "_MEIPASS", APP_CONFIG.app_dir))
    index = root / "frontend" / "dist" / "index.html"
    if not args.dev and not index.is_file():
        _message("Интерфейс не собран. Выполните в frontend: npm ci; npm run build")
        return 1
    url = str(index)
    if args.dev:
        from urllib.error import URLError
        from urllib.request import urlopen

        url = "http://127.0.0.1:5173"
        try:
            with urlopen(url, timeout=2):
                pass
        except URLError:
            _message("Сначала запустите сервер интерфейса: npm run dev --prefix frontend")
            return 1
    try:
        import webview
    except ImportError:
        _message("Установите зависимости: python -m pip install -r requirements.txt")
        return 1

    from .desktop_api import DesktopApi, WebviewDialogHost

    configure_logging(APP_CONFIG.app_dir / "logs")
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetDllDirectoryW("")
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_CONFIG.app_id)
    guard = SingleInstanceGuard()
    try:
        if not guard.acquire():
            _message("Scewin GUI уже запущен.")
            return 0
        dialog_host = WebviewDialogHost()
        api = DesktopApi(dialog_host=dialog_host)
        window = webview.create_window(
            APP_CONFIG.app_name, url, js_api=api,
            width=APP_CONFIG.window_width, height=APP_CONFIG.window_height,
            min_size=(960, 640), background_color="#202020", text_select=True,
        )
        dialog_host.window = window
        api._window = window
        window.events.shown += lambda: _style_window(window)
        window.events.closing += api._on_closing
        webview.start(
            gui="edgechromium" if sys.platform == "win32" else None,
            debug=args.debug or args.dev, icon=str(root / "icon.ico"),
        )
        return 0
    except Exception as error:
        _message(f"Не удалось запустить приложение: {error}")
        return 1
    finally:
        guard.release()
