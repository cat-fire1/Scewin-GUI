import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, RotateCcw, Undo2 } from 'lucide-react';
import type { RunAction, Setting, Translate } from '../types';

type SortKey = 'name' | 'token' | 'default' | 'status';
interface Props {
  settings: Setting[];
  documentId: string;
  query: string;
  hideRegisters: boolean;
  selected: number | null;
  onSelect: (id: number) => void;
  busy: boolean;
  run: RunAction;
  t: Translate;
}

function NumericEditor({ setting, disabled, save, onDraft, t }: {
  setting: Setting; disabled: boolean; save: (value: string) => void;
  onDraft: (dirty: boolean) => void; t: Translate;
}) {
  const value = setting.value.replace(/^<|>$/g, '');
  const [draft, setDraft] = useState(value);
  const [invalid, setInvalid] = useState(false);
  const escaping = useRef(false);
  useEffect(() => { setDraft(value); setInvalid(false); }, [value]);
  const commit = () => {
    if (escaping.current) { escaping.current = false; return; }
    if (draft === value) return;
    if (!/^(?:0[xX])?[0-9a-fA-F]+$/.test(draft.trim())) {
      setDraft(value); setInvalid(true); onDraft(false); return;
    }
    setInvalid(false);
    save(draft.trim());
  };
  return <input className="value-input" aria-label={`${t('table.value')}: ${setting.name}`}
    data-setting-id={setting.id} data-draft-dirty={draft !== value ? 'true' : undefined}
    value={draft} disabled={disabled} spellCheck={false}
    aria-invalid={invalid || undefined} title={invalid ? t('desktop.invalid_number') : setting.value}
    onChange={e => { setDraft(e.target.value); setInvalid(false); onDraft(e.target.value !== value); }} onBlur={commit}
    onKeyDown={e => {
      if (e.key === 'Enter') e.currentTarget.blur();
      if (e.key === 'Escape') {
        escaping.current = true; setDraft(value); setInvalid(false); onDraft(false); e.currentTarget.blur();
      }
    }} />;
}

export function SettingsTable({ settings, documentId, query, hideRegisters, selected, onSelect, busy, run, t }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; direction: number } | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(400);
  const [rowHeight, setRowHeight] = useState(42);
  const scrollRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = scrollRef.current!;
    const measure = () => {
      setHeight(element.clientHeight);
      setRowHeight(parseFloat(getComputedStyle(element).getPropertyValue('--row-height')) || 42);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element); measure();
    return () => observer.disconnect();
  }, []);
  const filtered = useMemo(() => {
    const search = query.trim().toLocaleLowerCase();
    const rows = settings.filter(s => !(hideRegisters && s.register) && (!search ||
      [s.name, s.help, s.token, s.offset].some(value => value.toLocaleLowerCase().includes(search))));
    if (sort) rows.sort((a, b) => {
      const left = sort.key === 'status' ? Number(a.modified) * 4 + Number(a.active) * 2 + Number(a.register) : a[sort.key];
      const right = sort.key === 'status' ? Number(b.modified) * 4 + Number(b.active) * 2 + Number(b.register) : b[sort.key];
      return String(left).localeCompare(String(right), undefined, { numeric: true }) * sort.direction || a.id - b.id;
    });
    return rows;
  }, [settings, query, hideRegisters, sort]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 }); setScrollTop(0);
  }, [query, hideRegisters, sort, documentId]);
  const start = Math.max(0, Math.min(filtered.length - 1, Math.floor(Math.max(0, scrollTop - 36) / rowHeight) - 8));
  const end = Math.min(filtered.length, start + Math.ceil(height / rowHeight) + 16);
  const changeSort = (key: SortKey) => setSort(current => current?.key !== key
    ? { key, direction: -1 } : current.direction === -1 ? { key, direction: 1 } : null);
  const sortHeader = (key: SortKey, label: string) => <th scope="col"
    aria-sort={sort?.key === key ? sort.direction === 1 ? 'ascending' : 'descending' : 'none'}>
    <button onClick={() => changeSort(key)}>{t(label)}
      {sort?.key === key && (sort.direction === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
    </button></th>;
  const navigate = (direction: number) => {
    if (!filtered.length) return;
    const index = Math.max(0, Math.min(filtered.length - 1,
      filtered.findIndex(s => s.id === selected) + direction));
    onSelect(filtered[index].id);
    const viewport = scrollRef.current!;
    const top = index * rowHeight;
    if (top < viewport.scrollTop || top + rowHeight > viewport.scrollTop + height - 36)
      viewport.scrollTop = Math.max(0, top - (height - rowHeight) / 2);
  };
  return <section className="card table-card">
    <div className="table-scroll" ref={scrollRef} tabIndex={0} aria-label={t('editor.title')}
      onScroll={e => setScrollTop(e.currentTarget.scrollTop)}
      onKeyDown={e => {
        if (e.target !== e.currentTarget && e.target instanceof HTMLElement && e.target.tagName !== 'TR') return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault(); navigate(e.key === 'ArrowDown' ? 1 : -1);
        }
      }}>
      <table className="settings-table" aria-rowcount={filtered.length + 1}>
        <colgroup><col className="col-name" /><col className="col-token" /><col className="col-value" />
          <col className="col-default" /><col className="col-status" /></colgroup>
        <thead><tr>{sortHeader('name', 'table.param')}{sortHeader('token', 'table.token_offset')}
          <th scope="col"><button onClick={() => setSort(null)}>{t('table.value')}</button></th>
          {sortHeader('default', 'table.default')}{sortHeader('status', 'table.status')}</tr></thead>
        <tbody>
          {start > 0 && <tr aria-hidden="true"><td colSpan={5} className="spacer" style={{ height: start * rowHeight }} /></tr>}
          {filtered.slice(start, end).map((setting, offset) => <tr key={`${documentId}:${setting.id}`}
            aria-rowindex={start + offset + 2} aria-selected={selected === setting.id}
            className={`${selected === setting.id ? 'is-selected' : ''} ${setting.modified ? 'is-modified' : ''}`}
            onClick={() => onSelect(setting.id)} onFocus={() => onSelect(setting.id)}>
            <td title={setting.name}><span className="parameter-name">{setting.name}</span></td>
            <td className="token-cell" title={`Token: ${setting.token}\nOffset: ${setting.offset}`}>
              {setting.token || setting.offset || '—'}</td>
            <td>{setting.options.length > 0 ? <select className="value-input" disabled={busy}
              aria-label={`${t('table.value')}: ${setting.name}`} value={setting.option_id}
              onChange={e => void run('edit', { document_id: documentId, id: setting.id, value: e.target.value })}>
              {!setting.options.some(([id]) => id === setting.option_id) && <option value="">{setting.value || '—'}</option>}
              {setting.options.map(([id, label]) => <option key={id} value={id}>{label} [{id}]</option>)}
            </select> : setting.numeric ? <NumericEditor setting={setting} disabled={busy} t={t}
              onDraft={dirty => void run('draft', { document_id: documentId, id: setting.id, dirty })}
              save={value => void run('edit', { document_id: documentId, id: setting.id, value })} /> : setting.value || '—'}</td>
            <td className="default-cell" title={setting.default}>{setting.default || '—'}</td>
            <td><div className="setting-status">
              <span className={setting.modified ? 'text-success' : setting.active ? 'text-accent' : 'text-muted'}>
                {setting.modified ? t('status.modified') : setting.active ? t('status.active') : setting.register ? t('status.register') : ''}
              </span>
              <div className="row-actions">
                {setting.differs_default && <button className="icon-button" disabled={busy}
                  title={t('status.reset_default')} aria-label={`${t('status.reset_default')}: ${setting.name}`}
                  onClick={() => void run('reset', { document_id: documentId, id: setting.id, mode: 'default' })}><RotateCcw size={14} /></button>}
                {setting.modified && <button className="icon-button" disabled={busy}
                  title={t('status.revert')} aria-label={`${t('status.revert')}: ${setting.name}`}
                  onClick={() => void run('reset', { document_id: documentId, id: setting.id, mode: 'initial' })}><Undo2 size={14} /></button>}
              </div>
            </div></td>
          </tr>)}
          {end < filtered.length && <tr aria-hidden="true"><td colSpan={5} className="spacer"
            style={{ height: (filtered.length - end) * rowHeight }} /></tr>}
        </tbody>
      </table>
      {!filtered.length && <div className="empty-state">
        <strong>{t(settings.length ? 'desktop.no_results' : 'details.none')}</strong>
        <span>{t(settings.length ? 'desktop.search_hint' : 'desktop.open_hint')}</span>
      </div>}
    </div>
    <div className="table-footer"><span>{t('desktop.row_count', { count: filtered.length, total: settings.length })}</span>
      <span>{t('desktop.modified_count', { count: settings.filter(s => s.modified).length })}</span></div>
  </section>;
}
