/** Landing page — §6.1, in the approved Perch layout.
 *
 * Section order follows design/Perch Site.dc.html:
 *   hero (cream, orbit right) → stat row → dual marquee → blue panel →
 *   flow → trust → blue closing CTA.
 */

import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { CountUp } from '../components/CountUp';
import { Reveal } from '../components/common';
import { Icon } from '../components/Icon';
import { useI18n } from '../i18n/I18nProvider';

const SOURCES = [
  'HDFC', 'ICICI', 'SBI', 'Axis', 'Kotak', 'PNB', 'BoB',
  'PhonePe', 'Google Pay', 'Paytm', 'UPI', 'Swiggy', 'Zomato', 'Netflix',
];

export default function Landing() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');

  function start(e: FormEvent) {
    e.preventDefault();
    navigate('/upload');
  }

  const HANDLES = [
    { n: '01', title: t('handles.essentials'), body: t('handles.essentialsBody'), stat: t('handles.essentialsStat') },
    { n: '02', title: t('handles.leaks'), body: t('handles.leaksBody'), stat: t('handles.leaksStat') },
    { n: '03', title: t('handles.roundups'), body: t('handles.roundupsBody'), stat: t('handles.roundupsStat') },
    { n: '04', title: t('handles.decide'), body: t('handles.decideBody'), stat: t('handles.decideStat') },
  ];

  const STAGES = [
    { n: '01', title: t('flow.upload'), body: t('flow.uploadBody') },
    { n: '02', title: t('flow.understand'), body: t('flow.understandBody') },
    { n: '03', title: t('flow.protect'), body: t('flow.protectBody') },
    { n: '04', title: t('flow.find'), body: t('flow.findBody') },
    { n: '05', title: t('flow.simulate'), body: t('flow.simulateBody') },
  ];

  const TRUST = [
    t('trust.noInvest'), t('trust.verified'), t('trust.approval'),
    t('trust.delete'), t('trust.aiCannot'),
  ];

  return (
    <>
      {/* Drifting colour fields behind the hero, as in the design. */}
      <div className="blobs" aria-hidden="true">
        <span className="blob blob--a" />
        <span className="blob blob--b" />
      </div>

      {/* ---------- hero ---------- */}
      <section className="wrap hero">
        <div className="hero__grid">
          <div>
            <Reveal index={1}>
              <p className="pill">
                <span className="dot" aria-hidden="true" />
                {t('hero.badge')}
              </p>
            </Reveal>

            <Reveal index={2}>
              <h1 className="display-1 hero__headline">{t('landing.headline')}</h1>
            </Reveal>

            <Reveal index={3}>
              <p className="lede hero__lede">{t('landing.sub')}</p>
            </Reveal>

            <Reveal index={4}>
              <form className="hero__cta" onSubmit={start}>
                <label className="sr-only" htmlFor="hero-email">{t('hero.emailLabel')}</label>
                <input
                  id="hero-email"
                  className="input"
                  type="email"
                  placeholder={t('hero.emailPlaceholder')}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <button className="btn btn--primary btn--lg" type="submit">
                  {t('cta.analyze')}
                  <span className="btn__sheen" aria-hidden="true" />
                </button>
              </form>
            </Reveal>

            <Reveal index={5}>
              <p className="micro hero__note">{t('hero.note')}</p>
            </Reveal>

            <Reveal index={6}>
              <div className="row" style={{ gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
                <Link className="btn btn--ghost" to="/upload?demo=1">{t('cta.demo')}</Link>
                <Link className="btn btn--quiet" to="/speak"><Icon.mic size={16} /> {t('cta.speak')}</Link>
              </div>
            </Reveal>
          </div>

          {/* Obligations orbit the amount that survives them. Each ring
              rotates; each chip counter-rotates at the same duration so it
              travels the circle while its label stays upright — the technique
              used in design/Perch Site.dc.html. */}
          <div className="orbit" aria-hidden="true">
            <div className="orbit__stage">
            <div className="orbit__grid" />
            <div className="orbit__glow" />

            <div className="orbit__ring orbit__ring--outer">
              <span className="orbit__seat orbit__seat--n">
                <span className="orbit__chip">{t('orbit.rent')}</span>
              </span>
              <span className="orbit__seat orbit__seat--se">
                <span className="orbit__chip">{t('orbit.emi')}</span>
              </span>
              <span className="orbit__seat orbit__seat--sw">
                <span className="orbit__chip">{t('orbit.insurance')}</span>
              </span>
            </div>

            <div className="orbit__ring orbit__ring--mid">
              <span className="orbit__seat orbit__seat--ne">
                <span className="orbit__chip">{t('orbit.groceries')}</span>
              </span>
              <span className="orbit__seat orbit__seat--w">
                <span className="orbit__chip">{t('orbit.bills')}</span>
              </span>
              <span className="orbit__seat orbit__seat--s">
                <span className="orbit__chip orbit__chip--accent">{t('orbit.upi')}</span>
              </span>
            </div>

            {/* Decorative halo only — no chips, so nothing crosses the figure. */}
            <div className="orbit__ring orbit__ring--inner" />

            <div className="orbit__core">
              {/* Climbs like an ordinary round-up app's estimate, then lands
                  on what is genuinely spare. */}
              <CountUp
                className="orbit__value"
                values={[2000, 3456, 8940, 14200, 412, 0]}
                holdMs={1500}
              />
              <span className="orbit__caption">{t('hero.orbitCaption')}</span>
            </div>

            </div>

            <div className="orbit__bars">
              <div className="orbit__bar">
                <span className="mono">{t('hero.barSpare')}</span>
                <span className="orbit__track">
                  <i style={{ width: '4%' }} />
                </span>
                <CountUp className="mono" values={[0, 412]} holdMs={300} durationMs={1100} />
              </div>
              <div className="orbit__bar">
                <span className="mono">{t('hero.barCommitted')}</span>
                <span className="orbit__track orbit__track--warm">
                  <i style={{ width: '96%' }} />
                </span>
                <CountUp className="mono" values={[0, 31240]} holdMs={520} durationMs={1100} />
              </div>
            </div>
          </div>
        </div>

        <Reveal index={7}>
          <div className="statrow">
            <div className="statrow__item">
              <p className="statrow__figure">₹0</p>
              <p className="statrow__label">{t('stat.safeSpare')}</p>
            </div>
            <div className="statrow__item">
              <p className="statrow__figure">₹31,240</p>
              <p className="statrow__label">{t('stat.protected')}</p>
            </div>
            <div className="statrow__item">
              <p className="statrow__figure">17</p>
              <p className="statrow__label">{t('stat.recurring')}</p>
            </div>
            <div className="statrow__item">
              <p className="statrow__figure">78<span className="statrow__unit">/100</span></p>
              <p className="statrow__label">{t('stat.confidence')}</p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ---------- dual marquee ---------- */}
      <section className="section section--tight">
        <p className="eyebrow wrap" style={{ marginBottom: 18 }}>{t('marquee.eyebrow')}</p>
        <div className="marquee" aria-hidden="true">
          <div className="marquee__track">
            {[...SOURCES, ...SOURCES].map((name, i) => (
              <span className="marquee__item" key={`a-${name}-${i}`}>{name}</span>
            ))}
          </div>
          <div className="marquee__track marquee__track--rev">
            {[...SOURCES.slice(7), ...SOURCES.slice(0, 7), ...SOURCES].map((name, i) => (
              <span className="marquee__item marquee__item--ghost" key={`b-${name}-${i}`}>{name}</span>
            ))}
          </div>
        </div>
        <p className="micro t-muted wrap" style={{ marginTop: 16 }}>{t('marquee.note')}</p>
      </section>

      {/* ---------- blue panel: what it handles ---------- */}
      <section className="wrap section">
        <div className="hero-panel hero-panel--accent">
          <div className="hero-panel__dots" aria-hidden="true" />
          <div className="row row--between row--baseline" style={{ marginBottom: 30, gap: 20 }}>
            <h2 className="display-2" style={{ maxWidth: '17ch', margin: 0 }}>
              {t('handles.title')}
            </h2>
            <span className="mono" style={{ opacity: 0.72, fontSize: 12 }}>
              {t('handles.note')}
            </span>
          </div>

          <div className="grid grid--4">
            {HANDLES.map((h, i) => (
              <Reveal key={h.n} index={i + 1}>
                <div className="handle">
                  <p className="handle__num">{h.n}</p>
                  <h3 className="handle__title">{h.title}</h3>
                  <p className="handle__body">{h.body}</p>
                  <p className="handle__stat">{h.stat}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- how it works ---------- */}
      <section className="wrap section" id="how-it-works">
        <p className="eyebrow">{t('section.howItWorks')}</p>
        <h2 className="display-3" style={{ maxWidth: '24ch' }}>{t('section.howItWorksTitle')}</h2>
        <div className="flow" style={{ marginTop: 34 }}>
          {STAGES.map((stage, i) => (
            <Reveal key={stage.n} index={i + 1}>
              <div className="flow__step">
                <p className="flow__num">{stage.n}</p>
                <h3 className="flow__title">{stage.title}</h3>
                <p className="flow__body">{stage.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------- trust ---------- */}
      <section className="wrap section" id="trust">
        <div className="card card--dark">
          <div className="grid grid--2 grid--wide" style={{ alignItems: 'center' }}>
            <div>
              <p className="eyebrow">{t('section.neverDo')}</p>
              <ul className="stack stack--sm" style={{ listStyle: 'none', padding: 0, marginTop: 18 }}>
                {TRUST.map((line) => (
                  <li key={line} className="checkline checkline--static">
                    <Icon.check size={16} className="t-accent" />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="disclaimer disclaimer--on-dark">{t('trust.summary')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- closing blue CTA ---------- */}
      <section className="wrap section">
        <div className="hero-panel hero-panel--accent cta-panel">
          <div className="hero-panel__dots" aria-hidden="true" />
          <div>
            <h2 className="display-2" style={{ maxWidth: '16ch', margin: 0 }}>
              {t('cta.closingTitle')}
            </h2>
            <p className="lede" style={{ maxWidth: '44ch', marginTop: 16, opacity: 0.85 }}>
              {t('cta.closingBody')}
            </p>
          </div>
          <Link className="btn btn--lg cta-panel__btn" to="/upload?demo=1">
            {t('cta.demo')}
            <span className="btn__sheen" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </>
  );
}
