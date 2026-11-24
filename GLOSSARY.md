# ScewinGUI Domain

Desktop utility for reading, editing, and flashing AMI BIOS configurations via SCEWIN on Windows.

## Language

**NVRAM**:
A raw text representation of AMI BIOS setup tokens, offsets, defaults, and values extracted and flashed by SCEWIN.
_Avoid_: BIOS dump, config dump, setup dump

**BiosSetting**:
A single configurable BIOS setup item with its question text, help string, token, offset, options or numeric bounds, default, and modified status.
_Avoid_: Option, preference, config item

**NvramDocument**:
An immutable parsed representation of an NVRAM text file, preserving exact formatting and byte structure across round-trips.
_Avoid_: File buffer, parsed config

**BiosDocumentSession**:
State manager for active NVRAM document mutations, tracking dirty status, in-flight numeric drafts, differential changes, and atomic saves.
_Avoid_: Edit session, document state

**BackupVault**:
Repository managing timestamped NVRAM backup archives with path validation, safe rotation, and OS explorer integration.
_Avoid_: Backup manager, backup directory

**BiosHardware**:
Domain module managing low-level vendor binary execution (SCEWIN export/import), driver authentication, and mandatory pre-import safety backups.
_Avoid_: Runner, bios executor, hardware service

**DialogHost**:
Seam abstracting user prompts, confirmations, and file pickers away from desktop IPC handlers.
_Avoid_: Window manager, UI callback

**DriverGuard**:
Context manager managing vendor kernel driver lifecycle and ensuring driver service shutdown and file unlock upon process completion or error.
_Avoid_: Driver service, kernel wrapper

**BiosStore**:
Client-side state container partitioning document, log, and backup subscriptions to eliminate cross-component re-render cascades.
_Avoid_: Redux store, app state
