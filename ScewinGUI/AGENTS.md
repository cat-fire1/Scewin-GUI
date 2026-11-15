# Repository Guidelines

## Project Structure & Module Organization

- `main.py` is the application entrypoint.
- `frontend/src/` contains the React + TypeScript interface and CSS theme.
- `scewin_gui/desktop.py` hosts the interface with pywebview / WebView2.
- `scewin_gui/desktop_api.py` connects the interface to the Python services.
- `scewin_gui/core.py` contains BIOS parsing, validation, and file operations.
- `SCEWIN_64.exe`, `amifldrv64.sys`, `amigendrv64.sys` are bundled vendor tools/drivers.
- `icon.ico` contains the app icon asset.
- `nvram.txt` and `nvram_new.txt` are sample/exported BIOS data files.
- `settings.ini` stores local UI/app settings.
- `backups/` is used for user-created BIOS backups.

## Build, Test, and Development Commands

- Install Python deps: `python -m pip install -r requirements.txt`.
- Install frontend deps: `npm ci --prefix frontend`.
- Build frontend: `npm run build --prefix frontend`.
- Run locally: `python main.py`.
- Develop UI: `npm run dev --prefix frontend`, then `python main.py --dev`.
- Build Windows app: `.\build.ps1`; use a fresh `-DistPath` when old output contains local data.
- Package a clean ZIP: `.\package-release.ps1 -BundlePath <bundle-directory>`.

Windows builds use PyInstaller --onefile: Python dependencies and UI assets are
embedded in ScewinGUI.exe. Only the SCEWIN executable and two drivers are external.
The packaged app requires WebView2 Runtime. Never package an _internal directory.

## Coding Style & Naming Conventions

- Python: follow PEP 8 where practical; use 4-space indentation.
- Keep UI text and labels consistent in language (currently Russian).
- Prefer descriptive, explicit names for UI controls and BIOS field helpers.
- Avoid non-ASCII characters in code unless required for user-facing UI strings.

## Testing Guidelines

- API tests: `python -m unittest discover -s tests -v`.
- Native WebView2 smoke: `python tests/smoke_desktop.py` (synthetic files only).
- Never run real BIOS operations as part of testing or publishing.
- Do a manual smoke test after changes: launch the GUI, load a sample `nvram.txt`,
  edit a field, and save to a new file.

## Commit & Pull Request Guidelines

- Use clear, imperative commit messages (e.g., "Fix BIOS export path").
- PRs should describe the change, include steps to test, and attach screenshots
  for UI changes.

## Security & Configuration Notes

- BIOS modifications can brick a device. Always keep backups in `backups/`.
- Running requires admin privileges to access system-level BIOS operations.
- Do not store sensitive BIOS dumps in the repo; keep them local.
