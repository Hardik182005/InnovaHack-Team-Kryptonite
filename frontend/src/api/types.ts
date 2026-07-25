/* ============================================================================
   SafeSpare AI — API contract types (spec §18, §20).

   These mirror the FastAPI response models. Money is typed as `Money` (string
   or number) because the backend uses Python `Decimal`; depending on the
   Pydantic serialisation mode a Decimal arrives as either a JSON string or a
   JSON number. `toNumber()` in lib/format.ts normalises for charting only —
   the *displayed* figure is always the backend's own value.

   The frontend never derives a financial figure. If a number is shown, a field
   on one of these types produced it.
   ========================================================================= */

export type Money = string | number;

/** §6.5 — the 26 categories, verbatim from backend/app/models/enums.py */
export type Category =
  | 'salary_income'
  | 'other_income'
  | 'rent_housing'
  | 'utilities'
  | 'groceries'
  | 'dining_delivery'
  | 'transportation'
  | 'fuel'
  | 'shopping'
  | 'entertainment'
  | 'subscription'
  | 'software'
  | 'fitness'
  | 'education'
  | 'medical'
  | 'insurance'
  | 'loan_emi'
  | 'tax'
  | 'childcare'
  | 'travel'
  | 'savings'
  | 'investment'
  | 'internal_transfer'
  | 'cash_withdrawal'
  | 'bank_charge'
  | 'refund_reimbursement'
  | 'unknown';

export type Direction = 'debit' | 'credit';
export type Essentiality = 'essential' | 'discretionary' | 'unknown';
export type ReviewStatus = 'confirmed' | 'likely' | 'needs_review';
export type Frequency = 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'half_yearly' | 'annual';

/** §6.9 — the only permitted usage states. */
export type UsageStatus =
  | 'usage_unknown'
  | 'possibly_underused'
  | 'user_confirms_regular_use'
  | 'user_confirms_occasional_use'
  | 'user_confirms_not_used'
  | 'user_does_not_recognize_payment';

/** §6.9 — the eight available actions. */
export type LeakDecision =
  | 'keep'
  | 'review'
  | 'cancel'
  | 'downgrade'
  | 'renegotiate'
  | 'mark_essential'
  | 'not_mine'
  | 'review_later';

/** §19 — analysis state machine. */
export type AnalysisState =
  | 'UPLOADED'
  | 'EXTRACTING'
  | 'VALIDATING'
  | 'AWAITING_REVIEW'
  | 'NORMALIZING'
  | 'CATEGORIZING'
  | 'DETECTING_RECURRING'
  | 'CALCULATING_SAFE_SPARE'
  | 'GENERATING_INSIGHTS'
  | 'COMPLETED'
  | 'FAILED';

/* -------------------------------------------------------------------------
   Uploads / analyses
   ---------------------------------------------------------------------- */

export interface PresignRequest {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface PresignResponse {
  upload_id: string;
  upload_url: string;
  fields: Record<string, string>;
  expires_in_seconds: number;
  max_size_bytes: number;
}

export interface CreateAnalysisRequest {
  upload_id?: string;
  demo?: boolean;
  /** PDF password, forwarded once and never stored (§6.2). */
  document_password?: string;
  consent_confirmed: boolean;
  delete_after_processing: boolean;
  declared_currency?: string;
}

export interface AnalysisRef {
  analysis_id: string;
  state: AnalysisState;
}

export interface ProcessingStage {
  key: string;
  label: string;
  state: 'pending' | 'active' | 'done' | 'failed' | 'skipped';
  detail?: string | null;
}

export interface AnalysisStatus {
  analysis_id: string;
  state: AnalysisState;
  /** 0–100, produced by the backend. */
  progress_percent: number;
  stages: ProcessingStage[];
  /** Safe, user-facing message. Raw exceptions never reach the client (§5). */
  message?: string | null;
  error_code?: string | null;
  updated_at: string;
}

export interface DetectedDocumentMeta {
  currency: string;
  currency_confidence: number;
  date_range_start: string | null;
  date_range_end: string | null;
  transaction_count: number;
  pages: number | null;
  parser: string;
  password_protected: boolean;
  delete_after_processing: boolean;
  warnings: string[];
}

/* -------------------------------------------------------------------------
   Transactions (§6.3, §20)
   ---------------------------------------------------------------------- */

export interface Transaction {
  id: string;
  date: string;
  description: string;
  raw_merchant: string | null;
  normalized_merchant: string | null;
  merchant_method: string | null;
  merchant_confidence: number;
  debit: Money | null;
  credit: Money | null;
  direction: Direction;
  balance: Money | null;
  currency: string;
  category: Category;
  category_confidence: number;
  category_method: string | null;
  essentiality: Essentiality;
  source_page: number | null;
  source_row: number | null;
  parser: string | null;
  extraction_confidence: number;
  validation_warnings: string[];
  external_model_used: boolean;
  excluded: boolean;
  is_internal_transfer: boolean;
  is_reimbursement: boolean;
  user_overridden: boolean;
  status: ReviewStatus;
  reference: string | null;
  duplicate_of?: string | null;
}

export interface TransactionPage {
  analysis_id: string;
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
  /** Backend-computed roll-ups for the review header. */
  warning_count: number;
  needs_review_count: number;
  excluded_count: number;
}

/** §6.3 — every permitted correction. The backend writes the audit record. */
export interface TransactionPatch {
  normalized_merchant?: string;
  amount?: Money;
  direction?: Direction;
  category?: Category;
  essentiality?: Essentiality;
  is_internal_transfer?: boolean;
  is_reimbursement?: boolean;
  excluded?: boolean;
  merge_into_transaction_id?: string;
}

export interface BulkConfirmRequest {
  analysis_id: string;
  transaction_ids?: string[];
  confirm_all?: boolean;
}

export interface BulkConfirmResponse {
  analysis_id: string;
  confirmed_count: number;
  state: AnalysisState;
}

/* -------------------------------------------------------------------------
   Dashboard summary (§6.4)
   ---------------------------------------------------------------------- */

export interface SeriesPoint {
  label: string;
  [key: string]: string | number | null;
}

export interface AnalysisSummary {
  analysis_id: string;
  currency: string;
  period_start: string;
  period_end: string;
  months_covered: number;
  transaction_count: number;
  /** True when the statement carried no running balance (§6.6). */
  balance_is_estimated: boolean;

  total_income: Money;
  total_spending: Money;
  essential_spending: Money;
  discretionary_spending: Money;
  recurring_spending: Money;
  recurring_payment_count: number;
  average_monthly_surplus: Money;

  potential_round_ups: Money;
  safe_round_up_allowance: Money;
  potential_recoverable_spending: Money;
  confirmed_recoverable_spending: Money;
  high_confidence_recoverable_spending: Money;

  safe_spare_amount: Money;
  safe_spare_confidence: number;
  cashflow_confidence_score: number;

  goal_progress: {
    goal_id: string | null;
    goal_name: string | null;
    target_amount: Money | null;
    contributed_to_date: Money | null;
    percent_complete: number | null;
  };

  charts: {
    income_vs_spending: SeriesPoint[];
    category_breakdown: SeriesPoint[];
    essential_vs_discretionary: SeriesPoint[];
    recurring_vs_one_time: SeriesPoint[];
    monthly_surplus_trend: SeriesPoint[];
    safe_spare_trend: SeriesPoint[];
    upcoming_obligations: SeriesPoint[];
    principal_vs_growth: SeriesPoint[];
  };

  calculation_version: string;
  generated_at: string;
}

/* -------------------------------------------------------------------------
   Categories (§6.5)
   ---------------------------------------------------------------------- */

export interface CategoryEvidence {
  transaction_id: string;
  date: string;
  description: string;
  amount: Money;
}

export interface CategoryBreakdownItem {
  category: Category;
  label: string;
  total: Money;
  percent_of_spending: number;
  transaction_count: number;
  previous_period_total: Money | null;
  change_amount: Money | null;
  change_percent: number | null;
  essentiality: Essentiality;
  confidence: number;
  review_status: ReviewStatus;
  evidence: CategoryEvidence[];
}

export interface CategoryInsight {
  id: string;
  category: Category;
  headline: string;
  detail: string;
  evidence_transaction_ids: string[];
  /** Backend-computed. Never derived client-side. */
  releasable_amount: Money | null;
  confidence: number;
}

export interface CategoriesResponse {
  analysis_id: string;
  currency: string;
  items: CategoryBreakdownItem[];
  insights: CategoryInsight[];
  calculation_version: string;
}

/* -------------------------------------------------------------------------
   Recurring (§11, §12)
   ---------------------------------------------------------------------- */

export interface PriceChange {
  previous_amount: Money;
  current_amount: Money;
  absolute_increase: Money;
  percent_increase: number;
  first_date_of_new_price: string;
  evidence_transaction_ids: string[];
  confidence: number;
}

export interface RecurrencePattern {
  id: string;
  merchant: string;
  category: Category;
  frequency: Frequency;
  occurrence_count: number;
  median_amount: Money;
  monthly_cost: Money;
  annual_cost: Money;
  amount_varies: boolean;
  first_seen: string;
  last_seen: string;
  next_expected_date: string | null;
  confidence: number;
  review_status: ReviewStatus;
  essentiality: Essentiality;
  interval_regularity: number;
  merchant_similarity: number;
  amount_stability: number;
  occurrence_strength: number;
  price_change: PriceChange | null;
  evidence_transaction_ids: string[];
}

export interface RecurringResponse {
  analysis_id: string;
  currency: string;
  items: RecurrencePattern[];
  total_monthly_recurring: Money;
  calculation_version: string;
}

/* -------------------------------------------------------------------------
   Leak Radar (§6.9, §13)
   ---------------------------------------------------------------------- */

export interface LeakFinding {
  id: string;
  merchant: string;
  category: Category;
  frequency: Frequency;
  monthly_cost: Money;
  annual_cost: Money;
  leak_score: number;
  band: 'low_concern' | 'review' | 'consider_downgrade' | 'cancellation_review';
  usage_status: UsageStatus;
  review_status: ReviewStatus;
  decision: LeakDecision | null;
  recommended_actions: LeakDecision[];
  components: {
    price_hike_severity: number;
    duplicate_probability: number;
    cost_burden: number;
    recurrence_commitment: number;
    confirmed_non_usage: number;
  };
  duplicate_group: string | null;
  price_change: PriceChange | null;
  evidence_transaction_ids: string[];
  explanation: string;
  protected: boolean;
  /** Present when protected — states why cancellation advice is blocked. */
  protection_reason: string | null;
  calculation_version: string;
}

export interface LeaksResponse {
  analysis_id: string;
  currency: string;
  items: LeakFinding[];
  potential_recoverable_monthly: Money;
  high_confidence_recoverable_monthly: Money;
  user_confirmed_recoverable_monthly: Money;
  calculation_version: string;
}

export interface UsageConfirmationRequest {
  usage_status: UsageStatus;
}

export interface DecisionRequest {
  decision: LeakDecision;
  note?: string;
}

export interface DraftActionRequest {
  action: 'cancel' | 'downgrade' | 'renegotiate';
}

export interface DraftActionResponse {
  finding_id: string;
  action: string;
  subject: string;
  body: string;
  /** True when a deterministic template was used because no LLM was reachable. */
  generated_offline: boolean;
  disclaimer: string;
}

/* -------------------------------------------------------------------------
   Safe Spare Engine (§6.6)
   ---------------------------------------------------------------------- */

export interface SafeSpareSettings {
  user_minimum_buffer: Money;
  buffer_percentage: number;
  volatility_multiplier: number;
  user_monthly_cap: Money | null;
}

export interface SafeSpareResponse {
  analysis_id: string;
  currency: string;

  latest_verified_balance: Money;
  balance_is_estimated: boolean;
  expected_income: Money;
  upcoming_essential_outflows: Money;
  projected_balance_before_next_income: Money;
  safety_buffer: Money;
  volatility_reserve: Money;
  safe_spare_now: Money;
  safe_monthly_contribution: Money;
  calculated_monthly_surplus: Money;
  average_monthly_essential_spending: Money;

  confidence: number;
  limiting_factor: string;
  reason: string;
  missing_inputs: string[];
  next_income_date: string | null;
  settings: SafeSpareSettings;
  source_transaction_ids: string[];
  calculation_version: string;
}

/* -------------------------------------------------------------------------
   Cashflow Confidence (§6.7)
   ---------------------------------------------------------------------- */

export interface ConfidenceComponent {
  key: 'income_regularity' | 'essential_predictability' | 'buffer_coverage' | 'stability';
  label: string;
  weight_percent: number;
  score: number;
  weighted_points: number;
  evidence: string;
}

export interface CashflowConfidenceResponse {
  analysis_id: string;
  score: number;
  band: string;
  components: ConfidenceComponent[];
  confidence: number;
  improvement_suggestions: string[];
  disclaimer: string;
  calculation_version: string;
}

/* -------------------------------------------------------------------------
   Round-ups (§6.8)
   ---------------------------------------------------------------------- */

export interface RoundUpRules {
  increment: Money;
  monthly_cap: Money | null;
  per_transaction_cap: Money | null;
  excluded_categories: Category[];
  excluded_merchants: string[];
  large_transaction_threshold: Money;
  paused: boolean;
}

export interface RoundUpLine {
  transaction_id: string;
  date: string;
  merchant: string;
  category: Category;
  amount: Money;
  round_up: Money;
  eligible: boolean;
  reason: string | null;
}

export interface RoundUpsResponse {
  analysis_id: string;
  currency: string;
  rules: RoundUpRules;
  lines: RoundUpLine[];
  historical_round_up_total: Money;
  allowed_round_up_total: Money;
  safe_monthly_contribution: Money;
  limiting_factor: string;
  explanation: string;
  eligible_count: number;
  excluded_count: number;
  calculation_version: string;
}

/* -------------------------------------------------------------------------
   Goals and simulation (§6.10)
   ---------------------------------------------------------------------- */

export type GoalKind =
  | 'emergency_fund'
  | 'education'
  | 'laptop'
  | 'travel'
  | 'major_purchase'
  | 'long_term_wealth'
  | 'custom';

export interface GoalRequest {
  analysis_id: string;
  kind: GoalKind;
  name: string;
  target_amount: Money;
  target_date: string;
  starting_principal: Money;
  include_round_ups: boolean;
  include_confirmed_recovered: boolean;
  annual_return_rate: number;
}

export interface Goal extends GoalRequest {
  id: string;
  created_at: string;
}

export interface SimulationScenario {
  name: string;
  annual_rate: number;
  user_contributions: Money;
  illustrative_growth: Money;
  projected_value: Money;
}

export interface SimulationResponse {
  goal_id: string;
  currency: string;
  months: number;
  monthly_contribution: Money;
  safe_monthly_contribution: Money;
  round_up_contribution: Money;
  confirmed_recovered_amount: Money;

  user_contributions: Money;
  illustrative_growth: Money;
  projected_value: Money;
  goal_gap: Money;
  estimated_completion_months: number | null;
  estimated_completion_date: string | null;
  required_monthly_contribution: Money;
  contribution_shortfall: Money;
  achievable: boolean;

  scenarios: SimulationScenario[];
  timeline: SeriesPoint[];
  disclaimer: string;
  calculation_version: string;
}

/* -------------------------------------------------------------------------
   AI Coach (§6.11)
   ---------------------------------------------------------------------- */

export interface ChatRequest {
  analysis_id: string;
  question: string;
}

export interface ChatCitation {
  label: string;
  value: Money | string;
  source: string;
}

export interface ChatResponse {
  id: string;
  answer: string;
  citations: ChatCitation[];
  /** True when the answer came from a deterministic template (§3.21). */
  generated_offline: boolean;
  provider: string | null;
  /** Backend rejected an LLM draft that tried to alter a figure (§16). */
  validation_rejected: boolean;
  disclaimer: string;
}

/* -------------------------------------------------------------------------
   Voice (§6.12)
   ---------------------------------------------------------------------- */

export interface VoiceSummaryResponse {
  analysis_id: string;
  transcript: string;
  audio_url: string | null;
  duration_seconds: number | null;
  /** Voice provider unavailable / quota exhausted — transcript still valid. */
  audio_available: boolean;
  fallback_reason: string | null;
  generated_at: string;
}

/* -------------------------------------------------------------------------
   Privacy (§22)
   ---------------------------------------------------------------------- */

export interface DeleteResponse {
  deleted: boolean;
  analysis_id?: string;
  deleted_at: string;
  message: string;
}

export interface HealthResponse {
  status: string;
  version?: string;
}
