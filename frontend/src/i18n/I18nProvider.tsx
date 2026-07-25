/** Language context: selection, persistence, and document `lang`/`dir`. */

import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { DEFAULT_LANGUAGE, LanguageDef, findLanguage } from './languages';
import { StringKey, translate, translationCoverage } from './strings';

const STORAGE_KEY = 'safespare.language';

interface I18nValue {
  lang: LanguageDef;
  setLang: (code: string) => void;
  t: (key: StringKey) => string;
  coverage: number;
}

const I18nContext = createContext<I18nValue | null>(null);

function initialLanguage(): string {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
    // Fall back to the browser's language when it is one we support, so a
    // Hindi-speaking user is not greeted in English by default.
    const browser = (navigator.language || '').split('-')[0];
    return findLanguage(browser).code;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [code, setCode] = useState<string>(initialLanguage);
  const lang = useMemo(() => findLanguage(code), [code]);

  useEffect(() => {
    // Setting these on <html> is what makes screen readers switch voice and
    // right-to-left scripts lay out correctly.
    document.documentElement.lang = lang.code;
    document.documentElement.dir = lang.dir ?? 'ltr';
    document.documentElement.dataset.script = lang.script;
    try {
      window.localStorage.setItem(STORAGE_KEY, lang.code);
    } catch {
      /* storage unavailable — the choice simply will not persist */
    }
  }, [lang]);

  const setLang = useCallback((next: string) => setCode(findLanguage(next).code), []);
  const t = useCallback((key: StringKey) => translate(lang.code, key), [lang.code]);

  const value = useMemo(
    () => ({ lang, setLang, t, coverage: translationCoverage(lang.code) }),
    [lang, setLang, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>');
  return ctx;
}
