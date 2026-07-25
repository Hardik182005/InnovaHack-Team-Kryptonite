/** Processing page — §6.2 stages, §19 progress. */

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, NeedsAnalysis } from '../components/common';
import { toApiError } from '../api/errors';
import type { AnalysisStatus } from '../api/types';

const POLL_MS = 700;

export default function Processing() {
  const navigate = useNavigate();
  const analysisId = activeAnalysisId();
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [error, setError] = useState<unknown>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!analysisId) return undefined;
    let stopped = false;

    async function poll() {
      try {
        const next = await api.getStatus(analysisId as string);
        if (stopped) return;
        setStatus(next);
        if (next.state === 'AWAITING_REVIEW') {
          navigate('/review');
          return;
        }
        if (next.state === 'COMPLETED') {
          navigate('/dashboard');
          return;
        }
        if (next.state === 'FAILED') return;
        timer.current = window.setTimeout(poll, POLL_MS);
      } catch (err) {
        if (!stopped) setError(toApiError(err));
      }
    }

    void poll();
    return () => {
      stopped = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [analysisId, navigate]);

  if (!analysisId) return <NeedsAnalysis />;

  const failed = status?.state === 'FAILED';

  return (
    <div className="wrap section">
      <p className="eyebrow">Step 2 of 3</p>
      <h1 className="display-3">Analysing your statement</h1>

      {error ? <ErrorState error={error} onRetry={() => window.location.reload()} /> : null}

      {failed ? (
        <div className="state state--error" role="alert">
          <p className="eyebrow">We could not finish</p>
          <p className="prose">
            {status?.message ?? 'That statement could not be analysed.'}
          </p>
          <button className="btn btn--dark" type="button" onClick={() => navigate('/upload')}>
            Try another statement
          </button>
        </div>
      ) : null}

      <div
        className="meter"
        role="progressbar"
        aria-valuenow={status?.progress_percent ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Analysis progress"
      >
        <span style={{ width: `${status?.progress_percent ?? 0}%` }} />
      </div>
      <p className="micro" aria-live="polite">
        {status?.message ?? 'Starting…'} · {status?.progress_percent ?? 0}%
      </p>

      <ol className="stages" style={{ marginTop: 32 }}>
        {(status?.stages ?? []).map((stage) => (
          <li key={stage.key} className={`stage stage--${stage.state}`}>
            <span className="mono">{stage.state === 'done' ? '✓' : stage.state === 'active' ? '•' : '·'}</span>
            <span>{stage.label}</span>
            {stage.detail ? <span className="micro t-muted">{stage.detail}</span> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
