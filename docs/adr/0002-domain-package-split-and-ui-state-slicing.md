# Domain Package Split and Frontend State Slicing

We decompose the monolithic `core.py` into dedicated domain modules (`scewin_gui/nvram/`, `scewin_gui/vault.py`, and `scewin_gui/hardware.py`) with `core.py` acting as a backward-compatible re-export facade, and partition frontend React state into sliced subscription contexts (`useBiosDocument`, `useBiosLogs`, `useBiosBackups`). This eliminates file-level sprawl in Python and prevents log and backup polling events from causing cascading re-renders across the virtualized 1,000-row settings table.
