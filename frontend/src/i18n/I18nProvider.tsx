/** Language context: selection, persistence, and document `lang`/`dir`. */

import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { DEFAULT_LANGUAGE, LanguageDef, findLanguage } from './languages';
import { EN, StringKey, missingKeys, translate, translationCoverage } from './strings';
import * as machine from './machine';

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

  // Bumped whenever machine translations arrive. They land asynchronously,
  // after render, so without this they would sit in the cache unseen until
  // some unrelated state change happened to force a repaint.
  const [revision, setRevision] = useState(0);
  useEffect(() => machine.subscribe(() => setRevision((n) => n + 1)), []);

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

  useEffect(() => {
    // Ask for every key the curated dictionary lacks, in one batch, as soon as
    // the language changes. Requesting the whole gap up front rather than
    // per-component means the page fills in a single pass instead of visibly
    // translating itself line by line.
    const gaps = missingKeys(lang.code);
    if (gaps.length === 0) return;
    void machine.request(lang.code, gaps.map((key) => EN[key]));
  }, [lang.code]);

  const setLang = useCallback((next: string) => setCode(findLanguage(next).code), []);

  const t = useCallback(
    (key: StringKey) => {
      const curated = translate(lang.code, key);
      // `translate` returns English when the key is missing, and that is the
      // only case machine translation may fill: a curated string is a reviewed
      // decision and always wins, even when it happens to match English.
      if (curated !== EN[key]) return curated;
      return machine.lookup(lang.code, EN[key]) ?? curated;
    },
    // `revision` is a real dependency -- it is what makes `t` a new function
    // once translations arrive, which is what re-renders every consumer.
    [lang.code, revision],
  );

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
