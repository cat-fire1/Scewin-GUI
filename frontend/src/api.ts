import type { Action, BiosGateway, Language, Payload, RunAction, Update } from './types';

// Queue calls so a numeric input's blur is committed before Apply/Open/Bios runs.
let queue: Promise<unknown> = Promise.resolve();

export class DesktopError extends Error {
  constructor(message: string, public readonly update?: Update) {
    super(message);
  }
}

export function request(action: Action, payload: Payload = {}): Promise<Update> {
  const pending = queue.then(async () => {
    if (!window.pywebview?.api) throw new Error('Desktop bridge is unavailable');
    const result = await window.pywebview.api.request(action, payload);
    if (!result.ok) throw new DesktopError(result.error || 'Request failed', result.data);
    return result.data || {};
  });
  queue = pending.catch(() => undefined);
  return pending;
}

export function isActionBlocking(action: Action): boolean {
  return action !== 'edit' && action !== 'reset' && action !== 'draft';
}

export function createBiosGateway(run: RunAction, getDocumentId: () => string): BiosGateway {
  return {
    bootstrap: () => run('bootstrap'),
    openFile: () => run('open_file'),
    editSetting: (id: number, value: string) => run('edit', { document_id: getDocumentId(), id, value }),
    draftSetting: (id: number, dirty: boolean) => run('draft', { document_id: getDocumentId(), id, dirty }),
    resetSetting: (id: number, mode: 'default' | 'initial') => run('reset', { document_id: getDocumentId(), id, mode }),
    saveChanges: () => run('save_changes'),
    saveAs: () => run('save_as'),
    listBackups: () => run('backups'),
    createBackup: () => run('create_backup'),
    deleteBackup: (path: string) => run('delete_backup', { path }),
    openBackupFolder: () => run('open_backup_folder'),
    exportBios: () => run('bios', { operation: 'export' }),
    importBios: (mode: 'import' | 'import_loaded' | 'restore', path?: string) =>
      run('bios', { operation: mode, ...(path ? { path } : {}) }),
    setLanguage: (language: Language) => run('language', { language }),
    openExternalLink: (link: 'coffee') => run('external_link', { link }),
  };
}
