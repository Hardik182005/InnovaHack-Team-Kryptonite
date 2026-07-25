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

import { LanguageSwitcher } from './components/LanguageSwitcher';
import { Icon } from './components/Icon';
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

function Header({ hasAnalysis }: { hasAnalysis: boolean }) {
  const { t } = useI18n();
  return (
    <header className="header">
      <div className="header__inner">
        <NavLink to="/" className="brand" aria-label="SafeSpare AI home">
          <span className="brand__mark" aria-hidden="true" />
          <span className="brand__name">SafeSpare</span>
        </NavLink>

        <nav className="nav" aria-label="Main">
          <NavLink to="/speak" className="nav-link">
            <Icon.mic size={15} /> {t('cta.speak')}
          </NavLink>
          <a className="nav-link" href="/#how-it-works">
            {t('section.howItWorks')}
          </a>
          <a className="nav-link" href="/#trust">
            {t('nav.safety')}
          </a>
        </nav>

        <div className="row row--sm">
          <LanguageSwitcher compact />
          <NavLink to="/privacy" className="nav-link">
            {t('nav.privacy')}
          </NavLink>
          {hasAnalysis ? (
            <NavLink to="/dashboard" className="btn btn--dark btn--sm">
              {t('nav.dashboard')}
            </NavLink>
          ) : (
            <NavLink to="/upload" className="btn btn--dark btn--sm">
              {t('cta.analyze')}
            </NavLink>
          )}
        </div>
      </div>
    </header>
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
      <div className="footer__inner">
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

/** Routes that render inside the application shell and supply their own
 *  chrome. The marketing header and footer must not double up on them. */
const APP_ROUTES = [
  '/dashboard', '/spending', '/safe-spare', '/confidence', '/round-ups',
  '/leak-radar', '/goals', '/coach', '/review', '/privacy',
];

export default function App() {
  const location = useLocation();
  const inApp = APP_ROUTES.some((r) => location.pathname.startsWith(r));
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
      {inApp ? null : <Header hasAnalysis={hasAnalysis} />}

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

      {inApp ? null : <Footer />}
    </div>
  );
}
