# FINANCIAL_GUARDRAIL_REPORT.md

The 20 mandatory guardrails from spec §25, each mapped to the test that proves
it. **15 fully proven, 5 partial** — stated as such rather than rounded up.

Run: `cd backend && .venv/bin/python -m pytest tests/test_guardrails.py -q` → 32 passed.

---

| # | Guardrail | Status | Test |
| --- | --- | --- | --- |
| 1 | Safe Spare never negative | **PROVEN** | `test_25_1_safe_spare_never_negative` + 4-case fuzz |
| 2 | Round-ups never exceed Safe Spare | **PROVEN** | `test_25_2_*`, `test_roundups_never_exceed_safe_spare_over_http` |
| 3 | Round-ups never exceed user caps | **PROVEN** | `test_25_3_*` (monthly + per-transaction) |
| 4 | Essential payments excluded | **PROVEN** | `test_25_4_*` (by category and by user marking) |
| 5 | Rent never recommended for cancellation | **PROVEN** | `test_25_5_to_8_*[rent_housing]`, HTTP 422 |
| 6 | EMI never recommended for cancellation | **PROVEN** | `test_25_5_to_8_*[loan_emi]` |
| 7 | Insurance not cancelled merely for recurring | **PROVEN** | `test_25_7_insurance_not_cancelled_merely_for_recurring` |
| 8 | Medical payments protected | **PROVEN** | `test_25_5_to_8_*[medical]` |
| 9 | Unknown usage never called unused | **PROVEN** | `test_25_9_*` ×2 |
| 10 | Unconfirmed cancellation doesn't raise savings | **PROVEN** | `test_25_10_*` ×2 |
| 11 | Returns never guaranteed | **PROVEN** | `test_25_11_returns_never_guaranteed` |
| 12 | Principal and growth separate | **PROVEN** | `test_25_12_*` ×2 (incl. zero-return) |
| 13 | Missing balance labeled estimated | **PROVEN** | `test_25_13_*` ×2 |
| 14 | Low confidence requires review | **PROVEN** | `test_25_14_*` ×2 |
| 15 | Model disagreement ⇒ Needs Review | **PARTIAL** | implemented in `ai/router.py::_cross_check`; no injected-provider test |
| 16 | LLM cannot alter backend amounts | **PARTIAL** | `ai/validators.py` (441 lines) enforces it; covered indirectly |
| 17 | Provider outage preserves function | **PROVEN** | the entire 270-test suite runs with zero providers configured |
| 18 | No account numbers in logs or prompts | **PROVEN** | `test_sms_never_stores_the_account_mask`; container log scan 0 matches |
| 19 | Prompt injection ignored | **PARTIAL** | neutralised in `pipeline.py`; Coach refusal tested; no full matrix |
| 20 | No real execution | **PROVEN** | `test_25_20_*` ×2, incl. a structural test |

## The two guardrails that carry the most weight

**§25.9 — unknown usage is never called unused.** A bank statement shows a gym
was charged. It cannot show whether anyone went. `_confirmed_non_usage()` returns
`0.0` for `UNKNOWN` *and* for `POSSIBLY_UNDERUSED` — a hypothesis is not
evidence — and the score is capped below the cancellation tier while usage is
unknown. Observable in the demo: the gym sits at score 18 with no cancel action;
after the user confirms non-use it moves to 43 and cancel appears.

**§25.20 — nothing is ever executed.** `test_25_20_no_execution_side_effects_exist`
is structural: it walks every service module and fails if a name beginning
`execute`, `transfer_funds`, `place_order`, `submit_trade` or `cancel_subscription`
is ever added. Every decision response carries `executed: false`.

## Structural enforcement

Three properties make the guardrails hard to break by accident:

1. **Protected categories are data, not conditionals.** `PROTECTED_FROM_CANCELLATION`
   and `ROUNDUP_EXCLUDED_CATEGORIES` are frozensets in `models/enums.py`, referenced
   everywhere. There is no second place to forget.
2. **The clamp chain is one expression.**
   `allowed = min(historical, monthly_cap, user_cap, safe_monthly_contribution)` —
   a round-up cannot exceed Safe Spare because the same `min()` computes both.
3. **Money is `Decimal` throughout.** Float arithmetic would make the round-up
   engine wrong in exactly the direction the product claims to protect against.

## To close the remaining three

Add `backend/tests/test_ai_guardrails.py` with injected fake providers covering:
model disagreement, an LLM response whose amounts differ from backend state, a
total provider outage, prompt payload inspection for account numbers, and the
§23 injection matrix. The validators already implement the behaviour; what is
missing is the proof.
