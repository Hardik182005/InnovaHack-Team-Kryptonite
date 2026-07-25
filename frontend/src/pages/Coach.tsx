/** AI Coach + voice summary — §6.11, §6.12. */

import { FormEvent, useRef, useState } from 'react';

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, NeedsAnalysis, SectionHead } from '../components/common';
import { useMutation } from '../hooks/useResource';

interface Turn {
  who: 'user' | 'coach';
  text: string;
  offline?: boolean;
}

const SUGGESTIONS = [
  'Why was my Safe Spare capped?',
  'Why were my round-ups limited?',
  'Did I use the gym?',
  'Which transaction proves the price increase?',
];

export default function Coach() {
  const analysisId = activeAnalysisId();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState('');
  const [transcript, setTranscript] = useState<string | null>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const ask = useMutation(async (q: string) => {
    setTurns((t) => [...t, { who: 'user', text: q }]);
    const out = await api.chat({ analysis_id: analysisId as string, question: q });
    setTurns((t) => [...t, { who: 'coach', text: out.answer, offline: out.generated_offline }]);
    return out;
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
    <div className="wrap section">
      <SectionHead
        eyebrow="AI Coach"
        title="Ask about any figure"
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
                 placeholder="Ask about a figure on your dashboard"
                 onChange={(e) => setQuestion(e.target.value)} />
          <button className="btn btn--primary" type="submit" disabled={ask.pending || !question.trim()}>
            Ask
          </button>
        </form>
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
    </div>
  );
}
