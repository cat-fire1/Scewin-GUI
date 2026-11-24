# Deep Modules and Dialog Seams Architecture

We consolidate `BiosService` and `BiosExecutor` into a cohesive `BiosHardware` module, make `BackupVault` the single source of truth for all backups, and introduce an explicit `DialogHost` seam for all desktop dialogs. This eliminates duplicate backup management, reduces the IPC coordination surface from five objects to two, and allows the entire desktop application and test suite to run headlessly without PyWebView window dependencies.
