# SafeSpare AI

**"Invest only what life can safely spare."**

```
Selected Track:
FinTech — Problem Statement 2: Smart Expense & Micro-Investment Assistant

Supporting intelligence:
Recurring-payment and price-leak detection inspired by Problem Statement 1.
```

This is not an Open Innovation entry and it is not two problem statements. SafeSpare AI is a
Problem Statement 2 product — a smart expense and micro-investment assistant. The recurring-payment,
subscription-leak and silent-price-increase detection (Problem Statement 1's domain) exist only to
feed one metric the product actually ships: how much money the user can *safely* redirect toward a
goal this month.

## The problem with round-up apps

> Traditional round-up applications assume spare change is always safe to invest. SafeSpare first
> understands income, essential obligations, upcoming bills, spending volatility and safety buffer,
> then calculates how much can responsibly be spared.

An ordinary round-up app looks at a $4.30 coffee, rounds to $5.00, and invests the $0.70 — regardless
of whether rent is due tomorrow. SafeSpare's core engine (`backend/app/services/safe_spare.py`)
computes a **safety buffer** and a **volatility reserve** from the user's own transaction history
first, and only what clears both is ever offered up for round-ups or goal contributions.

Verified against the bundled synthetic demo statement (`demo_data/demo_statement.csv`, 195
transactions, 6 months, see `TEST_REPORT.md` for the run): historical round-ups on that statement
total **$31.60** for the partial period ending 2026-06-02, but the Safe Spare engine allows only
**$18.36** of it — the rest is reserved because rent, insurance, the auto loan and utilities are due
before the next payday. That gap between "spare change exists" and "spare change is safe" is the
entire product.

## Primary flow

```
UNDERSTAND → PROTECT → RECOVER → ROUND UP → REDIRECT → SIMULATE → GROW
```

| Stage | What happens | Backend module |
| --- | --- | --- |
| UNDERSTAND | Extract, validate, normalize and categorize every transaction | `services/extraction.py`, `validation.py`, `merchant_normalization.py`, `categorization.py` |
| PROTECT | Compute the safety buffer and volatility reserve; essentials are never touched | `services/safe_spare.py` |
| RECOVER | Detect recurring payments, price hikes and possible duplicate subscriptions; only user-confirmed non-usage counts | `services/recurrence.py`, `price_changes.py`, `leak_score.py` |
| ROUND UP | Compute historical vs. allowed round-ups, capped by Safe Spare and user rules | `services/roundups.py` |
| REDIRECT | Confirmed recovered spend + allowed round-ups raise the monthly contribution | `safe_spare.apply_confirmed_recovery`, `leak_score.confirmed_recoverable_from_decisions` |
| SIMULATE | Deterministic future-value projection toward a goal, principal vs. growth kept separate | `services/projections.py` |
| GROW | Illustrative only — no real investment is ever executed | `projections.ILLUSTRATIVE_DISCLAIMER` |

## What actually exists right now (2026-07-25)

This is a hackathon build in progress; other agents are actively writing the API, AI and frontend
layers while this documentation was written. Do not read this README as "finished product" — read
`IMPLEMENTATION_STATUS.md` for the live, authoritative status. As last verified directly against the
repository and by running the test suite myself:

| Layer | Status | Evidence |
| --- | --- | --- |
| Deterministic financial core (`backend/app/models`, `backend/app/services`) | **Built.** 9 modules, `Decimal`-only money math, no network calls | `backend/app/services/*.py` |
| Backend test suite | **78/78 passing** (50 unit + 28 mandatory guardrail tests), 0.04s | `cd backend && .venv/bin/python -m pytest tests/ -q` — see `TEST_REPORT.md` |
| Demo data generator | **Built.** Produces a reconciling synthetic CSV + text-layer PDF | `scripts/generate_demo_statement.py` → `demo_data/` |
| FastAPI HTTP layer (`backend/app/api/`) | **Not built.** Only an empty `__init__.py` exists | see `API_DOCUMENTATION.md` |
| AI provider layer (`backend/app/ai/`) | **Not built.** Only an empty `__init__.py` exists; no LLM keys configured in this environment | see `AI_MODEL_ROUTING.md` |
| Frontend (`frontend/`) | **Scaffolded only.** Vite + React + TS config, one design-tokens CSS file, no pages/components yet | `frontend/package.json`, `frontend/src/styles/tokens.css` |
| Infrastructure (`infra/`) | **Does not exist yet.** `terraform` and `aws` CLI are not installed in this environment | see `AWS_DEPLOYMENT.md` |

Everything documented in `FINANCIAL_GUARDRAILS.md`, `TEST_REPORT.md` and the formulas below is real
and independently re-verified while writing these docs, not assumed from the build spec.

## Repository layout

```
backend/
  app/
    models/       Decimal-based dataclasses: Transaction, enums, categories (§20)
    services/     the deterministic financial core — see ARCHITECTURE.md
    api/          FastAPI routes — not yet implemented (stub only)
    ai/           provider adapters (Gemini/Groq/OpenAI/ElevenLabs) — not yet implemented (stub only)
  tests/          test_engines.py (50), test_guardrails.py (28)
frontend/         React + Vite + TypeScript SPA — scaffold only, in progress
design/           Original Claude Design ("Perch") export — the visual source of truth for tokens
demo_data/        Generated synthetic demo statement (CSV + PDF)
scripts/          generate_demo_statement.py
infra/            AWS Terraform + deploy scripts — not created yet
```

## Running the backend tests

```bash
cd backend
.venv/bin/python -m pytest tests/ -q
```

Real output as of this writing:

```
78 passed in 0.04s
```

No API keys, network access, terraform or AWS CLI are required for this — the deterministic core has
zero external dependencies by design (spec §3.21: the app must keep working if every LLM API is
down).

## Documentation index

| Document | Covers |
| --- | --- |
| `ARCHITECTURE.md` | System design, module boundaries, data flow, real formulas |
| `AI_MODEL_ROUTING.md` | Confidence-based provider routing, deterministic fallback |
| `FINANCIAL_GUARDRAILS.md` | All 20 mandatory guardrails and their real, current verification status |
| `PRIVACY_AND_SECURITY.md` | File handling, PII, logging, prompt-injection posture |
| `AWS_DEPLOYMENT.md` | Target architecture and exact deploy commands (nothing deployed yet) |
| `API_DOCUMENTATION.md` | Planned HTTP surface, grounded in the real service dataclasses |
| `JUDGE_DEMO.md` | The 5-minute demo script, with real numbers computed from the demo statement |
| `TEST_REPORT.md` | The actual pytest run, numbers and environment |
| `IMPLEMENTATION_STATUS.md` | Live build log — owned by a different process, not this one |

## Non-negotiable product rules (spec §3, enforced in code)

- LLMs never calculate a financial value — every number in this product comes from
  `backend/app/services/`. See `AI_MODEL_ROUTING.md` and `FINANCIAL_GUARDRAILS.md` guardrail 16.
- No real investment, transfer, cancellation or trade is ever executed. Guardrail 20 includes a
  structural test (`test_25_20_no_execution_side_effects_exist`) that fails the build if any service
  module ever grows an `execute_*`/`transfer_funds`/`place_order` method.
- Nothing is ever labeled "unused" from bank data alone — only an explicit user confirmation can set
  `UsageStatus.CONFIRMED_NOT_USED`.
- Rent, EMI, insurance, taxes, medical, utilities, education and childcare are never recommended for
  cancellation, regardless of leak score (`PROTECTED_FROM_CANCELLATION` in
  `backend/app/models/enums.py`).

## Voice and language access

SafeSpare is usable by people who have no bank statement to upload — or who cannot read one.

**Speak your expenses** (`/speak`). Say *"मैंने सब्ज़ी पर 250 रुपये खर्च किए"* and it becomes a
transaction that flows through the same engines as a parsed statement row. The parser
(`backend/app/services/spoken_expenses.py`) is deterministic Python — §3.7 forbids an LLM computing
a financial value — and handles Indic digits (२५०, ৫০০, ௧௦௦), Indian numbering (lakh, crore,
hazaar), and spoken fractions (`dhai sau` = 2.5 × 100 = 250).

It refuses to guess. "I bought something" returns *no amount*, because an invented number would flow
straight into the Safe Spare calculation.

**26 languages** — all 22 Eighth Schedule languages plus English, Bhojpuri, Rajasthani and Tulu.
Each is listed in its own script, since that is the only label a non-English reader can recognise.
Urdu, Kashmiri and Sindhi render right-to-left. Every captured expense is *spoken back* in the
user's language before it counts.

Honest limits: 11 of 26 languages have full UI translation and the switcher displays the percentage
rather than silently showing a half-English screen; dictation depends on browser support, and
languages without it fall back to typing.

## Verified status

| Check | Result |
| --- | --- |
| Backend tests | **270 passed, 0 failed** |
| Frontend type check | **0 errors** (`strict: true`) |
| Frontend build | **passes** |
| Docker build | **passes** — 420 MB, non-root uid 10001 |
| Smoke test vs uvicorn | **16/16** |
| Smoke test vs container | **16/16** |
| Secret scan | **clean** — no credential tracked or bundled |
| AWS deployment | **NOT DEPLOYED** — terraform and aws CLI unavailable |

See `TEST_REPORT.md` for the full evidence and `BUGS_FOUND.md` for the nine defects found and fixed.
