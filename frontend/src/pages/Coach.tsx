/** AI Coach + voice summary — §6.11, §6.12. */

import { FormEvent, useRef, useState } from 'react';

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, NeedsAnalysis, SectionHead } from '../components/common';
import { useMutation } from '../hooks/useResource';
import { AppShell } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { useDictation, useSpeaker } from '../hooks/useSpeech';
import { useI18n } from '../i18n/I18nProvider';

interface Turn {
  who: 'user' | 'coach';
  text: string;
  offline?: boolean;
}

const SUGGESTIONS = [
  'How much can I safely spare?',
  'What is my biggest expense?',
  'Why was my Safe Spare capped?',
  'Where is my money leaking?',
];

export default function Coach() {
  const { t } = useI18n();
  const analysisId = activeAnalysisId();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState('');
  const [transcript, setTranscript] = useState<string | null>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [handsFree, setHandsFree] = useState(false);
  const speaker = useSpeaker();

  const ask = useMutation(async (q: string) => {
    setTurns((t) => [...t, { who: 'user', text: q }]);
    const out = await api.chat({ analysis_id: analysisId as string, question: q });
    setTurns((t) => [...t, { who: 'coach', text: out.answer, offline: out.generated_offline }]);
    // Only auto-speak when the question itself was spoken. Reading every typed
    // reply aloud unprompted is startling in a room with other people.
    if (handsFree) speaker.speak(out.answer);
    return out;
  });

  const dictation = useDictation((text) => {
    setHandsFree(true);
    void ask.run(text);
  });

  const speak = useMutation(async () => {
    const out = await api.voiceSummary(analysisId as string);
    setTranscript(out.transcript);
    setAudioSrc(out.audio_available && out.audio_url ? out.audio_url : null);
    return out;
  });

  if (!analysisId) return <NeedsAnalysis />;

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setQuestion('');
    void ask.run(q);
  }

  return (
    <AppShell title={t('page.coach')}>
      <SectionHead
        eyebrow="AI Coach"
        title={t('page.coach')}
        lede="The Coach explains values SafeSpare already calculated. It cannot change them, and it never invents a transaction."
      />

      <div className="card">
        <div className="chat" role="log" aria-live="polite" aria-label="Coach conversation">
          {turns.length === 0 ? (
            <p className="prose t-muted">Ask a question, or try one of the suggestions below.</p>
          ) : null}
          {turns.map((turn, i) => (
            <div key={i} className={turn.who === 'user' ? 'bubble bubble--user' : 'bubble bubble--coach'}>
              <p className="prose">{turn.text}</p>
              {turn.who === 'coach' && speaker.supported ? (
                <button
                  type="button"
                  className="chip"
                  onClick={() => (speaker.speaking ? speaker.cancel() : speaker.speak(turn.text))}
                  aria-label={speaker.speaking ? 'Stop reading' : 'Read this answer aloud'}
                >
                  {speaker.speaking ? 'Stop' : 'Listen'}
                </button>
              ) : null}
              {turn.offline ? <p className="micro t-muted">Answered from verified figures, no model used.</p> : null}
            </div>
          ))}
          {ask.pending ? <p className="micro" aria-live="polite">Thinking…</p> : null}
        </div>

        {ask.error ? <ErrorState error={ask.error} /> : null}

        <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" onClick={() => void ask.run(s)}>
              {s}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="row" style={{ gap: 8, marginTop: 16 }}>
          <label className="sr-only" htmlFor="coach-input">Your question</label>
          <input id="coach-input" className="input" value={question}
                 placeholder={dictation.listening ? (dictation.interim || 'Listening…') : 'Ask about a figure on your dashboard'}
                 onChange={(e) => setQuestion(e.target.value)} />
          {dictation.supported ? (
            <button
              type="button"
              className={dictation.listening ? 'btn btn--dark' : 'btn btn--ghost'}
              onClick={() => (dictation.listening ? dictation.stop() : dictation.start())}
              aria-pressed={dictation.listening}
              aria-label={dictation.listening ? 'Stop listening' : 'Ask by voice'}
            >
              <Icon.mic size={16} />
            </button>
          ) : null}
          <button className="btn btn--primary" type="submit" disabled={ask.pending || !question.trim()}>
            Ask
          </button>
        </form>
        {dictation.error ? (
          <p className="micro t-muted" role="status">
            The microphone could not be used ({dictation.error}). You can type instead.
          </p>
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h2 className="display-4">Voice summary</h2>
        <p className="prose t-muted">
          SafeSpare writes the summary from verified figures first; the voice provider only reads it aloud.
        </p>
        <button className="btn btn--dark" type="button" onClick={() => void speak.run()} disabled={speak.pending}>
          {speak.pending ? 'Preparing…' : 'Generate summary'}
        </button>
        {speak.error ? <ErrorState error={speak.error} /> : null}

        {transcript ? (
          <div style={{ marginTop: 16 }}>
            {audioSrc ? (
              <audio ref={audioRef} className="player" controls src={audioSrc}>
                Your browser cannot play audio. The transcript is below.
              </audio>
            ) : (
              <p className="notice" role="status">
                Audio is unavailable right now, so here is the summary as text.
              </p>
            )}
            <p className="prose" style={{ marginTop: 12 }}>{transcript}</p>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
