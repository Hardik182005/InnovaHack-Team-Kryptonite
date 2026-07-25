/** Landing page — §6.1. Copy is fixed by the spec. */

import { Link } from 'react-router-dom';

import { Reveal } from '../components/common';

const STAGES = [
  { n: '01', title: 'Upload', body: 'A PDF or CSV statement. Nothing is connected to your bank.' },
  { n: '02', title: 'Understand', body: 'Every transaction is categorised, with the evidence kept.' },
  { n: '03', title: 'Protect', body: 'Rent, bills and loan payments due before your next income are set aside first.' },
  { n: '04', title: 'Find safe spare money', body: 'What remains after a safety buffer and a volatility reserve.' },
  { n: '05', title: 'Simulate growth', body: 'See what controlled round-ups could become — illustratively.' },
];

const TRUST = [
  'No real investment is executed.',
  'Every financial amount comes from verified calculations.',
  'User approval is required.',
  'Uploaded files can be automatically deleted.',
  'AI explanations cannot modify calculated values.',
];

export default function Landing() {
  return (
    <>
      <section className="wrap section">
        <div className="hero-panel">
          <Reveal index={1}>
            <p className="eyebrow">
              <span className="dot" aria-hidden="true" /> FinTech · Problem Statement 2
            </p>
          </Reveal>
          <Reveal index={2}>
            <h1 className="display-1">
              Discover what you can safely save—<em>without risking tomorrow&rsquo;s bills.</em>
            </h1>
          </Reveal>
          <Reveal index={3}>
            <p className="lede">
              Upload a transaction statement. SafeSpare categorizes spending, protects essential
              expenses, identifies avoidable recurring costs and simulates how controlled
              round-ups could support your goals.
            </p>
          </Reveal>
          <Reveal index={4}>
            <div className="row" style={{ gap: 12, marginTop: 32 }}>
              <Link className="btn btn--primary btn--lg" to="/upload">
                Analyze My Spending
              </Link>
              <Link className="btn btn--ghost btn--lg" to="/upload?demo=1">
                Try Demo Statement
              </Link>
              <Link className="btn btn--quiet btn--lg" to="/speak">
                🎤 Speak your expenses
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="wrap section" id="how-it-works">
        <p className="eyebrow">How it works</p>
        <h2 className="display-3">
          Round-up apps assume spare change is always safe. SafeSpare checks first.
        </h2>
        <div className="flow">
          {STAGES.map((stage, i) => (
            <Reveal key={stage.n} index={i + 1}>
              <div className="card card--hover">
                <p className="mono t-accent">{stage.n}</p>
                <h3 className="display-4">{stage.title}</h3>
                <p className="prose t-muted">{stage.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="wrap section" id="trust">
        <div className="card card--dark">
          <p className="eyebrow">What SafeSpare will never do</p>
          <ul className="stack stack--sm" style={{ listStyle: 'none', padding: 0, marginTop: 16 }}>
            {TRUST.map((line) => (
              <li key={line} className="checkline">
                <span aria-hidden="true">✓</span> {line}
              </li>
            ))}
          </ul>
          <p className="disclaimer disclaimer--on-dark" style={{ marginTop: 24 }}>
            SafeSpare analyzes transaction history, protects essential obligations, identifies
            safely redirectable spending, applies controlled round-ups and simulates how confirmed
            savings could support financial goals. It is not a licensed financial adviser.
          </p>
        </div>
      </section>
    </>
  );
}
