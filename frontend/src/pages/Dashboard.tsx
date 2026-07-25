/** Dashboard — §6.4. Every figure and chart comes from the API. */

import { Link } from 'react-router-dom';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

import { api, activeAnalysisId } from '../api/client';
import { ErrorState, Loading, NeedsAnalysis, SectionHead, Stat, Reveal } from '../components/common';
import { useResource } from '../hooks/useResource';
import { money, moneyShort, chartColor, toNumber } from '../lib/format';

export default function Dashboard() {
  const analysisId = activeAnalysisId();
  const summary = useResource(() => api.getSummary(analysisId as string), [analysisId]);

  if (!analysisId) return <NeedsAnalysis />;
  if (summary.loading) return <div className="wrap section"><Loading label="Loading dashboard" /></div>;
  if (summary.error) return <div className="wrap section"><ErrorState error={summary.error} onRetry={summary.reload} /></div>;

  const s = summary.data;
  if (!s) return null;
  const c = s.currency;

  const series = (points: typeof s.charts.income_vs_spending) =>
    points.map((p) => ({ ...p, value: toNumber((p as Record<string, unknown>).value as string) }));

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow={`${s.period_start} to ${s.period_end} · ${s.months_covered} months`}
        title="Your money, understood"
        lede="Every figure below is calculated from your statement."
      />

      <div className="grid grid--4">
        <Reveal index={1}><Stat label="Total income" value={money(s.total_income, c)} /></Reveal>
        <Reveal index={2}><Stat label="Total spending" value={money(s.total_spending, c)} /></Reveal>
        <Reveal index={3}><Stat label="Essential spending" value={money(s.essential_spending, c)} hint="Protected first" /></Reveal>
        <Reveal index={4}><Stat label="Discretionary" value={money(s.discretionary_spending, c)} /></Reveal>
      </div>

      <div className="grid grid--4" style={{ marginTop: 16 }}>
        <Stat label="Avg monthly surplus" value={money(s.average_monthly_surplus, c)} />
        <Stat label="Recurring payments" value={String(s.recurring_payment_count)} hint={money(s.recurring_spending, c)} />
        <Stat label="Potential round-ups" value={money(s.potential_round_ups, c)} />
        <Stat label="Safe round-up allowance" value={money(s.safe_round_up_allowance, c)} tone="accent" />
      </div>

      <div className="grid grid--3" style={{ marginTop: 16 }}>
        <Stat label="Safe Spare amount" value={money(s.safe_spare_amount, c)} tone="accent"
              hint={<Link to="/safe-spare">See the breakdown</Link>} />
        <Stat label="Cashflow Confidence" value={`${s.cashflow_confidence_score} / 100`}
              hint={<Link to="/confidence">Not a credit score</Link>} />
        <Stat label="Confirmed recoverable" value={money(s.confirmed_recoverable_spending, c)} tone="positive"
              hint={<Link to="/leak-radar">Leak Radar</Link>} />
      </div>

      <div className="grid grid--2" style={{ marginTop: 32 }}>
        <div className="card">
          <h2 className="display-4">Income vs spending</h2>
          <div className="chart">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={s.charts.income_vs_spending}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" fontSize={11} />
                <YAxis fontSize={11} tickFormatter={(v) => moneyShort(v, c)} />
                <Tooltip formatter={(v: number) => money(v, c)} />
                <Legend />
                <Bar dataKey="income" fill={chartColor(0)} name="Income" />
                <Bar dataKey="spending" fill={chartColor(1)} name="Spending" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h2 className="display-4">Where it goes</h2>
          <div className="chart">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={series(s.charts.category_breakdown)} dataKey="value" nameKey="label"
                     innerRadius={50} outerRadius={90} paddingAngle={2}>
                  {s.charts.category_breakdown.map((_, i) => (
                    <Cell key={i} fill={chartColor(i)} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => money(v, c)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <table className="sr-only">
            <caption>Category breakdown</caption>
            <tbody>
              {s.charts.category_breakdown.map((p) => (
                <tr key={p.label}><th scope="row">{p.label}</th><td>{money(p.value as string, c)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2 className="display-4">Monthly surplus trend</h2>
          <div className="chart">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={series(s.charts.monthly_surplus_trend)}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" fontSize={11} />
                <YAxis fontSize={11} tickFormatter={(v) => moneyShort(v, c)} />
                <Tooltip formatter={(v: number) => money(v, c)} />
                <Line type="monotone" dataKey="value" stroke={chartColor(0)} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h2 className="display-4">Bills due before your next income</h2>
          <ul className="stack stack--sm" style={{ listStyle: 'none', padding: 0 }}>
            {s.charts.upcoming_obligations.map((o) => (
              <li key={String(o.label)} className="row row--between">
                <span>{o.label}</span>
                <span className="mono">{money(o.value as string, c)} · {String(o.due ?? '')}</span>
              </li>
            ))}
          </ul>
          {s.charts.upcoming_obligations.length === 0 ? (
            <p className="prose t-muted">No essential bills detected before your next expected income.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
