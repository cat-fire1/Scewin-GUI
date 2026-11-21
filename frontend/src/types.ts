export type Language = 'ru' | 'en' | 'uk';
export type Page = 'editor' | 'backup' | 'about';

export interface Setting {
  id: number;
  name: string;
  help: string;
  token: string;
  offset: string;
  width: string;
  value: string;
  option_id: string;
  options: [string, string][];
  default: string;
  numeric: boolean;
  modified: boolean;
  register: boolean;
  active: boolean;
  differs_default: boolean;
  context: string[];
}

export interface Backup {
  path: string;
  name: string;
  mtime: number;
  size: number;
}

export interface DesktopState {
  document_id: string;
  filepath: string;
  dirty: boolean;
  modified_count: number;
  logs: string[];
  language: Language;
  settings: Setting[];
  backups: Backup[];
  app_name: string;
  version: string;
  dependencies?: {
    ok: boolean;
    missing: string[];
    unreadable: string[];
    tampered: string[];
    hvci_active: boolean;
  };
}

export type Update = Partial<DesktopState> & {
  setting?: Setting;
  message?: string;
  cancelled?: boolean;
};

export type Action = 'bootstrap' | 'open_file' | 'edit' | 'draft' | 'reset' | 'save_changes'
  | 'save_as' | 'backups' | 'create_backup' | 'delete_backup' | 'open_backup_folder'
  | 'bios' | 'language' | 'external_link';
export type Payload = Record<string, unknown>;
export type RunAction = (action: Action, payload?: Payload) => Promise<void>;
export type Translate = (key: string, values?: Record<string, string | number>) => string;

declare global {
  interface Window {
    pywebview?: {
      api: {
        request: (action: Action, payload: Payload) => Promise<{
          ok: boolean; data?: Update; error?: string;
        }>;
      };
    };
  }
}
