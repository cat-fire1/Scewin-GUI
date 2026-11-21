import { useEffect, useRef } from 'react';
import type { Setting, Translate } from '../types';

export function LogPanel({ logs, setting, t, details = false }: {
  logs: string[]; setting?: Setting; t: Translate; details?: boolean;
}) {
  const logRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const element = logRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [logs]);
  return <section className={`card log-panel ${details ? 'log-panel--details' : ''}`}>
    {details && <div className="setting-details">
      <strong>{setting?.name || t('details.none')}</strong>
      <div className="setting-description">{setting ? <>
        {setting.help || t('details.no_description')}
        <p>{[setting.token && `Token: ${setting.token}`, setting.offset && `Offset: ${setting.offset}`,
          setting.width && `Width: ${setting.width}`].filter(Boolean).join(' | ')}</p>
        <span className={setting.register ? 'text-warning' : ''}>
          {t(setting.register ? 'details.type_register' : setting.active ? 'details.type_active' : 'details.type_user')}
        </span>
        {setting.register && <p className="text-warning">{t('details.type_register_warning')}</p>}
        {setting.context.length > 0 && <p>{t('details.environment')} {setting.context.join(', ')}</p>}
      </> : t('details.select_row')}</div>
    </div>}
    <pre ref={logRef} className="operation-log" aria-label={t('desktop.log')} tabIndex={0}>
      {logs.join('\n')}
    </pre>
  </section>;
}
