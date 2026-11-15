import { useEffect, useRef, useState } from 'react';
import { BookOpen, Coffee, X } from 'lucide-react';
import icon from '../../../icon.ico';
import type { DesktopState, RunAction, Translate } from '../types';

export function About({ state, busy, run, t }: {
  state: DesktopState; busy: boolean; run: RunAction; t: Translate;
}) {
  const [docs, setDocs] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (docs) dialog.current?.showModal(); else dialog.current?.close(); }, [docs]);
  return <div className="page about-page">
    <div className="about-title"><img src={icon} width={48} height={48} alt="" /><h1>{state.app_name}</h1></div>
    <p className="text-muted">{t('about.version', { version: state.version })}</p>
    <section className="card author-card"><h2>{t('about.developer')}</h2><p>🔥 cat_fire</p>
      <button className="button coffee-button" disabled={busy} onClick={() => void run('external_link', { link: 'coffee' })}>
        <Coffee size={17} />{t('about.coffee').replace('☕', '').trim()}</button>
    </section>
    <button className="button button--primary" onClick={() => setDocs(true)}><BookOpen size={17} />{t('about.docs')}</button>
    <footer>{t('about.footer', { year: new Date().getFullYear() })}</footer>
    <dialog ref={dialog} className="docs-dialog" onCancel={() => setDocs(false)} onClose={() => setDocs(false)}>
      <header><h2>{t('about.docs_header')}</h2><button className="icon-button" onClick={() => setDocs(false)}
        aria-label={t('desktop.close')}><X size={19} /></button></header>
      <pre>{t('docs.text')}</pre>
    </dialog>
  </div>;
}
