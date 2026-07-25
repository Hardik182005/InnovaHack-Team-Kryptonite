/** Spending intelligence — §6.5. Insights must be specific and evidence-backed. */

import { api, activeAnalysisId } from '../api/client';
import { Badge, ErrorState, Loading, NeedsAnalysis, SectionHead } from '../components/common';
import { useResource } from '../hooks/useResource';
import { money, categoryLabel, confidencePercent } from '../lib/format';

export default function Spending() {
  const analysisId = activeAnalysisId();
  const res = useResource(() => api.getCategories(analysisId as string), [analysisId]);

  if (!analysisId) return <NeedsAnalysis />;
  if (res.loading) return <div className="wrap section"><Loading /></div>;
  if (res.error) return <div className="wrap section"><ErrorState error={res.error} onRetry={res.reload} /></div>;
  const d = res.data;
  if (!d) return null;
  const c = d.currency;

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow="Spending intelligence"
        title="Where the money actually goes"
        lede="Each category links back to the transactions behind it."
      />

      {d.insights?.length ? (
        <div className="stack stack--sm" style={{ marginBottom: 24 }}>
          {d.insights.map((insight) => (
            <div key={insight.headline} className="notice">
              <p className="eyebrow">{insight.headline}</p>
              <p className="prose">{insight.detail}</p>
              {insight.evidence_transaction_ids?.length ? (
                <p className="micro t-muted">
                  Based on {insight.evidence_transaction_ids.length} transactions in your statement.
                </p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Spending by category</caption>
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">Total</th>
              <th scope="col">Share</th>
              <th scope="col">Transactions</th>
              <th scope="col">Type</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {d.items.map((row) => (
              <tr key={row.category}>
                <th scope="row">{categoryLabel(row.category)}</th>
                <td className="mono">{money(row.total, c)}</td>
                <td className="mono">{row.percent_of_spending}%</td>
                <td className="mono">{row.transaction_count}</td>
                <td>
                  <Badge tone={row.essentiality === 'essential' ? 'positive' : undefined}>
                    {row.essentiality}
                  </Badge>
                </td>
                <td className="mono">{confidencePercent(row.confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
