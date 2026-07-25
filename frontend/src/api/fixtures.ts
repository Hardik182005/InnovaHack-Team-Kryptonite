/* ============================================================================
   FIXTURE MODE — a bundled stand-in for the FastAPI backend.

   Everything in this file is DEMO DATA. It exists so the SPA is demonstrable
   and testable while the backend is being built, and so a reviewer can click
   every screen without running Python. Whenever fixtures are in use the app
   shows a persistent banner saying so; no fixture value is ever presented as a
   real analysis of a real statement.

   The arithmetic below deliberately mirrors backend/app/services/projections.py
   and safe_spare.py so that the demo stays internally consistent when the user
   changes a setting. It is the *mock backend* doing that work — the React
   components still only ever render a value handed to them by the API layer.

   The scenario reproduces the spec §2 worked example:
     historical round-ups  $48.70
     allowed               $31.00
     limited by            safe_spare_now  →  safe_monthly_contribution
   ========================================================================= */

import type {
  AnalysisStatus,
  AnalysisSummary,
  CashflowConfidenceResponse,
  CategoriesResponse,
  ChatResponse,
  DetectedDocumentMeta,
  DraftActionResponse,
  Goal,
  GoalRequest,
  LeakFinding,
  LeaksResponse,
  ProcessingStage,
  RecurringResponse,
  RoundUpLine,
  RoundUpRules,
  RoundUpsResponse,
  SafeSpareResponse,
  SafeSpareSettings,
  SeriesPoint,
  SimulationResponse,
  Transaction,
  TransactionPage,
  VoiceSummaryResponse,
} from './types';

export const FIXTURE_ANALYSIS_ID = 'demo-analysis-0001';
export const FIXTURE_CURRENCY = 'USD';
const CALC_VERSION = 'fixture-1.0.0';

const r2 = (n: number): number => Math.round(n * 100) / 100;

/* -------------------------------------------------------------------------
   Processing stages (§6.2)
   ---------------------------------------------------------------------- */

export const STAGE_DEFS: { key: string; label: string }[] = [
  { key: 'secure_upload', label: 'Secure upload' },
  { key: 'text_extraction', label: 'Text extraction' },
  { key: 'transaction_identification', label: 'Transaction identification' },
  { key: 'validation', label: 'Validation' },
  { key: 'merchant_normalization', label: 'Merchant normalization' },
  { key: 'categorization', label: 'Categorization' },
  { key: 'recurring_analysis', label: 'Recurring-payment analysis' },
  { key: 'safe_spare', label: 'Safe Spare calculation' },
  { key: 'insights', label: 'Insight generation' },
];

const STATE_BY_STAGE = [
  'EXTRACTING',
  'EXTRACTING',
  'EXTRACTING',
  'VALIDATING',
  'NORMALIZING',
  'CATEGORIZING',
  'DETECTING_RECURRING',
  'CALCULATING_SAFE_SPARE',
  'GENERATING_INSIGHTS',
] as const;

/** Build a status payload for `completedStages` finished stages. */
export function fixtureStatus(completedStages: number): AnalysisStatus {
  const total = STAGE_DEFS.length;
  const done = Math.max(0, Math.min(total, completedStages));
  const stages: ProcessingStage[] = STAGE_DEFS.map((s, i) => ({
    key: s.key,
    label: s.label,
    state: i < done ? 'done' : i === done ? 'active' : 'pending',
    detail: null,
  }));
  const finished = done >= total;
  return {
    analysis_id: FIXTURE_ANALYSIS_ID,
    state: finished ? 'COMPLETED' : (STATE_BY_STAGE[done] ?? 'EXTRACTING'),
    progress_percent: Math.round((done / total) * 100),
    stages,
    message: finished
      ? 'Analysis complete. 48 transactions read, 12 recurring payments detected.'
      : `Working on “${STAGE_DEFS[done]?.label ?? ''}”…`,
    error_code: null,
    updated_at: new Date().toISOString(),
  };
}

export const fixtureDocumentMeta: DetectedDocumentMeta = {
  currency: 'USD',
  currency_confidence: 0.98,
  date_range_start: '2026-04-01',
  date_range_end: '2026-06-30',
  transaction_count: 48,
  pages: 6,
  parser: 'pdfplumber+layout',
  password_protected: false,
  delete_after_processing: true,
  warnings: [
    'Two rows had no running balance; the balance column is treated as partially available.',
    'One pair of rows on page 4 looks like a duplicate and is flagged for review.',
  ],
};

/* -------------------------------------------------------------------------
   Transactions (§6.3)
   Tuple order: date, description, merchant, debit, credit, balance, category,
                essentiality, catConf, page, row, status, warnings
   ---------------------------------------------------------------------- */

type TxTuple = [
  string,
  string,
  string | null,
  number | null,
  number | null,
  number | null,
  Transaction['category'],
  Transaction['essentiality'],
  number,
  number,
  number,
  Transaction['status'],
  string[],
];

const TX_ROWS: TxTuple[] = [
  ['2026-06-30', 'MERIDIAN POWER AUTOPAY 8841', 'Meridian Power', 90.12, null, 2410.88, 'utilities', 'essential', 0.97, 6, 41, 'confirmed', []],
  ['2026-06-29', 'QUIRKY BEANS CO 118', 'Quirky Beans Coffee Club', 22.0, null, 2501.0, 'subscription', 'discretionary', 0.88, 6, 40, 'confirmed', []],
  ['2026-06-28', 'NORTHLINE INS PREMIUM', 'Northline Insurance', 145.0, null, 2523.0, 'insurance', 'essential', 0.99, 6, 39, 'confirmed', []],
  ['2026-06-27', 'SQ *GOLDEN FORK BISTRO', 'Golden Fork Bistro', 41.35, null, 2668.0, 'dining_delivery', 'discretionary', 0.93, 6, 38, 'confirmed', []],
  ['2026-06-26', 'PULSEFIT GYM MEMBER 4402', 'PulseFit Gym', 49.99, null, 2709.35, 'fitness', 'discretionary', 0.95, 6, 37, 'confirmed', []],
  ['2026-06-25', 'STREAMLY SUBSCRIPTION', 'Streamly', 17.99, null, 2759.34, 'subscription', 'discretionary', 0.96, 6, 36, 'confirmed', []],
  ['2026-06-24', 'HARBOUR MART #221', 'Harbour Mart', 86.42, null, 2777.33, 'groceries', 'essential', 0.94, 5, 35, 'confirmed', []],
  ['2026-06-23', 'TRANSIT AUTHORITY TAP', 'City Transit', 6.5, null, 2863.75, 'transportation', 'discretionary', 0.91, 5, 34, 'confirmed', []],
  ['2026-06-22', 'AMZ MKTPLACE ORDER 77F', 'Amazon Marketplace', 63.18, null, 2870.25, 'shopping', 'discretionary', 0.72, 5, 33, 'likely', ['Merchant resolved by fuzzy match.']],
  ['2026-06-21', 'NIMBUS CLOUD STORAGE', 'Nimbus Cloud Storage', 9.99, null, 2933.43, 'software', 'discretionary', 0.95, 5, 32, 'confirmed', []],
  ['2026-06-21', 'VAULTBOX BACKUP PLAN', 'Vaultbox Backup', 11.99, null, 2943.42, 'software', 'discretionary', 0.95, 5, 31, 'confirmed', []],
  ['2026-06-20', 'DELIVERO ORDER 5512', 'Delivero', 28.9, null, 2955.41, 'dining_delivery', 'discretionary', 0.96, 5, 30, 'confirmed', []],
  ['2026-06-19', 'ATM WITHDRAWAL 0042', null, 80.0, null, 2984.31, 'cash_withdrawal', 'discretionary', 0.99, 5, 29, 'confirmed', []],
  ['2026-06-18', 'TONEWAVE MUSIC MONTHLY', 'Tonewave Music', 10.99, null, 3064.31, 'subscription', 'discretionary', 0.94, 4, 28, 'confirmed', []],
  ['2026-06-18', 'HARMONIC AUDIO PREMIUM', 'Harmonic Audio', 9.99, null, 3075.3, 'subscription', 'discretionary', 0.93, 4, 27, 'confirmed', []],
  ['2026-06-17', 'PETROL STOP 19', 'Petrol Stop', 47.6, null, 3085.29, 'fuel', 'discretionary', 0.92, 4, 26, 'confirmed', []],
  ['2026-06-16', 'GOLDEN FORK BISTRO', 'Golden Fork Bistro', 38.75, null, 3132.89, 'dining_delivery', 'discretionary', 0.93, 4, 25, 'confirmed', []],
  ['2026-06-16', 'GOLDEN FORK BISTRO', 'Golden Fork Bistro', 38.75, null, 3132.89, 'dining_delivery', 'discretionary', 0.93, 4, 24, 'needs_review', ['Possible duplicate of row 25 — same date, amount and merchant.']],
  ['2026-06-15', 'CINELOOP PLUS', 'Cineloop+', 12.99, null, 3171.64, 'entertainment', 'discretionary', 0.9, 4, 23, 'confirmed', []],
  ['2026-06-14', 'HARBOUR MART #221', 'Harbour Mart', 112.07, null, 3184.63, 'groceries', 'essential', 0.94, 4, 22, 'confirmed', []],
  ['2026-06-13', 'DR L OKONKWO CLINIC', 'Okonkwo Clinic', 48.0, null, 3296.7, 'medical', 'essential', 0.89, 4, 21, 'confirmed', []],
  ['2026-06-12', 'TRANSFER TO SAVINGS 9910', 'Own Savings Account', 200.0, null, 3344.7, 'internal_transfer', 'unknown', 0.97, 3, 20, 'confirmed', []],
  ['2026-06-11', 'UNRECOGNISED DEBIT 33XZ', null, 24.5, null, 3544.7, 'unknown', 'unknown', 0.21, 3, 19, 'needs_review', ['Description could not be resolved to a merchant.']],
  ['2026-06-10', 'DELIVERO ORDER 5477', 'Delivero', 33.4, null, 3569.2, 'dining_delivery', 'discretionary', 0.96, 3, 18, 'confirmed', []],
  ['2026-06-09', 'CITY PARKING GARAGE', 'City Parking', 14.0, null, 3602.6, 'transportation', 'discretionary', 0.88, 3, 17, 'confirmed', []],
  ['2026-06-08', 'THREADWELL APPAREL', 'Threadwell Apparel', 96.4, null, 3616.6, 'shopping', 'discretionary', 0.9, 3, 16, 'confirmed', []],
  ['2026-06-07', 'HARBOUR MART #221', 'Harbour Mart', 74.28, null, 3713.0, 'groceries', 'essential', 0.94, 3, 15, 'confirmed', []],
  ['2026-06-05', 'LEDGERLY PRO ANNUAL', 'Ledgerly Pro', 119.0, null, 3787.28, 'software', 'discretionary', 0.91, 3, 14, 'confirmed', []],
  ['2026-06-04', 'BANK MONTHLY SERVICE FEE', 'Bank charge', 4.05, null, 3906.28, 'bank_charge', 'discretionary', 0.99, 2, 13, 'confirmed', []],
  ['2026-06-03', 'CASCADE PROPERTY MGMT RENT', 'Cascade Property Mgmt', 1150.0, null, 3910.33, 'rent_housing', 'essential', 0.99, 2, 12, 'confirmed', []],
  ['2026-06-01', 'PAYROLL ACME LOGISTICS', 'Acme Logistics', null, 3200.0, 5060.33, 'salary_income', 'unknown', 0.99, 2, 11, 'confirmed', []],
  ['2026-05-29', 'MERIDIAN POWER AUTOPAY 8841', 'Meridian Power', 112.4, null, 1860.33, 'utilities', 'essential', 0.97, 2, 10, 'confirmed', []],
  ['2026-05-27', 'NORTHLINE INS PREMIUM', 'Northline Insurance', 145.0, null, 1972.73, 'insurance', 'essential', 0.99, 2, 9, 'confirmed', []],
  ['2026-05-25', 'STREAMLY SUBSCRIPTION', 'Streamly', 17.99, null, 2117.73, 'subscription', 'discretionary', 0.96, 2, 8, 'confirmed', []],
  ['2026-05-22', 'REFUND THREADWELL APPAREL', 'Threadwell Apparel', null, 42.0, 2135.72, 'refund_reimbursement', 'unknown', 0.93, 2, 7, 'confirmed', []],
  ['2026-05-18', 'PULSEFIT GYM MEMBER 4402', 'PulseFit Gym', 49.99, null, 2093.72, 'fitness', 'discretionary', 0.95, 1, 6, 'confirmed', []],
  ['2026-05-12', 'QUIRKY BEANS CO 118', 'Quirky Beans Coffee Club', 22.0, null, 2143.71, 'subscription', 'discretionary', 0.88, 1, 5, 'confirmed', []],
  ['2026-05-03', 'CASCADE PROPERTY MGMT RENT', 'Cascade Property Mgmt', 1150.0, null, 2165.71, 'rent_housing', 'essential', 0.99, 1, 4, 'confirmed', []],
  ['2026-05-01', 'PAYROLL ACME LOGISTICS', 'Acme Logistics', null, 3200.0, 3315.71, 'salary_income', 'unknown', 0.99, 1, 3, 'confirmed', []],
  ['2026-04-25', 'STREAMLY SUBSCRIPTION', 'Streamly', 15.49, null, 115.71, 'subscription', 'discretionary', 0.96, 1, 2, 'confirmed', []],
  ['2026-04-03', 'CASCADE PROPERTY MGMT RENT', 'Cascade Property Mgmt', 1150.0, null, 131.2, 'rent_housing', 'essential', 0.99, 1, 1, 'confirmed', []],
  ['2026-04-01', 'PAYROLL ACME LOGISTICS', 'Acme Logistics', null, 3200.0, 1281.2, 'salary_income', 'unknown', 0.99, 1, 0, 'confirmed', []],
];

export const fixtureTransactions: Transaction[] = TX_ROWS.map((t, i) => ({
  id: `demo-tx-${String(i + 1).padStart(3, '0')}`,
  date: t[0],
  description: t[1],
  raw_merchant: t[1],
  normalized_merchant: t[2],
  merchant_method: t[2] ? (t[11] === 'likely' ? 'fuzzy' : 'alias') : null,
  merchant_confidence: t[2] ? (t[11] === 'likely' ? 0.79 : 0.96) : 0.0,
  debit: t[3] === null ? null : t[3].toFixed(2),
  credit: t[4] === null ? null : t[4].toFixed(2),
  direction: t[4] === null ? 'debit' : 'credit',
  balance: t[5] === null ? null : t[5].toFixed(2),
  currency: FIXTURE_CURRENCY,
  category: t[6],
  category_confidence: t[8],
  category_method: t[8] > 0.5 ? 'merchant_dictionary' : 'unresolved',
  essentiality: t[7],
  source_page: t[9],
  source_row: t[10],
  parser: 'pdfplumber+layout',
  extraction_confidence: t[11] === 'needs_review' ? 0.62 : 0.98,
  validation_warnings: t[12],
  external_model_used: false,
  excluded: false,
  is_internal_transfer: t[6] === 'internal_transfer',
  is_reimbursement: t[6] === 'refund_reimbursement',
  user_overridden: false,
  status: t[11],
  reference: `REF${100000 + i * 37}`,
  duplicate_of: t[12].some((w) => w.startsWith('Possible duplicate')) ? 'demo-tx-017' : null,
}));

export function fixtureTransactionPage(items: Transaction[]): TransactionPage {
  return {
    analysis_id: FIXTURE_ANALYSIS_ID,
    items,
    total: items.length,
    page: 1,
    page_size: items.length,
    warning_count: items.filter((t) => t.validation_warnings.length > 0).length,
    needs_review_count: items.filter((t) => t.status === 'needs_review').length,
    excluded_count: items.filter((t) => t.excluded).length,
  };
}

/* -------------------------------------------------------------------------
   Dashboard summary (§6.4)
   ---------------------------------------------------------------------- */

const PRINCIPAL_VS_GROWTH: SeriesPoint[] = Array.from({ length: 12 }, (_, i) => {
  const month = i + 1;
  const rate = 0.07 / 12;
  const principal = 250 + 31 * month;
  const fv = 250 * Math.pow(1 + rate, month) + 31 * ((Math.pow(1 + rate, month) - 1) / rate);
  return {
    label: `M${month}`,
    principal: r2(principal),
    growth: r2(fv - principal),
  };
});

export const fixtureSummary: AnalysisSummary = {
  analysis_id: FIXTURE_ANALYSIS_ID,
  currency: FIXTURE_CURRENCY,
  period_start: '2026-04-01',
  period_end: '2026-06-30',
  months_covered: 3,

  total_income: '9600.00',
  total_spending: '8412.55',
  essential_spending: '5441.00',
  discretionary_spending: '2971.55',
  recurring_spending: '4617.75',
  recurring_payment_count: 12,
  average_monthly_surplus: '395.82',

  potential_round_ups: '48.70',
  safe_round_up_allowance: '31.00',
  potential_recoverable_spending: '155.85',
  confirmed_recoverable_spending: '0.00',
  high_confidence_recoverable_spending: '43.98',

  safe_spare_amount: '31.00',
  safe_spare_confidence: 0.82,
  cashflow_confidence_score: 72,

  goal_progress: {
    goal_id: 'demo-goal-001',
    goal_name: 'Emergency fund',
    target_amount: '3000.00',
    contributed_to_date: '250.00',
    percent_complete: 8.3,
  },

  charts: {
    income_vs_spending: [
      { label: 'Apr 2026', income: 3200, spending: 2761.44 },
      { label: 'May 2026', income: 3200, spending: 2854.72 },
      { label: 'Jun 2026', income: 3200, spending: 2796.39 },
    ],
    category_breakdown: [
      { label: 'Rent / housing', value: 3450.0 },
      { label: 'Groceries', value: 1062.4 },
      { label: 'Dining / food delivery', value: 684.2 },
      { label: 'Shopping', value: 611.3 },
      { label: 'Insurance', value: 435.0 },
      { label: 'Transportation', value: 402.85 },
      { label: 'Utilities', value: 397.6 },
      { label: 'Fuel', value: 288.14 },
      { label: 'Subscription', value: 268.53 },
      { label: 'Entertainment', value: 214.44 },
      { label: 'Software', value: 179.97 },
      { label: 'Cash withdrawal', value: 160.0 },
      { label: 'Fitness', value: 149.97 },
      { label: 'Medical', value: 96.0 },
      { label: 'Bank charge', value: 12.15 },
    ],
    essential_vs_discretionary: [
      { label: 'Essential', value: 5441.0 },
      { label: 'Discretionary', value: 2971.55 },
    ],
    recurring_vs_one_time: [
      { label: 'Recurring', value: 4617.75 },
      { label: 'One-time', value: 3794.8 },
    ],
    monthly_surplus_trend: [
      { label: 'Apr 2026', surplus: 438.56 },
      { label: 'May 2026', surplus: 345.28 },
      { label: 'Jun 2026', surplus: 403.61 },
    ],
    safe_spare_trend: [
      { label: 'Apr 2026', safe_spare: 64.2 },
      { label: 'May 2026', safe_spare: 12.4 },
      { label: 'Jun 2026', safe_spare: 31.0 },
    ],
    upcoming_obligations: [
      { label: 'Rent — Cascade Property Mgmt', amount: 1150.0, due: '2026-07-01' },
      { label: 'Insurance — Northline', amount: 145.0, due: '2026-06-28' },
      { label: 'Utilities — Meridian Power', amount: 90.0, due: '2026-06-30' },
    ],
    principal_vs_growth: PRINCIPAL_VS_GROWTH,
  },

  calculation_version: CALC_VERSION,
  generated_at: '2026-06-30T09:12:00Z',
};

/* -------------------------------------------------------------------------
   Categories (§6.5)
   ---------------------------------------------------------------------- */

export const fixtureCategories: CategoriesResponse = {
  analysis_id: FIXTURE_ANALYSIS_ID,
  currency: FIXTURE_CURRENCY,
  calculation_version: CALC_VERSION,
  items: [
    { category: 'rent_housing', label: 'Rent / housing', total: '3450.00', percent_of_spending: 41.0, transaction_count: 3, previous_period_total: '3450.00', change_amount: '0.00', change_percent: 0, essentiality: 'essential', confidence: 0.99, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-030', date: '2026-06-03', description: 'CASCADE PROPERTY MGMT RENT', amount: '1150.00' }] },
    { category: 'groceries', label: 'Groceries', total: '1062.40', percent_of_spending: 12.63, transaction_count: 12, previous_period_total: '1004.10', change_amount: '58.30', change_percent: 5.81, essentiality: 'essential', confidence: 0.94, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-020', date: '2026-06-14', description: 'HARBOUR MART #221', amount: '112.07' }] },
    { category: 'dining_delivery', label: 'Dining / food delivery', total: '684.20', percent_of_spending: 8.13, transaction_count: 18, previous_period_total: '512.60', change_amount: '171.60', change_percent: 33.48, essentiality: 'discretionary', confidence: 0.95, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-012', date: '2026-06-20', description: 'DELIVERO ORDER 5512', amount: '28.90' }, { transaction_id: 'demo-tx-024', date: '2026-06-10', description: 'DELIVERO ORDER 5477', amount: '33.40' }] },
    { category: 'shopping', label: 'Shopping', total: '611.30', percent_of_spending: 7.27, transaction_count: 9, previous_period_total: '702.15', change_amount: '-90.85', change_percent: -12.94, essentiality: 'discretionary', confidence: 0.86, review_status: 'likely', evidence: [{ transaction_id: 'demo-tx-026', date: '2026-06-08', description: 'THREADWELL APPAREL', amount: '96.40' }] },
    { category: 'insurance', label: 'Insurance', total: '435.00', percent_of_spending: 5.17, transaction_count: 3, previous_period_total: '435.00', change_amount: '0.00', change_percent: 0, essentiality: 'essential', confidence: 0.99, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-003', date: '2026-06-28', description: 'NORTHLINE INS PREMIUM', amount: '145.00' }] },
    { category: 'transportation', label: 'Transportation', total: '402.85', percent_of_spending: 4.79, transaction_count: 21, previous_period_total: '388.20', change_amount: '14.65', change_percent: 3.77, essentiality: 'discretionary', confidence: 0.9, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-008', date: '2026-06-23', description: 'TRANSIT AUTHORITY TAP', amount: '6.50' }] },
    { category: 'utilities', label: 'Utilities', total: '397.60', percent_of_spending: 4.73, transaction_count: 3, previous_period_total: '341.20', change_amount: '56.40', change_percent: 16.53, essentiality: 'essential', confidence: 0.97, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-001', date: '2026-06-30', description: 'MERIDIAN POWER AUTOPAY 8841', amount: '90.12' }] },
    { category: 'fuel', label: 'Fuel', total: '288.14', percent_of_spending: 3.43, transaction_count: 6, previous_period_total: '266.00', change_amount: '22.14', change_percent: 8.32, essentiality: 'discretionary', confidence: 0.92, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-016', date: '2026-06-17', description: 'PETROL STOP 19', amount: '47.60' }] },
    { category: 'subscription', label: 'Subscription', total: '268.53', percent_of_spending: 3.19, transaction_count: 12, previous_period_total: '241.44', change_amount: '27.09', change_percent: 11.22, essentiality: 'discretionary', confidence: 0.93, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-006', date: '2026-06-25', description: 'STREAMLY SUBSCRIPTION', amount: '17.99' }] },
    { category: 'entertainment', label: 'Entertainment', total: '214.44', percent_of_spending: 2.55, transaction_count: 7, previous_period_total: '198.90', change_amount: '15.54', change_percent: 7.81, essentiality: 'discretionary', confidence: 0.9, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-019', date: '2026-06-15', description: 'CINELOOP PLUS', amount: '12.99' }] },
    { category: 'software', label: 'Software', total: '179.97', percent_of_spending: 2.14, transaction_count: 7, previous_period_total: '65.94', change_amount: '114.03', change_percent: 172.93, essentiality: 'discretionary', confidence: 0.93, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-028', date: '2026-06-05', description: 'LEDGERLY PRO ANNUAL', amount: '119.00' }] },
    { category: 'cash_withdrawal', label: 'Cash withdrawal', total: '160.00', percent_of_spending: 1.9, transaction_count: 2, previous_period_total: '120.00', change_amount: '40.00', change_percent: 33.33, essentiality: 'unknown', confidence: 0.99, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-013', date: '2026-06-19', description: 'ATM WITHDRAWAL 0042', amount: '80.00' }] },
    { category: 'fitness', label: 'Fitness', total: '149.97', percent_of_spending: 1.78, transaction_count: 3, previous_period_total: '149.97', change_amount: '0.00', change_percent: 0, essentiality: 'discretionary', confidence: 0.95, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-005', date: '2026-06-26', description: 'PULSEFIT GYM MEMBER 4402', amount: '49.99' }] },
    { category: 'medical', label: 'Medical', total: '96.00', percent_of_spending: 1.14, transaction_count: 2, previous_period_total: '0.00', change_amount: '96.00', change_percent: null, essentiality: 'essential', confidence: 0.89, review_status: 'likely', evidence: [{ transaction_id: 'demo-tx-021', date: '2026-06-13', description: 'DR L OKONKWO CLINIC', amount: '48.00' }] },
    { category: 'unknown', label: 'Unknown', total: '24.50', percent_of_spending: 0.29, transaction_count: 1, previous_period_total: '0.00', change_amount: '24.50', change_percent: null, essentiality: 'unknown', confidence: 0.21, review_status: 'needs_review', evidence: [{ transaction_id: 'demo-tx-023', date: '2026-06-11', description: 'UNRECOGNISED DEBIT 33XZ', amount: '24.50' }] },
    { category: 'bank_charge', label: 'Bank charge', total: '12.15', percent_of_spending: 0.14, transaction_count: 3, previous_period_total: '12.15', change_amount: '0.00', change_percent: 0, essentiality: 'discretionary', confidence: 0.99, review_status: 'confirmed', evidence: [{ transaction_id: 'demo-tx-029', date: '2026-06-04', description: 'BANK MONTHLY SERVICE FEE', amount: '4.05' }] },
  ],
  insights: [
    {
      id: 'ins-1',
      category: 'dining_delivery',
      headline: 'Food-delivery spending rose by $171.60 across the period.',
      detail:
        'Food-delivery spending increased from $512.60 to $684.20 between the previous and current period, across 18 orders. Two orders of a similar size to your recent ones total $62.30; skipping them would release that amount toward your selected goal.',
      evidence_transaction_ids: ['demo-tx-012', 'demo-tx-024'],
      releasable_amount: '62.30',
      confidence: 0.88,
    },
    {
      id: 'ins-2',
      category: 'software',
      headline: 'Two cloud-storage services are billed in the same week.',
      detail:
        'Nimbus Cloud Storage ($9.99) and Vaultbox Backup ($11.99) were both charged on 21 June. They occupy the same service category. If one of them is redundant, $11.99 a month is recoverable — but only after you confirm which one you actually use.',
      evidence_transaction_ids: ['demo-tx-010', 'demo-tx-011'],
      releasable_amount: '11.99',
      confidence: 0.74,
    },
    {
      id: 'ins-3',
      category: 'utilities',
      headline: 'Your electricity bill varies month to month, which widens your volatility reserve.',
      detail:
        'Meridian Power billed $112.40 in May and $90.12 in June. Variable essential bills increase the volatility reserve the Safe Spare Engine holds back, which is one reason this month’s safe amount is $31.00 rather than higher.',
      evidence_transaction_ids: ['demo-tx-001', 'demo-tx-032'],
      releasable_amount: null,
      confidence: 0.81,
    },
  ],
};

/* -------------------------------------------------------------------------
   Recurring (§11, §12)
   ---------------------------------------------------------------------- */

export const fixtureRecurring: RecurringResponse = {
  analysis_id: FIXTURE_ANALYSIS_ID,
  currency: FIXTURE_CURRENCY,
  total_monthly_recurring: '1539.25',
  calculation_version: CALC_VERSION,
  items: [
    { id: 'rec-01', merchant: 'Cascade Property Mgmt', category: 'rent_housing', frequency: 'monthly', occurrence_count: 3, median_amount: '1150.00', monthly_cost: '1150.00', annual_cost: '13800.00', amount_varies: false, first_seen: '2026-04-03', last_seen: '2026-06-03', next_expected_date: '2026-07-03', confidence: 0.97, review_status: 'confirmed', essentiality: 'essential', interval_regularity: 0.99, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-030', 'demo-tx-038', 'demo-tx-041'] },
    { id: 'rec-02', merchant: 'Northline Insurance', category: 'insurance', frequency: 'monthly', occurrence_count: 3, median_amount: '145.00', monthly_cost: '145.00', annual_cost: '1740.00', amount_varies: false, first_seen: '2026-04-27', last_seen: '2026-06-28', next_expected_date: '2026-07-28', confidence: 0.96, review_status: 'confirmed', essentiality: 'essential', interval_regularity: 0.97, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-003', 'demo-tx-033'] },
    { id: 'rec-03', merchant: 'Meridian Power', category: 'utilities', frequency: 'monthly', occurrence_count: 3, median_amount: '101.26', monthly_cost: '101.26', annual_cost: '1215.12', amount_varies: true, first_seen: '2026-04-29', last_seen: '2026-06-30', next_expected_date: '2026-07-30', confidence: 0.91, review_status: 'confirmed', essentiality: 'essential', interval_regularity: 0.96, merchant_similarity: 1.0, amount_stability: 0.72, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-001', 'demo-tx-032'] },
    { id: 'rec-04', merchant: 'PulseFit Gym', category: 'fitness', frequency: 'monthly', occurrence_count: 3, median_amount: '49.99', monthly_cost: '49.99', annual_cost: '599.88', amount_varies: false, first_seen: '2026-04-18', last_seen: '2026-06-26', next_expected_date: '2026-07-26', confidence: 0.93, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.94, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-005', 'demo-tx-036'] },
    { id: 'rec-05', merchant: 'Quirky Beans Coffee Club', category: 'subscription', frequency: 'monthly', occurrence_count: 3, median_amount: '22.00', monthly_cost: '22.00', annual_cost: '264.00', amount_varies: false, first_seen: '2026-04-12', last_seen: '2026-06-29', next_expected_date: '2026-07-29', confidence: 0.89, review_status: 'likely', essentiality: 'discretionary', interval_regularity: 0.88, merchant_similarity: 0.92, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-002', 'demo-tx-037'] },
    { id: 'rec-06', merchant: 'Streamly', category: 'subscription', frequency: 'monthly', occurrence_count: 3, median_amount: '17.99', monthly_cost: '17.99', annual_cost: '215.88', amount_varies: false, first_seen: '2026-04-25', last_seen: '2026-06-25', next_expected_date: '2026-07-25', confidence: 0.95, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.99, merchant_similarity: 1.0, amount_stability: 0.86, occurrence_strength: 0.85, price_change: { previous_amount: '15.49', current_amount: '17.99', absolute_increase: '2.50', percent_increase: 16.14, first_date_of_new_price: '2026-05-25', evidence_transaction_ids: ['demo-tx-040', 'demo-tx-034', 'demo-tx-006'], confidence: 0.94 }, evidence_transaction_ids: ['demo-tx-006', 'demo-tx-034', 'demo-tx-040'] },
    { id: 'rec-07', merchant: 'Cineloop+', category: 'entertainment', frequency: 'monthly', occurrence_count: 3, median_amount: '12.99', monthly_cost: '12.99', annual_cost: '155.88', amount_varies: false, first_seen: '2026-04-15', last_seen: '2026-06-15', next_expected_date: '2026-07-15', confidence: 0.9, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.98, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-019'] },
    { id: 'rec-08', merchant: 'Vaultbox Backup', category: 'software', frequency: 'monthly', occurrence_count: 3, median_amount: '11.99', monthly_cost: '11.99', annual_cost: '143.88', amount_varies: false, first_seen: '2026-04-21', last_seen: '2026-06-21', next_expected_date: '2026-07-21', confidence: 0.92, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.99, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-011'] },
    { id: 'rec-09', merchant: 'Tonewave Music', category: 'subscription', frequency: 'monthly', occurrence_count: 3, median_amount: '10.99', monthly_cost: '10.99', annual_cost: '131.88', amount_varies: false, first_seen: '2026-04-18', last_seen: '2026-06-18', next_expected_date: '2026-07-18', confidence: 0.91, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.99, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-014'] },
    { id: 'rec-10', merchant: 'Nimbus Cloud Storage', category: 'software', frequency: 'monthly', occurrence_count: 3, median_amount: '9.99', monthly_cost: '9.99', annual_cost: '119.88', amount_varies: false, first_seen: '2026-04-21', last_seen: '2026-06-21', next_expected_date: '2026-07-21', confidence: 0.92, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.99, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-010'] },
    { id: 'rec-11', merchant: 'Harmonic Audio', category: 'subscription', frequency: 'monthly', occurrence_count: 3, median_amount: '9.99', monthly_cost: '9.99', annual_cost: '119.88', amount_varies: false, first_seen: '2026-04-18', last_seen: '2026-06-18', next_expected_date: '2026-07-18', confidence: 0.9, review_status: 'confirmed', essentiality: 'discretionary', interval_regularity: 0.99, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.85, price_change: null, evidence_transaction_ids: ['demo-tx-015'] },
    { id: 'rec-12', merchant: 'Ledgerly Pro', category: 'software', frequency: 'annual', occurrence_count: 2, median_amount: '119.00', monthly_cost: '9.92', annual_cost: '119.00', amount_varies: false, first_seen: '2025-06-05', last_seen: '2026-06-05', next_expected_date: '2027-06-05', confidence: 0.68, review_status: 'needs_review', essentiality: 'discretionary', interval_regularity: 0.95, merchant_similarity: 1.0, amount_stability: 1.0, occurrence_strength: 0.4, price_change: null, evidence_transaction_ids: ['demo-tx-028'] },
  ],
};

/* -------------------------------------------------------------------------
   Leak Radar (§6.9, §13)
   ---------------------------------------------------------------------- */

const LEAKS: LeakFinding[] = [
  {
    id: 'leak-01', merchant: 'PulseFit Gym', category: 'fitness', frequency: 'monthly',
    monthly_cost: '49.99', annual_cost: '599.88', leak_score: 64, band: 'consider_downgrade',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['review', 'downgrade', 'renegotiate', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.0, cost_burden: 0.82, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: null, price_change: null,
    evidence_transaction_ids: ['demo-tx-005', 'demo-tx-036'],
    explanation:
      'This is your largest optional recurring payment at $49.99 a month ($599.88 a year). Bank data cannot show whether you attend, so the score is capped below the cancellation tier until you confirm usage.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-02', merchant: 'Streamly', category: 'subscription', frequency: 'monthly',
    monthly_cost: '17.99', annual_cost: '215.88', leak_score: 58, band: 'review',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['review', 'renegotiate', 'downgrade', 'keep'],
    components: { price_hike_severity: 0.72, duplicate_probability: 0.0, cost_burden: 0.31, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: null,
    price_change: { previous_amount: '15.49', current_amount: '17.99', absolute_increase: '2.50', percent_increase: 16.14, first_date_of_new_price: '2026-05-25', evidence_transaction_ids: ['demo-tx-040', 'demo-tx-034'], confidence: 0.94 },
    evidence_transaction_ids: ['demo-tx-006', 'demo-tx-034', 'demo-tx-040'],
    explanation:
      'The price rose from $15.49 to $17.99 on 25 May — a 16.14% increase, verified against three payments. That is $30.00 more a year at the same service level.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-03', merchant: 'Quirky Beans Coffee Club', category: 'subscription', frequency: 'monthly',
    monthly_cost: '22.00', annual_cost: '264.00', leak_score: 55, band: 'review',
    usage_status: 'usage_unknown', review_status: 'likely', decision: null,
    recommended_actions: ['review', 'cancel', 'downgrade', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.0, cost_burden: 0.45, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: null, price_change: null,
    evidence_transaction_ids: ['demo-tx-002', 'demo-tx-037'],
    explanation:
      'A recurring optional delivery of $22.00 a month. The merchant name matched at 0.92 confidence, so this finding is marked Likely rather than Confirmed.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-04', merchant: 'Vaultbox Backup', category: 'software', frequency: 'monthly',
    monthly_cost: '11.99', annual_cost: '143.88', leak_score: 52, band: 'review',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['review', 'cancel', 'downgrade', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.78, cost_burden: 0.24, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: 'cloud-storage', price_change: null,
    evidence_transaction_ids: ['demo-tx-011'],
    explanation:
      'Overlaps with Nimbus Cloud Storage — both are cloud-storage services charged on 21 June. Only one of the two can be recovered, and only after you say which you use.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-05', merchant: 'Nimbus Cloud Storage', category: 'software', frequency: 'monthly',
    monthly_cost: '9.99', annual_cost: '119.88', leak_score: 47, band: 'review',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['review', 'cancel', 'downgrade', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.78, cost_burden: 0.2, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: 'cloud-storage', price_change: null,
    evidence_transaction_ids: ['demo-tx-010'],
    explanation: 'Overlaps with Vaultbox Backup in the cloud-storage category. Both were charged on 21 June.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-06', merchant: 'Tonewave Music', category: 'subscription', frequency: 'monthly',
    monthly_cost: '10.99', annual_cost: '131.88', leak_score: 44, band: 'review',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['review', 'cancel', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.71, cost_burden: 0.22, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: 'music-streaming', price_change: null,
    evidence_transaction_ids: ['demo-tx-014'],
    explanation: 'Overlaps with Harmonic Audio — two music services billed on the same day.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-07', merchant: 'Harmonic Audio', category: 'subscription', frequency: 'monthly',
    monthly_cost: '9.99', annual_cost: '119.88', leak_score: 41, band: 'review',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['review', 'cancel', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.71, cost_burden: 0.2, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: 'music-streaming', price_change: null,
    evidence_transaction_ids: ['demo-tx-015'],
    explanation: 'Overlaps with Tonewave Music — two music services billed on the same day.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-08', merchant: 'Cineloop+', category: 'entertainment', frequency: 'monthly',
    monthly_cost: '12.99', annual_cost: '155.88', leak_score: 33, band: 'review',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['keep', 'review'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.0, cost_burden: 0.26, recurrence_commitment: 0.9, confirmed_non_usage: 0.0 },
    duplicate_group: null, price_change: null,
    evidence_transaction_ids: ['demo-tx-019'],
    explanation: 'A steady optional subscription with no price change and no overlap detected.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-09', merchant: 'Ledgerly Pro', category: 'software', frequency: 'annual',
    monthly_cost: '9.92', annual_cost: '119.00', leak_score: 29, band: 'low_concern',
    usage_status: 'usage_unknown', review_status: 'needs_review', decision: null,
    recommended_actions: ['review_later', 'keep'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.0, cost_burden: 0.18, recurrence_commitment: 0.4, confirmed_non_usage: 0.0 },
    duplicate_group: null, price_change: null,
    evidence_transaction_ids: ['demo-tx-028'],
    explanation:
      'An annual renewal seen twice. Two occurrences is below the three-occurrence threshold for a confirmed pattern, so this stays in Needs review.',
    protected: false, protection_reason: null, calculation_version: CALC_VERSION,
  },
  {
    id: 'leak-10', merchant: 'Northline Insurance', category: 'insurance', frequency: 'monthly',
    monthly_cost: '145.00', annual_cost: '1740.00', leak_score: 0, band: 'low_concern',
    usage_status: 'usage_unknown', review_status: 'confirmed', decision: null,
    recommended_actions: ['keep', 'mark_essential'],
    components: { price_hike_severity: 0.0, duplicate_probability: 0.0, cost_burden: 0.0, recurrence_commitment: 0.0, confirmed_non_usage: 0.0 },
    duplicate_group: null, price_change: null,
    evidence_transaction_ids: ['demo-tx-003', 'demo-tx-033'],
    explanation: 'Listed for transparency only. No leak score is produced for essential obligations.',
    protected: true,
    protection_reason:
      'Insurance is protected from cancellation advice. SafeSpare never suggests cancelling rent, loans, insurance, tax, medical, utilities, education or childcare merely because they recur.',
    calculation_version: CALC_VERSION,
  },
];

/** Monthly costs of the findings whose decision counts as user-confirmed recovery. */
const CONFIRMED_DECISIONS = new Set(['cancel', 'downgrade', 'renegotiate']);

export function fixtureLeaks(state: Map<string, Partial<LeakFinding>>): LeaksResponse {
  const items = LEAKS.map((f) => {
    const patch = state.get(f.id);
    if (!patch) return f;
    return recomputeLeak({ ...f, ...patch });
  });
  let confirmed = 0;
  for (const f of items) {
    if (f.decision && CONFIRMED_DECISIONS.has(f.decision) && !f.protected) {
      confirmed += Number.parseFloat(String(f.monthly_cost));
    }
  }
  return {
    analysis_id: FIXTURE_ANALYSIS_ID,
    currency: FIXTURE_CURRENCY,
    items,
    potential_recoverable_monthly: '155.85',
    high_confidence_recoverable_monthly: '43.98',
    user_confirmed_recoverable_monthly: r2(confirmed).toFixed(2),
    calculation_version: CALC_VERSION,
  };
}

/**
 * MOCK BACKEND: re-derive the leak score after a usage confirmation, applying
 * the §13 rules — usage-unknown contributes zero and caps the score below the
 * cancellation tier; essentials can never receive cancellation advice.
 */
function recomputeLeak(f: LeakFinding): LeakFinding {
  const c = { ...f.components };
  let capped = false;
  switch (f.usage_status) {
    case 'user_confirms_not_used':
      c.confirmed_non_usage = 1.0;
      break;
    case 'user_does_not_recognize_payment':
      c.confirmed_non_usage = 0.9;
      break;
    case 'user_confirms_occasional_use':
      c.confirmed_non_usage = 0.4;
      break;
    case 'user_confirms_regular_use':
      c.confirmed_non_usage = 0.0;
      break;
    case 'possibly_underused':
      c.confirmed_non_usage = 0.0;
      capped = true;
      break;
    default:
      c.confirmed_non_usage = 0.0;
      capped = true;
  }
  let score = Math.round(
    100 *
      (0.25 * c.price_hike_severity +
        0.2 * c.duplicate_probability +
        0.15 * c.cost_burden +
        0.15 * c.recurrence_commitment +
        0.25 * c.confirmed_non_usage),
  );
  if (f.protected) score = 0;
  if (capped) score = Math.min(score, 79);

  const band: LeakFinding['band'] =
    score >= 80 ? 'cancellation_review' : score >= 60 ? 'consider_downgrade' : score >= 30 ? 'review' : 'low_concern';

  const actions: LeakFinding['recommended_actions'] = f.protected
    ? ['keep', 'mark_essential']
    : band === 'cancellation_review'
      ? ['cancel', 'downgrade', 'renegotiate', 'keep']
      : band === 'consider_downgrade'
        ? ['downgrade', 'renegotiate', 'review', 'keep']
        : band === 'review'
          ? ['review', 'downgrade', 'keep', 'review_later']
          : ['keep', 'review_later'];

  return { ...f, components: c, leak_score: score, band, recommended_actions: actions };
}

export function fixtureDraft(finding: LeakFinding, action: string): DraftActionResponse {
  const verb =
    action === 'cancel' ? 'cancel my subscription' : action === 'downgrade' ? 'move to a lower plan' : 'review my pricing';
  return {
    finding_id: finding.id,
    action,
    subject: `Request to ${verb} — ${finding.merchant}`,
    body:
      `Hello ${finding.merchant} team,\n\n` +
      `I would like to ${verb}. My records show a recurring charge of ${String(finding.monthly_cost)} ` +
      `${FIXTURE_CURRENCY} per month.\n\n` +
      (finding.price_change
        ? `I also noticed the price moved from ${String(finding.price_change.previous_amount)} to ` +
          `${String(finding.price_change.current_amount)} on ${finding.price_change.first_date_of_new_price}. ` +
          `Could you confirm what changed at that point?\n\n`
        : '') +
      `Please confirm in writing once this is actioned, along with the effective date.\n\n` +
      `Thank you,\n[Your name]`,
    generated_offline: true,
    disclaimer:
      'This is a draft for you to review and send yourself. SafeSpare never contacts a merchant or cancels anything on your behalf.',
  };
}

/* -------------------------------------------------------------------------
   Safe Spare Engine (§6.6)
   ---------------------------------------------------------------------- */

export const DEFAULT_SAFE_SPARE_SETTINGS: SafeSpareSettings = {
  user_minimum_buffer: '200.00',
  buffer_percentage: 0.25,
  volatility_multiplier: 0.5,
  user_monthly_cap: '250.00',
};

/** Fixed inputs — these come from the statement, not from the settings. */
const SS_INPUTS = {
  latest_verified_balance: 2410.88,
  expected_income: 0.0,
  upcoming_essential_outflows: 1385.0,
  average_monthly_essential_spending: 1813.67,
  outflow_stdev: 1082.92,
  calculated_monthly_surplus: 395.82,
  next_income_date: '2026-07-01',
};

/**
 * MOCK BACKEND: the §6.6 formulas, so the demo responds to settings changes.
 * Mirrors backend/app/services/safe_spare.py.
 */
export function fixtureSafeSpare(settings: SafeSpareSettings): SafeSpareResponse {
  const minBuffer = Number.parseFloat(String(settings.user_minimum_buffer)) || 0;
  const cap = settings.user_monthly_cap === null ? null : Number.parseFloat(String(settings.user_monthly_cap));

  const projected = r2(
    SS_INPUTS.latest_verified_balance + SS_INPUTS.expected_income - SS_INPUTS.upcoming_essential_outflows,
  );
  const buffer = r2(Math.max(minBuffer, settings.buffer_percentage * SS_INPUTS.average_monthly_essential_spending));
  const reserve = r2(settings.volatility_multiplier * SS_INPUTS.outflow_stdev);
  const safeNow = r2(Math.max(0, projected - buffer - reserve));

  const candidates: { value: number; key: string }[] = [
    { value: safeNow, key: 'safe_spare_now' },
    { value: SS_INPUTS.calculated_monthly_surplus, key: 'calculated_monthly_surplus' },
  ];
  if (cap !== null) candidates.push({ value: cap, key: 'user_monthly_cap' });
  candidates.sort((a, b) => a.value - b.value);
  const winner = candidates[0] as { value: number; key: string };
  const safeMonthly = r2(Math.max(0, winner.value));

  const reason =
    safeMonthly <= 0
      ? 'No amount is safely redirectable right now. Your projected balance before the next expected income does not clear your safety buffer and volatility reserve.'
      : winner.key === 'safe_spare_now'
        ? 'Limited by the cash expected to remain before your next income, after rent, insurance and utilities are paid.'
        : winner.key === 'user_monthly_cap'
          ? 'Limited by the monthly cap you set.'
          : 'Limited by your calculated monthly surplus.';

  return {
    analysis_id: FIXTURE_ANALYSIS_ID,
    currency: FIXTURE_CURRENCY,
    latest_verified_balance: SS_INPUTS.latest_verified_balance.toFixed(2),
    balance_is_estimated: false,
    expected_income: SS_INPUTS.expected_income.toFixed(2),
    upcoming_essential_outflows: SS_INPUTS.upcoming_essential_outflows.toFixed(2),
    projected_balance_before_next_income: projected.toFixed(2),
    safety_buffer: buffer.toFixed(2),
    volatility_reserve: reserve.toFixed(2),
    safe_spare_now: safeNow.toFixed(2),
    safe_monthly_contribution: safeMonthly.toFixed(2),
    calculated_monthly_surplus: SS_INPUTS.calculated_monthly_surplus.toFixed(2),
    average_monthly_essential_spending: SS_INPUTS.average_monthly_essential_spending.toFixed(2),
    confidence: 0.82,
    limiting_factor: safeMonthly <= 0 ? 'zero' : winner.key,
    reason,
    missing_inputs: [],
    next_income_date: SS_INPUTS.next_income_date,
    settings,
    source_transaction_ids: ['demo-tx-001', 'demo-tx-003', 'demo-tx-030', 'demo-tx-031'],
    calculation_version: CALC_VERSION,
  };
}

/* -------------------------------------------------------------------------
   Cashflow Confidence (§6.7)
   ---------------------------------------------------------------------- */

export const fixtureConfidence: CashflowConfidenceResponse = {
  analysis_id: FIXTURE_ANALYSIS_ID,
  score: 72,
  band: 'Steady, with a thin buffer',
  components: [
    { key: 'income_regularity', label: 'Income regularity', weight_percent: 30, score: 92, weighted_points: 27.6, evidence: 'Three salary credits of $3,200.00 on the 1st of each month, with no missed cycle.' },
    { key: 'essential_predictability', label: 'Essential-expense predictability', weight_percent: 25, score: 84, weighted_points: 21.0, evidence: 'Rent and insurance are fixed. Electricity varies between $90.12 and $112.40, which lowers this component.' },
    { key: 'buffer_coverage', label: 'Safety-buffer coverage', weight_percent: 30, score: 46, weighted_points: 13.8, evidence: 'Your balance covers about 0.6 months of essential spending. One month or more scores higher.' },
    { key: 'stability', label: 'Spending / balance stability', weight_percent: 15, score: 61, weighted_points: 9.15, evidence: 'Monthly outflows range from $2,761.44 to $2,854.72, with one large annual software charge in June.' },
  ],
  confidence: 0.86,
  improvement_suggestions: [
    'Raising the balance you keep before rent day by about $400 would move buffer coverage above one month.',
    'The two overlapping cloud-storage services are worth reviewing — one of them is $11.99 a month.',
    'A fixed-rate electricity plan would reduce the volatility reserve currently held back.',
  ],
  disclaimer:
    'Cashflow Confidence is not a credit score. It describes how predictable your cash position is, using only the transactions you uploaded. It never infers creditworthiness and never uses personal attributes.',
  calculation_version: CALC_VERSION,
};

/* -------------------------------------------------------------------------
   Round-ups (§6.8)
   ---------------------------------------------------------------------- */

export const DEFAULT_ROUNDUP_RULES: RoundUpRules = {
  increment: '1.00',
  monthly_cap: '40.00',
  per_transaction_cap: '2.00',
  excluded_categories: [
    'rent_housing', 'loan_emi', 'insurance', 'medical', 'tax', 'education', 'childcare',
    'internal_transfer', 'cash_withdrawal', 'savings', 'investment', 'refund_reimbursement',
    'bank_charge', 'salary_income', 'other_income',
  ],
  excluded_merchants: [],
  large_transaction_threshold: '2000.00',
  paused: false,
};

/**
 * MOCK BACKEND: the §6.8 round-up formula over the fixture transactions, so
 * changing the increment or a cap visibly changes the result.
 */
export function fixtureRoundUps(rules: RoundUpRules, safeMonthlyContribution: number): RoundUpsResponse {
  const increment = Math.max(0.01, Number.parseFloat(String(rules.increment)) || 1);
  const perTxCap = rules.per_transaction_cap === null ? null : Number.parseFloat(String(rules.per_transaction_cap));
  const monthlyCap = rules.monthly_cap === null ? null : Number.parseFloat(String(rules.monthly_cap));
  const largeThreshold = Number.parseFloat(String(rules.large_transaction_threshold)) || 2000;
  const excluded = new Set(rules.excluded_categories);
  const excludedMerchants = new Set(rules.excluded_merchants.map((m) => m.toLowerCase()));

  const lines: RoundUpLine[] = [];
  let historical = 0;

  for (const tx of fixtureTransactions) {
    if (tx.direction === 'credit') continue;
    const amount = Number.parseFloat(String(tx.debit ?? '0'));
    if (!amount) continue;

    let reason: string | null = null;
    if (tx.excluded) reason = 'Excluded by you during review';
    else if (excluded.has(tx.category)) reason = 'Protected category — never rounded up';
    else if (tx.normalized_merchant && excludedMerchants.has(tx.normalized_merchant.toLowerCase()))
      reason = 'Merchant excluded by you';
    else if (amount >= largeThreshold) reason = 'Large or uncertain transaction';
    else if (tx.status === 'needs_review') reason = 'Awaiting your review';

    let roundUp = r2(Math.ceil(amount / increment) * increment - amount);
    if (roundUp <= 0) {
      reason = reason ?? 'Already a whole multiple of the increment';
      roundUp = 0;
    }
    if (!reason && perTxCap !== null && roundUp > perTxCap) roundUp = r2(perTxCap);

    const eligible = reason === null && roundUp > 0;
    if (eligible) historical = r2(historical + roundUp);

    lines.push({
      transaction_id: tx.id,
      date: tx.date,
      merchant: tx.normalized_merchant ?? tx.description,
      category: tx.category,
      amount: amount.toFixed(2),
      round_up: (eligible ? roundUp : 0).toFixed(2),
      eligible,
      reason,
    });
  }

  const candidates: { value: number; key: string }[] = [
    { value: historical, key: 'historical_round_up_total' },
    { value: safeMonthlyContribution, key: 'safe_monthly_contribution' },
  ];
  if (monthlyCap !== null) candidates.push({ value: monthlyCap, key: 'user_round_up_cap' });
  candidates.sort((a, b) => a.value - b.value);
  const winner = rules.paused ? { value: 0, key: 'paused' } : (candidates[0] as { value: number; key: string });
  const allowed = r2(Math.max(0, winner.value));

  const explanation = rules.paused
    ? 'Round-ups are paused, so nothing is being redirected. Your calculated figures are unaffected.'
    : allowed <= 0
      ? `Your transactions created ${historical.toFixed(2)} ${FIXTURE_CURRENCY} in potential round-ups, but none of it is safely redirectable this month — essential bills are due before your next expected income.`
      : `Your transactions created $${historical.toFixed(2)} in potential round-ups, but only $${allowed.toFixed(2)} is considered safely redirectable because essential bills are due before your next expected income.`;

  return {
    analysis_id: FIXTURE_ANALYSIS_ID,
    currency: FIXTURE_CURRENCY,
    rules,
    lines,
    historical_round_up_total: historical.toFixed(2),
    allowed_round_up_total: allowed.toFixed(2),
    safe_monthly_contribution: safeMonthlyContribution.toFixed(2),
    limiting_factor: winner.key,
    explanation,
    eligible_count: lines.filter((l) => l.eligible).length,
    excluded_count: lines.filter((l) => !l.eligible).length,
    calculation_version: CALC_VERSION,
  };
}

/* -------------------------------------------------------------------------
   Goals and simulation (§6.10)
   ---------------------------------------------------------------------- */

export const ILLUSTRATIVE_DISCLAIMER =
  'Illustrative simulation only. Actual returns may be higher, lower or negative.';

export const fixtureGoal: Goal = {
  id: 'demo-goal-001',
  analysis_id: FIXTURE_ANALYSIS_ID,
  kind: 'emergency_fund',
  name: 'Emergency fund',
  target_amount: '3000.00',
  target_date: '2027-06-30',
  starting_principal: '250.00',
  include_round_ups: true,
  include_confirmed_recovered: true,
  annual_return_rate: 0.07,
  created_at: '2026-06-30T09:14:00Z',
};

function futureValue(principal: number, monthly: number, monthlyRate: number, months: number): number {
  if (months <= 0) return principal;
  if (monthlyRate === 0) return principal + monthly * months;
  const growth = Math.pow(1 + monthlyRate, months);
  return principal * growth + monthly * ((growth - 1) / monthlyRate);
}

function monthsBetween(from: Date, to: Date): number {
  return Math.max(1, Math.round((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24 * 30.44)));
}

/**
 * MOCK BACKEND: the §6.10 deterministic future-value maths, mirroring
 * backend/app/services/projections.py — including the zero-rate branch, and
 * always reporting principal and illustrative growth separately.
 */
export function fixtureSimulate(
  goal: Goal,
  ctx: { safeMonthly: number; roundUps: number; confirmedRecovered: number },
): SimulationResponse {
  const target = Number.parseFloat(String(goal.target_amount)) || 0;
  const principal = Number.parseFloat(String(goal.starting_principal)) || 0;
  const months = monthsBetween(new Date('2026-06-30'), new Date(goal.target_date));

  const roundUpPart = goal.include_round_ups ? Math.min(ctx.roundUps, ctx.safeMonthly) : 0;
  const recoveredPart = goal.include_confirmed_recovered ? ctx.confirmedRecovered : 0;
  const monthly = r2(Math.min(ctx.safeMonthly, Math.max(roundUpPart, 0) + recoveredPart) || Math.min(ctx.safeMonthly, roundUpPart));

  const rate = goal.annual_return_rate / 12;
  const fv = r2(futureValue(principal, monthly, rate, months));
  const contributions = r2(principal + monthly * months);
  const growth = r2(fv - contributions);
  const gap = r2(Math.max(0, target - fv));

  const principalGrowthAtTarget = principal * (rate === 0 ? 1 : Math.pow(1 + rate, months));
  const annuityFactor = rate === 0 ? months : (Math.pow(1 + rate, months) - 1) / rate;
  const required = r2(Math.max(0, (target - principalGrowthAtTarget) / annuityFactor));

  let completionMonths: number | null = null;
  if (monthly > 0 || principal >= target) {
    for (let m = 1; m <= 1200; m += 1) {
      if (futureValue(principal, monthly, rate, m) >= target) {
        completionMonths = m;
        break;
      }
    }
  }
  let completionDate: string | null = null;
  if (completionMonths !== null) {
    const d = new Date('2026-06-30');
    d.setMonth(d.getMonth() + completionMonths);
    completionDate = d.toISOString().slice(0, 10);
  }

  const scenarioRates: [string, number][] = [
    ['Contributions only', 0],
    ['Lower illustrative return', 0.04],
    ['Medium illustrative return', 0.07],
    ['Higher-volatility illustrative return', 0.1],
  ];

  const timeline: SeriesPoint[] = [];
  const step = Math.max(1, Math.round(months / 12));
  for (let m = step; m <= months; m += step) {
    const value = futureValue(principal, monthly, rate, m);
    const contributed = principal + monthly * m;
    timeline.push({
      label: `M${m}`,
      principal: r2(contributed),
      growth: r2(value - contributed),
      target,
    });
  }

  return {
    goal_id: goal.id,
    currency: FIXTURE_CURRENCY,
    months,
    monthly_contribution: monthly.toFixed(2),
    safe_monthly_contribution: ctx.safeMonthly.toFixed(2),
    round_up_contribution: roundUpPart.toFixed(2),
    confirmed_recovered_amount: recoveredPart.toFixed(2),
    user_contributions: contributions.toFixed(2),
    illustrative_growth: growth.toFixed(2),
    projected_value: fv.toFixed(2),
    goal_gap: gap.toFixed(2),
    estimated_completion_months: completionMonths,
    estimated_completion_date: completionDate,
    required_monthly_contribution: required.toFixed(2),
    contribution_shortfall: r2(Math.max(0, required - monthly)).toFixed(2),
    achievable: fv >= target,
    scenarios: scenarioRates.map(([name, annual]) => {
      const r = annual / 12;
      const v = r2(futureValue(principal, monthly, r, months));
      const c = r2(principal + monthly * months);
      return {
        name,
        annual_rate: annual,
        user_contributions: c.toFixed(2),
        illustrative_growth: r2(v - c).toFixed(2),
        projected_value: v.toFixed(2),
      };
    }),
    timeline,
    disclaimer: ILLUSTRATIVE_DISCLAIMER,
    calculation_version: CALC_VERSION,
  };
}

export function fixtureGoalFromRequest(req: GoalRequest, id?: string): Goal {
  return { ...req, id: id ?? `demo-goal-${Date.now()}`, created_at: new Date().toISOString() };
}

/* -------------------------------------------------------------------------
   AI Coach (§6.11)
   ---------------------------------------------------------------------- */

const COACH_ANSWERS: { match: RegExp; answer: string; citations: ChatResponse['citations'] }[] = [
  {
    match: /safe spare|safely|how much can i/i,
    answer:
      'Your Safe Spare amount this month is $31.00.\n\nIt starts from your latest verified balance of $2,410.88. Rent ($1,150.00), insurance ($145.00) and electricity ($90.00) are all due before your next salary on 1 July, which leaves a projected $1,025.88. A safety buffer of $453.42 and a volatility reserve of $541.46 are then held back, because your monthly outflows have varied by about $1,082.92.\n\nWhat is left — $31.00 — is what the engine considers safely redirectable.',
    citations: [
      { label: 'Latest verified balance', value: '2410.88', source: 'safe_spare.latest_verified_balance' },
      { label: 'Upcoming essential outflows', value: '1385.00', source: 'safe_spare.upcoming_essential_outflows' },
      { label: 'Safe Spare amount', value: '31.00', source: 'safe_spare.safe_monthly_contribution' },
    ],
  },
  {
    match: /round.?up|capped|48/i,
    answer:
      'Your transactions created $48.70 in potential round-ups, but only $31.00 is considered safely redirectable this month.\n\nThe cap is not arbitrary: $31.00 is your safe monthly contribution, which is itself limited by the cash expected to remain before your next income once rent and insurance are paid. Round-ups can never exceed that figure — that is the difference between SafeSpare and an ordinary round-up app.',
    citations: [
      { label: 'Potential round-ups', value: '48.70', source: 'roundups.historical_round_up_total' },
      { label: 'Allowed round-ups', value: '31.00', source: 'roundups.allowed_round_up_total' },
    ],
  },
  {
    match: /recurring|subscription|leak/i,
    answer:
      'I found 12 recurring payments totalling $1,539.25 a month. Nine are optional and carry a leak score; three — rent, insurance and electricity — are protected and are never put forward for cancellation.\n\nTwo things stand out. Streamly rose from $15.49 to $17.99 on 25 May, a 16.14% increase. And two cloud-storage services, Nimbus ($9.99) and Vaultbox ($11.99), are billed on the same day.\n\nI cannot tell from bank data whether you use any of these. If you confirm usage on the Leak Radar page, the scores update and any recovered amount can be included in your goal simulation.',
    citations: [
      { label: 'Recurring payments', value: '12', source: 'recurring.count' },
      { label: 'Monthly recurring total', value: '1539.25', source: 'recurring.total_monthly_recurring' },
      { label: 'Streamly increase', value: '16.14%', source: 'leaks.leak-02.price_change' },
    ],
  },
  {
    match: /goal|emergency|projection|grow/i,
    answer:
      'At $31.00 a month against a $3,000.00 emergency fund, the simulation reaches about $652.24 after 12 months — $622.00 of that is money you put in, and about $30.24 is illustrative growth at a 7% annual assumption.\n\nTo hit $3,000.00 within 12 months you would need roughly $220.45 a month, which is $189.45 more than is currently safe. Extending the date, or confirming some of the recoverable subscriptions, closes that gap without putting your bills at risk.\n\nIllustrative simulation only. Actual returns may be higher, lower or negative.',
    citations: [
      { label: 'Projected value', value: '652.24', source: 'simulation.projected_value' },
      { label: 'Your contributions', value: '622.00', source: 'simulation.user_contributions' },
      { label: 'Illustrative growth', value: '30.24', source: 'simulation.illustrative_growth' },
    ],
  },
  {
    match: /food|dining|delivery|eat/i,
    answer:
      'Food-delivery spending increased from $512.60 to $684.20 between the previous and current period, across 18 orders. Two orders of a size similar to your recent ones total $62.30. Skipping those would release that amount toward your goal.\n\nThis is a suggestion based on your own transactions, not a judgement about your spending.',
    citations: [
      { label: 'Dining / food delivery', value: '684.20', source: 'categories.dining_delivery.total' },
      { label: 'Previous period', value: '512.60', source: 'categories.dining_delivery.previous_period_total' },
    ],
  },
];

const COACH_FALLBACK =
  'I can explain anything the engine calculated: your Safe Spare amount, why round-ups were capped, what the recurring payments are, how the goal projection works, or a specific spending category.\n\nI cannot invent a figure, change one, or tell you what to invest in — every number I quote comes from the calculation the backend already performed.';

export function fixtureChat(question: string): ChatResponse {
  const hit = COACH_ANSWERS.find((a) => a.match.test(question));
  return {
    id: `chat-${Date.now()}`,
    answer: hit ? hit.answer : COACH_FALLBACK,
    citations: hit ? hit.citations : [],
    generated_offline: true,
    provider: null,
    validation_rejected: false,
    disclaimer:
      'SafeSpare is not a licensed financial adviser. Explanations describe figures the backend calculated; they never change them, and no securities are recommended.',
  };
}

/* -------------------------------------------------------------------------
   Voice (§6.12)
   ---------------------------------------------------------------------- */

export const fixtureVoice: VoiceSummaryResponse = {
  analysis_id: FIXTURE_ANALYSIS_ID,
  transcript:
    'I found twelve recurring payments. Nine are optional and three are protected essentials. One optional subscription increased by sixteen per cent, and two cloud-storage services overlap. Your transactions created forty-eight dollars and seventy cents in potential round-ups, but based on your safety settings, up to thirty-one dollars may be redirected this month. Nothing has been invested, cancelled or transferred.',
  audio_url: null,
  duration_seconds: 27,
  audio_available: false,
  fallback_reason:
    'Voice playback is unavailable in demo mode. The transcript below is the verified summary the backend produced.',
  generated_at: '2026-06-30T09:15:00Z',
};

/* -------------------------------------------------------------------------
   Landing-page content (§6.1) — copy, not financial data.
   ---------------------------------------------------------------------- */

export const TRUST_STATEMENTS = [
  'No real investment is executed.',
  'Every financial amount comes from verified calculations.',
  'User approval is required.',
  'Uploaded files can be automatically deleted.',
  'AI explanations cannot modify calculated values.',
];

export const PRODUCT_FLOW = [
  { num: '01', title: 'Upload', body: 'A PDF or CSV statement. No bank login, no live account connection.' },
  { num: '02', title: 'Understand', body: 'Merchants normalized, spending categorized, income timing established.' },
  { num: '03', title: 'Protect', body: 'Rent, insurance, loans and medical costs are ring-fenced before anything else.' },
  { num: '04', title: 'Find safe spare money', body: 'A buffer and a volatility reserve are held back. What survives is spare.' },
  { num: '05', title: 'Simulate growth', body: 'Controlled round-ups, illustrative returns, principal and growth always separate.' },
];

export const CAPABILITY_MARQUEE = [
  'Digital PDF', 'CSV export', 'XLSX', 'Scanned PDF', 'SMS alerts', 'Email alerts',
  'Merchant normalization', 'Recurring detection', 'Price-hike detection', 'Duplicate services',
  'Round-up engine', 'Goal simulation',
];
