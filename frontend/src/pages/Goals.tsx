/** Goal simulation — §6.10. Principal and growth are always separate. */

import { FormEvent, useState } from 'react';
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { api, activeAnalysisId, storedGoal } from '../api/client';
import { Disclaimer, ErrorState, NeedsAnalysis, SectionHead, Stat } from '../components/common';
import { useMutation } from '../hooks/useResource';
import { money, moneyShort, toNumber, chartColor } from '../lib/format';
import type { Goal, SimulationResponse } from '../api/types';

const SCENARIOS = [
  { key: 'contributions_only', label: 'Contributions only (0%)', rate: '0' },
  { key: 'lower', label: 'Lower (4%)', rate: '0.04' },
  { key: 'medium', label: 'Medium (7%)', rate: '0.07' },
  { key: 'higher_volatility', label: 'Higher volatility (10%)', rate: '0.10' },
];

export default function Goals() {
  const analysisId = activeAnalysisId();
  const [goal, setGoal] = useState<Goal | null>(() => storedGoal());
  const [sim, setSim] = useState<SimulationResponse | null>(null);
  const [rate, setRate] = useState('0.07');
  const [name, setName] = useState('Emergency fund');
  const [target, setTarget] = useState('2000');
  const [months, setMonths] = useState('24');

  const create = useMutation(async (annual: string = rate) => {
    const created = await api.createGoal({
      analysis_id: analysisId as string,
      name,
      kind: 'emergency_fund',
      target_amount: target,
      target_date: new Date(Date.now() + Number.parseInt(months, 10) * 2629800000).toISOString().slice(0, 10),
      starting_principal: '0',
      include_round_ups: true,
      include_confirmed_recovered: true,
      annual_return_rate: Number.parseFloat(annual),
    });
    setGoal(created);
    return created;
  });

  const run = useMutation(async (goalId: string) => {
    const out = await api.simulateGoal(analysisId as string, goalId);
    setSim(out);
    return out;
  });

  if (!analysisId) return <NeedsAnalysis />;

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow="Goal simulation"
        title="What controlled round-ups could become"
        lede="An illustration built from your own safe contribution — not a forecast, and not an investment."
      />

      <form
        className="card"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void create.run();
        }}
      >
        <div className="grid grid--3">
          <div className="field">
            <label htmlFor="goal-name">Goal</label>
            <input id="goal-name" className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="goal-target">Target amount</label>
            <input id="goal-target" className="input" type="number" min="1" value={target}
                   onChange={(e) => setTarget(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="goal-months">Months</label>
            <input id="goal-months" className="input" type="number" min="1" max="600" value={months}
                   onChange={(e) => setMonths(e.target.value)} required />
          </div>
        </div>
        <button className="btn btn--primary" type="submit" disabled={create.pending}>
          {create.pending ? 'Creating…' : goal ? 'Update goal' : 'Create goal'}
        </button>
        {create.error ? <ErrorState error={create.error} /> : null}
      </form>

      {goal ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h2 className="display-4">Scenario</h2>
          <div className="segmented" role="group" aria-label="Illustrative return scenario">
            {SCENARIOS.map((s) => (
              <button key={s.key} type="button"
                className={rate === s.rate ? 'chip chip--on' : 'chip'}
                aria-pressed={rate === s.rate}
                onClick={() => {
                  setRate(s.rate);
                  void run.run(goal.id);
                }}>
                {s.label}
              </button>
            ))}
          </div>
          <button className="btn btn--dark" type="button" style={{ marginTop: 12 }}
                  disabled={run.pending} onClick={() => void run.run(goal.id)}>
            {run.pending ? 'Simulating…' : 'Run simulation'}
          </button>
          {run.error ? <ErrorState error={run.error} /> : null}
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

          <div className="grid grid--2" style={{ marginTop: 16 }}>
            <Stat label="Required monthly" value={money(sim.required_monthly_contribution, sim.currency)} />
            <Stat label="Your safe monthly" value={money(sim.safe_monthly_contribution, sim.currency)}
                  hint={toNumber(sim.contribution_shortfall) > 0
                    ? `Short by ${money(sim.contribution_shortfall, sim.currency)}`
                    : 'Within your safe amount'} />
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
            <Disclaimer />
          </div>
        </>
      ) : (
        <div style={{ marginTop: 24 }}><Disclaimer /></div>
      )}
    </div>
  );
}
