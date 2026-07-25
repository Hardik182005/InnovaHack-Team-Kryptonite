/**
 * Signed-in application shell: fixed left sidebar, sticky top bar, content well.
 *
 * The marketing site keeps the cream Perch identity; this surface is neutral
 * white/slate so that the figures — and only the figures — carry colour.
 */

import { ReactNode } from 'react';
import { NavLink, Link } from 'react-router-dom';

import { dataSource } from '../api/config';
import { LanguageSwitcher } from './LanguageSwitcher';
import { useI18n } from '../i18n/I18nProvider';
import type { StringKey } from '../i18n/strings';

interface NavItem {
  to: string;
  key: StringKey;
  icon: ReactNode;
}

/* Inline 16px stroke icons — no icon dependency, no network request. */
const I = {
  grid: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  chart: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round" />
    </svg>
  ),
  shield: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" strokeLinejoin="round" />
    </svg>
  ),
  coins: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
      <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  ),
  radar: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12l6-4" strokeLinecap="round" />
    </svg>
  ),
  target: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.4" fill="currentColor" />
    </svg>
  ),
  chat: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M21 12a8 8 0 01-8 8H7l-4 3v-5.5A8 8 0 1121 12z" strokeLinejoin="round" />
    </svg>
  ),
  mic: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" strokeLinecap="round" />
    </svg>
  ),
  lock: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 018 0v3" />
    </svg>
  ),
  file: (
    <svg className="sidebar__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" strokeLinejoin="round" /><path d="M14 3v5h5" />
    </svg>
  ),
};

const MAIN: NavItem[] = [
  { to: '/dashboard', key: 'nav.dashboard', icon: I.grid },
  { to: '/spending', key: 'nav.spending', icon: I.chart },
  { to: '/safe-spare', key: 'nav.safeSpare', icon: I.shield },
  { to: '/round-ups', key: 'nav.roundUps', icon: I.coins },
  { to: '/leak-radar', key: 'nav.leakRadar', icon: I.radar },
  { to: '/goals', key: 'nav.goals', icon: I.target },
];

const ASSIST: NavItem[] = [
  { to: '/coach', key: 'nav.coach', icon: I.chat },
  { to: '/speak', key: 'cta.speak', icon: I.mic },
];

const ACCOUNT: NavItem[] = [
  { to: '/review', key: 'nav.transactions', icon: I.file },
  { to: '/privacy', key: 'nav.privacy', icon: I.lock },
];

function links(items: NavItem[], t: (k: StringKey) => string) {
  return items.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      className={({ isActive }) => (isActive ? 'sidebar__link sidebar__link--on' : 'sidebar__link')}
    >
      {item.icon}
      <span>{t(item.key)}</span>
    </NavLink>
  ));
}

export function AppShell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useI18n();

  return (
    <div className="app">
      <aside className="sidebar">
        <Link to="/" className="sidebar__brand">
          <span className="sidebar__logo" aria-hidden="true">S</span>
          <span>
            <span className="sidebar__name" style={{ display: "block" }}>SafeSpare</span>
            <span className="sidebar__tag" style={{ display: "block" }}>{t('app.shortTagline')}</span>
          </span>
        </Link>

        <div className="sidebar__card">
          <div style={{ display: 'flex', gap: 11, alignItems: 'center' }}>
            <span className="sidebar__avatar" aria-hidden="true">YOU</span>
            <span style={{ minWidth: 0 }}>
              <span className="sidebar__who" style={{ display: "block" }}>{t('sidebar.thisStatement')}</span>
              <span className="sidebar__meta" style={{ display: "block" }}>{t('sidebar.synthetic')}</span>
            </span>
          </div>
          <span className="sidebar__chip sidebar__chip--ok">{t('sidebar.noMoneyMoved')}</span>
        </div>

        <nav className="sidebar__group" aria-label={t('sidebar.main')}>
          <p className="sidebar__label">{t('sidebar.main')}</p>
          {links(MAIN, t)}
        </nav>

        <nav className="sidebar__group" aria-label={t('sidebar.assist')}>
          <p className="sidebar__label">{t('sidebar.assist')}</p>
          {links(ASSIST, t)}
        </nav>

        <nav className="sidebar__group sidebar__foot" aria-label={t('sidebar.account')}>
          <p className="sidebar__label">{t('sidebar.account')}</p>
          {links(ACCOUNT, t)}
        </nav>
      </aside>

      <div className="app__main">
        <header className="topbar">
          <div style={{ minWidth: 0 }}>
            <h1 className="topbar__title">{title}</h1>
            {subtitle ? <p className="topbar__sub">{subtitle}</p> : null}
          </div>
          <div className="topbar__right">
            {actions}
            <LanguageSwitcher compact />
            {dataSource.mode !== 'live' ? (
              <span className="demo-tag">{t('sidebar.demoData')}</span>
            ) : null}
          </div>
        </header>

        <div className="app__body">{children}</div>
      </div>
    </div>
  );
}
