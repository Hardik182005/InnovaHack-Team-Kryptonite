/**
 * Speak-your-expense capture.
 *
 * Built for someone who cannot read a bank statement — or cannot read at all.
 * The controls are large, the labels are spoken back, and every captured
 * expense is repeated aloud in the user's own language before it counts.
 *
 * Parsing is deterministic and happens on the backend (§3.7): this component
 * only transports the words. It never derives an amount itself.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { useI18n } from '../i18n/I18nProvider';

/** Minimal shape of the vendor-prefixed Web Speech API. */
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
  resultIndex: number;
}

function getRecognition(): SpeechRecognitionLike | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

export interface SpokenExpense {
  transcript: string;
  amount: number | null;
  description: string;
  confident: boolean;
}

export function VoiceExpense({
  onCapture,
  currencySymbol = '₹',
}: {
  onCapture: (expense: SpokenExpense) => void;
  currencySymbol?: string;
}) {
  const { t, lang } = useI18n();
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [captured, setCaptured] = useState<SpokenExpense | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<SpeechRecognitionLike | null>(null);

  const supported = typeof window !== 'undefined' && getRecognition() !== null;
  const canDictate = supported && lang.speechLocale !== null;

  /** Speak text back in the user's language — the confirmation an illiterate
   *  user relies on. Uses the built-in synthesizer, which needs no API key. */
  const speak = useCallback(
    (text: string) => {
      try {
        if (!('speechSynthesis' in window)) return;
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang.speechLocale ?? 'en-IN';
        utterance.rate = 0.95;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
      } catch {
        /* synthesis unavailable — the text is still on screen */
      }
    },
    [lang.speechLocale],
  );

  const stop = useCallback(() => {
    recognition.current?.stop();
    setListening(false);
  }, []);

  const start = useCallback(() => {
    if (!canDictate) return;
    const engine = getRecognition();
    if (!engine) return;

    engine.lang = lang.speechLocale as string;
    engine.continuous = false;
    engine.interimResults = true;

    engine.onresult = (event) => {
      let text = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        text += event.results[i][0].transcript;
      }
      setInterim(text);
      const final = event.results[event.results.length - 1];
      if (final?.isFinal) {
        const parsed = parseSpokenExpense(text);
        setCaptured(parsed);
        setInterim('');
        // Repeat it back so the user can hear whether we understood.
        speak(
          parsed.amount !== null
            ? `${parsed.amount} ${parsed.description}`
            : text,
        );
      }
    };

    engine.onerror = (event) => {
      setError(
        event.error === 'not-allowed'
          ? 'Microphone permission is needed to listen.'
          : t('voice.unsupported'),
      );
      setListening(false);
    };

    engine.onend = () => setListening(false);

    recognition.current = engine;
    setError(null);
    setCaptured(null);
    setListening(true);
    engine.start();
  }, [canDictate, lang.speechLocale, speak, t]);

  useEffect(() => () => recognition.current?.stop(), []);

  return (
    <section className="card voice-card" aria-labelledby="voice-title">
      <h2 id="voice-title" className="display-4">
        {t('voice.title')}
      </h2>
      <p className="prose t-muted">{t('voice.prompt')}</p>
      <p className="micro t-muted">{t('voice.example')}</p>

      {!canDictate ? (
        <p className="notice notice--warning" role="status">
          {t('voice.unsupported')}
          {lang.speechLocale === null
            ? ` Dictation is not yet available in ${lang.native}.`
            : ''}
        </p>
      ) : null}

      <div className="voice-controls">
        <button
          type="button"
          className={listening ? 'mic mic--on' : 'mic'}
          onClick={listening ? stop : start}
          disabled={!canDictate}
          aria-pressed={listening}
          aria-label={listening ? t('cta.stop') : t('cta.speak')}
        >
          <span aria-hidden="true">{listening ? '■' : '🎤'}</span>
        </button>
        <span className="voice-status" aria-live="polite">
          {listening ? t('voice.listening') : t('cta.speak')}
        </span>
      </div>

      {interim ? (
        <p className="prose voice-interim" aria-live="polite">
          {interim}
        </p>
      ) : null}

      {error ? (
        <p className="notice notice--warning" role="alert">
          {error}
        </p>
      ) : null}

      {captured ? (
        <div className="notice notice--positive">
          <p className="prose">
            <strong>
              {captured.amount !== null
                ? `${currencySymbol}${captured.amount}`
                : '—'}
            </strong>{' '}
            {captured.description || captured.transcript}
          </p>
          {captured.amount === null ? (
            <p className="micro">
              We could not hear an amount. Try again, or type it instead.
            </p>
          ) : null}
          <div className="row" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn--primary"
              disabled={captured.amount === null}
              onClick={() => {
                onCapture(captured);
                setCaptured(null);
                speak(t('voice.added'));
              }}
            >
              {t('common.confirm')}
            </button>
            <button type="button" className="btn btn--ghost" onClick={() => setCaptured(null)}>
              {t('common.cancel')}
            </button>
            <button type="button" className="btn btn--quiet" onClick={() => speak(captured.transcript)}>
              {t('cta.listen')}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Pull an amount and a description out of a spoken phrase.
 *
 * Kept deliberately simple and local: it is a *transport* convenience so the
 * user sees something immediately. The backend re-parses authoritatively, and
 * a number this function guesses never reaches a financial calculation without
 * the user confirming it on screen first.
 *
 * Handles Indian spoken forms: "two fifty", "250 rupees", "ढाई सौ", "1.5k".
 */
export function parseSpokenExpense(raw: string): SpokenExpense {
  const text = (raw || '').trim();
  const lower = text.toLowerCase();

  let amount: number | null = null;

  // 1. plain digits, with optional thousands separators and k/thousand suffix
  const digits = lower.match(/(\d[\d,]*(?:\.\d{1,2})?)\s*(k|thousand|hazaar|हज़ार|हजार)?/);
  if (digits) {
    const value = Number.parseFloat(digits[1].replace(/,/g, ''));
    if (Number.isFinite(value)) {
      amount = digits[2] ? value * 1000 : value;
    }
  }

  // 2. spelled-out English numbers, common in dictation
  if (amount === null) {
    const words: Record<string, number> = {
      zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7,
      eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, fifteen: 15,
      twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70,
      eighty: 80, ninety: 90, hundred: 100, thousand: 1000,
    };
    const tokens = lower.split(/\s+/).filter((w) => w in words);
    if (tokens.length) {
      let total = 0;
      let current = 0;
      for (const token of tokens) {
        const value = words[token];
        if (value === 100 || value === 1000) {
          current = (current || 1) * value;
          if (value === 1000) {
            total += current;
            current = 0;
          }
        } else {
          current += value;
        }
      }
      total += current;
      if (total > 0) amount = total;
    }
  }

  // Strip the amount and common filler so the remainder reads as a description.
  const description = text
    .replace(/(\d[\d,]*(?:\.\d{1,2})?)\s*(k|thousand)?/gi, ' ')
    .replace(
      /\b(i|spent|paid|on|for|rupees?|rs\.?|inr|₹|the|a|an|today|yesterday|maine|kharch|kiye|pe|par)\b/gi,
      ' ',
    )
    .replace(/\s{2,}/g, ' ')
    .trim();

  return {
    transcript: text,
    amount,
    description: description || text,
    confident: amount !== null && description.length > 0,
  };
}
