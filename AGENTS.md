# Repository Guidelines

## Project Structure & Module Organization

- `main.py` is the application entrypoint.
- `scewin_gui/` contains the modular GUI, services, workers, and localization code.
- `SCEWIN_64.exe`, `amifldrv64.sys`, `amigendrv64.sys` are bundled vendor tools/drivers.
- `icon.ico` contains the app icon asset.
- `nvram.txt` and `nvram_new.txt` are sample/exported BIOS data files.
- `settings.ini` stores local UI/app settings.
- `backups/` is used for user-created BIOS backups.

## Build, Test, and Development Commands

- Run locally: `python main.py` (starts the PyQt6 GUI).
- Install deps: `pip install PyQt6 PyQt6-Fluent-Widgets` (required GUI libraries).
- Optional: `pip install pywin32` (recommended for single-instance handling).

This repo does not include a formal build system; development is done by running the
Python entrypoint directly on Windows.

## Coding Style & Naming Conventions

- Python: follow PEP 8 where practical; use 4-space indentation.
- Keep UI text and labels consistent in language (currently Russian).
- Prefer descriptive, explicit names for UI controls and BIOS field helpers.
- Avoid non-ASCII characters in code unless required for user-facing UI strings.

## Testing Guidelines

- No automated test suite is currently present.
- Do a manual smoke test after changes: launch the GUI, load a sample `nvram.txt`,
  edit a field, and save to a new file.

## Commit & Pull Request Guidelines

- No Git history is available in this repository, so no commit conventions are
  established yet. Use clear, imperative messages (e.g., "Fix BIOS export path").
- PRs should describe the change, include steps to test, and attach screenshots
  for UI changes.

## Security & Configuration Notes

- BIOS modifications can brick a device. Always keep backups in `backups/`.
- Running requires admin privileges to access system-level BIOS operations.
- Do not store sensitive BIOS dumps in the repo; keep them local.
