/**
 * A figure that counts between values.
 *
 * Used in the hero orbit to dramatise the product's argument: an ordinary
 * round-up app sees a healthy-looking spare balance, the number climbs — and
 * then it lands on ₹0, which is what SafeSpare actually reports once the
 * essentials due before payday are subtracted.
 *
 * Purely decorative. It renders no figure the backend calculated, so it can
 * never misreport one.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

/** Values are cycled in order and the sequence holds on the last one. */
export function CountUp({
  values,
  holdMs = 1500,
  durationMs = 700,
  prefix = '₹',
  className,
}: {
  values: number[];
  holdMs?: number;
  durationMs?: number;
  prefix?: string;
  className?: string;
}) {
  const [display, setDisplay] = useState(values[0] ?? 0);
  const step = useRef(0);
  const frame = useRef<number | null>(null);
  const timer = useRef<number | null>(null);

  // Callers pass an inline array literal, so `values` has a fresh identity on
  // every render. Depending on it directly meant each `setDisplay` re-ran the
  // effect and restarted the sequence — the counter froze on its first value.
  // Keying on the contents makes the dependency stable.
  const key = values.join(',');
  const steps = useMemo(() => values, [key]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced || steps.length < 2) {
      // Land straight on the final value rather than animating.
      setDisplay(steps[steps.length - 1] ?? 0);
      return undefined;
    }

    // Timer-driven rather than requestAnimationFrame. rAF does not fire in a
    // headless renderer, which made this untestable; at ~60fps the difference
    // is imperceptible for a six-step counter, and this runs anywhere.
    function tween(from: number, to: number, done: () => void) {
      const started = Date.now();
      frame.current = window.setInterval(() => {
        const p = Math.min(1, (Date.now() - started) / durationMs);
        const eased = 1 - Math.pow(1 - p, 3);   // ease-out cubic
        setDisplay(Math.round(from + (to - from) * eased));
        if (p >= 1) {
          if (frame.current) window.clearInterval(frame.current);
          done();
        }
      }, 16);
    }

    function next() {
      const from = steps[step.current];
      const upcoming = step.current + 1;
      if (upcoming >= steps.length) return;       // hold on the last value
      step.current = upcoming;
      tween(from, steps[upcoming], () => {
        timer.current = window.setTimeout(next, holdMs);
      });
    }

    timer.current = window.setTimeout(next, holdMs);
    return () => {
      if (frame.current) window.clearInterval(frame.current);
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [steps, holdMs, durationMs]);

  return (
    <span className={className}>
      {prefix}
      {display.toLocaleString('en-IN')}
    </span>
  );
}
