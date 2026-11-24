import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { Backup, DesktopState, Setting } from '../types';

export interface DocumentSlice {
  document_id: string;
  filepath: string;
  dirty: boolean;
  modified_count: number;
  settings: Setting[];
}

export interface LogsSlice {
  logs: string[];
}

export interface BackupsSlice {
  backups: Backup[];
}

export interface AppSlice {
  app_name: string;
  version: string;
  language: DesktopState['language'];
  dependencies?: DesktopState['dependencies'];
}

const DocumentContext = createContext<DocumentSlice | null>(null);
const LogsContext = createContext<LogsSlice | null>(null);
const BackupsContext = createContext<BackupsSlice | null>(null);
const AppContext = createContext<AppSlice | null>(null);

export function BiosStoreProvider({
  state,
  children,
}: {
  state: DesktopState;
  children: ReactNode;
}) {
  const docSlice = useMemo<DocumentSlice>(() => ({
    document_id: state.document_id,
    filepath: state.filepath,
    dirty: state.dirty,
    modified_count: state.modified_count,
    settings: state.settings,
  }), [state.document_id, state.filepath, state.dirty, state.modified_count, state.settings]);

  const logsSlice = useMemo<LogsSlice>(() => ({
    logs: state.logs,
  }), [state.logs]);

  const backupsSlice = useMemo<BackupsSlice>(() => ({
    backups: state.backups,
  }), [state.backups]);

  const appSlice = useMemo<AppSlice>(() => ({
    app_name: state.app_name,
    version: state.version,
    language: state.language,
    dependencies: state.dependencies,
  }), [state.app_name, state.version, state.language, state.dependencies]);

  return (
    <AppContext.Provider value={appSlice}>
      <DocumentContext.Provider value={docSlice}>
        <LogsContext.Provider value={logsSlice}>
          <BackupsContext.Provider value={backupsSlice}>
            {children}
          </BackupsContext.Provider>
        </LogsContext.Provider>
      </DocumentContext.Provider>
    </AppContext.Provider>
  );
}

export function useBiosDocument(): DocumentSlice {
  const ctx = useContext(DocumentContext);
  if (!ctx) throw new Error('useBiosDocument must be used within BiosStoreProvider');
  return ctx;
}

export function useBiosLogs(): LogsSlice {
  const ctx = useContext(LogsContext);
  if (!ctx) throw new Error('useBiosLogs must be used within BiosStoreProvider');
  return ctx;
}

export function useBiosBackups(): BackupsSlice {
  const ctx = useContext(BackupsContext);
  if (!ctx) throw new Error('useBiosBackups must be used within BiosStoreProvider');
  return ctx;
}

export function useBiosApp(): AppSlice {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useBiosApp must be used within BiosStoreProvider');
  return ctx;
}
