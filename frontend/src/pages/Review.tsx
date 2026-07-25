/** Extraction review — §6.3. Every correction is sent to the backend, which
 * writes the audit record and recalculates downstream figures. */

import { useNavigate } from 'react-router-dom';

import { api, activeAnalysisId } from '../api/client';
import {
  ErrorState,
  Loading,
  NeedsAnalysis,
  SectionHead,
  Badge,
} from '../components/common';
import { useMutation, useResource } from '../hooks/useResource';
import { ALL_CATEGORIES, categoryLabel, money, formatDateShort, confidencePercent } from '../lib/format';
import type { Category, Transaction } from '../api/types';

export default function Review() {
  const analysisId = activeAnalysisId();
  const navigate = useNavigate();
  const page = useResource(
    () => api.getTransactions(analysisId as string),
    [analysisId],
  );

  const patch = useMutation(async (id: string, field: string, value: unknown) => {
    const result = await api.patchTransaction(analysisId as string, id, { [field]: value } as never);
    page.reload();
    return result;
  });

  const confirm = useMutation(async () => {
    const result = await api.bulkConfirm({ analysis_id: analysisId as string, confirm_all: true });
    navigate('/dashboard');
    return result;
  });

  if (!analysisId) return <NeedsAnalysis />;
  if (page.loading) return <div className="wrap section"><Loading label="Loading transactions" /></div>;
  if (page.error) return <div className="wrap section"><ErrorState error={page.error} onRetry={page.reload} /></div>;

  const data = page.data;
  if (!data) return null;

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow="Step 3 of 3"
        title="Check the extraction"
        lede="Correct anything that looks wrong before SafeSpare calculates from it. Every change is recorded and recalculates the figures."
        aside={
          <button
            className="btn btn--primary"
            type="button"
            onClick={() => void confirm.run()}
            disabled={confirm.pending}
          >
            {confirm.pending ? 'Confirming…' : 'Confirm and continue'}
          </button>
        }
      />

      <div className="row" style={{ gap: 12, marginBottom: 16 }}>
        <Badge>{data.total} transactions</Badge>
        {data.needs_review_count > 0 ? (
          <Badge tone="warning">{data.needs_review_count} need review</Badge>
        ) : null}
        {data.warning_count > 0 ? <Badge tone="warning">{data.warning_count} with warnings</Badge> : null}
        {data.excluded_count > 0 ? <Badge>{data.excluded_count} excluded</Badge> : null}
      </div>

      {patch.error ? <ErrorState error={patch.error} /> : null}

      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Extracted transactions, editable</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Description</th>
              <th scope="col">Merchant</th>
              <th scope="col">Debit</th>
              <th scope="col">Credit</th>
              <th scope="col">Balance</th>
              <th scope="col">Category</th>
              <th scope="col">Type</th>
              <th scope="col">Confidence</th>
              <th scope="col">Source</th>
              <th scope="col">Status</th>
              <th scope="col">Exclude</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((t: Transaction) => (
              <tr key={t.id} className={t.excluded ? 't-muted' : undefined}>
                <td className="mono">{formatDateShort(t.date)}</td>
                <td>{t.description}</td>
                <td>
                  <input
                    className="input input--sm"
                    defaultValue={t.normalized_merchant ?? ''}
                    aria-label={`Merchant for ${t.description}`}
                    onBlur={(e) => {
                      if (e.target.value !== (t.normalized_merchant ?? '')) {
                        void patch.run(t.id, 'normalized_merchant', e.target.value);
                      }
                    }}
                  />
                </td>
                <td className="mono">{t.debit ? money(t.debit, t.currency) : ''}</td>
                <td className="mono t-positive">{t.credit ? money(t.credit, t.currency) : ''}</td>
                <td className="mono t-muted">{t.balance ? money(t.balance, t.currency) : '—'}</td>
                <td>
                  <select
                    className="select select--sm"
                    value={t.category}
                    aria-label={`Category for ${t.description}`}
                    onChange={(e) => void patch.run(t.id, 'category', e.target.value as Category)}
                  >
                    {ALL_CATEGORIES.map((c) => (
                      <option key={c} value={c}>{categoryLabel(c)}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    className="select select--sm"
                    value={t.essentiality}
                    aria-label={`Essential or discretionary for ${t.description}`}
                    onChange={(e) => void patch.run(t.id, 'essentiality', e.target.value)}
                  >
                    <option value="essential">Essential</option>
                    <option value="discretionary">Discretionary</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </td>
                <td className="mono">{confidencePercent(t.category_confidence)}</td>
                <td className="mono t-muted">
                  {t.source_page ? `p${t.source_page}` : ''}{t.source_row ? `:${t.source_row}` : ''}
                </td>
                <td>
                  {t.user_overridden ? <Badge tone="accent">edited</Badge> : null}
                  {t.validation_warnings.length ? (
                    <Badge tone="warning">{t.validation_warnings.length} warning</Badge>
                  ) : null}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={t.excluded}
                    aria-label={`Exclude ${t.description}`}
                    onChange={(e) => void patch.run(t.id, 'excluded', e.target.checked)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
