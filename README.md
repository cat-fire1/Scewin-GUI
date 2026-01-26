# Scewin GUI

A utility with a convenient interface for dumping BIOS to a PC and performing basic edits.

## Features

- Dump BIOS to a file on the PC.
- Edit available parameters through a graphical interface.
- Save changes to a file for later flashing/applying.

## Requirements

- Windows x64.
- Administrator privileges (for access to system settings).
- SCEWIN drivers/utilities (included in the repository).

## Quick Start

1. Run the application as administrator.
2. Click "Dump BIOS" and choose a save path.
3. Open the file in the interface and make changes.
4. Save the result to a new file.

## How It Works

<img width="1097" height="747" alt="Screenshot_4" src="https://github.com/user-attachments/assets/a10edbe7-9dd4-4610-a49b-98237b106c74" />

- The main UI and logic are in `combined_source.py`.
- BIOS access uses SCEWIN utilities and drivers: `SCEWIN_64.exe`, `amifldrv64.sys`, `amigendrv64.sys`.
- If you do not trust the .exe files and drivers in the original archive, download it from the official Msi Center website, copy the files to the program folder, or use this script https://github.com/ab3lkaizen/SCEHUB to export .exe files and .sys drivers.
- The dump is saved as a text file (e.g., `nvram.txt`); edits can be saved to a new file (e.g., `nvram_new.txt`).
- Keep backups in the `backups/` folder.

## Important

- You modify BIOS at your own risk.
- Always make a backup before editing.
- Incorrect parameters can make the device unusable.

## License

Apache-2.0. All rights reserved by the developer cat_fire.
