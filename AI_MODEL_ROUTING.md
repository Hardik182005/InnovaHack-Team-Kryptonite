# AI Model Routing

## Current state of this environment — read this first

`backend/app/ai/` contains a single empty `__init__.py`. No provider adapter (`base.py`, `router.py`,
`schemas.py`, `validators.py`, `prompts.py`, `openai_provider.py`, `gemini_provider.py`,
`groq_provider.py`, `elevenlabs_provider.py`) exists yet. There is no `backend/.env` or
`backend/.env.example` in the repository, and none of `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`GROQ_API_KEY`, or `ELEVENLABS_API_KEY` are set in this environment (verified: `env | grep` returns
nothing for any of them).

**Practical consequence: every piece of functionality that exists today runs in 100%
deterministic-template mode.** This is not a degraded fallback path being exercised under failure —
it is the only path that exists, because nothing above the deterministic core has been built yet. The
78 passing backend tests (`TEST_REPORT.md`) exercise exactly zero AI/network code.

This document describes the routing design from spec §14 that the (not-yet-built) `app/ai/router.py`
must implement, and shows the deterministic-template behavior that already exists and is already
tested as the fallback of last resort.

## The one rule that governs everything else

**LLMs never calculate a financial value. LLMs may only explain a value the backend already
computed.** Every number that appears anywhere in the product — Safe Spare amount, round-up total,
leak score, projected balance — originates in `backend/app/services/`. This is enforceable today even
without `app/ai` existing: none of the nine service modules import anything from `app.ai`, make a
network call, or accept a parameter that lets a caller override a computed `Decimal`. The structural
guardrail test `test_25_20_no_execution_side_effects_exist` (in `backend/tests/test_guardrails.py`)
additionally asserts no service module ever grows an `execute_*`/`transfer_funds`/`place_order`
method.

## Provider roles (spec §14)

| Provider | Role | Never does |
| --- | --- | --- |
| **Gemini** | Multimodal extraction fallback for scanned/failed PDF regions; resolving ambiguous merchants or classifications | Calculate a financial figure |
| **Groq** | Fast explanations: dashboard summaries, spending-insight wording, cancellation/downgrade/negotiation draft text, AI Coach responses | Detect recurrence, compute leak score, or produce a number |
| **OpenAI** | Verification of high-impact ambiguous findings, contradiction detection, evidence-support validation, final action-plan check | Originate a finding — it can only confirm or reject one already produced deterministically |
| **ElevenLabs** | Text-to-speech only, reading a summary the backend already wrote | Generate any financial content itself |
| **Local deterministic system** (already built) | Parsing, merchant normalization, categorization, recurrence detection, price-change math, Leak Score, Safe Spare, round-ups, simulations | — this is the only tier that runs today |

## Confidence-based routing (spec §14)

| Confidence band | Behavior |
| --- | --- |
| **≥ 90** | No LLM needed for detection. Groq may *phrase* an explanation of the already-verified finding — it cannot alter it. |
| **70–89** | Gemini may help resolve genuine ambiguity (e.g. an unreadable merchant string). Any Gemini output must be validated against the evidence already on file. Status stays `Likely` until independently confirmed — an LLM opinion does not itself promote a finding to `Confirmed`. |
| **< 70** | Marked `Needs Review`. No consequential recommendation (e.g. no cancellation advice) is produced at this confidence. OpenAI may optionally act as a second verifier, but the finding remains `Needs Review` regardless of what a single model says. |

These bands are not a new invention for the AI layer — they are the same 90 / 70 thresholds already
implemented and tested in the deterministic core today:

- `backend/app/services/recurrence.py::_status_for` — `≥90 → CONFIRMED`, `70–89 → LIKELY`,
  `<70 → NEEDS_REVIEW`, exercised by `test_monthly_subscription_detected_and_confirmed` and
  `test_25_14_low_confidence_requires_review`.
- `backend/app/services/leak_score.py` — `ReviewStatus.NEEDS_REVIEW` is forced whenever
  `pattern.confidence < 70`, and `LeakDecision.CANCEL` is never offered on a `NEEDS_REVIEW` finding
  (`_actions()`).

When `app/ai` is built, its job is to *layer LLM assistance on top of* this existing confidence
scoring, not replace it.

## High-impact cases

Per spec §14: apply deterministic checks first, require explicit user confirmation for any
consequential action, and optionally require a second-model verification before surfacing a strong
recommendation (e.g. "cancel this subscription"). The deterministic half of this is already built:
`leak_score.py`'s `_actions()` only ever includes `LeakDecision.CANCEL` after
`UsageStatus.CONFIRMED_NOT_USED` or `NOT_RECOGNIZED` — never from bank data alone (guardrail 9). The
"optionally require a second-model verification" half depends on `app/ai/router.py`, which does not
exist yet.

## Model disagreement

**Rule: do not average outputs. Mark `Needs Review`.** If Gemini and OpenAI (or Gemini and the
deterministic classifier) disagree on a classification or an ambiguous merchant, the correct behavior
is to surface `ReviewStatus.NEEDS_REVIEW`, not to blend, vote, or take a mean of two numeric outputs.
This is straightforward to implement once `app/ai/router.py` exists — the `ReviewStatus` enum it will
route into already exists in `backend/app/models/enums.py` today.

## All providers unavailable → deterministic templates

This is the one behavior that is **already implemented, already tested, and already running in
production today** — because it's the only path that exists. Every "explanation" surface in the
current codebase is a deterministic Python string template, not a model call:

- `safe_spare.py::_explain()` — produces sentences like *"No safely spare money right now: after your
  expected income of $0.00 and $2300.59 of essential bills due before 2026-07-29, the projected
  balance of $579.41 does not clear your $564.76 safety buffer and $49.14 volatility reserve."* This
  is a real sentence generated by running the actual demo statement through the engine (see
  `JUDGE_DEMO.md` / `TEST_REPORT.md`), not an example string.
- `roundups.py::_explain()` — produces the exact wording from the build spec's own worked example:
  *"Your transactions created $X in potential round-ups, but only $Y is considered safely
  redirectable because essential bills are due before your next expected income."*
- `leak_score.py::_explain()` — assembles an evidence-backed sentence per finding: charge amount and
  cadence, any detected price change, any duplicate-service group, and an explicit "Usage is unknown —
  bank data cannot show whether you use this" line whenever usage hasn't been confirmed.

Because these templates are pure Python string formatting over already-computed `Decimal` values, the
product's core narrative (why a number is what it is) works completely with zero API keys configured,
which is exactly the state of this environment right now.

## Structured LLM output (spec §16) — designed, not yet implemented

`backend/app/ai/schemas.py` does not exist yet. When built, it must define Pydantic schemas for:

- `MerchantResolution` (LLM-assisted variant) — `normalized_merchant`, `category`, `explanation`,
  `confidence`, `evidence_tokens`. **Naming collision to resolve during implementation**: a plain
  `@dataclass MerchantResolution` already exists in `backend/app/services/merchant_normalization.py`
  for the deterministic resolver. The `app/ai` version must be named distinctly (e.g.
  `LLMMerchantResolution`) or imported under an alias to avoid confusion between "the deterministic
  ladder resolved this" and "an LLM proposed this, pending validation."
- `InsightExplanation` — `insight_type`, `title`, `explanation`, `evidence_transaction_ids`,
  `suggested_action`, `confidence`.
- `ActionDraft` — `action_type`, `merchant`, `subject`, `body`, `facts_used`, `unsupported_claims`.
- `VerificationResult` — `supported`, `contradictions`, `unsupported_values`, `corrected_text`,
  `confidence`.

Validators (`backend/app/ai/validators.py`, not yet implemented) must reject any LLM output where:

| Rejection condition |
| --- |
| Amounts don't match backend context |
| Merchant is unsupported (not present in the evidence given to the model) |
| Percentages differ from the calculated values |
| Referenced transaction IDs don't exist |
| An "unused" status is asserted without a user confirmation on file |
| Returns are described as guaranteed |
| A specific stock, fund, cryptocurrency or security is recommended |
| An essential (protected) category is recommended for cancellation |
| PII is exposed |
| A required schema field is absent |

## Configuration (spec §15) — designed, not yet implemented

No `backend/.env.example` exists yet. When created, it should follow this shape (placeholders only —
never real values in Git, per §22):

```
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_FALLBACK_MODEL=

GEMINI_API_KEY=
GEMINI_MODEL=
GEMINI_FALLBACK_MODEL=

GROQ_API_KEY=
GROQ_MODEL=
GROQ_FALLBACK_MODEL=

ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL_ID=

LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

`frontend/.env.example` already exists and already gets this right for the browser side — its own
comment states the rule plainly:

> NOTHING SECRET GOES IN THIS FILE. Vite inlines every `VITE_*` variable into the JavaScript bundle,
> so an LLM / ElevenLabs / AWS key placed here would ship to every browser. Spec §3.16 and §29.17
> forbid it. All provider credentials live in the backend only.

At startup, `app/ai` (once built) should validate configured credentials, select an available
fallback model, log only model identifiers and status (never secrets), and — critically — never crash
the application because one provider is unavailable. That last requirement is already satisfied
trivially today: the deterministic core has no dependency on `app/ai` at import time, so its absence
causes no failure anywhere in the 78-test suite.
