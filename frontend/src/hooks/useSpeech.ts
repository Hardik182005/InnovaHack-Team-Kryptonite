/** Browser speech-to-text and text-to-speech, in the user's selected language.
 *
 * Both sit on the Web Speech API, which needs no key and no network round trip
 * — the point being that voice keeps working when the paid voice provider is
 * unavailable, and costs nothing per use. `VoiceExpense` had its own copy of
 * this; the Coach needs the same behaviour, so it lives here rather than being
 * written twice and drifting.
 *
 * Everything degrades quietly: a browser without the API reports `supported:
 * false` and the caller hides the microphone rather than showing a button that
 * does nothing.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { useI18n } from '../i18n/I18nProvider';

/** Minimal shape of the vendor-prefixed Web Speech API. */
export interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

export interface SpeechRecognitionEventLike {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
  resultIndex: number;
}

export function getRecognition(): SpeechRecognitionLike | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

/** Dictation. `onFinal` fires once, with the completed utterance. */
export function useDictation(onFinal: (text: string) => void) {
  const { lang } = useI18n();
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);
  const engineRef = useRef<SpeechRecognitionLike | null>(null);

  // `onFinal` is usually an inline arrow, so a new identity every render. Held
  // in a ref, `start` stays stable and the engine is not torn down mid-phrase.
  const handler = useRef(onFinal);
  useEffect(() => { handler.current = onFinal; }, [onFinal]);

  const supported = typeof window !== 'undefined' && getRecognition() !== null;
  const canDictate = supported && lang.speechLocale !== null;

  const stop = useCallback(() => {
    engineRef.current?.stop();
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
      const last = event.results[event.results.length - 1];
      if (last?.isFinal && text.trim()) {
        handler.current(text.trim());
        setInterim('');
      }
    };
    engine.onerror = (event) => {
      // `no-speech` and `aborted` are ordinary outcomes of tapping the mic and
      // saying nothing. Surfacing them as errors would be alarming and wrong.
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(event.error);
      }
      setListening(false);
    };
    engine.onend = () => setListening(false);

    engineRef.current = engine;
    setError(null);
    setInterim('');
    try {
      engine.start();
      setListening(true);
    } catch {
      /* already running — a double tap is harmless */
    }
  }, [canDictate, lang.speechLocale]);

  useEffect(() => () => engineRef.current?.stop(), []);

  return { start, stop, listening, interim, error, supported: canDictate };
}

/** Read text aloud in the selected language. */
export function useSpeaker() {
  const { lang } = useI18n();
  const [speaking, setSpeaking] = useState(false);

  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const cancel = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || !text) return;
      try {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang.speechLocale ?? 'en-IN';
        // Slightly under natural pace: these are money figures, and a digit
        // misheard is worse than a sentence that takes a moment longer.
        utterance.rate = 0.95;
        utterance.onend = () => setSpeaking(false);
        utterance.onerror = () => setSpeaking(false);
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
        setSpeaking(true);
      } catch {
        /* synthesis unavailable — the text is still on screen */
      }
    },
    [lang.speechLocale, supported],
  );

  useEffect(() => () => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);

  return { speak, cancel, speaking, supported };
}
