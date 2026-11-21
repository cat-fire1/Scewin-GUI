"""Exercise the actual React/WebView2 UI against temporary synthetic files.

Run from the repository root: python tests/smoke_desktop.py
Native file pickers are replaced with deterministic paths. Vendor calls fail closed.
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import webview

from scewin_gui.core import BiosParser
from scewin_gui.desktop_api import DesktopApi


def fixture(count: int = 2400) -> str:
    blocks = ["// Synthetic UI fixture, no hardware data"]
    for index in range(count):
        name = "PMU Register" if index % 8 == 7 else "Memory Frequency"
        block = f"Setup Question = {name} {index}\nHelp String = Test setting\nToken = {index:04X}\nOffset = 10\n"
        if index % 2 == 0:
            block += "BIOS Default = <0>\nValue = <1> // preserved\n"
        else:
            block += "BIOS Default = [00]Auto\nOptions = [00]Auto\n         *[01]Enabled\n          [02]Enabled\n"
        blocks.append(block)
    return "\n".join(blocks)


class Dialogs:
    def __init__(self, sample: Path, saved: Path):
        self.sample = sample
        self.saved = saved

    def create_file_dialog(self, dialog_type, **_kwargs):
        return (str(self.saved if dialog_type == webview.FileDialog.SAVE else self.sample),)

    def create_confirmation_dialog(self, *_args):
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true', help='Exercise the running Vite server')
    args = parser.parse_args()
    errors = []
    with tempfile.TemporaryDirectory(prefix="scewin_webview_") as directory:
        folder = Path(directory)
        sample = folder / "sample.txt"
        saved = folder / "edited.txt"
        sample.write_text(fixture(), encoding="utf-8")
        api = DesktopApi(base_dir=folder)
        api._window = Dialogs(sample, saved)
        window = webview.create_window("Scewin GUI — offline smoke test",
            "http://127.0.0.1:5173" if args.dev else str(ROOT / "frontend/dist/index.html"), js_api=api,
            width=1100, height=750, min_size=(960, 640), background_color="#202020")
        window.events.closing += api._on_closing

        def evaluate(script):
            return window.evaluate_js(script)

        def wait_for(script, timeout=20):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if evaluate(script):
                    return
                time.sleep(0.1)
            raise AssertionError(f"Timed out: {script}\n{evaluate('document.body.innerText')}")

        def click_text(text):
            evaluate(f"Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === {json.dumps(text)}).click()")

        def set_input(selector, value):
            evaluate(f"""(() => {{
              const element = document.querySelector({json.dumps(selector)});
              element.focus();
              Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, {json.dumps(value)});
              element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }})()""")

        def smoke():
            try:
                wait_for("document.querySelector('.connection-banner') === null")
                evaluate("document.querySelector('button[aria-label=\"Открыть файл\"]').click()")
                wait_for("document.querySelector('table').getAttribute('aria-rowcount') === '2401'")
                count = evaluate("document.querySelectorAll('input[data-setting-id]').length")
                assert count < 100, count

                # Invalid drafts must not reach Python; Escape restores the original.
                set_input('input[data-setting-id="0"]', "not-hex")
                evaluate("document.querySelector('input[data-setting-id=\"0\"]').blur()")
                wait_for("document.querySelector('input[data-setting-id=\"0\"]').getAttribute('aria-invalid') === 'true'")
                assert api._document.settings[0].current_value == '<1>'

                set_input('input[data-setting-id="0"]', "AB")
                # Blur and Apply in one turn: the queue must save the new value.
                evaluate("""(() => {
                  document.querySelector('input[data-setting-id="0"]').blur();
                  Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Применить').click();
                })()""")
                wait_for("document.querySelector('main').getAttribute('aria-busy') === 'false'")
                partial = BiosParser().parse_file((folder / "nvram_new.txt").read_text(encoding="utf-8"))
                assert partial.settings[0].current_value == "<AB>"

                # Two identical labels must retain their distinct SCEWIN IDs.
                evaluate("""(() => { const select = document.querySelector('.settings-table select');
                  select.value = '02'; select.dispatchEvent(new Event('change', {bubbles: true})); })()""")
                wait_for("document.querySelector('.table-footer').textContent.includes('Изменено: 2')")
                click_text("Сохранить как…")
                wait_for("document.querySelector('.file-strip').textContent.includes('edited.txt')")
                document = BiosParser().parse_file(saved.read_text(encoding="utf-8"))
                assert len(document.settings) == 2400
                assert document.settings[0].current_value == "<AB>"
                assert document.settings[1].current_option_id == "02"

                # Filtering and virtualization must cooperate when scrolled to the end.
                evaluate("document.querySelector('.table-scroll').scrollTop = 999999")
                wait_for("document.querySelector('input[data-setting-id=\"2398\"]') !== null")
                set_input('.search-field input', 'Memory Frequency 120')
                expected = sum('Memory Frequency 120' in s.name for s in document.settings) + 1
                wait_for(f"document.querySelector('table').getAttribute('aria-rowcount') === '{expected}'")
                set_input('.search-field input', '')
                wait_for("document.querySelector('table').getAttribute('aria-rowcount') === '2401'")
                click_text("Скрыть регистры")
                wait_for("Number(document.querySelector('table').getAttribute('aria-rowcount')) < 2401")
                click_text("Скрыть регистры")

                # Switch locales through the native bridge, then visit every page.
                evaluate("""(() => { const select = document.querySelector('.language-picker select');
                  select.value = 'en'; select.dispatchEvent(new Event('change', {bubbles: true})); })()""")
                wait_for("document.documentElement.lang === 'en'")
                assert DesktopApi(base_dir=folder)._language == "en"
                click_text("Backup")
                wait_for("document.querySelector('.backup-page') !== null")
                click_text("About")
                wait_for("document.querySelector('.about-page') !== null")
                click_text("Documentation")
                wait_for("document.querySelector('dialog').open")
                evaluate("document.querySelector('dialog button').click()")
                click_text("NVRAM Editor")
                wait_for("document.querySelector('.editor-page') !== null")
                wait_for("document.querySelector('main').getAttribute('aria-busy') === 'false'")
                # Selection and all three sorting states operate on stable IDs.
                evaluate("document.querySelector('.settings-table th button').click()")
                wait_for("document.querySelector('.settings-table th').getAttribute('aria-sort') === 'descending'")
                evaluate("document.querySelector('.settings-table th button').click()")
                wait_for("document.querySelector('.settings-table th').getAttribute('aria-sort') === 'ascending'")
                evaluate("document.querySelector('.settings-table th button').click()")
                wait_for("document.querySelector('.settings-table th').getAttribute('aria-sort') === 'none'")
                # Do not capture the previous compositor frame after navigation.
                time.sleep(0.4)

                # Capture just the application for visual review when Pillow is installed.
                try:
                    from PIL import ImageGrab
                    import ctypes
                    from ctypes import wintypes

                    hwnd = ctypes.windll.user32.FindWindowW(None, "Scewin GUI — offline smoke test")
                    rect = wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    destination = ROOT / f"artifacts/desktop-{'dev-' if args.dev else ''}smoke.png"
                    destination.parent.mkdir(exist_ok=True)
                    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(destination)
                    print(f"Screenshot: {destination}")
                except (ImportError, OSError):
                    pass
                print("Desktop smoke passed: real WebView2, 2400 rows, load/edit/apply/save/reload, duplicate option IDs, virtualization, search, register filter, locales, backup/about/docs")
            except Exception:
                errors.append(traceback.format_exc())
                print(errors[-1], file=sys.stderr)
            finally:
                window.destroy()

        with patch("scewin_gui.desktop_api.subprocess.run", side_effect=AssertionError("Vendor execution forbidden")):
            webview.start(smoke, gui="edgechromium")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
