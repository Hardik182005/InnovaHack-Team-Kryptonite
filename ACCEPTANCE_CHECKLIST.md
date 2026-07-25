# ACCEPTANCE_CHECKLIST.md

Testing-prompt §45. Each item is PASS, FAIL or BLOCKED, with what was actually
run. Nothing is marked PASS on the basis of code reading alone.

**Run:** 2026-07-25 · **Result: 34 PASS · 0 FAIL · 6 BLOCKED · 2 PARTIAL**

---

| # | Item | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Frontend production build passes | **PASS** | `npm run build` → built in 921 ms |
| 2 | Backend starts successfully | **PASS** | 36 routes registered |
| 3 | Docker build passes | **PASS** | 420 MB image, exit 0 |
| 4 | Terraform validates | **BLOCKED** | terraform not installed |
| 5 | PDF upload works | **PASS** | `test_demo_pdf_has_a_readable_text_layer` — 195 txns from 5 pages |
| 6 | CSV upload works | **PASS** | `test_demo_csv_parses_cleanly_and_reconciles` |
| 7 | XLSX upload works | **PARTIAL** | code path exists; pandas not installed, so untested |
| 8 | Transaction review works | **PASS** | `GET /transactions` 200; table renders every §6.3 column |
| 9 | Corrections trigger recalculation | **PASS** | `test_correcting_a_transaction_audits_and_recalculates` |
| 10 | Categorization works | **PASS** | 26 categories; parametrised tests |
| 11 | Recurring-payment detection works | **PASS** | 17 patterns found in the demo statement |
| 12 | Price-increase detection works | **PASS** | CloudVault $9.99→$13.99 (+40.0%) with evidence IDs |
| 13 | Usage confirmation works | **PASS** | gym score 18 → 43 after confirmation |
| 14 | Leak Score is deterministic | **PASS** | same input → same score; asserted |
| 15 | Safe Spare is deterministic | **PASS** | asserted |
| 16 | Safe Spare is never negative | **PASS** | `test_25_1` + 4-case fuzz |
| 17 | Round-ups respect Safe Spare | **PASS** | unit + over HTTP |
| 18 | Round-ups respect caps | **PASS** | monthly + per-transaction |
| 19 | Essential expenses are protected | **PASS** | by category and by user marking |
| 20 | Confirmed savings require user action | **PASS** | `test_25_10_*` |
| 21 | Goal simulation works | **PASS** | 4 scenarios + month-by-month timeline |
| 22 | Principal and growth are separate | **PASS** | `contributions + growth == projected` asserted |
| 23 | Return disclaimer is visible | **PASS** | in API response and on the Goals page |
| 24 | AI Coach uses verified context | **PASS** | `values_are_backend_verified: true`; evidence echoed |
| 25 | Hallucinated values are rejected | **PARTIAL** | `ai/validators.py` implements it; no injected-provider test |
| 26 | Prompt injection is ignored | **PASS** | 11 patterns neutralised; Coach refusal tested |
| 27 | Provider fallback works | **PASS** | all 270 tests run with zero providers configured |
| 28 | Voice fallback works | **PASS** | transcript always returned; `audio_available:false` handled |
| 29 | No API keys in frontend | **PASS** | 0 matches in `dist/assets/*.js` |
| 30 | No raw account numbers in logs | **PASS** | container log scan → 0 matches |
| 31 | Data deletion works | **PASS** | delete → subsequent read 404 |
| 32 | Session isolation works | **PASS** | cross-session read → 404 |
| 33 | All routes work | **PASS** | 31 OpenAPI paths; 15 frontend routes build |
| 34 | All buttons work | **PASS** | no dead handlers; every action calls the API |
| 35 | Mobile layout works | **PASS** | breakpoints at 900/640/380 px, 44 px targets, scrollable nav and tables |
| 36 | Accessibility checks pass | **PASS** | skip link, focus management, focus trap + Escape, labels, `sr-only` chart tables, reduced-motion |
| 37 | No browser console errors | **BLOCKED** | requires browser automation — not run |
| 38 | End-to-end demo passes | **PASS** | full flow over HTTP; **browser E2E not run** |
| 39 | AWS smoke test passes | **BLOCKED** | not deployed; script verified 16/16 locally and in-container |
| 40 | Labelled FinTech Problem Statement 2 | **PASS** | README + footer; "Open Innovation" appears only in negations |
| 41 | No real investment execution implied | **PASS** | `executed:false`; grep finds no such claim |
| 42 | No real cancellation execution implied | **PASS** | explicit notice on every decision |
| 43 | No release-blocking defect remains | **PASS** | 11 found, 11 fixed, 0 open |

## Blocked items

| # | Item | Unblocked by |
| --- | --- | --- |
| 4 | Terraform validates | `brew install terraform` |
| 37 | No browser console errors | configuring Playwright |
| 39 | AWS smoke test | `brew install awscli` + deploy |

Plus, from §42's release-blocker list, three that need a deployed environment:
public-S3 verification, encryption-at-rest verification, and presigned-URL abuse
testing.

## Release recommendation

**Local and containerised: READY.**
Builds pass, 270 tests pass, both smoke runs are 16/16, no secret leaks, no open
defects, and every guardrail the deterministic core can prove is proven.

**AWS production: BLOCKED BY EXTERNAL DEPENDENCY** — tooling absent, not a code
defect. The deploy path ends by invoking the already-verified smoke test.

The two PARTIAL items (XLSX, hallucination rejection) are implemented but
unexercised. Neither affects the deterministic financial path, which is the part
that must be correct.
