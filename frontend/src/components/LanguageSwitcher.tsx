/**
 * Language picker.
 *
 * Each option shows the language in its own script first, because that is the
 * only label a user who cannot read English can recognise. Where the UI is only
 * partly translated we say so rather than showing a half-English screen without
 * explanation.
 */

import { useI18n } from '../i18n/I18nProvider';
import { LANGUAGES } from '../i18n/languages';

export function LanguageSwitcher({ compact }: { compact?: boolean }) {
  const { lang, setLang, coverage } = useI18n();

  const scheduled = LANGUAGES.filter((l) => l.scheduled);
  const other = LANGUAGES.filter((l) => !l.scheduled && l.code !== 'en');
  const english = LANGUAGES.find((l) => l.code === 'en');

  return (
    <div className="lang">
      <label className="sr-only" htmlFor="lang-select">
        Choose your language
      </label>
      <select
        id="lang-select"
        className={compact ? 'select select--sm' : 'select'}
        value={lang.code}
        onChange={(event) => setLang(event.target.value)}
      >
        {english ? (
          <option value={english.code}>
            {english.native} {dictationMark(english.speechLocale)}
          </option>
        ) : null}
        <optgroup label="भारत की भाषाएँ / Languages of India">
          {scheduled.map((l) => (
            <option key={l.code} value={l.code}>
              {l.native} — {l.english} {dictationMark(l.speechLocale)}
            </option>
          ))}
        </optgroup>
        <optgroup label="अन्य / Other">
          {other.map((l) => (
            <option key={l.code} value={l.code}>
              {l.native} — {l.english} {dictationMark(l.speechLocale)}
            </option>
          ))}
        </optgroup>
      </select>

      {lang.code !== 'en' && coverage < 1 ? (
        <p className="micro t-muted">
          {Math.round(coverage * 100)}% translated — the rest is shown in English while
          native review is pending.
        </p>
      ) : null}
    </div>
  );
}

/** 🎤 marks languages where the user can dictate rather than type. */
function dictationMark(speechLocale: string | null): string {
  return speechLocale ? '🎤' : '';
}
