/** Safe Spare Engine — §6.6. Every intermediate value is shown. */

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, Loading, NeedsAnalysis, SectionHead } from '../components/common';
import { useMutation, useResource } from '../hooks/useResource';
import { AppShell } from '../components/AppShell';
import { useI18n } from '../i18n/I18nProvider';
import { money, confidencePercent, limitingFactorLabel } from '../lib/format';

export default function SafeSpare() {
  const { t } = useI18n();
  const analysisId = activeAnalysisId();
  const res = useResource(() => api.getSafeSpare(analysisId as string), [analysisId]);
  const save = useMutation(async (field: string, value: string) => {
    const out = await api.updateSafeSpareSettings(analysisId as string, { [field]: value } as never);
    res.reload();
    return out;
  });

  if (!analysisId) return <NeedsAnalysis />;
  if (res.loading) return <AppShell title={t('page.safeSpare')}><Loading /></AppShell>;
  if (res.error) return <AppShell title={t('page.safeSpare')}><ErrorState error={res.error} onRetry={res.reload} /></AppShell>;
  const d = res.data;
  if (!d) return null;
  const c = d.currency;

  const WATERFALL = [
    { label: 'Latest balance', value: d.latest_verified_balance, tone: undefined as undefined | 'warning' },
    { label: 'Expected income before next payday', value: d.expected_income },
    { label: 'Essential bills due first', value: d.upcoming_essential_outflows, tone: 'warning' as const },
    { label: 'Projected balance', value: d.projected_balance_before_next_income },
    { label: 'Safety buffer', value: d.safety_buffer, tone: 'warning' as const },
    { label: 'Volatility reserve', value: d.volatility_reserve, tone: 'warning' as const },
  ];

  return (
    <AppShell title={t('page.safeSpare')}>
      <SectionHead
        eyebrow="Safe Spare Engine"
        title="What your life can actually spare"
        lede="Ordinary round-up apps treat all spare change as investable. SafeSpare subtracts what is already spoken for first."
      />

      {d.balance_is_estimated ? (
        <p className="notice notice--warning" role="status">
          <strong>Estimated balance.</strong> Your statement did not include a running balance, so
          this uses a cash-flow estimate. Confidence is reduced accordingly.
        </p>
      ) : null}

      <div className="grid grid--2">
        <div className="card card--accent">
          <p className="micro">{t('safeSpare.now')}</p>
          <p className="display-2">{money(d.safe_spare_now, c)}</p>
          <p className="micro">
            Safe monthly contribution <strong>{money(d.safe_monthly_contribution, c)}</strong>
            {' · '}limited by {limitingFactorLabel(d.limiting_factor)}
            {' · '}confidence {confidencePercent(d.confidence)}
          </p>
          <p className="prose">{d.reason}</p>
        </div>

        <div className="card">
          <h2 className="display-4">How it was calculated</h2>
          <ul className="waterfall">
            {WATERFALL.map((row) => (
              <li key={row.label} className="row row--between">
                <span>{row.label}</span>
                <span className={row.tone ? `mono t-${row.tone}` : 'mono'}>
                  {money(row.value, c)}
                </span>
              </li>
            ))}
            <li className="row row--between" style={{ borderTop: '1px solid var(--rule)', paddingTop: 8 }}>
              <strong>Safe Spare</strong>
              <strong className="mono t-accent">{money(d.safe_spare_now, c)}</strong>
            </li>
          </ul>
          {d.next_income_date ? (
            <p className="micro t-muted">Next expected income: {d.next_income_date}</p>
          ) : null}
        </div>
      </div>

      {d.missing_inputs.length ? (
        <div className="card" style={{ marginTop: 16 }}>
          <p className="eyebrow">Missing inputs</p>
          <ul className="prose t-muted">
            {d.missing_inputs.map((m) => <li key={m}>{m.replace(/_/g, ' ')}</li>)}
          </ul>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 24 }}>
        <h2 className="display-4">Your safety settings</h2>
        <p className="prose t-muted">Tighten these and the safe amount falls immediately.</p>
        <div className="grid grid--3" style={{ marginTop: 16 }}>
          <div className="field">
            <label htmlFor="buffer">Minimum buffer ({c})</label>
            <input id="buffer" className="input" type="number" min="0" step="10"
              defaultValue={String(d.settings.user_minimum_buffer)}
              onBlur={(e) => void save.run('user_minimum_buffer', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="pct">Buffer as share of essentials</label>
            <input id="pct" className="input" type="number" min="0" max="2" step="0.05"
              defaultValue={String(d.settings.buffer_percentage)}
              onBlur={(e) => void save.run('buffer_percentage', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="cap">Monthly cap ({c}, optional)</label>
            <input id="cap" className="input" type="number" min="0" step="5"
              defaultValue={d.settings.user_monthly_cap ? String(d.settings.user_monthly_cap) : ''}
              onBlur={(e) => void save.run('user_monthly_cap', e.target.value)} />
          </div>
        </div>
        {save.pending ? <p className="micro" aria-live="polite">Recalculating…</p> : null}
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>
    </AppShell>
  );
}
