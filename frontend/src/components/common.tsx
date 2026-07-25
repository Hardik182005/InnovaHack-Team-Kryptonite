/**
 * Shared UI primitives in the Perch visual language.
 *
 * These exist so every page renders loading, empty and error states the same
 * way (§5) rather than each inventing its own.
 */

import { ReactNode, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/errors';

/** Section heading with the design's mono eyebrow above it. */
export function SectionHead({
  eyebrow,
  title,
  lede,
  aside,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
  aside?: ReactNode;
}) {
  return (
    <div className="row row--between row--baseline" style={{ marginBottom: 24 }}>
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1 className="display-3">{title}</h1>
        {lede ? <p className="lede">{lede}</p> : null}
      </div>
      {aside}
    </div>
  );
}

/** A figure with a mono label. `value` must already be formatted by the caller. */
export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'accent' | 'positive' | 'warning' | 'dark';
}) {
  return (
    <div className={tone ? `stat stat--${tone}` : 'stat'}>
      <p className="micro">{label}</p>
      <p className="figure">{value}</p>
      {hint ? <p className="micro t-muted">{hint}</p> : null}
    </div>
  );
}

export function Skeleton({ height = 120, width }: { height?: number; width?: string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

/** Full-page loading state. */
export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <Skeleton height={28} width="35%" />
      <Skeleton />
      <Skeleton />
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Error state with a retry affordance. Never shows raw backend text (§5). */
export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const api = error instanceof ApiError ? error : null;
  const message = api ? api.userMessage : 'Something went wrong. Please try again.';
  return (
    <div className="state state--error" role="alert">
      <p className="eyebrow">Something went wrong</p>
      <p className="prose">{message}</p>
      {onRetry ? (
        <button type="button" className="btn btn--dark" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

/** Empty state, used when there is genuinely nothing rather than an error. */
export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <p className="eyebrow">{title}</p>
      <p className="prose t-muted">{body}</p>
      {action}
    </div>
  );
}

/** Shown when a page needs an analysis and none exists yet. */
export function NeedsAnalysis() {
  return (
    <div className="wrap section">
      <EmptyState
        title="No analysis yet"
        body="Upload a statement or try the demo statement, and this page will fill with figures calculated from it."
        action={
          <Link className="btn btn--primary" to="/upload">
            Analyze my spending
          </Link>
        }
      />
    </div>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone?: 'accent' | 'positive' | 'warning' | 'solid';
  children: ReactNode;
}) {
  return <span className={tone ? `badge badge--${tone}` : 'badge'}>{children}</span>;
}

/** Always-visible illustrative-returns disclaimer (§6.10, §25.11). */
export function Disclaimer({ onDark }: { onDark?: boolean }) {
  return (
    <p className={onDark ? 'disclaimer disclaimer--on-dark' : 'disclaimer'}>
      Illustrative simulation only. Actual returns may be higher, lower or negative.
      SafeSpare does not invest money and does not recommend specific investments.
    </p>
  );
}

/**
 * Accessible modal with a focus trap and Escape-to-close (§31).
 * Used for destructive confirmations.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = 'Confirm',
  danger,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    if (!open) return undefined;
    const node = ref.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusable = node?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.[0]?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== 'Tab' || !focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [open, onCancel]);

  useEffect(() => {
    firstRender.current = false;
  }, []);

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-title" className="display-4">
          {title}
        </h2>
        <div className="prose">{body}</div>
        <div className="row row--end" style={{ marginTop: 24, gap: 8 }}>
          <button type="button" className="btn btn--ghost" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={danger ? 'btn btn--danger' : 'btn btn--primary'}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Reveal-on-scroll wrapper matching the design's `data-reveal` stagger. */
export function Reveal({ index = 1, children }: { index?: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    // Respect reduced-motion: show immediately rather than animating (§31).
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced || typeof IntersectionObserver === 'undefined') {
      node.style.opacity = '1';
      node.style.transform = 'none';
      return undefined;
    }
    node.style.opacity = '0';
    node.style.transform = 'translateY(16px)';
    node.style.transition =
      'opacity 620ms cubic-bezier(0.2,0.8,0.2,1), transform 620ms cubic-bezier(0.2,0.8,0.2,1)';
    node.style.transitionDelay = `${(index - 1) * 70}ms`;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            node.style.opacity = '1';
            node.style.transform = 'none';
            observer.disconnect();
          }
        });
      },
      { rootMargin: '0px 0px -12% 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [index]);

  return <div ref={ref}>{children}</div>;
}
