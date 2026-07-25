# API_DOCUMENTATION.md

31 paths. Generated from the live OpenAPI schema — run the server and open
`/docs` for the interactive version, or `/openapi.json` for the raw schema.

**Base URL (local):** `http://localhost:8000`

---

## Conventions

**Session.** Every request carries `X-Session-Id`. An analysis belongs to the
session that created it; another session receives **404**, not 403 — existence is
not disclosed (§29).

**Money is a string.** `"1450.00"`, never a JSON number. Floats would reintroduce
the rounding errors the engines avoid by using `Decimal` throughout.

**Errors are uniform** — never a stack trace, never an internal path (§5):

```json
{ "error": { "code": "PROTECTED_EXPENSE", "message": "…" }, "request_id": "…" }
```

| Status | Meaning |
| --- | --- |
| 400 | malformed request |
| 404 | not found, or not yours |
| 409 | wrong state (e.g. reading a summary before COMPLETED) |
| 422 | validation failed, or a guardrail refused the action |
| 429 | rate limited (`Retry-After` header) |

**Idempotency.** `POST /api/analyses` honours `Idempotency-Key`; a repeat returns
the original analysis rather than starting a second.

---

## Health

| | |
| --- | --- |
| `GET /health` | liveness |
| `GET /ready` | readiness plus AI provider status — model identifiers and configured/unconfigured only, **never a credential** |

## Uploads

**`POST /api/uploads/presign`** → 201

```json
{ "filename": "statement.pdf", "content_type": "application/pdf", "size_bytes": 248000 }
```

The response `upload_id` is the storage key. The original filename is never used
as a path (§22), so `../../etc/passwd` cannot traverse.

**`POST|PUT /api/uploads/{upload_id}/content`** — multipart body.

## Analyses

**`POST /api/analyses`** → 202

```json
{ "demo": true, "consent_confirmed": true, "delete_after_processing": true }
```

Returns immediately; the §19 pipeline runs in the background. **Clients must poll
`/status`** — the analysis is not ready when this returns.

**`GET /api/analyses/{id}/status`** — `state`, `progress_percent`, and every stage
with its own state, for the progress UI.

**`GET /api/analyses/{id}/summary`** — the §6.4 dashboard: totals, essential vs
discretionary, recurring, surplus, round-ups, Safe Spare, Cashflow Confidence,
recoverable spending, plus eight chart series. Every value is computed from
transactions; none is hardcoded.

Other reads: `/transactions`, `/categories`, `/recurring`, `/leaks`,
`/safe-spare`, `/roundups`, `/cashflow-confidence`.

**`POST /api/analyses/{id}/confirm`** — user confirmed the extraction (§6.3).
**`DELETE /api/analyses/{id}`** — removes the analysis and everything derived from it.

## Transactions

**`PATCH /api/transactions/{id}`** — correct merchant, amount, direction,
category, essentiality, transfer/reimbursement flags, or exclude.

Every correction writes an audit record and **recalculates downstream metrics**.
The corrected field is marked `user_overridden` so re-categorisation cannot
overwrite a human decision.

**`POST /api/transactions/bulk-confirm`** — confirm and continue the pipeline.

## Leak Radar

**`POST /api/leaks/{id}/usage-confirmation`**

```json
{ "usage_status": "user_confirms_not_used" }
```

One of: `usage_unknown`, `possibly_underused`, `user_confirms_regular_use`,
`user_confirms_occasional_use`, `user_confirms_not_used`,
`user_does_not_recognize_payment`. Stored with a timestamp; re-scores the finding
and recalculates. Reversing it undoes the effect.

**`POST /api/leaks/{id}/decision`**

```json
{ "decision": "cancel" }
```

Two guardrails enforced here:

- **422 `ACTION_NOT_AVAILABLE`** if the action isn't yet permitted — `cancel` is
  never offered before the user confirms non-use (§25.9).
- **422 `PROTECTED_EXPENSE`** for rent, EMI, insurance, medical, tax, utilities,
  education and childcare — regardless of score (§25.5–25.8).

A successful decision returns `"executed": false` and a notice stating that
SafeSpare has not contacted the merchant.

**`POST /api/leaks/{id}/draft-action`** — drafts a message the *user* sends.
Refuses to draft a cancellation for a protected expense.

## Safe Spare and round-ups

**`GET /api/analyses/{id}/safe-spare`** — every intermediate value (§6.6):
balance, whether it is estimated, expected income, upcoming essentials, projected
balance, safety buffer, volatility reserve, Safe Spare, safe monthly
contribution, confidence, limiting factor, and a plain-language reason.

**`PATCH /api/analyses/{id}/safe-spare-settings`** — buffer, percentage,
volatility multiplier, monthly cap. Recalculates immediately.

**`GET /api/analyses/{id}/roundups`** / **`PATCH …/roundup-rules`** — increment,
caps, exclusions, pause. `allowed_round_up_total` can never exceed
`safe_monthly_contribution`; when it is zero the response always explains why.

## Goals

**`POST /api/goals`**, **`PATCH /api/goals/{id}`**, **`POST /api/goals/{id}/simulate`**

The simulation returns `user_contributions` and `illustrative_growth` as separate
figures — never combined (§25.12) — plus all four scenarios, a month-by-month
timeline, the required-vs-safe contribution gap, and the mandatory disclaimer.

## Insights and voice

**`POST /api/insights/chat`** — the AI Coach explains computed values. It cannot
change one. With no providers configured it answers deterministically, and every
prohibited request (guaranteed returns, specific securities, cancelling rent,
account numbers, asserting unused status) is refused.

**`POST /api/voice/summary`** — the backend composes the transcript from verified
figures **first**, then optionally sends that finished text to TTS. The provider
is never asked to produce content, so it cannot introduce a number. `transcript`
is always present even when audio is not.

**`POST /api/voice/parse-expense`** — parse a spoken phrase. Deterministic; no
side effects. Handles Indic digits, lakh/crore, and spoken fractions. Returns
`amount: null` rather than guessing when no number was heard.

**`POST /api/voice/confirm-expense`** — the user confirmed what was heard; only
then does it become a transaction.

## Privacy

**`POST /api/privacy/delete-data`** — `{"confirm": true}` deletes every analysis
for the session, the uploaded bytes, and all derived figures.
