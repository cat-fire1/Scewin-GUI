import en from '../../scewin_gui/translations/en.json';
import ru from '../../scewin_gui/translations/ru.json';
import uk from '../../scewin_gui/translations/uk.json';
import desktopEn from '../../scewin_gui/translations/desktop_en.json';
import desktopRu from '../../scewin_gui/translations/desktop_ru.json';
import desktopUk from '../../scewin_gui/translations/desktop_uk.json';
import type { Language, Translate } from './types';

const catalogs: Record<Language, Record<string, string>> = {
  en: { ...en, ...desktopEn }, ru: { ...ru, ...desktopRu }, uk: { ...uk, ...desktopUk },
};

export function translator(language: Language): Translate {
  return (key, values = {}) => {
    const text = catalogs[language][key] || catalogs.ru[key] || key;
    return text.replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match));
  };
}
