import { useDeferredValue, useEffect, useRef, useState } from 'react';
import { Download, FileInput, Filter, FolderOpen, Save, SaveAll, Search, Upload, X } from 'lucide-react';
import { LogPanel } from '../components/LogPanel';
import { SettingsTable } from '../components/SettingsTable';
import type { DesktopState, RunAction, Translate } from '../types';

export function Editor({ state, busy, run, t }: {
  state: DesktopState; busy: boolean; run: RunAction; t: Translate;
}) {
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);
  const [hideRegisters, setHideRegisters] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setSelected(null); }, [state.document_id]);
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.key.toLowerCase() === 'f') {
        event.preventDefault(); searchRef.current?.focus();
      }
      if (event.ctrlKey && event.key.toLowerCase() === 's') {
        event.preventDefault();
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
        void run(event.shiftKey ? 'save_as' : 'save_changes');
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [run]);
  return <div className="page editor-page">
    <header className="editor-header">
      <div className="editor-heading">
        <h1>{t('editor.title')}</h1><p className="subtitle">{t('editor.subtitle')}</p>
        <div className="search-tools">
          <div className="search-field" title={t('search.tooltip')}><Search size={16} />
            <input ref={searchRef} aria-label={t('search.placeholder')} placeholder={t('search.placeholder')}
              value={query} onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') setQuery(''); }} />
            {query && <button className="icon-button" aria-label={t('desktop.clear_search')}
              onClick={() => setQuery('')}><X size={14} /></button>}
          </div>
          <button className={`button filter-button ${hideRegisters ? 'is-checked' : ''}`}
            aria-pressed={hideRegisters} title={t('tooltip.hide_registers')} onClick={() => setHideRegisters(v => !v)}>
            <Filter size={15} />{t('button.hide_registers')}
          </button>
        </div>
      </div>
      <div className="editor-actions">
        <div className="action-group"><span>{t('category.export')}</span>
          <button className="button" disabled={busy} title={t('tooltip.export')}
            onClick={() => void run('bios', { operation: 'export' })}><Upload size={16} />{t('button.export')}</button>
          <small>{t('hint.export')}</small>
        </div>
        <div className="open-actions"><button className="icon-button" disabled={busy}
          title={t('tooltip.open_file')} aria-label={t('button.open_file')} onClick={() => void run('open_file')}>
          <FolderOpen size={19} /></button></div>
        <div className="action-group"><span>{t('category.import')}</span>
          <div className="action-pair">
            <div><button className="button" disabled={busy || !state.filepath} title={t('tooltip.import_loaded')}
              onClick={() => void run('bios', { operation: 'import_loaded' })}><FileInput size={16} />{t('button.import_loaded')}</button>
              <small>{t('hint.import_loaded')}</small></div>
            <div><button className="button" disabled={busy} title={t('tooltip.import')}
              onClick={() => void run('bios', { operation: 'import' })}><Download size={16} />{t('button.import')}</button>
              <small>{t('hint.import')}</small></div>
          </div>
        </div>
        <div className="action-group"><span>{t('category.apply')}</span>
          <button className="button button--primary" disabled={busy || !state.settings.length}
            title={t('tooltip.apply')} onClick={() => void run('save_changes')}><Save size={16} />{t('button.apply')}</button>
          <small>{t('hint.apply')}</small>
        </div>
      </div>
    </header>
    <div className="file-strip"><span title={state.filepath}>{state.dirty && <b className="unsaved-dot">● </b>}
      {state.filepath || t('infobar.no_loaded_file')}</span>
      <button className="text-button" disabled={busy || !state.settings.length} onClick={() => void run('save_as')}>
        <SaveAll size={14} />{t('desktop.save_as')}</button>
    </div>
    <SettingsTable settings={state.settings} documentId={state.document_id} query={deferredQuery}
      hideRegisters={hideRegisters} selected={selected} onSelect={setSelected} busy={busy} run={run} t={t} />
    <LogPanel details logs={state.logs} setting={state.settings.find(s => s.id === selected)} t={t} />
  </div>;
}
