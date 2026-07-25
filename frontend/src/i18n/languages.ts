/**
 * Language registry — the 22 scheduled languages of India plus English and
 * several widely-spoken regional languages.
 *
 * Each entry carries three separate capability flags, because they genuinely
 * differ per language and the UI must not promise what a browser or provider
 * cannot deliver:
 *
 *   `speechLocale`  BCP-47 tag for the Web Speech API. `null` means dictation
 *                   is unavailable and the UI must fall back to typing.
 *   `tts`           whether ElevenLabs multilingual v2 handles it well. When
 *                   false the app still shows the transcript.
 *   `script`        used to load the right font stack and set `lang`/`dir`.
 */

export interface LanguageDef {
  code: string;
  /** Name in the language itself — the only label an illiterate user's helper
   *  or a non-English reader can recognise. */
  native: string;
  english: string;
  speechLocale: string | null;
  tts: boolean;
  script: 'latin' | 'devanagari' | 'bengali' | 'tamil' | 'telugu' | 'kannada' |
          'malayalam' | 'gujarati' | 'gurmukhi' | 'odia' | 'arabic' | 'ol-chiki' | 'meitei';
  dir?: 'rtl';
  /** Scheduled in the Eighth Schedule of the Constitution of India. */
  scheduled: boolean;
}

export const LANGUAGES: LanguageDef[] = [
  { code: 'en', native: 'English', english: 'English', speechLocale: 'en-IN', tts: true, script: 'latin', scheduled: false },

  // --- Eighth Schedule (22) ------------------------------------------------
  { code: 'hi', native: 'हिन्दी', english: 'Hindi', speechLocale: 'hi-IN', tts: true, script: 'devanagari', scheduled: true },
  { code: 'bn', native: 'বাংলা', english: 'Bengali', speechLocale: 'bn-IN', tts: true, script: 'bengali', scheduled: true },
  { code: 'te', native: 'తెలుగు', english: 'Telugu', speechLocale: 'te-IN', tts: true, script: 'telugu', scheduled: true },
  { code: 'mr', native: 'मराठी', english: 'Marathi', speechLocale: 'mr-IN', tts: true, script: 'devanagari', scheduled: true },
  { code: 'ta', native: 'தமிழ்', english: 'Tamil', speechLocale: 'ta-IN', tts: true, script: 'tamil', scheduled: true },
  { code: 'ur', native: 'اُردُو', english: 'Urdu', speechLocale: 'ur-IN', tts: true, script: 'arabic', dir: 'rtl', scheduled: true },
  { code: 'gu', native: 'ગુજરાતી', english: 'Gujarati', speechLocale: 'gu-IN', tts: true, script: 'gujarati', scheduled: true },
  { code: 'kn', native: 'ಕನ್ನಡ', english: 'Kannada', speechLocale: 'kn-IN', tts: true, script: 'kannada', scheduled: true },
  { code: 'ml', native: 'മലയാളം', english: 'Malayalam', speechLocale: 'ml-IN', tts: true, script: 'malayalam', scheduled: true },
  { code: 'or', native: 'ଓଡ଼ିଆ', english: 'Odia', speechLocale: 'or-IN', tts: false, script: 'odia', scheduled: true },
  { code: 'pa', native: 'ਪੰਜਾਬੀ', english: 'Punjabi', speechLocale: 'pa-IN', tts: true, script: 'gurmukhi', scheduled: true },
  { code: 'as', native: 'অসমীয়া', english: 'Assamese', speechLocale: 'as-IN', tts: false, script: 'bengali', scheduled: true },
  { code: 'mai', native: 'मैथिली', english: 'Maithili', speechLocale: null, tts: false, script: 'devanagari', scheduled: true },
  { code: 'sat', native: 'ᱥᱟᱱᱛᱟᱲᱤ', english: 'Santali', speechLocale: null, tts: false, script: 'ol-chiki', scheduled: true },
  { code: 'ks', native: 'کٲشُر', english: 'Kashmiri', speechLocale: null, tts: false, script: 'arabic', dir: 'rtl', scheduled: true },
  { code: 'ne', native: 'नेपाली', english: 'Nepali', speechLocale: 'ne-NP', tts: false, script: 'devanagari', scheduled: true },
  { code: 'sd', native: 'سنڌي', english: 'Sindhi', speechLocale: null, tts: false, script: 'arabic', dir: 'rtl', scheduled: true },
  { code: 'kok', native: 'कोंकणी', english: 'Konkani', speechLocale: null, tts: false, script: 'devanagari', scheduled: true },
  { code: 'doi', native: 'डोगरी', english: 'Dogri', speechLocale: null, tts: false, script: 'devanagari', scheduled: true },
  { code: 'mni', native: 'ꯃꯤꯇꯩꯂꯣꯟ', english: 'Manipuri', speechLocale: null, tts: false, script: 'meitei', scheduled: true },
  { code: 'brx', native: 'बड़ो', english: 'Bodo', speechLocale: null, tts: false, script: 'devanagari', scheduled: true },
  { code: 'sa', native: 'संस्कृतम्', english: 'Sanskrit', speechLocale: null, tts: false, script: 'devanagari', scheduled: true },

  // --- widely spoken, not scheduled ---------------------------------------
  { code: 'bho', native: 'भोजपुरी', english: 'Bhojpuri', speechLocale: null, tts: false, script: 'devanagari', scheduled: false },
  { code: 'raj', native: 'राजस्थानी', english: 'Rajasthani', speechLocale: null, tts: false, script: 'devanagari', scheduled: false },
  { code: 'tcy', native: 'ತುಳು', english: 'Tulu', speechLocale: null, tts: false, script: 'kannada', scheduled: false },
];

export const DEFAULT_LANGUAGE = 'en';

export function findLanguage(code: string): LanguageDef {
  return LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
}

/** Languages where the user can dictate rather than type. */
export function dictationLanguages(): LanguageDef[] {
  return LANGUAGES.filter((l) => l.speechLocale !== null);
}
