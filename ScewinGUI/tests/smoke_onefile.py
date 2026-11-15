"""Verify the published onefile ZIP with synthetic data and an unrelated CWD.

Usage: python tests/smoke_onefile.py releases/v4.0.1/ScewinGUI-windows-x64.zip
No SCEWIN command is executed; the app only auto-loads the synthetic NVRAM file.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile


SAMPLE = """// Synthetic packaging smoke fixture, no real BIOS data
Setup Question = Test Frequency
Help String = Synthetic numeric setting
Token = 1000
Offset = 10
BIOS Default = <0>
Value = <1>

Setup Question = Test Boot Mode
Help String = Synthetic enum setting
Token = 1001
Offset = 11
BIOS Default = [00]Auto
Options = [00]Auto
         *[01]Enabled
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve()
    expected = {
        'ScewinGUI/ScewinGUI.exe', 'ScewinGUI/SCEWIN_64.exe',
        'ScewinGUI/amifldrv64.sys', 'ScewinGUI/amigendrv64.sys',
        'ScewinGUI/LICENSE', 'ScewinGUI/README.txt',
    }
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert checksum == (archive.parent / 'SHA256SUMS.txt').read_text().split()[0]
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    if user32.FindWindowW(None, 'Scewin GUI'):
        raise RuntimeError('Close the existing Scewin GUI before running the packaging smoke.')

    with tempfile.TemporaryDirectory(prefix='scewin_onefile_') as directory:
        folder = Path(directory)
        with zipfile.ZipFile(archive) as zipped:
            assert set(zipped.namelist()) == expected, zipped.namelist()
            assert zipped.testzip() is None
            zipped.extractall(folder)
        bundle = folder / 'ScewinGUI'
        sample = bundle / 'nvram.txt'
        sample.write_text(SAMPLE, encoding='utf-8')
        initial_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
        unrelated = folder / 'unrelated-cwd'
        unrelated.mkdir()
        temporary_root = Path(tempfile.gettempdir())
        initial_runtime_dirs = set(temporary_root.glob('_MEI*'))
        process = subprocess.Popen([str(bundle / 'ScewinGUI.exe')], cwd=unrelated)
        runtime = None
        window = None
        log_path = bundle / 'logs/scewin_gui.log'
        try:
            deadline = time.monotonic() + 30
            log = ''
            while time.monotonic() < deadline and process.poll() is None:
                window = user32.FindWindowW(None, 'Scewin GUI')
                if log_path.exists():
                    log = log_path.read_text(encoding='utf-8')
                if window and 'Успешно загружено: 2 настроек' in log:
                    break
                time.sleep(.1)
            else:
                raise AssertionError(f'Onefile app did not load the fixture: {process.poll()}\n{log}')
            assert 'Система готова. Зависимости найдены.' in log, log
            assert not (bundle / '_internal').exists()
            for candidate in set(temporary_root.glob('_MEI*')) - initial_runtime_dirs:
                if (candidate / 'frontend/dist/index.html').is_file():
                    runtime = candidate
                    break
            assert runtime is not None, 'Embedded interface was not extracted'
            assert (runtime / 'translations/desktop_ru.json').is_file()
            assert (runtime / 'python314.dll').is_file() or list(runtime.glob('python3*.dll'))
            assert not list(unrelated.iterdir()), 'App wrote files into the working directory'
            assert hashlib.sha256(sample.read_bytes()).hexdigest() == initial_hash
            user32.PostMessageW(window, 0x10, 0, 0)
            process.wait(timeout=10)
            assert process.returncode == 0, process.returncode
            assert not runtime.exists(), 'Onefile extraction directory was not cleaned up'
            print(f'Onefile ZIP passed: six files, SHA256 {checksum}')
            print('Embedded Python/UI/translations, external vendor files, synthetic NVRAM auto-load, unrelated CWD, normal close and temporary runtime cleanup verified.')
        finally:
            if process.poll() is None:
                if window:
                    user32.PostMessageW(window, 0x10, 0, 0)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)


if __name__ == '__main__':
    main()
