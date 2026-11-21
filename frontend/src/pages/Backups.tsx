import { DatabaseBackup, FileText, FolderOpen, RefreshCw, Trash2, Download } from 'lucide-react';
import { LogPanel } from '../components/LogPanel';
import type { DesktopState, RunAction, Translate } from '../types';

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function Backups({ state, busy, run, t }: {
  state: DesktopState; busy: boolean; run: RunAction; t: Translate;
}) {
  const backups = state.backups;
  const date = (timestamp: number) => new Date(timestamp * 1000).toLocaleString(state.language);
  return <div className="page backup-page">
    <header className="page-header"><div><h1>{t('backup.title')}</h1><p className="subtitle">{t('backup.subtitle')}</p></div>
      <div className="button-row"><button className="button button--primary" disabled={busy}
        onClick={() => void run('create_backup')}><DatabaseBackup size={16} />{t('button.create_backup')}</button>
        <button className="button" disabled={busy} onClick={() => void run('open_backup_folder')}>
          <FolderOpen size={16} />{t('button.open_folder')}</button>
        <button className="icon-button" disabled={busy} aria-label={t('button.refresh')} title={t('tooltip.refresh')}
          onClick={() => void run('backups')}><RefreshCw size={17} /></button>
      </div>
    </header>
    <section className="card backup-summary">
      {[[t('backup.summary_total'), String(backups.length)],
        [t('backup.summary_last'), backups.length ? date(backups[0].mtime) : t('backup.summary_none')],
        [t('backup.summary_size'), formatSize(backups.reduce((sum, item) => sum + item.size, 0))]]
        .map(([label, value]) => <div className="summary-item" key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </section>
    <section className="card backup-list">
      {!backups.length && <div className="empty-state"><DatabaseBackup size={28} /><strong>{t('backup.empty')}</strong></div>}
      {backups.map(backup => <article className="backup-item" key={backup.path}>
        <FileText size={22} /><div className="backup-description"><strong>{backup.name}</strong>
          <span>{date(backup.mtime)} · {formatSize(backup.size)}</span></div>
        <button className="button" disabled={busy} title={t('tooltip.restore')}
          onClick={() => void run('bios', { operation: 'restore', path: backup.path })}>
          <Download size={16} />{t('button.restore')}</button>
        <button className="button" disabled={busy} title={t('tooltip.delete_backup')}
          onClick={() => void run('delete_backup', { path: backup.path })}><Trash2 size={16} />{t('button.delete')}</button>
      </article>)}
    </section>
    <LogPanel logs={state.logs} t={t} />
  </div>;
}
