# Scewin GUI

A Windows desktop utility for reading, editing and applying SCEWIN NVRAM settings.

## Download

**[Download the latest Windows x64 ZIP](https://github.com/cat-fire1/Scewin-GUI/releases/latest/download/ScewinGUI-windows-x64.zip)**

[Version 4.0.0 release notes and SHA-256 checksum](https://github.com/cat-fire1/Scewin-GUI/releases/tag/v4.0.0)

1. Extract the **entire** archive to a writable folder.
2. Keep `_internal`, `SCEWIN_64.exe` and both `.sys` files beside `ScewinGUI.exe`.
3. Start `ScewinGUI.exe`. Run as administrator when performing BIOS operations.

The packaged application does not require Python or Node.js. Windows x64 and Microsoft Edge WebView2 Runtime are required.

## What's new in 4.0.0

- React + TypeScript interface in a pywebview / WebView2 desktop window.
- The familiar dark Fluent styling, editor, backup manager and documentation.
- Plain CSS with shared theme variables for changing colors, fonts, spacing and controls.
- A virtualized parameter table, search, sorting and register filtering.
- Russian, Ukrainian and English interface languages.
- Full-document Save As and changes-only Apply, with validation in Python.
- Confirmed BIOS writes, serialized operations, vendor-file integrity checks and mandatory safety backups.
- Explicit BIOS export: starting the application does not run SCEWIN automatically.

## Source and development

The application source is in [`ScewinGUI/`](ScewinGUI/). The previous Git history and the older `bios` release remain available.

```powershell
cd ScewinGUI
python -m pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
python main.py
```

For live interface updates, start `npm run dev --prefix frontend` in one terminal and `python main.py --dev` in another.

- Theme tokens: [`theme.css`](ScewinGUI/frontend/src/styles/theme.css)
- Component styles: [`app.css`](ScewinGUI/frontend/src/styles/app.css)
- React pages: [`frontend/src/pages/`](ScewinGUI/frontend/src/pages/)
- Python bridge: [`desktop_api.py`](ScewinGUI/scewin_gui/desktop_api.py)
- Parsing, validation and file operations: [`core.py`](ScewinGUI/scewin_gui/core.py)
- Detailed usage, build and customization instructions: [`ScewinGUI/README.md`](ScewinGUI/README.md)

## Checks and packaging

```powershell
python -m unittest discover -s tests -v
python tests/smoke_desktop.py
python -m pip install pyinstaller
.\build.ps1
.\package-release.ps1
```

Run these commands from `ScewinGUI/`. The smoke test uses synthetic files with 2,400 parameters and blocks all SCEWIN process execution. Release ZIPs exclude user dumps, backups, settings, logs, caches and development dependencies.

## BIOS operations

- **Export** reads BIOS settings into `nvram.txt` and creates a backup.
- **Apply** saves modified blocks into `nvram_new.txt`; it does not write BIOS.
- **Save As** writes the full edited document to a new file.
- **Import file** writes the open file from disk; **Import** writes `nvram_new.txt`.
- The **Backup** page creates, restores and deletes backups.

Always keep backups before modifying BIOS. Incorrect settings can prevent a device from booting. Keep personal BIOS dumps and backups outside Git and release archives.

## License

[Apache License 2.0](LICENSE). Developed by cat_fire.
