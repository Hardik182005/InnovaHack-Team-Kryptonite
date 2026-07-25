/** Goal simulation — §6.10. Principal and growth are always separate. */

import { FormEvent, ReactNode, useState } from 'react';
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { api, activeAnalysisId, storedGoal } from '../api/client';
import { Disclaimer, ErrorState, NeedsAnalysis, SectionHead, Stat } from '../components/common';
import { useMutation } from '../hooks/useResource';
import { AppShell } from '../components/AppShell';
import { useI18n } from '../i18n/I18nProvider';
import { money, moneyShort, toNumber, chartColor } from '../lib/format';
import type { Goal, SimulationResponse } from '../api/types';

// Labels name the *assumption*, never a promise. A scenario is an input the user
// chose, not a return the fund will deliver, and the wording has to carry that on
// its own — the disclaimer at the foot of the page is read after the number is.
const SCENARIOS = [
  { key: 'contributions_only', label: 'Contributions only — 0%', rate: '0' },
  { key: 'lower', label: 'Lower illustrative return — 4%', rate: '0.04' },
  { key: 'medium', label: 'Medium illustrative return — 7%', rate: '0.07' },
  { key: 'higher_volatility', label: 'Higher-volatility scenario — 10%', rate: '0.10' },
];

/** One line of the contribution breakdown. */
function SourceRow({ label, value, strong }: { label: string; value: ReactNode; strong?: boolean }) {
  return (
    <div className="row row--between" style={{ padding: '8px 0', borderTop: '1px solid var(--ink-07)' }}>
      <span className={strong ? 'prose' : 'prose t-muted'}>{strong ? <strong>{label}</strong> : label}</span>
      <span className="mono">{strong ? <strong>{value}</strong> : value}</span>
    </div>
  );
}

export default function Goals() {
  const { t } = useI18n();
  const analysisId = activeAnalysisId();
  const [goal, setGoal] = useState<Goal | null>(() => storedGoal());
  const [sim, setSim] = useState<SimulationResponse | null>(null);
  const [rate, setRate] = useState('0.07');
  const [name, setName] = useState('Laptop');
  // A ₹2,000 target reached the same month it is set demonstrates nothing about
  // compounding. A realistic multi-year goal is what makes the simulation legible.
  const [target, setTarget] = useState('80000');
  const [existing, setExisting] = useState('10000');
  const [months, setMonths] = useState('36');

  const create = useMutation(async (annual: string = rate) => {
    const created = await api.createGoal({
      analysis_id: analysisId as string,
      name,
      kind: 'emergency_fund',
      target_amount: target,
      target_date: new Date(Date.now() + Number.parseInt(months, 10) * 2629800000).toISOString().slice(0, 10),
      starting_principal: existing,
      include_round_ups: true,
      include_confirmed_recovered: true,
      annual_return_rate: Number.parseFloat(annual),
    });
    setGoal(created);
    return created;
  });

  // The rate is passed in rather than read from state: a scenario chip calls
  // setRate and simulates in the same handler, and state has not updated yet at
  // that point, so reading `rate` here would simulate the *previous* scenario.
  const run = useMutation(async (goalId: string, annual: string = rate) => {
    const out = await api.simulateGoal(analysisId as string, goalId, Number.parseFloat(annual));
    setSim(out);
    return out;
  });

  if (!analysisId) return <NeedsAnalysis />;

  const scenarioLabel = SCENARIOS.find((s) => s.rate === rate)?.label ?? rate;

  // The part of the monthly contribution that is neither a round-up nor a
  // confirmed recovery — headroom the Safe Spare engine allowed on top.
  const additional = sim
    ? Math.max(
        0,
        toNumber(sim.monthly_contribution) -
          toNumber(sim.round_up_contribution) -
          toNumber(sim.confirmed_recovered_amount),
      )
    : 0;
  const paused = sim !== null && toNumber(sim.monthly_contribution) <= 0;

  return (
    <AppShell title={t('page.goals')}>
      <SectionHead
        eyebrow="Goal simulation"
        title="Simulated Mutual Fund SIP Growth"
        lede="See how your safely available round-ups and confirmed savings could grow over time. This is an illustration only — no real investment is made."
      />

      <div style={{ marginBottom: 16 }}><Disclaimer /></div>

      <form
        className="card"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void create.run();
        }}
      >
        <h2 className="display-4">Goal details</h2>
        <div className="grid grid--4">
          <div className="field">
            <label htmlFor="goal-name">Goal name</label>
            <input id="goal-name" className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="goal-target">Target amount</label>
            <input id="goal-target" className="input" type="number" min="1" value={target}
                   onChange={(e) => setTarget(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="goal-existing">Existing savings</label>
            <input id="goal-existing" className="input" type="number" min="0" value={existing}
                   onChange={(e) => setExisting(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="goal-months">Simulation period (months)</label>
            <input id="goal-months" className="input" type="number" min="1" max="600" value={months}
                   onChange={(e) => setMonths(e.target.value)} required />
          </div>
        </div>
        <p className="micro t-muted" style={{ marginTop: 8 }}>
          Selected scenario: {scenarioLabel}. The monthly contribution is not an input — it comes from
          the Safe Spare engine and is shown below.
        </p>
        <button className="btn btn--primary" type="submit" disabled={create.pending} style={{ marginTop: 12 }}>
          {create.pending ? 'Creating…' : goal ? 'Update goal' : 'Create goal'}
        </button>
        {create.error ? <ErrorState error={create.error} /> : null}
      </form>

      {sim ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h2 className="display-4">Your safe monthly contribution</h2>
          <div style={{ marginTop: 8 }}>
            <SourceRow label="Allowed round-ups" value={money(sim.round_up_contribution, sim.currency)} />
            <SourceRow label="Confirmed subscription savings"
                       value={money(sim.confirmed_recovered_amount, sim.currency)} />
            <SourceRow label="Additional safe contribution" value={money(additional, sim.currency)} />
            <SourceRow label="Total simulated SIP"
                       value={`${money(sim.monthly_contribution, sim.currency)}/month`} strong />
          </div>
          <p className="micro t-muted" style={{ marginTop: 10 }}>
            The total is capped by your Safe Spare Amount, so money required for bills is never included.
          </p>
        </div>
      ) : null}

      {goal ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h2 className="display-4">Illustrative return scenario</h2>
          <div className="segmented" role="group" aria-label="Illustrative return scenario">
            {SCENARIOS.map((s) => (
              <button key={s.key} type="button"
                className={rate === s.rate ? 'chip chip--on' : 'chip'}
                aria-pressed={rate === s.rate}
                onClick={() => {
                  setRate(s.rate);
                  void run.run(goal.id, s.rate);
                }}>
                {s.label}
              </button>
            ))}
          </div>
          <p className="micro t-muted" style={{ marginTop: 8 }}>
            Each scenario is an assumption you chose, not a return any fund guarantees.
          </p>
          <button className="btn btn--dark" type="button" style={{ marginTop: 12 }}
                  disabled={run.pending} onClick={() => void run.run(goal.id)}>
            {run.pending ? 'Simulating…' : 'Run simulation'}
          </button>
          {run.error ? <ErrorState error={run.error} /> : null}
        </div>
      ) : null}

      {paused ? (
        <div className="state" style={{ marginTop: 16 }}>
          <p className="eyebrow">Simulation paused for safety</p>
          <p className="prose t-muted">
            This statement gives a safe monthly contribution of {money(sim?.monthly_contribution ?? '0', sim?.currency)},
            so SafeSpare will not simulate a SIP from it. That is usually because outflows over the period
            matched or exceeded income — the monthly contribution is capped by your average monthly surplus,
            not by today&rsquo;s balance, so a healthy balance can still yield zero. Check the Safe Spare page for
            the limiting factor, review unknown transactions, or use the synthetic demo statement to see a
            complete example.
          </p>
        </div>
      ) : null}

      {sim ? (
        <>
          <div className="grid grid--4" style={{ marginTop: 16 }}>
            <Stat label="Your contributions" value={money(sim.user_contributions, sim.currency)} tone="accent" />
            <Stat label="Illustrative growth" value={money(sim.illustrative_growth, sim.currency)} tone="positive" />
            <Stat label="Projected value" value={money(sim.projected_value, sim.currency)} />
            <Stat label="Gap to target" value={money(sim.goal_gap, sim.currency)}
                  tone={toNumber(sim.goal_gap) > 0 ? 'warning' : 'positive'} />
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <h2 className="display-4">Principal vs illustrative growth</h2>
            <div className="chart">
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={(sim.timeline ?? []).map((p) => ({
                  month: p.month,
                  contributions: toNumber(p.user_contributions),
                  growth: toNumber(p.illustrative_growth),
                }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" fontSize={11} />
                  <YAxis fontSize={11} tickFormatter={(v) => moneyShort(v, sim.currency)} />
                  <Tooltip formatter={(v: number) => money(v, sim.currency)} />
                  <Legend />
                  <Area type="monotone" dataKey="contributions" stackId="1"
                        stroke={chartColor(0)} fill={chartColor(0)} name="Your contributions" />
                  <Area type="monotone" dataKey="growth" stackId="1"
                        stroke={chartColor(2)} fill={chartColor(2)} name="Illustrative growth" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <h2 className="display-4">Estimated goal completion</h2>
            <p className="prose">
              {sim.estimated_completion_months !== null ? (
                <>
                  At your current safe contribution of {money(sim.monthly_contribution, sim.currency)} per month,
                  you may reach your {money(goal?.target_amount ?? '0', sim.currency)} goal in approximately{' '}
                  <strong>{sim.estimated_completion_months} months</strong>
                  {sim.estimated_completion_date ? ` (around ${sim.estimated_completion_date})` : ''} under the
                  selected illustrative scenario.
                </>
              ) : (
                <>
                  At your current safe contribution this goal is not reached within the simulated period. The
                  safe answer is a longer horizon, not a larger contribution.
                </>
              )}
            </p>
            <div className="grid grid--3" style={{ marginTop: 12 }}>
              <Stat label="Required monthly" value={money(sim.required_monthly_contribution, sim.currency)} />
              <Stat label="Your safe monthly" value={money(sim.monthly_contribution, sim.currency)} />
              <Stat label="Shortfall" value={money(sim.contribution_shortfall, sim.currency)}
                    tone={toNumber(sim.contribution_shortfall) > 0 ? 'warning' : 'positive'} />
            </div>
            {toNumber(sim.contribution_shortfall) > 0 ? (
              <p className="micro t-muted" style={{ marginTop: 10 }}>
                You can extend the goal date rather than investing more than SafeSpare considers affordable.
              </p>
            ) : null}
          </div>
        </>
      ) : null}

      <div style={{ marginTop: 24 }}><Disclaimer /></div>
    </AppShell>
  );
}
