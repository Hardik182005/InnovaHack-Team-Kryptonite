/**
 * SafeSpare AI — application shell and routing.
 *
 * Track: FinTech — Problem Statement 2: Smart Expense & Micro-Investment Assistant.
 *
 * The visual language is the approved Perch design (see design/Perch Site.dc.html);
 * only the domain content is SafeSpare's. Every financial figure rendered here
 * arrives from the API — the frontend never calculates money.
 */

import { Suspense, lazy, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { dataSource } from './api/config';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { useI18n } from './i18n/I18nProvider';
import { activeAnalysisId } from './api/client';

const Landing = lazy(() => import('./pages/Landing'));
const Upload = lazy(() => import('./pages/Upload'));
const Processing = lazy(() => import('./pages/Processing'));
const Review = lazy(() => import('./pages/Review'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Spending = lazy(() => import('./pages/Spending'));
const SafeSpare = lazy(() => import('./pages/SafeSpare'));
const Confidence = lazy(() => import('./pages/Confidence'));
const RoundUps = lazy(() => import('./pages/RoundUps'));
const LeakRadar = lazy(() => import('./pages/LeakRadar'));
const Goals = lazy(() => import('./pages/Goals'));
const Coach = lazy(() => import('./pages/Coach'));
const Speak = lazy(() => import('./pages/Speak'));
const Privacy = lazy(() => import('./pages/Privacy'));
const NotFound = lazy(() => import('./pages/NotFound'));

/** Routes that only make sense once an analysis exists. */
const ANALYSIS_NAV = [
  { to: '/dashboard', key: 'nav.dashboard' },
  { to: '/spending', key: 'nav.spending' },
  { to: '/safe-spare', key: 'nav.safeSpare' },
  { to: '/round-ups', key: 'nav.roundUps' },
  { to: '/leak-radar', key: 'nav.leakRadar' },
  { to: '/goals', key: 'nav.goals' },
  { to: '/coach', key: 'nav.coach' },
] as const;

function Header({ hasAnalysis }: { hasAnalysis: boolean }) {
  const { t } = useI18n();
  return (
    <header className="header">
      <div className="wrap row row--between">
        <NavLink to="/" className="brand" aria-label="SafeSpare AI home">
          <span className="brand-mark" aria-hidden="true" />
          <span>SafeSpare</span>
        </NavLink>

        {hasAnalysis ? (
          <nav className="nav" aria-label="Analysis sections">
            {ANALYSIS_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => (isActive ? 'nav-link nav-link--on' : 'nav-link')}
              >
                {t(item.key)}
              </NavLink>
            ))}
          </nav>
        ) : (
          <nav className="nav" aria-label="Main">
            <NavLink to="/speak" className="nav-link">
              🎤 {t('cta.speak')}
            </NavLink>
            <a className="nav-link" href="/#how-it-works">
              How it works
            </a>
            <a className="nav-link" href="/#trust">
              Safety
            </a>
          </nav>
        )}

        <div className="row row--sm">
          <LanguageSwitcher compact />
          <NavLink to="/privacy" className="nav-link">
            {t('nav.privacy')}
          </NavLink>
          <NavLink to="/upload" className="btn btn--dark btn--sm">
            {hasAnalysis ? 'New analysis' : t('cta.analyze')}
          </NavLink>
        </div>
      </div>
    </header>
  );
}

function ModeBanner() {
  // §41: synthetic data must be visibly labelled, and it must be obvious which
  // backend the numbers came from.
  if (dataSource.mode === 'live') return null;
  return (
    <div className="mode-banner" role="status">
      <span className="mono">DEMO DATA</span> — synthetic statement, no real account is
      connected. No money is invested or moved.
    </div>
  );
}

function PageFallback() {
  return (
    <div className="wrap section" aria-busy="true" aria-live="polite">
      <div className="skeleton" style={{ height: 32, width: '40%' }} />
      <div className="stack" style={{ marginTop: 24 }}>
        <div className="skeleton" style={{ height: 120 }} />
        <div className="skeleton" style={{ height: 120 }} />
      </div>
      <span className="sr-only">Loading</span>
    </div>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="wrap">
        <p className="micro">
          SafeSpare AI — FinTech, Problem Statement 2: Smart Expense &amp; Micro-Investment
          Assistant. Recurring-payment and price-leak detection is supporting intelligence.
        </p>
        <p className="micro t-muted">
          SafeSpare never executes a real investment, transfer or cancellation, and never
          guarantees a return. Every figure is calculated from your own statement.
        </p>
      </div>
    </footer>
  );
}

export default function App() {
  const location = useLocation();
  const [hasAnalysis, setHasAnalysis] = useState<boolean>(() => Boolean(activeAnalysisId()));

  // Re-check on navigation so the nav appears as soon as an analysis exists and
  // disappears after the user deletes their data.
  useEffect(() => {
    setHasAnalysis(Boolean(activeAnalysisId()));
  }, [location.pathname]);

  // Move focus to the top on route change so keyboard and screen-reader users
  // are not left where the previous page ended (§31).
  useEffect(() => {
    const main = document.getElementById('main');
    if (main) main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <ModeBanner />
      <Header hasAnalysis={hasAnalysis} />

      <main id="main" tabIndex={-1}>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/processing" element={<Processing />} />
            <Route path="/review" element={<Review />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/spending" element={<Spending />} />
            <Route path="/safe-spare" element={<SafeSpare />} />
            <Route path="/confidence" element={<Confidence />} />
            <Route path="/round-ups" element={<RoundUps />} />
            <Route path="/leak-radar" element={<LeakRadar />} />
            <Route path="/goals" element={<Goals />} />
            <Route path="/coach" element={<Coach />} />
            <Route path="/speak" element={<Speak />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/index.html" element={<Navigate to="/" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>

      <Footer />
    </div>
  );
}
