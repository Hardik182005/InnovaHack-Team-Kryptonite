/* ============================================================================
   SafeSpare AI — the one place the SPA talks to a data source.

   Two implementations sit behind every call:

     live      → the FastAPI backend (spec §18 endpoints), over fetch().
     fixtures  → the bundled synthetic demo backend in ./fixtures.ts.

   `auto` tries live first and falls back to fixtures with a visible banner.
   The switch is explicit: VITE_DATA_MODE=live|fixtures|auto (VITE_USE_FIXTURES=true
   is accepted as an alias), and a runtime toggle lives in the mode banner.

   IMPORTANT — where financial arithmetic is allowed to live.
   React components never compute a money figure; they render a field returned
   from here. In fixture mode *this module plus fixtures.ts is the backend*, so
   the re-derivations below (marked MOCK BACKEND) are the stand-in for
   backend/app/services/. In live mode not a single number is touched.

   NO SECRETS. Only a base URL and a timeout are read from the environment.
   ========================================================================= */

import { API_BASE_URL, API_TIMEOUT_MS, dataSource } from './config';
import { ApiError, toApiError } from './errors';
import {
  DEFAULT_ROUNDUP_RULES,
  DEFAULT_SAFE_SPARE_SETTINGS,
  FIXTURE_ANALYSIS_ID,
  FIXTURE_CURRENCY,
  fixtureCategories,
  fixtureChat,
  fixtureConfidence,
  fixtureDocumentMeta,
  fixtureDraft,
  fixtureGoalFromRequest,
  fixtureLeaks,
  fixtureRecurring,
  fixtureRoundUps,
  fixtureSafeSpare,
  fixtureSimulate,
  fixtureStatus,
  fixtureSummary,
  fixtureTransactionPage,
  fixtureTransactions,
  fixtureVoice,
} from './fixtures';
import type {
  AnalysisRef,
  AnalysisStatus,
  AnalysisSummary,
  BulkConfirmRequest,
  BulkConfirmResponse,
  CashflowConfidenceResponse,
  CategoriesResponse,
  Category,
  ChatRequest,
  ChatResponse,
  CreateAnalysisRequest,
  DecisionRequest,
  DeleteResponse,
  DetectedDocumentMeta,
  DraftActionRequest,
  DraftActionResponse,
  Goal,
  GoalRequest,
  HealthResponse,
  LeakDecision,
  LeakFinding,
  LeaksResponse,
  PresignRequest,
  PresignResponse,
  RecurringResponse,
  RoundUpRules,
  RoundUpRulesPatch,
  RoundUpsResponse,
  SafeSpareResponse,
  SafeSpareSettings,
  SeriesPoint,
  SimulationResponse,
  Transaction,
  TransactionPage,
  TransactionPatch,
  UsageConfirmationRequest,
  VoiceSummaryResponse,
} from './types';
import { CATEGORY_LABELS } from '@/lib/format';

/* -------------------------------------------------------------------------
   Live transport
   ---------------------------------------------------------------------- */

const SESSION_KEY = 'safespare.session';

/**
 * A stable per-browser session id.
 *
 * The backend scopes every analysis to this value and returns 404 for anyone
 * else's (§29), so it must survive a refresh but never be shared.
 */
function sessionId(): string {
  try {
    let id = window.localStorage.getItem(SESSION_KEY);
    if (!id) {
      id =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      window.localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return 'ephemeral-session';
  }
}

/** Multipart POST (file bodies). Shares error handling with `request`. */
async function requestRaw(method: string, path: string, form: FormData): Promise<void> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { Accept: 'application/json', 'X-Session-Id': sessionId() },
      body: form,
      signal: controller.signal,
    });
    if (!res.ok) throw ApiError.fromStatus(res.status, await res.text());
  } catch (err) {
    throw toApiError(err);
  } finally {
    window.clearTimeout(timer);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      'X-Session-Id': sessionId(),
    };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const raw = await res.text();
    let parsed: unknown = null;
    if (raw) {
      try {
        parsed = JSON.parse(raw) as unknown;
      } catch {
        parsed = raw;
      }
    }
    if (!res.ok) {
      const failure = ApiError.fromStatus(res.status, parsed);
      forgetAnalysisIfGone(failure);
      throw failure;
    }
    return parsed as T;
  } catch (err) {
    throw toApiError(err);
  } finally {
    window.clearTimeout(timer);
  }
}

/**
 * Drop the stored analysis pointer once the backend says that analysis is gone.
 *
 * The backend keeps analyses in process memory only, so every container restart
 * or redeploy destroys them all while the browser goes on holding the id in
 * localStorage. Without this the app asks for a dead analysis on every route and
 * renders the generic error page forever, and reloading cannot help because the
 * dead id is exactly what survives a reload. Clearing it sends the user back to
 * the "no analysis yet" state, which is the truth and is recoverable.
 */
function forgetAnalysisIfGone(err: ApiError): void {
  if (err.code === 'ANALYSIS_NOT_FOUND' && activeAnalysisId()) {
    setActiveAnalysisId(null);
    clearStore();
  }
}

/** Run the live call, or the fixture stand-in, according to the current mode. */
async function call<T>(live: () => Promise<T>, fixture: () => T): Promise<T> {
  const mode = dataSource.mode;
  if (mode === 'fixtures') return fixture();
  if (mode === 'auto' && dataSource.fellBack) return fixture();
  try {
    const out = await live();
    if (mode === 'auto') dataSource.clearFallback();
    return out;
  } catch (err) {
    const e = toApiError(err);
    if (mode === 'auto' && (e.kind === 'unreachable' || e.kind === 'timeout' || e.kind === 'offline')) {
      dataSource.markFellBack();
      return fixture();
    }
    throw e;
  }
}

/* =========================================================================
   FIXTURE BACKEND
   A tiny durable store so the demo survives a browser refresh on every route
   (spec §30 "test browser refresh on every major route").
   ====================================================================== */

const STORE_KEY = 'safespare.fixtureStore.v1';
const ACTIVE_KEY = 'safespare.activeAnalysis';
const GOAL_KEY = 'safespare.activeGoal';

/** Milliseconds each of the nine processing stages occupies. */
const STAGE_MS = 380;

interface FixtureStore {
  analysisId: string;
  startedAt: number;
  demo: boolean;
  fileName: string;
  deleteAfterProcessing: boolean;
  declaredCurrency: string | null;
  confirmed: boolean;
  deleted: boolean;
  txPatches: Record<string, TransactionPatch>;
  leakState: Record<string, { usage_status?: LeakFinding['usage_status']; decision?: LeakDecision }>;
  safeSpareSettings: SafeSpareSettings;
  roundUpRules: RoundUpRules;
  goal: Goal | null;
}

function blankStore(): FixtureStore {
  return {
    analysisId: FIXTURE_ANALYSIS_ID,
    startedAt: Date.now(),
    demo: true,
    fileName: 'demo_statement.csv',
    deleteAfterProcessing: true,
    declaredCurrency: null,
    confirmed: false,
    deleted: false,
    txPatches: {},
    leakState: {},
    safeSpareSettings: { ...DEFAULT_SAFE_SPARE_SETTINGS },
    roundUpRules: { ...DEFAULT_ROUNDUP_RULES, excluded_categories: [...DEFAULT_ROUNDUP_RULES.excluded_categories] },
    goal: null,
  };
}

let cached: FixtureStore | null = null;

function readStore(): FixtureStore | null {
  if (cached) return cached;
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return null;
    cached = { ...blankStore(), ...(JSON.parse(raw) as Partial<FixtureStore>) } as FixtureStore;
    return cached;
  } catch {
    return null;
  }
}

function writeStore(store: FixtureStore): FixtureStore {
  cached = store;
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    /* private mode — the in-memory copy still works for this tab */
  }
  return store;
}

function clearStore(): void {
  cached = null;
  try {
    window.localStorage.removeItem(STORE_KEY);
  } catch {
    /* ignore */
  }
}

/** The fixture store for an analysis id, or a not-found error. */
function need(analysisId: string): FixtureStore {
  const store = readStore();
  if (!store || store.deleted || store.analysisId !== analysisId) {
    throw new ApiError('not_found');
  }
  return store;
}

const r2 = (n: number): number => Math.round(n * 100) / 100;
const num = (v: unknown): number => {
  const n = typeof v === 'number' ? v : Number.parseFloat(String(v ?? ''));
  return Number.isFinite(n) ? n : 0;
};

/* --- transactions -------------------------------------------------------- */

/** MOCK BACKEND: apply stored corrections, exactly as PATCH would server-side. */
function patchedTransactions(store: FixtureStore): Transaction[] {
  return fixtureTransactions.map((tx) => {
    const p = store.txPatches[tx.id];
    if (!p) return tx;
    const next: Transaction = { ...tx, user_overridden: true, status: 'confirmed' };
    if (p.normalized_merchant !== undefined) {
      next.normalized_merchant = p.normalized_merchant;
      next.merchant_method = 'user_override';
      next.merchant_confidence = 1;
    }
    if (p.category !== undefined) {
      next.category = p.category;
      next.category_method = 'user_override';
      next.category_confidence = 1;
    }
    if (p.essentiality !== undefined) next.essentiality = p.essentiality;
    if (p.is_internal_transfer !== undefined) next.is_internal_transfer = p.is_internal_transfer;
    if (p.is_reimbursement !== undefined) next.is_reimbursement = p.is_reimbursement;
    if (p.excluded !== undefined) next.excluded = p.excluded;

    const direction = p.direction ?? tx.direction;
    const amount = p.amount !== undefined ? num(p.amount) : num(tx.debit ?? tx.credit);
    if (p.direction !== undefined || p.amount !== undefined) {
      next.direction = direction;
      next.debit = direction === 'debit' ? amount.toFixed(2) : null;
      next.credit = direction === 'credit' ? amount.toFixed(2) : null;
    }
    if (p.merge_into_transaction_id) {
      next.excluded = true;
      next.duplicate_of = p.merge_into_transaction_id;
    }
    if (next.validation_warnings.length) next.validation_warnings = [];
    return next;
  });
}

interface Totals {
  income: number;
  spending: number;
  essential: number;
  discretionary: number;
  byCategory: Map<Category, number>;
}

function totals(list: Transaction[]): Totals {
  const byCategory = new Map<Category, number>();
  let income = 0;
  let spending = 0;
  let essential = 0;
  let discretionary = 0;
  for (const tx of list) {
    if (tx.excluded) continue;
    if (tx.direction === 'credit') {
      if (tx.category === 'salary_income' || tx.category === 'other_income') income += num(tx.credit);
      continue;
    }
    if (tx.is_internal_transfer) continue;
    const amount = num(tx.debit);
    spending += amount;
    if (tx.essentiality === 'essential') essential += amount;
    else if (tx.essentiality === 'discretionary') discretionary += amount;
    byCategory.set(tx.category, (byCategory.get(tx.category) ?? 0) + amount);
  }
  return { income, spending, essential, discretionary, byCategory };
}

/* --- engines ------------------------------------------------------------- */

function safeSpareOf(store: FixtureStore): SafeSpareResponse {
  return fixtureSafeSpare(store.safeSpareSettings);
}

function roundUpsOf(store: FixtureStore): RoundUpsResponse {
  return fixtureRoundUps(store.roundUpRules, num(safeSpareOf(store).safe_monthly_contribution));
}

function leaksOf(store: FixtureStore): LeaksResponse {
  const map = new Map<string, Partial<LeakFinding>>();
  for (const [id, patch] of Object.entries(store.leakState)) {
    map.set(id, patch as Partial<LeakFinding>);
  }
  return fixtureLeaks(map);
}

/** The subset of a goal the API will accept, named the way the API names it.
 *
 * `GoalRequest` is the *client's* idea of a goal and carries four fields the
 * backend has never had — `kind`, `include_round_ups`,
 * `include_confirmed_recovered` and `annual_return_rate` — plus `kind` where
 * the schema says `goal_type`. `GoalRequest` on the server sets
 * `extra="forbid"`, so posting the object wholesale was rejected every time
 * with "some of the details supplied were not accepted" and no goal could be
 * created at all. Send exactly the accepted fields; the rest stay client-side.
 */
function goalWirePayload(req: GoalRequest): Record<string, unknown> {
  return {
    analysis_id: req.analysis_id,
    name: req.name,
    goal_type: req.kind,
    target_amount: req.target_amount,
    target_date: req.target_date,
    starting_principal: req.starting_principal,
  };
}

function simulationOf(store: FixtureStore, goal: Goal): SimulationResponse {
  const leaks = leaksOf(store);
  return fixtureSimulate(goal, {
    safeMonthly: num(safeSpareOf(store).safe_monthly_contribution),
    roundUps: num(roundUpsOf(store).allowed_round_up_total),
    confirmedRecovered: num(leaks.user_confirmed_recoverable_monthly),
  });
}

/**
 * MOCK BACKEND: the dashboard roll-up.
 *
 * Every headline figure is taken from the engine that owns it, so the numbers a
 * reviewer sees on the dashboard are the same numbers the Safe Spare, Round-Up
 * and Leak Radar pages show. User corrections move the spending aggregates by
 * their own delta rather than being ignored.
 */
function buildSummary(store: FixtureStore): AnalysisSummary {
  const txs = patchedTransactions(store);
  const base = totals(fixtureTransactions);
  const now = totals(txs);

  const ss = safeSpareOf(store);
  const ru = roundUpsOf(store);
  const leaks = leaksOf(store);

  const dIncome = now.income - base.income;
  const dSpending = now.spending - base.spending;
  const dEssential = now.essential - base.essential;
  const dDiscretionary = now.discretionary - base.discretionary;

  const categoryChart: SeriesPoint[] = fixtureSummary.charts.category_breakdown.map((row) => {
    const entry = Object.entries(CATEGORY_LABELS).find(([, label]) => label === row.label);
    const key = entry ? (entry[0] as Category) : null;
    if (!key) return row;
    const delta = (now.byCategory.get(key) ?? 0) - (base.byCategory.get(key) ?? 0);
    return { ...row, value: r2(Math.max(0, num(row.value) + delta)) };
  });

  const goal = store.goal;
  const sim = goal ? simulationOf(store, goal) : null;

  return {
    ...fixtureSummary,
    analysis_id: store.analysisId,
    currency: store.declaredCurrency ?? FIXTURE_CURRENCY,

    total_income: r2(num(fixtureSummary.total_income) + dIncome).toFixed(2),
    total_spending: r2(num(fixtureSummary.total_spending) + dSpending).toFixed(2),
    essential_spending: r2(num(fixtureSummary.essential_spending) + dEssential).toFixed(2),
    discretionary_spending: r2(num(fixtureSummary.discretionary_spending) + dDiscretionary).toFixed(2),

    potential_round_ups: ru.historical_round_up_total,
    safe_round_up_allowance: ru.allowed_round_up_total,
    potential_recoverable_spending: leaks.potential_recoverable_monthly,
    confirmed_recoverable_spending: leaks.user_confirmed_recoverable_monthly,
    high_confidence_recoverable_spending: leaks.high_confidence_recoverable_monthly,

    safe_spare_amount: ss.safe_monthly_contribution,
    safe_spare_confidence: ss.confidence,
    cashflow_confidence_score: fixtureConfidence.score,

    goal_progress: goal
      ? {
          goal_id: goal.id,
          goal_name: goal.name,
          target_amount: goal.target_amount,
          contributed_to_date: goal.starting_principal,
          percent_complete: r2(
            Math.min(100, (num(goal.starting_principal) / Math.max(1, num(goal.target_amount))) * 100),
          ),
        }
      : { goal_id: null, goal_name: null, target_amount: null, contributed_to_date: null, percent_complete: null },

    charts: {
      ...fixtureSummary.charts,
      category_breakdown: categoryChart,
      essential_vs_discretionary: [
        { label: 'Essential', value: r2(num(fixtureSummary.essential_spending) + dEssential) },
        { label: 'Discretionary', value: r2(num(fixtureSummary.discretionary_spending) + dDiscretionary) },
      ],
      principal_vs_growth: sim ? sim.timeline : [],
    },
    generated_at: new Date().toISOString(),
  };
}

/* --- AI Coach ------------------------------------------------------------ */

/** §6.11 — questions the coach must decline, whatever the provider says. */
const PROHIBITED =
  /(guarantee|guaranteed|risk[- ]?free|sure[- ]?shot)\b|\bwhich (stock|share|fund|crypto|coin|etf)|\bbuy (stock|shares|crypto|bitcoin)|\bbest (stock|fund|mutual fund|crypto)|\bdouble my money|\bhow much will i (earn|make)\b/i;

const COACH_DISCLAIMER =
  'SafeSpare is not a licensed financial adviser. Explanations describe figures the backend calculated; they never change them, and no securities are recommended.';

/**
 * MOCK BACKEND: composes the answer from the values the engines just produced,
 * so a quoted figure always equals the figure shown on the matching page
 * (spec §3.7, §3.8 — the model may phrase a verified value, never derive one).
 */
function coachAnswer(store: FixtureStore, question: string): ChatResponse {
  const id = `chat-${Date.now()}`;
  const base = { id, generated_offline: true, provider: null, validation_rejected: false, disclaimer: COACH_DISCLAIMER };

  if (PROHIBITED.test(question)) {
    return {
      ...base,
      answer:
        'I can’t answer that one, and I want to be straight about why.\n\n' +
        'No return can be guaranteed, and I never name a stock, fund, cryptocurrency or any other security. ' +
        'SafeSpare does not invest money — every projection here is an illustrative simulation, and actual returns may be higher, lower or negative.\n\n' +
        'What I can do is explain the figures the engine calculated: your Safe Spare amount, why round-ups were capped, what your recurring payments cost, or how a goal projection was built.',
      citations: [],
    };
  }

  const ss = safeSpareOf(store);
  const ru = roundUpsOf(store);
  const cur = store.declaredCurrency ?? FIXTURE_CURRENCY;
  const fmt = (v: unknown): string => `${cur === 'USD' ? '$' : `${cur} `}${num(v).toFixed(2)}`;

  if (/safe spare|safely|capped|why.*(limit|cap)|how much can i/i.test(question)) {
    return {
      ...base,
      answer:
        `Your safe monthly contribution is ${fmt(ss.safe_monthly_contribution)}.\n\n` +
        `It starts from a ${ss.balance_is_estimated ? 'estimated' : 'verified'} balance of ${fmt(ss.latest_verified_balance)}. ` +
        `Expected income before the next pay date adds ${fmt(ss.expected_income)}, and essential bills due before then take ` +
        `${fmt(ss.upcoming_essential_outflows)} out, leaving a projected ${fmt(ss.projected_balance_before_next_income)}.\n\n` +
        `A safety buffer of ${fmt(ss.safety_buffer)} and a volatility reserve of ${fmt(ss.volatility_reserve)} are then held back, ` +
        `which leaves ${fmt(ss.safe_spare_now)} available right now. ${ss.reason}`,
      citations: [
        { label: 'Latest balance', value: ss.latest_verified_balance, source: 'safe_spare.latest_verified_balance' },
        {
          label: 'Upcoming essential outflows',
          value: ss.upcoming_essential_outflows,
          source: 'safe_spare.upcoming_essential_outflows',
        },
        { label: 'Safety buffer', value: ss.safety_buffer, source: 'safe_spare.safety_buffer' },
        { label: 'Volatility reserve', value: ss.volatility_reserve, source: 'safe_spare.volatility_reserve' },
        {
          label: 'Safe monthly contribution',
          value: ss.safe_monthly_contribution,
          source: 'safe_spare.safe_monthly_contribution',
        },
      ],
    };
  }

  if (/round.?up|increment/i.test(question)) {
    return {
      ...base,
      answer:
        `${ru.explanation}\n\n` +
        `Round-ups can never exceed your safe monthly contribution of ${fmt(ru.safe_monthly_contribution)}. ` +
        `That is the difference between SafeSpare and an ordinary round-up app: the spare change is only spare once rent, ` +
        `insurance and other essentials due before your next income have been set aside.`,
      citations: [
        { label: 'Potential round-ups', value: ru.historical_round_up_total, source: 'roundups.historical_round_up_total' },
        { label: 'Allowed round-ups', value: ru.allowed_round_up_total, source: 'roundups.allowed_round_up_total' },
        { label: 'Limiting factor', value: ru.limiting_factor, source: 'roundups.limiting_factor' },
      ],
    };
  }

  if (/recurring|subscription|leak|cancel|gym/i.test(question)) {
    const leaks = leaksOf(store);
    const protectedCount = leaks.items.filter((f) => f.protected).length;
    return {
      ...base,
      answer:
        `I found ${fixtureRecurring.items.length} recurring payments totalling ${fmt(fixtureRecurring.total_monthly_recurring)} a month. ` +
        `${protectedCount} of them are protected essentials and are never put forward for cancellation.\n\n` +
        `Potentially recoverable: ${fmt(leaks.potential_recoverable_monthly)} a month. ` +
        `High-confidence: ${fmt(leaks.high_confidence_recoverable_monthly)}. ` +
        `Confirmed by you so far: ${fmt(leaks.user_confirmed_recoverable_monthly)}.\n\n` +
        `Bank data cannot show whether you actually use a service, so nothing is treated as unused until you say so on the Leak Radar page. ` +
        `Any action there is a draft for you to send — SafeSpare never contacts a merchant or cancels anything.`,
      citations: [
        { label: 'Recurring payments', value: String(fixtureRecurring.items.length), source: 'recurring.items' },
        {
          label: 'Monthly recurring total',
          value: fixtureRecurring.total_monthly_recurring,
          source: 'recurring.total_monthly_recurring',
        },
        {
          label: 'User-confirmed recoverable',
          value: leaks.user_confirmed_recoverable_monthly,
          source: 'leaks.user_confirmed_recoverable_monthly',
        },
      ],
    };
  }

  if (/goal|emergency|projection|simulat|grow/i.test(question)) {
    if (!store.goal) {
      return {
        ...base,
        answer:
          'You have not created a goal yet. Open the Goals page, pick a goal type, a target amount and a target date, and I can then explain exactly how the projection was built — including how much of the projected value is money you put in and how much is illustrative growth.\n\nIllustrative simulation only. Actual returns may be higher, lower or negative.',
        citations: [],
      };
    }
    const sim = simulationOf(store, store.goal);
    return {
      ...base,
      answer:
        `At ${fmt(sim.monthly_contribution)} a month towards “${store.goal.name}”, the simulation reaches ` +
        `${fmt(sim.projected_value)} after ${sim.months} months. ${fmt(sim.user_contributions)} of that is money you put in and ` +
        `${fmt(sim.illustrative_growth)} is illustrative growth — the two are always reported separately.\n\n` +
        `Reaching ${fmt(store.goal.target_amount)} in that time would need about ${fmt(sim.required_monthly_contribution)} a month, ` +
        `which is ${fmt(sim.contribution_shortfall)} more than is currently safe.\n\n${sim.disclaimer}`,
      citations: [
        { label: 'Your contributions', value: sim.user_contributions, source: 'simulation.user_contributions' },
        { label: 'Illustrative growth', value: sim.illustrative_growth, source: 'simulation.illustrative_growth' },
        { label: 'Projected value', value: sim.projected_value, source: 'simulation.projected_value' },
        {
          label: 'Required monthly contribution',
          value: sim.required_monthly_contribution,
          source: 'simulation.required_monthly_contribution',
        },
      ],
    };
  }

  /* Category questions and the generic fallback are already written against the
     fixture category totals, so they stay consistent. */
  return fixtureChat(question);
}

/* =========================================================================
   PUBLIC API — one function per §18 endpoint
   ====================================================================== */

export function activeAnalysisId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

function setActiveAnalysisId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(ACTIVE_KEY, id);
    else window.localStorage.removeItem(ACTIVE_KEY);
  } catch {
    /* ignore */
  }
}

/** The goal the user last created, so Goals survives a refresh in both modes. */
export function storedGoal(): Goal | null {
  try {
    const raw = window.localStorage.getItem(GOAL_KEY);
    return raw ? (JSON.parse(raw) as Goal) : null;
  } catch {
    return null;
  }
}

function setStoredGoal(goal: Goal | null): void {
  try {
    if (goal) window.localStorage.setItem(GOAL_KEY, JSON.stringify(goal));
    else window.localStorage.removeItem(GOAL_KEY);
  } catch {
    /* ignore */
  }
}

const fixtureCashflowConfidence: Omit<CashflowConfidenceResponse, 'analysis_id'> = {
  score: 78,
  band: 'predictable',
  components: [
    { key: 'income_regularity', label: 'Income regularity', weight_percent: 30, score: 0.94,
      weighted_points: 28.0, evidence: 'Income arrived 6 times with highly consistent timing and amounts.' },
    { key: 'essential_predictability', label: 'Essential-expense predictability', weight_percent: 25,
      score: 0.96, weighted_points: 24.0, evidence: 'Essential spending averaged $2,259 per month and was highly consistent.' },
    { key: 'buffer_coverage', label: 'Safety-buffer coverage', weight_percent: 30, score: 0.42,
      weighted_points: 12.7, evidence: 'A balance of $2,880 covers about 1.2 months of essential spending.' },
    { key: 'stability', label: 'Spending stability', weight_percent: 15, score: 0.92,
      weighted_points: 13.8, evidence: 'Total monthly spending averaged $3,155 and was highly consistent.' },
  ],
  confidence: 1.0,
  improvement_suggestions: [
    'Building the balance toward three months of essential spending would raise this component the most.',
  ],
  disclaimer:
    'Cashflow Confidence is not a credit score. It measures how predictable your income and essential spending are, and is never used to assess creditworthiness.',
  calculation_version: 'cashflow_confidence.v1',
};

export const api = {
  /* --- uploads / analyses ---------------------------------------------- */

  presignUpload(req: PresignRequest): Promise<PresignResponse> {
    return call(
      () => request<PresignResponse>('POST', '/api/uploads/presign', req),
      () => ({
        upload_id: `demo-upload-${Date.now()}`,
        upload_url: 'about:blank',
        fields: {},
        expires_in_seconds: 900,
        max_size_bytes: 15 * 1024 * 1024,
      }),
    );
  },

  createAnalysis(req: CreateAnalysisRequest): Promise<AnalysisRef> {
    return call(
      async () => {
        const ref = await request<AnalysisRef>('POST', '/api/analyses', req);
        setActiveAnalysisId(ref.analysis_id);
        return ref;
      },
      () => {
        const store = writeStore({
          ...blankStore(),
          startedAt: Date.now(),
          demo: req.demo === true,
          deleteAfterProcessing: req.delete_after_processing,
          declaredCurrency: req.declared_currency ?? null,
        });
        setStoredGoal(null);
        setActiveAnalysisId(store.analysisId);
        return { analysis_id: store.analysisId, state: 'UPLOADED' };
      },
    );
  },

  getStatus(analysisId: string): Promise<AnalysisStatus> {
    return call(
      () => request<AnalysisStatus>('GET', `/api/analyses/${analysisId}/status`),
      () => {
        const store = need(analysisId);
        const elapsed = Date.now() - store.startedAt;
        const status = fixtureStatus(Math.floor(elapsed / STAGE_MS));
        return { ...status, analysis_id: store.analysisId };
      },
    );
  },

  /** Detected currency, date range and parser warnings for the demo statement. */
  getDocumentMeta(): DetectedDocumentMeta {
    return fixtureDocumentMeta;
  },

  getSummary(analysisId: string): Promise<AnalysisSummary> {
    return call(
      () => request<AnalysisSummary>('GET', `/api/analyses/${analysisId}/summary`),
      () => buildSummary(need(analysisId)),
    );
  },

  getTransactions(analysisId: string): Promise<TransactionPage> {
    return call(
      () => request<TransactionPage>('GET', `/api/analyses/${analysisId}/transactions`),
      () => {
        const store = need(analysisId);
        const page = fixtureTransactionPage(patchedTransactions(store));
        return { ...page, analysis_id: store.analysisId };
      },
    );
  },

  patchTransaction(analysisId: string, transactionId: string, patch: TransactionPatch): Promise<Transaction> {
    return call(
      () => request<Transaction>('PATCH', `/api/transactions/${transactionId}`, patch),
      () => {
        const store = need(analysisId);
        const merged: TransactionPatch = { ...(store.txPatches[transactionId] ?? {}), ...patch };
        writeStore({ ...store, txPatches: { ...store.txPatches, [transactionId]: merged } });
        const updated = patchedTransactions(readStore() as FixtureStore).find((t) => t.id === transactionId);
        if (!updated) throw new ApiError('not_found');
        return updated;
      },
    );
  },

  bulkConfirm(req: BulkConfirmRequest): Promise<BulkConfirmResponse> {
    return call(
      () => request<BulkConfirmResponse>('POST', '/api/transactions/bulk-confirm', req),
      () => {
        const store = need(req.analysis_id);
        writeStore({ ...store, confirmed: true });
        return {
          analysis_id: store.analysisId,
          confirmed_count: patchedTransactions(store).filter((t) => !t.excluded).length,
          state: 'COMPLETED',
        };
      },
    );
  },

  /* --- intelligence ----------------------------------------------------- */

  getCategories(analysisId: string): Promise<CategoriesResponse> {
    return call(
      () => request<CategoriesResponse>('GET', `/api/analyses/${analysisId}/categories`),
      () => ({ ...fixtureCategories, analysis_id: need(analysisId).analysisId }),
    );
  },

  getRecurring(analysisId: string): Promise<RecurringResponse> {
    return call(
      () => request<RecurringResponse>('GET', `/api/analyses/${analysisId}/recurring`),
      () => ({ ...fixtureRecurring, analysis_id: need(analysisId).analysisId }),
    );
  },

  getLeaks(analysisId: string): Promise<LeaksResponse> {
    return call(
      () => request<LeaksResponse>('GET', `/api/analyses/${analysisId}/leaks`),
      () => {
        const store = need(analysisId);
        return { ...leaksOf(store), analysis_id: store.analysisId };
      },
    );
  },

  confirmUsage(analysisId: string, leakId: string, req: UsageConfirmationRequest): Promise<LeaksResponse> {
    return call(
      async () => {
        await request<unknown>('POST', `/api/leaks/${leakId}/usage-confirmation`, req);
        return request<LeaksResponse>('GET', `/api/analyses/${analysisId}/leaks`);
      },
      () => {
        const store = need(analysisId);
        const prev = store.leakState[leakId] ?? {};
        writeStore({
          ...store,
          leakState: { ...store.leakState, [leakId]: { ...prev, usage_status: req.usage_status } },
        });
        return leaksOf(readStore() as FixtureStore);
      },
    );
  },

  decideLeak(analysisId: string, leakId: string, req: DecisionRequest): Promise<LeaksResponse> {
    return call(
      async () => {
        await request<unknown>('POST', `/api/leaks/${leakId}/decision`, req);
        return request<LeaksResponse>('GET', `/api/analyses/${analysisId}/leaks`);
      },
      () => {
        const store = need(analysisId);
        const finding = leaksOf(store).items.find((f) => f.id === leakId);
        if (!finding) throw new ApiError('not_found');
        /* Guardrail §25.5–§25.8: a protected essential can never be marked for
           cancellation, whatever the client sends. */
        if (finding.protected && (req.decision === 'cancel' || req.decision === 'downgrade')) {
          throw new ApiError('validation', { code: 'PROTECTED_FINDING' });
        }
        const prev = store.leakState[leakId] ?? {};
        writeStore({ ...store, leakState: { ...store.leakState, [leakId]: { ...prev, decision: req.decision } } });
        return leaksOf(readStore() as FixtureStore);
      },
    );
  },

  draftAction(analysisId: string, leakId: string, req: DraftActionRequest): Promise<DraftActionResponse> {
    return call(
      () => request<DraftActionResponse>('POST', `/api/leaks/${leakId}/draft-action`, req),
      () => {
        const store = need(analysisId);
        const finding = leaksOf(store).items.find((f) => f.id === leakId);
        if (!finding) throw new ApiError('not_found');
        return fixtureDraft(finding, req.action);
      },
    );
  },

  /* --- Safe Spare ------------------------------------------------------- */

  getSafeSpare(analysisId: string): Promise<SafeSpareResponse> {
    return call(
      () => request<SafeSpareResponse>('GET', `/api/analyses/${analysisId}/safe-spare`),
      () => {
        const store = need(analysisId);
        return { ...safeSpareOf(store), analysis_id: store.analysisId };
      },
    );
  },

  updateSafeSpareSettings(analysisId: string, settings: SafeSpareSettings): Promise<SafeSpareResponse> {
    return call(
      () => request<SafeSpareResponse>('PATCH', `/api/analyses/${analysisId}/safe-spare-settings`, settings),
      () => {
        const store = need(analysisId);
        writeStore({ ...store, safeSpareSettings: settings });
        return safeSpareOf(readStore() as FixtureStore);
      },
    );
  },

  /* --- round-ups -------------------------------------------------------- */

  getRoundUps(analysisId: string): Promise<RoundUpsResponse> {
    return call(
      () => request<RoundUpsResponse>('GET', `/api/analyses/${analysisId}/roundups`),
      () => {
        const store = need(analysisId);
        return { ...roundUpsOf(store), analysis_id: store.analysisId };
      },
    );
  },

  // Takes a *partial* patch, and only of the fields the server will accept.
  // `RoundUpRules` also carries `large_transaction_threshold`, which the server
  // computes and `RoundUpRulesPatch` does not declare; since that schema sets
  // `extra="forbid"`, sending the whole rules object back would be rejected
  // outright — the same trap that stopped goals from being created at all.
  updateRoundUpRules(analysisId: string, patch: RoundUpRulesPatch): Promise<RoundUpsResponse> {
    return call(
      () => request<RoundUpsResponse>('PATCH', `/api/analyses/${analysisId}/roundup-rules`, patch),
      () => {
        const store = need(analysisId);
        // The fixture store holds whole rules, so merge the patch onto what is
        // already there rather than replacing it with a partial object.
        const rules: RoundUpRules = { ...store.roundUpRules, ...patch };
        writeStore({ ...store, roundUpRules: rules });
        return roundUpsOf(readStore() as FixtureStore);
      },
    );
  },

  /* --- goals ------------------------------------------------------------ */

  createGoal(req: GoalRequest): Promise<Goal> {
    return call(
      async () => {
        const goal = await request<Goal>('POST', '/api/goals', goalWirePayload(req));
        // The response carries only the fields the backend stores. Preferences
        // like the return rate live on the client, so merge them back on or the
        // simulation loses the rate the user just picked.
        const merged = { ...req, ...goal };
        setStoredGoal(merged);
        return merged;
      },
      () => {
        const store = need(req.analysis_id);
        const goal = fixtureGoalFromRequest(req, 'demo-goal-001');
        writeStore({ ...store, goal });
        setStoredGoal(goal);
        return goal;
      },
    );
  },

  updateGoal(goalId: string, req: GoalRequest): Promise<Goal> {
    return call(
      async () => {
        // GoalPatch accepts only these four; analysis_id and goal_type are not
        // patchable and would be rejected outright.
        const goal = await request<Goal>('PATCH', `/api/goals/${goalId}`, {
          name: req.name,
          target_amount: req.target_amount,
          target_date: req.target_date,
          starting_principal: req.starting_principal,
        });
        const merged = { ...req, ...goal };
        setStoredGoal(merged);
        return merged;
      },
      () => {
        const store = need(req.analysis_id);
        const goal: Goal = { ...fixtureGoalFromRequest(req, goalId), created_at: store.goal?.created_at ?? new Date().toISOString() };
        writeStore({ ...store, goal });
        setStoredGoal(goal);
        return goal;
      },
    );
  },

  simulateGoal(analysisId: string, goalId: string, annualReturnRate?: number): Promise<SimulationResponse> {
    return call(
      // SimulateRequest takes the projection assumptions and nothing else — the
      // goal id in the path already identifies the analysis, and sending
      // `analysis_id` in the body was rejected as an unexpected field.
      () => request<SimulationResponse>('POST', `/api/goals/${goalId}/simulate`,
        annualReturnRate === undefined ? {} : { annual_return_rate: String(annualReturnRate) }),
      () => {
        const store = need(analysisId);
        if (!store.goal || store.goal.id !== goalId) throw new ApiError('not_found');
        return simulationOf(store, store.goal);
      },
    );
  },

  /* --- coach, voice ----------------------------------------------------- */

  chat(req: ChatRequest): Promise<ChatResponse> {
    return call(
      () => request<ChatResponse>('POST', '/api/insights/chat', req),
      () => coachAnswer(need(req.analysis_id), req.question),
    );
  },

  voiceSummary(analysisId: string): Promise<VoiceSummaryResponse> {
    return call(
      () => request<VoiceSummaryResponse>('POST', '/api/voice/summary', { analysis_id: analysisId }),
      () => {
        const store = need(analysisId);
        return { ...fixtureVoice, analysis_id: store.analysisId, generated_at: new Date().toISOString() };
      },
    );
  },

  /* --- privacy ---------------------------------------------------------- */

  deleteAnalysis(analysisId: string): Promise<DeleteResponse> {
    return call(
      async () => {
        const out = await request<DeleteResponse>('DELETE', `/api/analyses/${analysisId}`);
        setActiveAnalysisId(null);
        setStoredGoal(null);
        return out;
      },
      () => {
        need(analysisId);
        clearStore();
        setActiveAnalysisId(null);
        setStoredGoal(null);
        return {
          deleted: true,
          analysis_id: analysisId,
          deleted_at: new Date().toISOString(),
          message: 'The analysis, its extracted transactions and every figure derived from them have been removed.',
        };
      },
    );
  },

  deleteAllData(): Promise<DeleteResponse> {
    return call(
      async () => {
        const out = await request<DeleteResponse>('POST', '/api/privacy/delete-data', {});
        setActiveAnalysisId(null);
        setStoredGoal(null);
        return out;
      },
      () => {
        clearStore();
        setActiveAnalysisId(null);
        setStoredGoal(null);
        return {
          deleted: true,
          deleted_at: new Date().toISOString(),
          message: 'Every analysis held for this browser has been removed, along with the uploaded document copy.',
        };
      },
    );
  },

  /** §6.7 — Cashflow Confidence. Not a credit score. */
  getCashflowConfidence(analysisId: string): Promise<CashflowConfidenceResponse> {
    return call(
      () => request<CashflowConfidenceResponse>('GET', `/api/analyses/${analysisId}/cashflow-confidence`),
      () => ({ ...fixtureCashflowConfidence, analysis_id: need(analysisId).analysisId }),
    );
  },

  /** Uploads the file body against a presign grant. */
  async uploadContent(grant: PresignResponse, file: File): Promise<void> {
    if (dataSource.usingFixtures) return;
    const form = new FormData();
    form.append('file', file, file.name);
    await requestRaw('POST', `/api/uploads/${grant.upload_id}/content`, form);
  },

  health(): Promise<HealthResponse> {
    return call(
      () => request<HealthResponse>('GET', '/health'),
      () => ({ status: 'fixtures', version: 'demo' }),
    );
  },
};

export type Api = typeof api;
