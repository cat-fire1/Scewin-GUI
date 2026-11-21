import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, LoaderCircle, X } from 'lucide-react';
import { DesktopError, request } from './api';
import { Sidebar } from './components/Sidebar';
import { translator } from './i18n';
import { About } from './pages/About';
import { Backups } from './pages/Backups';
import { Editor } from './pages/Editor';
import type { DesktopState, Page, RunAction, Update } from './types';

const initial: DesktopState = {
  document_id: '', filepath: '', dirty: false, modified_count: 0, logs: [],
  language: 'ru', settings: [], backups: [], app_name: 'Scewin GUI', version: '2.0.0',
};

export function App() {
  const [state, setState] = useState(initial);
  const [page, setPage] = useState<Page>('editor');
  const [compact, setCompact] = useState(false);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ message: string; error: boolean } | null>(null);
  const pending = useRef(0);
  const started = useRef(false);
  const t = useMemo(() => translator(state.language), [state.language]);
  const update = useCallback((data: Update) => {
    setState(current => {
      const { setting, message: _message, cancelled: _cancelled, ...patch } = data;
      return { ...current, ...patch, settings: setting
        ? current.settings.map(s => s.id === setting.id ? setting : s)
        : patch.settings ?? current.settings };
    });
  }, []);
  const run = useCallback<RunAction>(async (action, payload = {}) => {
    const blocking = action !== 'edit' && action !== 'reset' && action !== 'draft';
    if (blocking) { pending.current += 1; setBusy(true); }
    try {
      const data = await request(action, payload);
      update(data);
      if (data.message) setNotice({ message: data.message, error: false });
      if (action === 'bootstrap') setConnected(true);
    } catch (error) {
      if (error instanceof DesktopError && error.update) update(error.update);
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      if (blocking) {
        pending.current -= 1;
        if (!pending.current) setBusy(false);
      }
    }
  }, [update]);
  useEffect(() => {
    const connect = () => {
      if (started.current) return;
      started.current = true; void run('bootstrap');
    };
    if (window.pywebview?.api) connect();
    window.addEventListener('pywebviewready', connect);
    return () => window.removeEventListener('pywebviewready', connect);
  }, [run]);
  useEffect(() => { document.documentElement.lang = state.language; }, [state.language]);
  useEffect(() => {
    if (!notice || notice.error) return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);
  const activeBusy = busy || !connected;
  return <div className="app-shell">
    <Sidebar page={page} onPage={next => { setPage(next); if (next === 'backup' && connected) void run('backups'); }}
      language={state.language} compact={compact} onToggle={() => setCompact(value => !value)}
      run={run} busy={activeBusy} t={t} />
    <main className="main-content" aria-busy={busy}>
      {connected && state.dependencies && (!state.dependencies.ok || state.dependencies.hvci_active) &&
        <div className="dependency-banner" role="status"><AlertTriangle size={16} />
          {!state.dependencies.ok ? t('deps.missing', { files: [...state.dependencies.missing,
            ...state.dependencies.unreadable, ...state.dependencies.tampered].join(', ') }) : t('desktop.hvci')}</div>}
      {!connected && <div className="connection-banner" role="status">{busy
        ? t('desktop.connecting') : t('desktop.desktop_only')}</div>}
      {page === 'editor' && <Editor state={state} busy={activeBusy} run={run} t={t} />}
      {page === 'backup' && <Backups state={state} busy={activeBusy} run={run} t={t} />}
      {page === 'about' && <About state={state} busy={activeBusy} run={run} t={t} />}
      {busy && <div className="busy-indicator" role="status"><LoaderCircle size={15} />{t('desktop.working')}</div>}
      {notice && <div className={`toast ${notice.error ? 'toast--error' : ''}`} role={notice.error ? 'alert' : 'status'}>
        {notice.error ? <AlertTriangle size={19} /> : <CheckCircle2 size={19} />}
        <span>{notice.message}</span><button className="icon-button" aria-label={t('desktop.close')}
          onClick={() => setNotice(null)}><X size={16} /></button></div>}
    </main>
  </div>;
}
