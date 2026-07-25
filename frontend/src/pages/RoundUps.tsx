/** Smart Round-Up Engine — §6.8. */

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, Loading, NeedsAnalysis, SectionHead, Stat } from '../components/common';
import { useMutation, useResource } from '../hooks/useResource';
import { AppShell } from '../components/AppShell';
import { useI18n } from '../i18n/I18nProvider';
import { money, limitingFactorLabel } from '../lib/format';

const INCREMENTS = ['1.00', '2.00', '5.00'];

function exclusionReasons(lines: { eligible: boolean; reason?: string | null }[]) {
  const out: Record<string, number> = {};
  for (const line of lines ?? []) {
    if (line.eligible || !line.reason) continue;
    const key = line.reason.split(':')[0];
    out[key] = (out[key] ?? 0) + 1;
  }
  return out;
}

export default function RoundUps() {
  const { t } = useI18n();
  const analysisId = activeAnalysisId();
  const res = useResource(() => api.getRoundUps(analysisId as string), [analysisId]);
  const save = useMutation(async (patch: Record<string, unknown>) => {
    const out = await api.updateRoundUpRules(analysisId as string, patch as never);
    res.reload();
    return out;
  });

  if (!analysisId) return <NeedsAnalysis />;
  if (res.loading) return <AppShell title={t('page.roundups')}><Loading /></AppShell>;
  if (res.error) return <AppShell title={t('page.roundups')}><ErrorState error={res.error} onRetry={res.reload} /></AppShell>;
  const d = res.data;
  if (!d) return null;
  const c = d.currency;

  return (
    <AppShell title={t('page.roundups')}>
      <SectionHead
        eyebrow="Smart Round-Up Engine"
        title={t('page.roundups')}
        lede="Round-ups never exceed your Safe Spare amount, so they cannot take money your bills need."
      />

      <div className="grid grid--3">
        <Stat label="Potential round-ups" value={money(d.historical_round_up_total, c)} />
        <Stat label="Allowed this month" value={money(d.allowed_round_up_total, c)} tone="accent"
              hint={`Limited by ${limitingFactorLabel(d.limiting_factor)}`} />
        <Stat label="Eligible transactions" value={`${d.eligible_count} of ${d.eligible_count + d.excluded_count}`} />
      </div>

      <div className="notice" style={{ marginTop: 16 }} aria-live="polite">
        <p className="prose">{d.explanation}</p>
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h2 className="display-4">Rules</h2>
        <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <span className="micro">Round to nearest:</span>
          <div className="segmented" role="group" aria-label="Round-up increment">
            {INCREMENTS.map((inc) => (
              <button key={inc} type="button"
                className={String(d.rules.increment) === inc ? 'chip chip--on' : 'chip'}
                aria-pressed={String(d.rules.increment) === inc}
                onClick={() => void save.run({ increment: inc })}>
                {money(inc, c)}
              </button>
            ))}
          </div>
          <button type="button" className={d.rules.paused ? 'btn btn--sm btn--dark' : 'btn btn--sm btn--ghost'}
            onClick={() => void save.run({ paused: !d.rules.paused })}>
            {d.rules.paused ? 'Resume round-ups' : 'Pause round-ups'}
          </button>
        </div>
        {save.pending ? <p className="micro" aria-live="polite">Recalculating…</p> : null}
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2 className="display-4">Why transactions were skipped</h2>
        <ul className="stack stack--sm" style={{ listStyle: 'none', padding: 0 }}>
          {Object.entries(exclusionReasons(d.lines)).map(([reason, count]) => (
            <li key={reason} className="row row--between">
              <span>{reason.replace(/_/g, ' ')}</span>
              <span className="mono">{String(count)}</span>
            </li>
          ))}
        </ul>
        <p className="micro t-muted">
          Rent, loans, insurance, medical, tax, transfers and withdrawals are excluded by default.
        </p>
      </div>
    </AppShell>
  );
}
