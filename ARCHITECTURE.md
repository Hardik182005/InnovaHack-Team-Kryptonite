# Architecture

This describes what the codebase actually contains as of 2026-07-25, verified by reading every file
in `backend/app/models/` and `backend/app/services/`, running the test suite, and running the real
demo statement through the engines directly. Where a layer from the build spec does not exist yet,
that is stated explicitly rather than described as if it were built.

## System overview

```
┌─────────────────────────────────────────────────────────────────────┐
│ frontend/  (React + Vite + TS)                                      │
│   scaffolded only: package.json, vite.config.ts, tokens.css         │
│   no pages, components, routing or API client exist yet             │
└───────────────────────────┬───────────────────────────────────────────┘
                             │ HTTP (planned — see API_DOCUMENTATION.md)
┌───────────────────────────▼───────────────────────────────────────────┐
│ backend/app/api/            FastAPI routes — NOT YET IMPLEMENTED     │
│   (empty package: only __init__.py exists)                          │
├───────────────────────────────────────────────────────────────────────┤
│ backend/app/ai/              provider adapters — NOT YET IMPLEMENTED │
│   (empty package: only __init__.py exists; no API keys configured)  │
├───────────────────────────────────────────────────────────────────────┤
│ backend/app/services/        ★ THE DETERMINISTIC FINANCIAL CORE ★    │
│   extraction → validation → merchant_normalization → categorization │
│   → recurrence → price_changes → leak_score → safe_spare → roundups │
│   → projections                                                     │
│   Pure Python, Decimal-only money, zero network calls, 78/78 tests  │
├───────────────────────────────────────────────────────────────────────┤
│ backend/app/models/           Transaction, enums, category taxonomy │
└───────────────────────────────────────────────────────────────────────┘
                             │
┌───────────────────────────▼───────────────────────────────────────────┐
│ infra/                       Terraform + AWS — DOES NOT EXIST YET    │
│   terraform and aws CLI are not installed in this environment        │
└───────────────────────────────────────────────────────────────────────┘
```

## Why the deterministic core is dependency-free dataclasses, not Pydantic

`backend/app/models/transaction.py` uses plain `@dataclass`, not Pydantic, and says why in its own
docstring: the engines are the financial source of truth (spec §3.7, §16) and must be importable and
unit-testable with no web framework, no database and no network. Pydantic is reserved for the future
API boundary and for validating LLM output — the actual place spec §16 requires it.

All money is `Decimal`, never `float`. The single coercion point is `money()`:

```python
# backend/app/models/transaction.py
TWO_PLACES = Decimal("0.01")

def money(value) -> Decimal:
    """Coerce to a 2dp Decimal without going through binary float."""
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    return d.quantize(TWO_PLACES)
```

`test_money_uses_decimal_not_float` feeds it the classic float trap `0.1 + 0.2` (`0.30000000000000004`
as a float) and asserts it comes out `Decimal("0.30")`.

A signed import is normalized rather than rejected: `Transaction.__post_init__` flips a negative
amount into `amount=abs(x)` plus the opposite `Direction`, so a reversed-sign CSV export can never
silently become a negative debit (`test_signed_amount_is_normalised_to_direction`).

## The pipeline, module by module

### 1. Extraction — `backend/app/services/extraction.py` (spec §7)

Layered by cost/certainty: CSV via stdlib `csv` with flexible column-alias mapping
(`COLUMN_ALIASES`), XLSX via `pandas` (optional import, degrades to a warning if absent), digital PDF
via `pdfplumber` first (`extract_pdf`), falling back to `PyMuPDF` if `pdfplumber` isn't installed, and
SMS/email alerts via regex (`extract_sms`). Every row keeps its `parser`, `source_page`/`source_row`
and `extraction_confidence` — nothing is silently dropped (§8). `deduplicate()` matches on
`(date, amount, direction, merchant, reference)` and returns both kept and removed rows so the caller
can show what was merged.

Account masks captured from SMS text are deliberately **not** stored on the `Transaction` — only a
`validation_warnings=["account_mask_discarded"]` flag survives (§22).

### 2. Validation — `backend/app/services/validation.py` (spec §8)

`validate()` runs six checks and annotates rows, never deletes them: per-row sanity (`_check_rows`),
exact duplicates (`_check_duplicates`), date-range/ambiguity (`_check_date_range`), mixed currency
(`_check_currency`), transfer-pair matching within a 3-day window (`_check_transfer_pairs`), and
running-balance reconciliation (`_check_running_balance`) — which also detects a reversed
debit/credit by checking whether the mismatch is exactly `2 × amount`.

### 3. Merchant normalization — `backend/app/services/merchant_normalization.py` (spec §9)

Resolution ladder, cheapest and most certain first: exact alias → regex/substring alias → fuzzy match
(RapidFuzz if installed, stdlib `difflib` otherwise) → (embeddings/LLM fallback live in `app/ai`,
not yet built) → user review. `resolve_merchant()` records which rung resolved each row
(`method`, `confidence`). The spec's own worked example — `NETFLIX.COM` / `NETFLIX INDIA` /
`NFX*SUBSCRIPTION` all resolving to `Netflix` — is a literal parametrized test
(`test_netflix_variants_resolve_together`).

One real bug found and fixed by these tests during Phase 2 (per `IMPLEMENTATION_STATUS.md`): the
noise-stripping regex kept short digit runs, so `QUIRKY BEANS CO 123` scored just under the 0.86
fuzzy threshold against `QUIRKY BEANS` and split into two merchants. The fix strips standalone digit
runs of 2+ digits (`r"\b\d{2,}\b"` in `_NOISE_PATTERNS`).

### 4. Categorization — `backend/app/services/categorization.py` (spec §10)

Ensemble in order: merchant dictionary (`MERCHANT_CATEGORIES`, confidence 0.95) → ordered keyword/regex
rules (`KEYWORD_RULES`, confidence 0.82) → direction-based fallback for credits (confidence 0.5) →
`Category.UNKNOWN` (confidence 0.3). The module's docstring is explicit that no labelled training set
exists, so this is rules-plus-dictionary and says so rather than dressing up an untrained classifier.
`classify_transactions()` skips any row the user already corrected (`user_overridden`).

### 5. Recurrence detection — `backend/app/services/recurrence.py` (spec §11)

Groups debits by normalized merchant key and scores each group with the exact spec formula:

```
recurrence_confidence =
    0.35 × interval_regularity
  + 0.25 × merchant_similarity
  + 0.20 × amount_stability
  + 0.20 × occurrence_strength
```

implemented verbatim in `detect_recurring()`. Bands: ≥90 `CONFIRMED`, 70–89 `LIKELY`, <70
`NEEDS_REVIEW` (`_status_for`). Three occurrences are required for `CONFIRMED` unless the cadence is
`ANNUAL`, where two charges a year apart is the strongest evidence available
(`MIN_OCCURRENCES_FOR_CONFIRMED`). `VARIABLE_AMOUNT_CATEGORIES` (utilities, fuel, medical) get a 3×
wider amount-stability tolerance so a fluctuating utility bill isn't penalized for being a utility
bill — but `amount_varies` is computed from the *strict* (non-lenient) stability so a genuine swing is
still flagged. This distinction was the second real bug found in Phase 2: `amount_varies` used to
read the lenient score, so a utility bill swinging $79→$112 reported as "not varying."

### 6. Price-increase detection — `backend/app/services/price_changes.py` (spec §12)

`detect_price_changes()` compares the latest charge against a **baseline**, not just the previous
payment — `_baseline()` takes the *minimum* of {previous payment, median, rolling average} over the
prior charges, so a hike that happened three cycles ago and has been stable since is still measured
against the old price. Both an absolute (`$1.00`) and a percentage (`5.0%`) threshold must be cleared
(`DEFAULT_MIN_ABSOLUTE_INCREASE`, `DEFAULT_MIN_PERCENTAGE_INCREASE`). Confidence in the hike is capped
by confidence in the underlying recurrence pattern (`_confidence`) — a hike on a shaky pattern cannot
be more certain than the pattern itself.

### 7. Leak Radar scoring — `backend/app/services/leak_score.py` (spec §13)

Only categories in `LEAK_ELIGIBLE_CATEGORIES` (subscription, software, entertainment, fitness,
dining/delivery, shopping, travel) — or protected essentials, shown but capped — are scored at all.
The exact spec formula, implemented verbatim in `score_leaks()`:

```
leak_score =
    0.25 × price_hike_severity
  + 0.20 × duplicate_probability
  + 0.15 × cost_burden
  + 0.15 × recurrence_commitment
  + 0.25 × confirmed_non_usage
```

`confirmed_non_usage` is the load-bearing rule: it is non-zero **only** when the user has explicitly
said so (`UsageStatus.CONFIRMED_NOT_USED` → 1.0, `NOT_RECOGNIZED` → 0.9, `CONFIRMED_OCCASIONAL` → 0.4;
`UNKNOWN` and `POSSIBLY_UNDERUSED` → 0.0). While usage is unknown, the score is hard-capped at 79
(`UNKNOWN_USAGE_CAP`), one point below the "strong cancellation review" band, and protected essentials
are floored into the review band regardless of score. `_actions()` only ever offers
`LeakDecision.CANCEL` after non-usage is confirmed on a non-protected finding.

**Verified integration gap found while writing this documentation**: `DUPLICATE_GROUPS["cloud_storage"]`
matches merchant names containing `dropbox`, `google one`, `icloud`, `onedrive` or `box`. Running the
real demo statement through the pipeline (extraction → normalization → categorization → recurrence →
leak scoring) shows the demo's "Cloudvault Storage Plus" merchant normalizes to that literal name and
categorizes as `Category.UNKNOWN` (no keyword or dictionary entry matches "storage"). Because
`score_leaks()` skips any pattern whose category is neither protected nor in
`LEAK_ELIGIBLE_CATEGORIES`, Cloudvault never reaches the duplicate-detection or price-hike-severity
logic at all — even though `price_changes.detect_price_changes()` (which is not category-filtered)
does correctly detect its 9.99→13.99 (40%) increase at the module level. The demo statement's intended
"silent price increase" and "duplicate cloud-storage service" story is therefore only partially wired
end-to-end today. This is a categorization-dictionary gap (`categorization.py` has no `storage`/`cloud`
keyword and no `cloudvault` dictionary entry), not a flaw in the leak-scoring formula itself.

### 8. Safe Spare Engine — `backend/app/services/safe_spare.py` (spec §6.6) — the product's core

```
projected_balance_before_next_income =
    latest_verified_balance + expected_income_before_next_income
    - expected_essential_outflows_before_next_income

safety_buffer =
    max(user_minimum_buffer, buffer_percentage × average_monthly_essential_spending)

volatility_reserve =
    volatility_multiplier × stdev(recent_monthly_outflows)

safe_spare_now =
    max(0, projected_balance_before_next_income - safety_buffer - volatility_reserve)

safe_monthly_contribution =
    min(safe_spare_now, calculated_monthly_surplus, user_monthly_cap)
```

This is `compute_safe_spare()` line for line. `_stdev()` is a hand-rolled Decimal sample standard
deviation (not `statistics.stdev`) specifically so float rounding can never leak into a number that
reduces someone's contribution. `safe_spare_now` is clamped with `max(ZERO, …)` — it is structurally
impossible for this function to return a negative value (guardrail 1).

`build_inputs()` derives every one of those inputs from real transactions: it takes the latest row
that actually carries a balance; when none exists it falls back to a cash-flow estimate
(`inflow - outflow`) and sets `balance_is_estimated = True`, which both lowers `_confidence()` (never
above 0.6 when estimated) and is stated in the human-readable `_explain()` text. Next-income date is
the median historical gap between salary credits; a single-salary user's own upcoming paycheck is
deliberately **not** added to `expected_income_before_next_income` — crediting it would double-count a
paycheck the user hasn't received yet, exactly the mistake the product exists to avoid (see the
in-code comment in `build_inputs`).

`apply_confirmed_recovery()` is the only way a Leak Radar decision can move the needle: it adds
*already-confirmed* recoverable spend to `safe_monthly_contribution` and appends a sentence to
`reason`; unconfirmed or potential recoverable amounts never reach this function (guardrail 10).

### 9. Smart Round-Up Engine — `backend/app/services/roundups.py` (spec §6.8)

```
round_up = ceil(amount / increment) × increment - amount
```

`round_up_for_amount()` implements this with `Decimal.to_integral_value(rounding=ROUND_CEILING)`.
`calculate_roundups()` walks every transaction, records *why* each is ineligible
(`_ineligibility_reason`: excluded by user, credit, internal transfer, reimbursement, excluded
category, marked essential, low-confidence unknown category, excluded merchant, or above
`DEFAULT_LARGE_TRANSACTION_THRESHOLD = $2000.00`), then clamps the total:

```
allowed_round_up_total = min(historical_round_up_total, monthly_cap, user_round_up_cap, safe_monthly_contribution)
```

`result.limiting_factor` records which ceiling actually bound the number, and `_explain()` always
produces a human sentence — a silent `$0.00` is treated as a bug in the spec, not an acceptable UI
state.

### 10. Goal simulation — `backend/app/services/projections.py` (spec §6.10)

```
FV = P(1+r)^n + C × (((1+r)^n − 1) / r)
```

`future_value()` implements the end-of-month annuity formula, with an explicit `monthly_rate == 0`
branch (`P + C×n`) rather than letting the general formula divide by zero — required because
"contributions only" is one of the four mandated scenarios (`SCENARIOS`), not an edge case to tolerate.
`simulate()` always reports `user_contributions` and `illustrative_growth` as two separate numbers
computed as `growth = projected − contributions` — never a single blended figure — and every
`SimulationResult` carries `ILLUSTRATIVE_DISCLAIMER` ("Illustrative simulation only. Actual returns
may be higher, lower or negative."). `months_to_target()` is iterative (not closed-form) specifically
so it stays correct in the zero-rate and zero-contribution cases, returning `None` when a goal is
mathematically unreachable.

## Category taxonomy and protection sets — `backend/app/models/enums.py`

The 26 categories from spec §6.5 are an `Enum`. Three frozensets, defined once and imported
everywhere else, are what make the guardrails provable rather than merely asserted:

| Set | Members | Used by |
| --- | --- | --- |
| `ESSENTIAL_CATEGORIES` | rent, utilities, groceries, medical, insurance, loan/EMI, tax, education, childcare | Safe Spare's essential-outflow projection |
| `PROTECTED_FROM_CANCELLATION` | rent, loan/EMI, insurance, tax, medical, utilities, education, childcare | Leak Radar — hard-blocks `CANCEL` regardless of score |
| `ROUNDUP_EXCLUDED_CATEGORIES` | protected categories + transfers, withdrawals, savings, investment, refunds, bank charges, salary, other income | Round-up eligibility |

`default_essentiality()` deliberately leaves `Category.UNKNOWN` as `Essentiality.UNKNOWN` rather than
defaulting to discretionary, so an unclassified transaction can never be silently swept into round-up
eligibility.

## Calculation provenance

Every service module stamps its dataclasses with a `CALCULATION_VERSION` string (e.g.
`"safe_spare.v1"`, `"roundups.v1"`, `"leak_score.v1"`) and, where relevant, `source_transaction_ids` /
`evidence_transaction_ids`. This is the concrete mechanism behind spec §20's "every calculated record
must store calculation version, source transaction IDs, confidence and method" — it already exists in
every result dataclass (`SafeSpareResult`, `RoundUpResult`, `LeakFinding`, `RecurrencePattern`,
`PriceChange`, `SimulationResult`), it is just not yet persisted anywhere because there is no database
layer or repository implementation yet (`backend/app/repositories/` is an empty stub).

## What is designed but not yet built

| Component | Spec ref | Current state |
| --- | --- | --- |
| Analysis state machine (`UPLOADED → … → COMPLETED`) | §19 | Not implemented — no orchestration layer exists yet |
| FastAPI routes (`backend/app/api/*.py`) | §18 | Empty package; see `API_DOCUMENTATION.md` for the planned surface |
| AI provider adapters (`backend/app/ai/*.py`) | §14 | Empty package; see `AI_MODEL_ROUTING.md` |
| Repositories / persistence (`backend/app/repositories/`) | §20 | Empty package; no database connected |
| Storage / privacy services (`storage.py`, `privacy.py`) | §21, §22 | Not present in `backend/app/services/` yet |
| Frontend pages and API client | §6 | `frontend/` has build tooling and one CSS tokens file only |
| Infrastructure (`infra/terraform`, `infra/scripts`) | §21 | Directory does not exist |

## Frontend visual system (as extracted, per `IMPLEMENTATION_STATUS.md`)

The approved design source is `design/Perch Site.dc.html` (a Claude Design export, not a runnable
app). The extracted token system — measured directly from that file — is what `frontend/src/styles/tokens.css`
is porting into the SPA:

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#F7F4ED` | page background |
| `--ink` | `#14120F` | primary text / dark panels |
| `--accent` | `#2438E0` | brand blue |
| `--positive` / `--positive-soft` | `#1E8A5F` / `#8CE0B0` | gains, confirmed savings |
| `--warning` / `--warning-soft` | `#D2432A` / `#FFB08F` | price hikes, escalation |
| Display type | Space Grotesk | headings, numerals |
| Data/label type | IBM Plex Mono | uppercase micro-labels, figures |
| Body type | Figtree | prose |
