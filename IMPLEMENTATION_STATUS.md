# IMPLEMENTATION_STATUS.md

**Project:** SafeSpare AI — *“Invest only what life can safely spare.”*
**Track:** FinTech — Problem Statement 2: Smart Expense & Micro-Investment Assistant
**Supporting intelligence:** Recurring-payment and price-leak detection inspired by Problem Statement 1.
**Last updated:** 2026-07-25

---

## 1. Phase 1 audit — what actually exists

The repository was empty except for a Claude Design export pulled down earlier in this session.
Every item below was verified by running the command, not assumed.

### 1.1 Repository contents

```
.
├── .claude/settings.local.json
├── design/
│   ├── Perch Site.dc.html      53 KB   ← visual source of truth
│   ├── support.js              66 KB   ← Claude Design "dc-runtime" (generated)
│   └── index.html                      ← local-run copy, adds React UMD tags
└── You are the principal full-stack en.md   ← the build specification
```

Git: branch `main`, **zero commits**. Working tree was clean at session start.

### 1.2 Audit checklist from spec §4

| Item asked for | Finding |
| --- | --- |
| Frontend framework | **None.** Claude Design `.dc.html` — a proprietary template format (`<x-dc>`, `{{ }}` bindings, `<sc-for>`, `<sc-if>`, `class Component extends DCLogic`). |
| Routing | **None.** Single document; view switching is `this.state.view === "site" \| "app"` inside one component. |
| Styling system | Inline `style="…"` attributes only. No CSS file, no Tailwind, no CSS modules. Pseudo-states via non-standard `style-hover` / `style-focus` attributes the runtime interprets. |
| State management | `DCLogic` class component with `setState`. No store. |
| Component library | **None.** Every element is hand-written inline markup. |
| Existing APIs | **None.** Zero `fetch` / `XMLHttpRequest` calls in the document. |
| Mock data | **All of it.** `TICKETS`, `MOMENTS`, `HANDLES`, `PLANS`, `TOOLS` are hardcoded arrays in the `<script data-dc-script>` block. |
| Static screens | Marketing site + a simulated "inbox" app view. |
| Incomplete components | N/A — it is a design artifact, not an application. |
| Authentication | **None.** |
| Deployment config | **None.** No Dockerfile, no CI, no IaC. |
| Package manager | **None.** No `package.json`, no lockfile, no `node_modules`. |
| Current build errors | **No build exists to error.** See §1.4 for the runtime error found instead. |

### 1.3 Toolchain present on this machine

| Tool | Status |
| --- | --- |
| python3 | 3.9.6 (system) — constrains typing syntax; code targets 3.9 |
| node | v25.6.1 |
| npm | 11.9.0 |
| docker | 29.4.3 |
| git | 2.39.5 |
| **terraform** | **NOT INSTALLED** |
| **aws CLI** | **NOT INSTALLED** |
| AWS credentials | `~/.aws/sso` directory exists; no usable CLI to exercise it |
| LLM provider keys | **None set** — no `OPENAI_*`, `GEMINI_*`, `GROQ_*`, `ELEVENLABS_*` in env |

### 1.4 Running the frontend (spec §4.3 / §4.5)

Served `design/` over `python3 -m http.server 8000`. Both files return HTTP 200.

**Defect found:** the document loads `./support.js` but nothing loads React. The runtime
throws `dc-runtime: window.React is not available yet` and the page renders blank standalone —
Claude Design injects React in its own preview host.

**Fix applied:** `design/index.html` is a copy with React 18 UMD `<script>` tags inserted ahead of
`support.js`. `Perch Site.dc.html` is left byte-exact as pulled from the design project.

### 1.5 Non-functional UI elements (spec §4.6)

Every interactive element is non-functional in the product sense — all state is local and
all data is a literal. Specifically: `Get started` / `Sign in` only toggle a local view flag;
the email input is captured to state and never submitted; pricing Monthly/Annual toggles
recompute from a hardcoded `PLANS` array; the inbox "Draft with Perch" button replays a
canned string via `setInterval`; `Send` / `Rewrite` / `Escalate` only set local booleans.

---

## 2. The blocking mismatch, and the assumption I am proceeding under

The spec (§5) calls the existing frontend “the visual source of truth” and says to preserve
branding, typography, layout, palette, navigation, components and animation.

**The existing design is “Perch” — an AI customer-support helpdesk.** Its content is support
tickets, agent inboxes, CSAT and per-seat SaaS pricing. SafeSpare AI is a personal-finance
product. The two share no domain surface: there is no upload screen, no transaction table, no
chart, no goal simulator anywhere in the design.

**Assumption adopted (flagged for your override):** “preserve the design” means preserve the
*visual system* — palette, type scale, spacing rhythm, radii, motion, component shapes — and
rebuild the *domain content* for SafeSpare. The alternative reading (ship a finance product that
still says “Close 71% of tickets”) is incoherent, and §6 mandates finance-specific pages that do
not exist in the design, so some new screens are unavoidable regardless.

### 2.1 Extracted design tokens — the actual source of truth

Measured by frequency directly out of `Perch Site.dc.html`:

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#F7F4ED` | page background (warm cream) |
| `--ink` | `#14120F` | primary text / dark panels |
| `--accent` | `#2438E0` | electric blue — 24 uses, the brand colour |
| `--accent-700` | `#1B2BB8` | accent hover |
| `--accent-300` | `#8C9BFF` | accent tint |
| `--accent-200` | `#A8B4FF` | accent tint |
| `--accent-100` | `#C8CEFF` | selection background |
| `--panel` | `#EFEBE2` | raised surface |
| `--positive` / `--positive-soft` | `#1E8A5F` / `#8CE0B0` | gains, confirmed savings |
| `--warning` / `--warning-soft` | `#D2432A` / `#FFB08F` | price hikes, escalation |
| Display / UI type | **Space Grotesk** 400–700 | headings, numerals |
| Label / data type | **IBM Plex Mono** 400–500 | uppercase micro-labels, figures |
| Body type | **Figtree** 400–600 | prose |
| Radii | `999px` pills, `10–12px` controls, `16px` cards, `24–28px` hero panels | |
| Motion | `p-pulse`, `p-marquee(-rev)`, `p-sheen`, `p-bar`, `p-rise`, `p-spin(-rev)`, `p-glow`, `p-blob`, `p-run` | reuse names/easings |
| Reveal pattern | `data-reveal="n"` + staggered 70 ms transition-delay on scroll | preserve |

This palette is directly usable for fintech: cream paper, one electric accent, mono data labels,
and a green/red semantic pair already present for gains and warnings.

### 2.2 Why the `.dc.html` cannot be the shipped app

- Requires the proprietary `dc-runtime` (`support.js`) plus React injected by the host.
- No build step, so spec §29.21 (“frontend production build passes”) is unsatisfiable.
- No routing, so the multi-page requirement in §6 is unsatisfiable.
- No component/module boundaries, so §24 frontend tests and Playwright E2E have nothing to target.
- §21 targets an S3 + CloudFront **static SPA**.

**Decision:** port the token system above into React + Vite + TypeScript. The design is preserved
as tokens and component shapes; `design/` is retained verbatim as the reference.

---

## 3. Planned architecture

```
backend/            FastAPI, Python 3.9-compatible
  app/
    api/            §18 endpoints
    services/       deterministic engines — the source of financial truth
    ai/             provider adapters behind one interface (§14)
    models/         Pydantic entities (§20)
    repositories/
    tests/
frontend/           React + Vite + TS, Perch tokens
infra/terraform/    §21 low-cost AWS
scripts/            generate_demo_statement.py
```

**Hard rule carried into code:** every financial number originates in `backend/app/services/`.
LLMs may only phrase values the backend already computed; provider output is schema-validated and
rejected if any amount, percentage or transaction ID fails to match backend state (§16).

---

## 4. Completed changes

| # | Change | Evidence |
| --- | --- | --- |
| 1 | Pulled the Claude Design project into `design/` | `Perch Site.dc.html`, `support.js` byte-exact from project `06c2b3b0-…` |
| 2 | Diagnosed and fixed blank-page render | `design/index.html` adds React 18 UMD ahead of `support.js`; verified HTTP 200 |
| 3 | Extracted the design-token system | §2.1 above, measured from the source |
| 4 | Wrote this audit | this file |
| 5 | **Deterministic financial core** — 9 modules, no network, no LLM | `backend/app/{models,services}/` |
| 6 | **78 tests passing** (50 unit + 28 guardrail) | `cd backend && .venv/bin/python -m pytest tests/ -q` |

### 4.1 Deterministic core — modules delivered

| Module | Spec | Notes |
| --- | --- | --- |
| `models/enums.py` | §6.5 | 26 categories; `PROTECTED_FROM_CANCELLATION` and `ROUNDUP_EXCLUDED_CATEGORIES` as data, which is what makes the guardrails provable |
| `models/transaction.py` | §20 | `Decimal` money throughout; signed imports normalised to amount+direction; full provenance fields |
| `services/merchant_normalization.py` | §9 | alias → regex → fuzzy ladder; RapidFuzz optional, stdlib `difflib` fallback |
| `services/categorization.py` | §10 | merchant dictionary + 25 keyword rules; **documents that no labelled dataset exists** rather than faking a trained classifier |
| `services/recurrence.py` | §11 | the §11 weighted confidence formula verbatim; 6 cadences; utilities get amount leniency |
| `services/price_changes.py` | §12 | previous / median / rolling comparison, evidence IDs, dual thresholds |
| `services/leak_score.py` | §13 | the §13 5-component formula; usage-unknown score cap; essentials hard-blocked from CANCEL |
| `services/safe_spare.py` | §6.6 | all four formulas; clamped at zero; confidence degrades on estimated balance |
| `services/projections.py` | §6.10 | annuity FV with explicit zero-rate branch; principal and growth always separate |

**Verification that the engine matches the spec's own worked example (§2):**

```
historical: 48.70
allowed:    31.00
limited by: safe_monthly_contribution

"Your transactions created $48.70 in potential round-ups, but only $31.00 is
 considered safely redirectable because essential bills are due before your
 next expected income."
```

### 4.2 Guardrail coverage (§25)

| # | Guardrail | Status |
| --- | --- | --- |
| 1 | Safe Spare never negative | ✅ + parametrised fuzz |
| 2 | Round-ups never exceed Safe Spare | ✅ |
| 3 | Round-ups never exceed user caps | ✅ monthly + per-transaction |
| 4 | Essential payments excluded | ✅ by category and by user marking |
| 5–8 | Rent / EMI / insurance / medical never cancelled | ✅ parametrised, tested under worst-case "user confirms not used" |
| 9 | Unknown usage never called unused | ✅ incl. `POSSIBLY_UNDERUSED` treated as hypothesis |
| 10 | Unconfirmed cancellation doesn't raise savings | ✅ |
| 11 | Returns never guaranteed | ✅ |
| 12 | Principal and growth separate | ✅ incl. zero-return |
| 13 | Missing balance labeled estimated | ✅ confidence drops to ≤0.6 |
| 14 | Low confidence requires review | ✅ |
| 15–19 | Model disagreement, LLM cannot alter amounts, provider outage, PII in logs, prompt injection | ⏳ **blocked on `app/ai`** (Phase 4) |
| 20 | No real investment/cancellation executed | ✅ incl. structural test that fails if an `execute_*` method is ever added |

**Two real bugs were found and fixed by these tests**, not worked around:
- `merchant_normalization._clean` kept 3-digit store numbers, so `QUIRKY BEANS CO 123`
  scored 0.857 against `QUIRKY BEANS` — just under the 0.86 threshold — and split one
  merchant into two. Standalone digit runs are now stripped at 2+ digits.
- `recurrence.amount_varies` was derived from the leniency-adjusted stability, so a
  utility bill swinging \$79→\$112 reported as *not* varying. The flag now uses strict
  stability; leniency remains only in the confidence score.

### 4.3 Phase 2 — extraction, validation, demo data

| Module | Spec | Notes |
| --- | --- | --- |
| `services/extraction.py` | §7 | CSV (stdlib, encoding ladder, §7 column aliases, preamble skipping), XLSX (pandas), digital PDF (pdfplumber tables → PyMuPDF → layout-aware line parsing, password support), SMS/email regex, cross-source dedup |
| `services/validation.py` | §8 | all 12 §8 checks incl. running-balance reconciliation, reversed debit/credit detection, transfer-pair matching, ambiguous d/m detection. **Annotates, never deletes** |
| `scripts/generate_demo_statement.py` | §23 | all 17 required elements; deterministic seed; emits `demo_statement.csv` **and a real digital PDF with a text layer, written with zero dependencies** |

**End-to-end demo verification** (195 transactions, balance reconciles, both formats agree):

```
STAGE 1 UNDERSTAND  195 transactions, 17 recurring patterns, balance reconciles
STAGE 2 PROTECT     $2,269.12 of essential bills due before next salary (2026-07-29)
STAGE 3 RECOVER     price hike: CloudVault $9.99 -> $13.99 (+40.0%)
                    gym, usage unknown:   score=18  low_concern  cancel offered = False
                    gym, user confirms:   score=43  review       cancel offered = True -> $49.00/mo
STAGE 4 ROUND UP    potential $37.81 -> allowed $0.00 (limited by safe_monthly_contribution)
STAGE 5 REDIRECT    after confirmed recovery: safe monthly $49.00, round-ups allowed $37.81
STAGE 6 SIMULATE    24mo: contributions $2,083.44 + growth $145.93 = $2,229.37
```

That sequence is the product thesis executing on real parsed data, and it exercises
guardrail §25.9 visibly: the gym is *not* cancellable until the user says so.

**Three further real bugs found and fixed via realistic demo data:**

1. **Price detection missed settled hikes.** Comparing only the last two payments made
   CloudVault's $9.99→$13.99 rise invisible once it stabilised, while random spend at
   one merchant (fuel, cafés) produced false "price rises". Replaced with **plateau-step
   detection**: a real hike is two internally-flat price levels; fluctuating discretionary
   spend has none. Both false positives disappeared and the real hike is now found.
2. **Safe Spare counted the next salary as already received.**
   `expected_income_before_next_income` was set to a full salary, inflating the projected
   balance by an entire paycheck. For a single-salary user it is now `0` — the salary *is*
   the next income event.
3. **SMS reference parsing was greedy.** `\D{0,4}` swallowed the alphabetic prefix of the
   reference, turning `Ref ABC123456` into `123456`.

## 5. In progress (4 parallel agents)

| Phase | Scope | Owner |
| --- | --- | --- |
| 4 | FastAPI surface, §18 endpoints, §19 state machine, §14/16 AI adapters + guardrails 15–19 | agent |
| 5 | React/Vite SPA in the preserved Perch visual language, §6 pages | agent |
| 8 | Terraform (§21), Dockerfile, `.env.example` (§15) | agent |
| 9 | The 9 documentation files (§27) | agent |

## 6. Not started

- Playwright E2E flow (§24) — depends on Phases 4 and 5 landing first.

---

## 7. Remaining external blockers — stated honestly

| Blocker | Consequence | Needed to clear |
| --- | --- | --- |
| `terraform` not installed | Cannot run `terraform validate`. Infra will be written but unvalidated. | `brew install terraform` |
| `aws` CLI not installed | Cannot deploy or smoke-test. **No deployment will be claimed** (§21, §3.24). | `brew install awscli` + SSO login |
| No LLM API keys in env | AI Coach, voice and LLM fallbacks run in deterministic-template mode only. | populate `.env` from `.env.example` |
| Python 3.9 | Cannot use `X | Y` unions at runtime; `from __future__ import annotations` used throughout. | optional: install 3.11+ |

Per spec §3.24 and §21, deployment status will remain **NOT DEPLOYED** until a real deployed
service has been tested.
