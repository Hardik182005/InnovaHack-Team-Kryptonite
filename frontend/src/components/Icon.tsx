/**
 * Icon set.
 *
 * Hand-drawn 24×24 stroke paths rather than an icon package or emoji: emoji
 * render differently on every platform, cannot inherit colour, and read as
 * unserious in a financial product. These inherit `currentColor`, scale with
 * font size, and add no network request.
 */

import { SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement> & { size?: number };

function Base({ size = 18, children, ...rest }: Props & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const Icon = {
  mic: (p: Props) => (
    <Base {...p}>
      <rect x="9" y="2.5" width="6" height="11.5" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5M8.5 21.5h7" />
    </Base>
  ),
  stop: (p: Props) => (
    <Base {...p}><rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" stroke="none" /></Base>
  ),
  check: (p: Props) => (
    <Base {...p}><path d="M4.5 12.5l5 5 10-11" /></Base>
  ),
  arrowRight: (p: Props) => (
    <Base {...p}><path d="M4 12h15m-6-6l6 6-6 6" /></Base>
  ),
  dot: (p: Props) => (
    <Base {...p}><circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" /></Base>
  ),
  circle: (p: Props) => (
    <Base {...p}><circle cx="12" cy="12" r="7" /></Base>
  ),
  spinner: (p: Props) => (
    <Base {...p}><path d="M12 3a9 9 0 1 0 9 9" /></Base>
  ),
  grid: (p: Props) => (
    <Base {...p}>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.6" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6" />
    </Base>
  ),
  chart: (p: Props) => (
    <Base {...p}><path d="M4 20V11M10 20V4M16 20v-6M21.5 20h-19" /></Base>
  ),
  shield: (p: Props) => (
    <Base {...p}><path d="M12 2.8l7.5 3.2v6c0 4.7-3.2 7.9-7.5 9.2-4.3-1.3-7.5-4.5-7.5-9.2v-6L12 2.8z" /></Base>
  ),
  coins: (p: Props) => (
    <Base {...p}>
      <ellipse cx="12" cy="6" rx="8" ry="3.2" />
      <path d="M4 6v6c0 1.8 3.6 3.2 8 3.2s8-1.4 8-3.2V6" />
      <path d="M4 12v6c0 1.8 3.6 3.2 8 3.2s8-1.4 8-3.2v-6" />
    </Base>
  ),
  radar: (p: Props) => (
    <Base {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.6" /><path d="M12 12l6.3-4.2" /></Base>
  ),
  target: (p: Props) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </Base>
  ),
  chat: (p: Props) => (
    <Base {...p}><path d="M21 11.6a8 8 0 0 1-8 8H7.4L3 22.5v-5.9A8 8 0 1 1 21 11.6z" /></Base>
  ),
  lock: (p: Props) => (
    <Base {...p}><rect x="4" y="10" width="16" height="10.5" rx="2.2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Base>
  ),
  file: (p: Props) => (
    <Base {...p}><path d="M14 2.8H7a2 2 0 0 0-2 2v14.4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.8l-5-5z" /><path d="M14 2.8v5h5" /></Base>
  ),
  upload: (p: Props) => (
    <Base {...p}><path d="M12 16V4m-5 5l5-5 5 5M4 17.5v1.5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1.5" /></Base>
  ),
  globe: (p: Props) => (
    <Base {...p}>
      <circle cx="12" cy="12" r="9" /><path d="M3 12h18" />
      <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z" />
    </Base>
  ),
  play: (p: Props) => (
    <Base {...p}><path d="M8 5.5l10 6.5-10 6.5V5.5z" fill="currentColor" stroke="none" /></Base>
  ),
  speaker: (p: Props) => (
    <Base {...p}>
      <path d="M4 9.5h3.5L12 5.5v13L7.5 14.5H4v-5z" />
      <path d="M16 9a4.5 4.5 0 0 1 0 6M18.8 6.5a8.5 8.5 0 0 1 0 11" />
    </Base>
  ),
  alert: (p: Props) => (
    <Base {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.3v.2" /></Base>
  ),
  trash: (p: Props) => (
    <Base {...p}><path d="M4 6.5h16M9.5 6.5V4.8a1.5 1.5 0 0 1 1.5-1.5h2a1.5 1.5 0 0 1 1.5 1.5v1.7" /><path d="M6.5 6.5l1 13a2 2 0 0 0 2 1.8h5a2 2 0 0 0 2-1.8l1-13" /></Base>
  ),
};

export type IconName = keyof typeof Icon;
