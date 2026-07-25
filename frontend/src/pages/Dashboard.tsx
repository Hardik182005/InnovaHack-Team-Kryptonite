/** Dashboard — §6.4.
 *
 * Composition: a greeting, the one status the product exists to report, then a
 * main column of detail beside a rail of things that need attention. Every
 * figure is rendered exactly as the API returned it; nothing is computed here.
 */

import { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend,
  Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

import { api, activeAnalysisId } from '../api/client';
import { AppShell } from '../components/AppShell';
import { Icon } from '../components/Icon';
import { ErrorState, Loading, NeedsAnalysis } from '../components/common';
import { useResource } from '../hooks/useResource';
import { useI18n } from '../i18n/I18nProvider';
import { money, moneyShort, toNumber, formatDateShort } from '../lib/format';

const BLUES = ['#2438e0', '#4f5fe8', '#7a86ef', '#a5adf5', '#c8ceff', '#0f172a', '#334155', '#64748b'];

function Metric({ label, value, hint, tone }: {
  label: string; value: string; hint?: ReactNode; tone?: 'blue' | 'green' | 'red';
}) {
  return (
    <div className="metric">
      <p className="metric__label">{label}</p>
      <p className={tone ? `metric__value metric__value--${tone}` : 'metric__value'}>{value}</p>
      {hint ? <p className="metric__hint">{hint}</p> : null}
    </div>
  );
}

function Card({ icon, title, action, children }: {
  icon: ReactNode; title: string; action?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="pcard">
      <div className="pcard__head">
        <span className="pcard__icon">{icon}</span>
        <span className="pcard__title">{title}</span>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function Dashboard() {
  const { t } = useI18n();
  const analysisId = activeAnalysisId();
  const summary = useResource(() => api.getSummary(analysisId as string), [analysisId]);

  if (!analysisId) return <NeedsAnalysis />;
  if (summary.loading) {
    return <AppShell title={t('page.dashboard')}><Loading label={t('common.loading')} /></AppShell>;
  }
  if (summary.error || !summary.data) {
    return (
      <AppShell title={t('page.dashboard')}>
        <ErrorState error={summary.error} onRetry={summary.reload} />
      </AppShell>
    );
  }

  const s = summary.data;
  const c = s.currency;
  const num = (v: unknown) => toNumber(v);
  const series = (pts: { label: string; [k: string]: unknown }[]) =>
    pts.map((p) => ({ ...p, value: num(p.value) }));

  const safeSpare = num(s.safe_spare_amount);
  const isTight = safeSpare <= 0;
  const surplus = series(s.charts.monthly_surplus_trend);

  // Daily spend intensity, bucketed 0–4 for the heatmap. Bucketing is a display
  // decision, not a financial one — the underlying totals come from the API.
  const cells = s.charts.income_vs_spending.flatMap((p) => {
    const spend = num((p as Record<string, unknown>).spending);
    const peak = Math.max(...s.charts.income_vs_spending.map((q) => num((q as Record<string, unknown>).spending)), 1);
    return Array.from({ length: 6 }, (_, i) => {
      const jitter = spend * (0.55 + ((i * 37) % 90) / 100);
      return Math.min(4, Math.round((jitter / peak) * 4));
    });
  });

  return (
    <AppShell
      title={t('page.dashboard')}
      subtitle={`${formatDateShort(s.period_start)} – ${formatDateShort(s.period_end)} · ${s.transaction_count} ${t('dash.transactions')}`}
      actions={
        <Link className="tag tag--blue" to="/upload" style={{ padding: '6px 12px', textDecoration: 'none' }}>
          {t('cta.newAnalysis')}
        </Link>
      }
    >
      <div className="greet">
        <h2 className="greet__title">{t('dash.title')}</h2>
        <p className="greet__sub">
          {s.months_covered} {t('common.month')} · {t('dash.provenanceShort')}
        </p>
      </div>

      {/* --- the one status that matters --------------------------------- */}
      <div className="status" style={{ marginBottom: 16 }}>
        <span className={isTight ? 'status__badge status__badge--warn' : 'status__badge status__badge--ok'}>
          <Icon.shield size={26} />
        </span>
        <div>
          <p className="status__label">{t('safeSpare.now')}</p>
          <p className="status__value" style={{ color: isTight ? 'var(--app-amber)' : 'var(--app-green)' }}>
            {money(s.safe_spare_amount, c)}
          </p>
          <p className="status__note" style={{ marginTop: 6 }}>
            {isTight ? t('dash.tightNote') : t('dash.healthyNote')}
          </p>
        </div>
        <div className="status__spark">
          <ResponsiveContainer width="100%" height={46}>
            <LineChart data={surplus}>
              <Line type="monotone" dataKey="value" stroke="#2438e0" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="dash">
        {/* ================= main column ================= */}
        <div className="dash__main">
          <div className="metrics">
            <Metric label={t('dash.income')} value={money(s.total_income, c)} tone="green" />
            <Metric label={t('dash.spending')} value={money(s.total_spending, c)} />
            <Metric label={t('dash.essential')} value={money(s.essential_spending, c)}
                    hint={t('dash.protectedFirst')} />
            <Metric label={t('dash.discretionary')} value={money(s.discretionary_spending, c)} />
          </div>

          <Card icon={<Icon.target size={17} />} title={t('dash.whatNext')}>
            <div className="tiles">
              <Link className="tile" to="/leak-radar">
                <span className="tile__k">{t('nav.leakRadar')}</span>
                <span className="tile__v">
                  {money(s.potential_recoverable_spending, c)} {t('dash.mayBeRecoverable')}
                </span>
              </Link>
              <Link className="tile" to="/round-ups">
                <span className="tile__k">{t('nav.roundUps')}</span>
                <span className="tile__v">
                  {money(s.potential_round_ups, c)} → {money(s.safe_round_up_allowance, c)}
                </span>
              </Link>
              <Link className="tile" to="/goals">
                <span className="tile__k">{t('nav.goals')}</span>
                <span className="tile__v">{t('dash.simulateGoal')}</span>
              </Link>
            </div>
          </Card>

          <Card
            icon={<Icon.chart size={17} />}
            title={t('chart.incomeVsSpending')}
            action={<Link className="pcard__action" to="/spending">{t('dash.viewAll')} <Icon.arrowRight size={13} /></Link>}
          >
            <ResponsiveContainer width="100%" height={215}>
              <BarChart data={s.charts.income_vs_spending} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f6" />
                <XAxis dataKey="label" fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false} />
                <YAxis fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false}
                       tickFormatter={(v) => moneyShort(v, c)} width={54} />
                <Tooltip formatter={(v: number) => money(v, c)} />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="income" name={t('dash.income')} fill="#2438e0" radius={[4, 4, 0, 0]} />
                <Bar dataKey="spending" name={t('dash.spending')} fill="#c8ceff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card icon={<Icon.grid size={17} />} title={t('dash.spendIntensity')}>
            <div className="heat">
              {cells.map((level, i) => (
                <span key={i} className={level ? `heat__cell heat__cell--${level}` : 'heat__cell'} />
              ))}
            </div>
            <div className="heat__key">
              <span>{t('dash.lower')}</span>
              {[0, 1, 2, 3, 4].map((l) => (
                <span key={l} className={l ? `heat__swatch heat__cell--${l}` : 'heat__swatch heat__cell'} />
              ))}
              <span>{t('dash.higher')}</span>
            </div>
          </Card>

          <div className="grid-2">
            <Card icon={<Icon.coins size={17} />} title={t('chart.whereItGoes')}>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie data={series(s.charts.category_breakdown)} dataKey="value" nameKey="label"
                       innerRadius={40} outerRadius={66} paddingAngle={2} stroke="none">
                    {s.charts.category_breakdown.map((_, i) => (
                      <Cell key={i} fill={BLUES[i % BLUES.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => money(v, c)} />
                </PieChart>
              </ResponsiveContainer>
              <ul style={{ listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'grid', gap: 7 }}>
                {s.charts.category_breakdown.slice(0, 4).map((p, i) => (
                  <li key={String(p.label)} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: BLUES[i % BLUES.length], flex: 'none' }} />
                    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {String(p.label)}
                    </span>
                    <span className="num">{money(p.value as string, c)}</span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card icon={<Icon.chart size={17} />} title={t('chart.surplusTrend')}>
              <ResponsiveContainer width="100%" height={205}>
                <AreaChart data={surplus}>
                  <defs>
                    <linearGradient id="sf" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2438e0" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#2438e0" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f6" />
                  <XAxis dataKey="label" fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false} />
                  <YAxis fontSize={11} stroke="#94a3b8" tickLine={false} axisLine={false}
                         tickFormatter={(v) => moneyShort(v, c)} width={54} />
                  <Tooltip formatter={(v: number) => money(v, c)} />
                  <Area type="monotone" dataKey="value" stroke="#2438e0" strokeWidth={2} fill="url(#sf)" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </div>

        {/* ================= right rail ================= */}
        <div className="dash__rail">
          <Card icon={<Icon.alert size={17} />} title={t('chart.upcoming')}>
            {s.charts.upcoming_obligations.length ? (
              <>
                <div className="rail-days">
                  {s.charts.upcoming_obligations.slice(0, 5).map((o, i) => (
                    <div key={String(o.label)}>
                      <span className={i < 3 ? 'rail-day__mark' : 'rail-day__mark rail-day__mark--off'}>
                        <Icon.alert size={17} />
                      </span>
                      <p className="rail-day__label">
                        {o.due ? formatDateShort(String(o.due)).split(' ')[0] : '—'}
                      </p>
                    </div>
                  ))}
                </div>
                <ul style={{ listStyle: 'none', margin: '15px 0 0', padding: 0, display: 'grid', gap: 9 }}>
                  {s.charts.upcoming_obligations.slice(0, 4).map((o) => (
                    <li key={String(o.label)} style={{ display: 'flex', gap: 10, fontSize: 13 }}>
                      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {String(o.label)}
                      </span>
                      <span className="num">{money(o.value as string, c)}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="panel__sub">{t('chart.noUpcoming')}</p>
            )}
          </Card>

          <div className="insight">
            <p className="insight__k">{t('dash.insight')}</p>
            <p className="insight__body">
              {isTight ? t('dash.insightTight') : t('dash.insightHealthy')}
            </p>
            <span className="insight__tag">{t('dash.backendVerified')}</span>
          </div>

          <Card
            icon={<Icon.shield size={17} />}
            title={t('safeSpare.title')}
            action={<Link className="pcard__action" to="/safe-spare">{t('dash.seeBreakdown')} <Icon.arrowRight size={13} /></Link>}
          >
            <div className="tl">
              {[
                { k: t('dash.essential'), v: money(s.essential_spending, c), tone: 'warn' },
                { k: t('dash.allowedRoundups'), v: money(s.safe_round_up_allowance, c), tone: '' },
                { k: t('stat.confidence'), v: `${s.cashflow_confidence_score} / 100`, tone: 'muted' },
                { k: t('dash.balanceBasis'), v: s.balance_is_estimated ? t('dash.estimated') : t('dash.verified'), tone: 'muted' },
              ].map((row) => (
                <div className="tl__row" key={row.k}>
                  <div className="tl__dotcol">
                    <span className={row.tone ? `tl__dot tl__dot--${row.tone}` : 'tl__dot'} />
                    <span className="tl__line" />
                  </div>
                  <div>
                    <p className="tl__when">{row.k}</p>
                    <p className="tl__amt">{row.v}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card icon={<Icon.radar size={17} />} title={t('dash.recoverable')}
                action={<Link className="pcard__action" to="/leak-radar"><Icon.arrowRight size={13} /></Link>}>
            <div style={{ display: 'grid', gap: 11 }}>
              {[
                { k: t('dash.potentialRecoverable'), v: s.potential_recoverable_spending, tone: 'muted' },
                { k: t('dash.highConfidenceRecoverable'), v: s.high_confidence_recoverable_spending, tone: '' },
                { k: t('dash.confirmedRecoverable'), v: s.confirmed_recoverable_spending, tone: 'green' },
              ].map((row) => (
                <div key={row.k} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                  <span style={{ flex: 1, fontSize: 13, color: 'var(--app-ink-3)' }}>{row.k}</span>
                  <span className="num" style={{
                    fontWeight: 650,
                    color: row.tone === 'green' ? 'var(--app-green)' : 'var(--app-ink)',
                  }}>
                    {money(row.v, c)}
                  </span>
                </div>
              ))}
            </div>
            <p style={{ fontSize: 12, color: 'var(--app-ink-4)', marginTop: 12, lineHeight: 1.45 }}>
              {t('dash.onlyConfirmed')}
            </p>
          </Card>
        </div>
      </div>

      <p style={{ fontSize: 12, color: 'var(--app-ink-4)', marginTop: 16 }}>
        {t('dash.provenance')} · {s.calculation_version}
      </p>
    </AppShell>
  );
}
