/** Leak Radar — §6.9.
 *
 * The two rules this page makes visible: usage is unknown until the user says
 * otherwise, and a "cancel" decision is a draft, never an executed action. */

import { useState } from 'react';

import { api, activeAnalysisId } from '../api/client';
import { Badge, ConfirmDialog, ErrorState, Loading, NeedsAnalysis, SectionHead, Stat } from '../components/common';
import { useMutation, useResource } from '../hooks/useResource';
import { money, USAGE_LABELS, DECISION_LABELS } from '../lib/format';
import type { LeakDecision, LeakFinding, UsageStatus } from '../api/types';

const USAGE_OPTIONS: UsageStatus[] = [
  'user_confirms_regular_use',
  'user_confirms_occasional_use',
  'user_confirms_not_used',
  'user_does_not_recognize_payment',
];

export default function LeakRadar() {
  const analysisId = activeAnalysisId();
  const [pendingCancel, setPendingCancel] = useState<LeakFinding | null>(null);
  const [draft, setDraft] = useState<{ subject: string; body: string } | null>(null);

  const res = useResource(() => api.getLeaks(analysisId as string), [analysisId]);

  const confirmUsage = useMutation(async (id: string, status: UsageStatus) => {
    const out = await api.confirmUsage(analysisId as string, id, { usage_status: status });
    res.reload();
    return out;
  });

  const decide = useMutation(async (id: string, decision: LeakDecision) => {
    const out = await api.decideLeak(analysisId as string, id, { decision });
    res.reload();
    return out;
  });

  const makeDraft = useMutation(async (id: string) => {
    const out = await api.draftAction(analysisId as string, id, { action: 'cancel' });
    setDraft({ subject: out.subject, body: out.body });
    return out;
  });

  if (!analysisId) return <NeedsAnalysis />;
  if (res.loading) return <div className="wrap section"><Loading /></div>;
  if (res.error) return <div className="wrap section"><ErrorState error={res.error} onRetry={res.reload} /></div>;
  const d = res.data;
  if (!d) return null;
  const c = d.currency;

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow="Leak Radar · supporting intelligence"
        title="Recurring costs worth a second look"
        lede="SafeSpare can see what recurs. It cannot see what you use — so it asks."
      />

      <div className="grid grid--3">
        <Stat label="Potential recoverable / month" value={money(d.potential_recoverable_monthly, c)} />
        <Stat label="High confidence" value={money(d.high_confidence_recoverable_monthly, c)} />
        <Stat label="You confirmed" value={money(d.user_confirmed_recoverable_monthly, c)} tone="positive"
              hint="Only this figure changes your contribution" />
      </div>

      {confirmUsage.error ? <ErrorState error={confirmUsage.error} /> : null}
      {decide.error ? <ErrorState error={decide.error} /> : null}

      <div className="stack" style={{ marginTop: 24 }}>
        {d.items.map((f) => (
          <article key={f.id} className="card">
            <div className="row row--between row--baseline">
              <div>
                <h2 className="display-4">{f.merchant}</h2>
                <p className="micro t-muted">
                  {money(f.monthly_cost, c)} / month · {money(f.annual_cost, c)} a year · {f.frequency}
                </p>
              </div>
              <div className="row" style={{ gap: 8 }}>
                <Badge tone={f.protected ? undefined : f.leak_score >= 60 ? 'warning' : 'accent'}>
                  score {f.leak_score}
                </Badge>
                {f.protected ? <Badge tone="positive">protected</Badge> : null}
              </div>
            </div>

            <p className="prose">{f.explanation}</p>

            {f.price_change ? (
              <p className="notice notice--warning">
                Price rose from {money(f.price_change.previous_amount, c)} to{' '}
                {money(f.price_change.current_amount, c)} ({f.price_change.percent_increase}%)
                from {f.price_change.first_date_of_new_price}.
              </p>
            ) : null}

            {!f.protected ? (
              <fieldset className="stack stack--sm" style={{ border: 0, padding: 0, marginTop: 16 }}>
                <legend className="micro">Have you used this service in the last 30 days?</legend>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  {USAGE_OPTIONS.map((status) => (
                    <button key={status} type="button"
                      className={f.usage_status === status ? 'chip chip--on' : 'chip'}
                      aria-pressed={f.usage_status === status}
                      disabled={confirmUsage.pending}
                      onClick={() => void confirmUsage.run(f.id, status)}>
                      {USAGE_LABELS[status] ?? status}
                    </button>
                  ))}
                </div>
                {f.usage_status === 'usage_unknown' ? (
                  <p className="micro t-muted">
                    Until you answer, SafeSpare will not call this unused and will not offer to cancel it.
                  </p>
                ) : null}
              </fieldset>
            ) : (
              <p className="micro t-muted">
                {f.protection_reason ?? 'This is an essential expense and is never recommended for cancellation.'}
              </p>
            )}

            <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              {f.recommended_actions.map((action) => (
                <button key={action} type="button"
                  className={action === 'cancel' ? 'btn btn--sm btn--danger' : 'btn btn--sm btn--ghost'}
                  disabled={decide.pending}
                  onClick={() => {
                    if (action === 'cancel') setPendingCancel(f);
                    else void decide.run(f.id, action);
                  }}>
                  {DECISION_LABELS[action] ?? action}
                </button>
              ))}
              {!f.protected && f.usage_status === 'user_confirms_not_used' ? (
                <button type="button" className="btn btn--sm btn--quiet"
                  onClick={() => void makeDraft.run(f.id)}>
                  Draft a message
                </button>
              ) : null}
              {f.decision ? <Badge tone="accent">you chose: {DECISION_LABELS[f.decision] ?? f.decision}</Badge> : null}
            </div>
          </article>
        ))}
      </div>

      <ConfirmDialog
        open={pendingCancel !== null}
        title={`Mark ${pendingCancel?.merchant ?? ''} as one to cancel?`}
        danger
        confirmLabel="Yes, plan to cancel"
        body={
          <>
            <p>
              This records your decision and adds {money(pendingCancel?.monthly_cost ?? 0, c)} a month
              to your confirmed recoverable savings.
            </p>
            <p><strong>SafeSpare will not contact the merchant and cannot cancel anything for you.</strong></p>
          </>
        }
        onCancel={() => setPendingCancel(null)}
        onConfirm={() => {
          if (pendingCancel) void decide.run(pendingCancel.id, 'cancel');
          setPendingCancel(null);
        }}
      />

      <ConfirmDialog
        open={draft !== null}
        title="Draft message"
        confirmLabel="Close"
        body={
          <>
            <p className="micro">Subject: {draft?.subject}</p>
            <pre className="prose" style={{ whiteSpace: 'pre-wrap' }}>{draft?.body}</pre>
            <p className="micro t-muted">Copy this and send it yourself. SafeSpare sends nothing.</p>
          </>
        }
        onCancel={() => setDraft(null)}
        onConfirm={() => setDraft(null)}
      />
    </div>
  );
}
