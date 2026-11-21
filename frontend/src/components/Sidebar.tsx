import { DatabaseBackup, Info, Languages, Menu, PencilLine } from 'lucide-react';
import type { Language, Page, RunAction, Translate } from '../types';

interface Props {
  page: Page;
  onPage: (page: Page) => void;
  language: Language;
  compact: boolean;
  onToggle: () => void;
  run: RunAction;
  busy: boolean;
  t: Translate;
}

export function Sidebar({ page, onPage, language, compact, onToggle, run, busy, t }: Props) {
  const items = [
    { page: 'editor' as const, label: 'nav.editor', Icon: PencilLine },
    { page: 'backup' as const, label: 'nav.backup', Icon: DatabaseBackup },
    { page: 'about' as const, label: 'nav.about', Icon: Info },
  ];
  return <aside className={`sidebar ${compact ? 'sidebar--compact' : ''}`}>
    <button className="nav-button menu-toggle" onClick={onToggle}
      title={t('desktop.navigation')} aria-label={t('desktop.navigation')} aria-expanded={!compact}>
      <Menu size={18} />
    </button>
    <nav aria-label={t('desktop.navigation')}>
      {items.map(({ page: destination, label, Icon }) =>
        <button key={destination} className={`nav-button ${page === destination ? 'is-active' : ''}`}
          aria-current={page === destination ? 'page' : undefined}
          title={t(label)} onClick={() => onPage(destination)}>
          <Icon size={19} /><span>{t(label)}</span>
        </button>)}
    </nav>
    <label className="language-picker" title={t('nav.language_tooltip')}>
      <Languages size={19} />
      <select aria-label={t('nav.language')} value={language} disabled={busy}
        onChange={e => void run('language', { language: e.target.value })}>
        <option value="ru">Русский</option>
        <option value="uk">Українська</option>
        <option value="en">English</option>
      </select>
    </label>
  </aside>;
}
