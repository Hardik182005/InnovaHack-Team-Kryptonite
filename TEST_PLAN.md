# TEST_PLAN.md

Scope, strategy and coverage map for SafeSpare AI. Results live in
`TEST_REPORT.md`; defects in `BUGS_FOUND.md`.

## 1. Strategy

The product's promise is that a number on screen is safe to act on. Testing is
therefore organised around **who computed a value**, not around code coverage:

1. **Deterministic core** (`app/services`, `app/models`) — pure Python, no
   network, no framework. Tested exhaustively and fast (145 tests in 0.71 s).
   This is where every financial value originates.
2. **HTTP surface** — the guardrails re-tested through the API, because that is
   where a user meets them. A guardrail that holds in a unit test but not behind
   a route is not a guardrail.
3. **Deployed artifact** — the Docker image is smoke-tested as built, not as
   assumed.

Three rules held throughout: never weaken a test to make code pass; never mock
production logic into success; never report an unrun check as a pass.

## 2. Test environment

| Mode | Data | Providers |
| --- | --- | --- |
| Automated tests | synthetic statement, fixed seed | none configured |
| Local dev | synthetic statement | optional via `backend/.env` |
| Demo | synthetic, visibly labelled | optional |
| Production | user upload | env-configured |

No real financial data is used anywhere. The demo generator is seeded
(`random.seed(20260725)`) and the closing balance is pinned, so the same input
produces the same output on every machine — a requirement for a demo whose whole
point is a specific numeric tension.

## 3. Fixtures

`demo_data/demo_statement.csv` and `.pdf` — 195 transactions, 6 months,
containing every §23 element: salary, rent, utilities, groceries, food delivery,
transport, streaming/software/gym subscriptions, insurance, EMI, a **duplicate
cloud-storage service**, a **silent price increase**, round-up-eligible
purchases, a refund, an internal transfer, and an unknown merchant.

The PDF is generated dependency-free with a real text layer, so the OCR-fallback
path can be distinguished from the digital path.

## 4. Coverage map

| Area | Suite | Tests |
| --- | --- | --- |
| Round-up arithmetic, exclusions, caps | `test_engines.py` | included in 58 |
| Merchant normalization (§9) | `test_engines.py` | " |
| Categorization (§10) | `test_engines.py` | " |
| Recurrence (§11) | `test_engines.py` | " |
| Price steps (§12) | `test_engines.py` | " |
| Safe Spare (§6.6) | `test_engines.py` | " |
| Projections (§6.10) | `test_engines.py` | " |
| Extraction + validation (§7, §8) | `test_extraction.py` | 41 |
| Cashflow Confidence (§6.7) | `test_cashflow_confidence.py` | 18 |
| Mandatory guardrails (§25) | `test_guardrails.py` | 28 |
| API, auth, errors, guardrails over HTTP | `test_api.py` | 50 |
| Voice entry, multilingual parsing | `test_spoken_expenses.py` | 43 |
| Deployed artifact | `infra/scripts/smoke-test.sh` | 16 checks |

## 5. What is deliberately not automated

| Gap | Why | Mitigation |
| --- | --- | --- |
| Playwright browser E2E | no browser automation configured | flow covered over HTTP end to end |
| Real provider calls | no API keys; would spend quota | injected-fake paths; deterministic mode is the default |
| Terraform validate/plan | terraform not installed | reviewed by inspection; documented as blocked |
| Load testing at 10k transactions | out of scope for the timebox | pagination implemented; noted as unmeasured |
| Dependency CVE scan | not run | noted as a gap in TEST_REPORT §10 |

Each is reported as a gap rather than quietly omitted.

## 6. Regression policy

Every defect in `BUGS_FOUND.md` has a test that fails against the old behaviour.
Two of the nine were found only because the code was run against realistic data
rather than hand-built fixtures — BUG-002 (Safe Spare counting an unarrived
salary) and BUG-008 (background tasks behaving differently under a real server
than under `TestClient`). Both are the kind of defect that unit tests alone
cannot surface, which is why the smoke test runs against a real process.
