/** Cashflow Confidence — §6.7. Explicitly not a credit score. */

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, Loading, NeedsAnalysis, SectionHead } from '../components/common';
import { AppShell } from '../components/AppShell';
import { useI18n } from '../i18n/I18nProvider';
import { useResource } from '../hooks/useResource';

export default function Confidence() {
  const { t } = useI18n();
  const analysisId = activeAnalysisId();
  const res = useResource(() => api.getCashflowConfidence(analysisId as string), [analysisId]);

  if (!analysisId) return <NeedsAnalysis />;
  if (res.loading) return <AppShell title={t('nav.safeSpare')}><Loading /></AppShell>;
  if (res.error) return <AppShell title={t('nav.safeSpare')}><ErrorState error={res.error} onRetry={res.reload} /></AppShell>;
  const d = res.data;
  if (!d) return null;

  return (
    <AppShell title={t('nav.safeSpare')}>
      <SectionHead
        eyebrow="Cashflow Confidence"
        title={`${d.score} out of 100`}
        lede="How predictable your income and essential spending are — and therefore how much confidence the Safe Spare figure deserves."
      />

      <p className="notice" role="note">{d.disclaimer}</p>

      <div className="stack" style={{ marginTop: 24 }}>
        {d.components.map((component) => (
          <div key={component.key} className="card">
            <div className="row row--between row--baseline">
              <h2 className="display-4">{component.label}</h2>
              <span className="mono">
                {component.weighted_points.toFixed(1)} / {component.weight_percent} pts
              </span>
            </div>
            <div className="meter" role="img"
                 aria-label={`${component.label}: ${Math.round(component.score * 100)} percent`}>
              <span style={{ width: `${Math.round(component.score * 100)}%` }} />
            </div>
            <p className="prose t-muted">{component.evidence}</p>
          </div>
        ))}
      </div>

      {d.improvement_suggestions?.length ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h2 className="display-4">What would raise this</h2>
          <ul className="prose">
            {d.improvement_suggestions.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </div>
      ) : null}
    </AppShell>
  );
}
