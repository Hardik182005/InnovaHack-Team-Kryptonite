/* ============================================================================
   Presentation helpers.

   IMPORTANT: nothing here derives a financial figure. `toNumber` only parses a
   backend value so a chart library can plot it, and the formatters only choose
   a currency symbol / separator. Every amount rendered anywhere in this app
   originates from an API field (spec §3.5, §3.6).
   ========================================================================= */

import type { Category, Essentiality, Frequency, LeakDecision, ReviewStatus, UsageStatus } from '@/api/types';

/** Parse a backend Decimal (string or number) for charting. Never for maths. */
export function toNumber(value: unknown): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'string') {
    const n = Number.parseFloat(value);
    return Number.isFinite(n) ? n : 0;
  }
  return 0;
}

const CURRENCY_FALLBACK = 'USD';

/**
 * Format a backend-supplied amount. Returns an em dash when the backend
 * genuinely has no value, so `undefined` can never reach the DOM (§5).
 */
export function money(
  value: unknown,
  currency: string = CURRENCY_FALLBACK,
  opts: { signed?: boolean; decimals?: number } = {},
): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = toNumber(value);
  const decimals = opts.decimals ?? 2;
  let out: string;
  try {
    out = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || CURRENCY_FALLBACK,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(Math.abs(n));
  } catch {
    out = `${currency} ${Math.abs(n).toFixed(decimals)}`;
  }
  if (opts.signed) return `${n < 0 ? '−' : '+'}${out}`;
  return n < 0 ? `−${out}` : out;
}

/** Compact form for axis ticks. */
export function moneyShort(value: unknown, currency: string = CURRENCY_FALLBACK): string {
  const n = toNumber(value);
  const symbol = currencySymbol(currency);
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${symbol}${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${symbol}${(n / 1_000).toFixed(1)}k`;
  return `${symbol}${n.toFixed(0)}`;
}

export function currencySymbol(currency: string = CURRENCY_FALLBACK): string {
  try {
    const parts = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || CURRENCY_FALLBACK,
    }).formatToParts(0);
    return parts.find((p) => p.type === 'currency')?.value ?? '$';
  } catch {
    return '$';
  }
}

export function percent(value: unknown, decimals = 0): string {
  if (value === null || value === undefined || value === '') return '—';
  return `${toNumber(value).toFixed(decimals)}%`;
}

/** Confidence arrives as 0–1 from the engines. */
export function confidencePercent(value: unknown): string {
  if (value === null || value === undefined) return '—';
  const n = toNumber(value);
  const scaled = n <= 1 ? n * 100 : n;
  return `${Math.round(scaled)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
}

export function formatDateShort(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { month: 'short', day: '2-digit' });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Safe text: guarantees a string reaches the DOM. */
export function text(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined) return fallback;
  const s = String(value).trim();
  return s.length ? s : fallback;
}

/* -------------------------------------------------------------------------
   Enum → human label maps. Keys mirror the backend enums exactly.
   ---------------------------------------------------------------------- */

export const CATEGORY_LABELS: Record<Category, string> = {
  salary_income: 'Salary / income',
  other_income: 'Other income',
  rent_housing: 'Rent / housing',
  utilities: 'Utilities',
  groceries: 'Groceries',
  dining_delivery: 'Dining / food delivery',
  transportation: 'Transportation',
  fuel: 'Fuel',
  shopping: 'Shopping',
  entertainment: 'Entertainment',
  subscription: 'Subscription',
  software: 'Software',
  fitness: 'Fitness',
  education: 'Education',
  medical: 'Medical',
  insurance: 'Insurance',
  loan_emi: 'Loan / EMI',
  tax: 'Tax',
  childcare: 'Childcare',
  travel: 'Travel',
  savings: 'Savings',
  investment: 'Investment',
  internal_transfer: 'Internal transfer',
  cash_withdrawal: 'Cash withdrawal',
  bank_charge: 'Bank charge',
  refund_reimbursement: 'Refund / reimbursement',
  unknown: 'Unknown',
};

export const ALL_CATEGORIES = Object.keys(CATEGORY_LABELS) as Category[];

export function categoryLabel(c: Category | string | null | undefined): string {
  if (!c) return 'Unknown';
  return CATEGORY_LABELS[c as Category] ?? String(c).replace(/_/g, ' ');
}

export const ESSENTIALITY_LABELS: Record<Essentiality, string> = {
  essential: 'Essential',
  discretionary: 'Discretionary',
  unknown: 'Unclassified',
};

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  confirmed: 'Confirmed',
  likely: 'Likely',
  needs_review: 'Needs review',
};

export const FREQUENCY_LABELS: Record<Frequency, string> = {
  weekly: 'Weekly',
  biweekly: 'Every 2 weeks',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  half_yearly: 'Half-yearly',
  annual: 'Annual',
};

export const USAGE_LABELS: Record<UsageStatus, string> = {
  usage_unknown: 'Usage unknown',
  possibly_underused: 'Possibly underused',
  user_confirms_regular_use: 'You confirmed regular use',
  user_confirms_occasional_use: 'You confirmed occasional use',
  user_confirms_not_used: 'You confirmed it is not used',
  user_does_not_recognize_payment: 'You do not recognise this payment',
};

export const DECISION_LABELS: Record<LeakDecision, string> = {
  keep: 'Keep',
  review: 'Review',
  cancel: 'Cancel',
  downgrade: 'Downgrade',
  renegotiate: 'Renegotiate',
  mark_essential: 'Mark essential',
  not_mine: 'Not mine',
  review_later: 'Review later',
};

export const LEAK_BAND_LABELS: Record<string, string> = {
  low_concern: 'Low concern',
  review: 'Review',
  consider_downgrade: 'Consider downgrade or renegotiation',
  cancellation_review: 'Strong cancellation review after confirmation',
};

/** Human phrasing for `limiting_factor` values coming out of the engines. */
export const LIMITING_FACTOR_LABELS: Record<string, string> = {
  none: 'Not limited',
  safe_spare_now: 'Cash available before your next expected income',
  safe_monthly_contribution: 'Your safe monthly contribution',
  calculated_monthly_surplus: 'Your calculated monthly surplus',
  user_monthly_cap: 'The monthly cap you set',
  user_round_up_cap: 'The round-up cap you set',
  historical_round_up_total: 'The round-ups your transactions actually produced',
  monthly_cap: 'The monthly round-up cap',
  paused: 'Round-ups are paused',
  zero: 'No safely redirectable amount this period',
};

export function limitingFactorLabel(key: string | null | undefined): string {
  if (!key) return '—';
  return LIMITING_FACTOR_LABELS[key] ?? key.replace(/_/g, ' ');
}

export function stateLabel(state: string): string {
  return state
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Deterministic accent-family colour for a category slice. */
export const CHART_COLORS = [
  '#2438E0',
  '#8C9BFF',
  '#1E8A5F',
  '#D2432A',
  '#14120F',
  '#A8B4FF',
  '#8CE0B0',
  '#FFB08F',
  '#1B2BB8',
  '#C8CEFF',
];

export function chartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length] as string;
}
