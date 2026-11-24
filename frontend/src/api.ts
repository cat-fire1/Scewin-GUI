import type { Action, Backup, BiosGateway, Language, Payload, RunAction, Setting, Update } from './types';

// Queue calls so a numeric input's blur is committed before Apply/Open/Bios runs.
let queue: Promise<unknown> = Promise.resolve();

export class DesktopError extends Error {
  constructor(message: string, public readonly update?: Update) {
    super(message);
  }
}

// In-memory mock state for autonomous browser development & testing
let mockLanguage: Language = 'ru';
let mockDirty = false;
let mockSettings: Setting[] = [
  {
    id: 0,
    name: 'Memory Frequency',
    help: 'Configures memory clock frequency',
    token: '1000',
    offset: '10',
    width: '2',
    value: '<3200>',
    option_id: '',
    options: [],
    default: '<3200>',
    numeric: true,
    modified: false,
    register: false,
    active: true,
    differs_default: false,
    context: ['Memory Timings', 'DRAM Voltage'],
  },
  {
    id: 1,
    name: 'Fast Boot',
    help: 'Enable or disable fast boot acceleration',
    token: '1001',
    offset: '12',
    width: '1',
    value: 'Enabled',
    option_id: '01',
    options: [['00', 'Disabled'], ['01', 'Enabled']],
    default: 'Enabled',
    numeric: false,
    modified: false,
    register: false,
    active: true,
    differs_default: false,
    context: ['Boot Priority', 'CSM Support'],
  },
  {
    id: 2,
    name: 'PCIe ASPM Support',
    help: 'PCI Express Active State Power Management',
    token: '1002',
    offset: '14',
    width: '1',
    value: 'Auto',
    option_id: '00',
    options: [['00', 'Auto'], ['01', 'Disabled'], ['02', 'L0s Only']],
    default: 'Auto',
    numeric: false,
    modified: false,
    register: true,
    active: false,
    differs_default: false,
    context: ['Root Port 0', 'Root Port 1'],
  },
];

let mockBackups: Backup[] = [
  { path: 'backups/nvram_backup_20261124_120000.txt', name: 'nvram_backup_20261124_120000.txt', mtime: Date.now() / 1000 - 3600, size: 45200 },
  { path: 'backups/nvram_backup_20261123_183000.txt', name: 'nvram_backup_20261123_183000.txt', mtime: Date.now() / 1000 - 86400, size: 45150 },
];

function handleMockRequest(action: Action, payload: Payload): Update {
  switch (action) {
    case 'bootstrap':
      return {
        document_id: 'mock-doc-1',
        filepath: 'nvram.txt',
        dirty: mockDirty,
        modified_count: mockSettings.filter(s => s.modified).length,
        logs: ['[MockGateway] Running in autonomous browser dev mode (mock adapter active)'],
        language: mockLanguage,
        settings: mockSettings,
        backups: mockBackups,
        app_name: 'Scewin GUI (Mock)',
        version: '2.0.1',
        dependencies: { ok: true, missing: [], unreadable: [], tampered: [], hvci_active: false },
      };
    case 'open_file':
      return { filepath: 'nvram_sample.txt', settings: mockSettings, dirty: false };
    case 'edit': {
      const id = payload.id as number;
      const val = payload.value as string;
      const target = mockSettings.find(s => s.id === id);
      if (target) {
        if (target.options.length) {
          const opt = target.options.find(([optId]) => optId === val);
          target.option_id = val;
          target.value = opt ? opt[1] : val;
        } else {
          target.value = `<${val.replace(/^<|>$/g, '')}>`;
        }
        target.modified = true;
        mockDirty = true;
        return {
          dirty: true,
          modified_count: mockSettings.filter(s => s.modified).length,
          setting: { ...target },
        };
      }
      return {};
    }
    case 'draft':
      mockDirty = Boolean(payload.dirty);
      return { dirty: mockDirty };
    case 'reset': {
      const id = payload.id as number;
      const target = mockSettings.find(s => s.id === id);
      if (target) {
        target.modified = false;
        target.value = target.default;
        return {
          dirty: mockSettings.some(s => s.modified),
          modified_count: mockSettings.filter(s => s.modified).length,
          setting: { ...target },
        };
      }
      return {};
    }
    case 'save_changes':
    case 'save_as':
      mockDirty = false;
      mockSettings = mockSettings.map(s => ({ ...s, modified: false }));
      return {
        dirty: false,
        modified_count: 0,
        settings: mockSettings,
        message: 'Mock: Saved successfully',
      };
    case 'backups':
      return { backups: mockBackups };
    case 'create_backup': {
      const newBackup: Backup = {
        path: `backups/nvram_backup_${Date.now()}.txt`,
        name: `nvram_backup_${Date.now()}.txt`,
        mtime: Date.now() / 1000,
        size: 45200,
      };
      mockBackups = [newBackup, ...mockBackups];
      return { backups: mockBackups, message: 'Mock: Backup created' };
    }
    case 'delete_backup': {
      const path = payload.path as string;
      mockBackups = mockBackups.filter(b => b.path !== path);
      return { backups: mockBackups };
    }
    case 'open_backup_folder':
      return {};
    case 'bios':
      return {
        message: 'Mock: BIOS operation completed successfully',
        backups: mockBackups,
      };
    case 'language':
      mockLanguage = (payload.language as Language) || 'ru';
      return { language: mockLanguage };
    case 'external_link':
      if (typeof window !== 'undefined') {
        window.open('https://buymeacoffee.com/cat_fire', '_blank');
      }
      return {};
    default:
      return {};
  }
}

export function request(action: Action, payload: Payload = {}): Promise<Update> {
  const pending = queue.then(async () => {
    if (!window.pywebview?.api) {
      // Graceful fallback to MockBiosGateway for browser development / component testing
      return handleMockRequest(action, payload);
    }
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
