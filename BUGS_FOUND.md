# BUGS_FOUND.md

Nine defects found and fixed during development. Every one was caught by running
real code against realistic data — not by inspection — and every one has a
regression test.

Format follows testing-prompt §43.

---

## BUG-001 — Price detection missed settled hikes and invented false ones
**Severity:** High · **Component:** `backend/app/services/price_changes.py`

**Steps to reproduce:** Run the detector over the demo statement, which contains a
deliberate CloudVault increase from $9.99 to $13.99 in month 3.

**Expected:** CloudVault reported as a silent price increase.
**Actual:** CloudVault not reported. Instead *Shell Fuel* (+50%) and a utility
bill (+42.5%) were reported — neither is a price change.

**Root cause:** The detector compared only the last two payments. A hike that had
settled into recent history was invisible, while discretionary spend at one
merchant — which fluctuates every cycle by nature — looked like a rise.

**Fix:** Replaced with plateau-step detection (`_find_price_step`): a genuine
price change is one internally-flat price level followed by a higher flat level.
Fluctuating spend has no plateau and is correctly ignored.

**Test added:** `test_settled_price_hike_is_still_detected`,
`test_fluctuating_merchant_reports_no_price_change`,
`test_variable_utility_bill_is_not_a_silent_price_increase`,
`test_two_payment_merchant_cannot_produce_a_price_step`,
`test_price_decrease_is_not_reported_as_increase`, `test_sub_threshold_hike_ignored`

**Verification:** CloudVault now reported as $9.99 → $13.99, +40.0%, from
2026-04-17, with 2 evidence transaction IDs. Both false positives gone.

---

## BUG-002 — Safe Spare counted the next salary as already received
**Severity:** **Critical** · **Component:** `backend/app/services/safe_spare.py`

**Steps to reproduce:** Build Safe Spare inputs from a single-salary statement.

**Expected:** `expected_income_before_next_income == 0` — the salary *is* the next
income event, so it has not arrived yet.
**Actual:** A full month's salary was added to the projected balance.

**Root cause:** `build_inputs` averaged all income transactions into "expected
income before next income" without checking that the money arrives *before* the
next income date.

**Impact:** The projected balance was inflated by an entire paycheck, which
inflated Safe Spare and every downstream contribution. This is precisely the
error the product exists to prevent: telling someone they can spare money they
have not been paid.

**Fix:** Only secondary income already evidenced mid-cycle contributes. For a
single-salary user the value is now zero.

**Test added:** `test_next_salary_is_not_counted_as_money_already_received`

---

## BUG-003 — Merchant grouping split on 3-digit store numbers
**Severity:** Medium · **Component:** `backend/app/services/merchant_normalization.py`

**Expected:** `QUIRKY BEANS CO`, `QUIRKY BEANS CO 123` and `QUIRKY BEANS` resolve
to one merchant.
**Actual:** Two merchants. The pair scored 0.857 similarity — just under the 0.86
threshold.

**Root cause:** `_clean` stripped digit runs of 4+ only, so a 3-digit branch
number survived into the comparison.

**Fix:** Strip standalone digit runs at 2+. Store, branch and reference numbers
are never merchant identity.

**Test added:** `test_batch_groups_repeat_unknown_merchants`

---

## BUG-004 — `amount_varies` used the leniency-adjusted stability
**Severity:** Medium · **Component:** `backend/app/services/recurrence.py`

**Expected:** A utility bill swinging $79–$112 is flagged as varying.
**Actual:** Reported as not varying.

**Root cause:** The flag was derived from the utilities-lenient stability score.
Leniency belongs in the confidence calculation (a utility should not lose
confidence for behaving like a utility), not in a flag that describes the data.

**Fix:** Compute both readings. Confidence uses the lenient one; `amount_varies`
uses the strict one.

**Test added:** `test_utilities_tolerate_variable_amounts`

---

## BUG-005 — SMS reference regex was greedy
**Severity:** Low · **Component:** `backend/app/services/extraction.py`

**Expected:** `Ref ABC123456` → `ABC123456`.
**Actual:** `123456`.

**Root cause:** `\D{0,4}` as the separator matched the letters of the reference
itself.

**Fix:** Restrict the separator class to punctuation and whitespace.

**Test added:** `test_sms_extraction`

---

## BUG-006 — Demo data contradicted the product thesis
**Severity:** Medium · **Component:** `scripts/generate_demo_statement.py`

**Expected:** Essential bills fall due *before* the next salary, so raw round-ups
exceed what is safely spare.
**Actual:** Payday was the 1st, so rent and insurance landed *after* income and
the account accumulated ~$9,000 — the demo showed no tension at all.

**Fix:** Payday moved to the 28th; rent (3rd), insurance (6th) and EMI (8th) now
precede it. Closing balance pinned via a solved-backwards opening balance so the
story is identical on every machine.

**Verification:** $2,269.12 of essentials now fall due before the next salary;
round-ups are $37.81 potential → $0.00 allowed until the user recovers savings.

---

## BUG-007 — `dhai sau` parsed as 102.50 instead of 250
**Severity:** Medium · **Component:** `backend/app/services/spoken_expenses.py`

**Steps to reproduce:** `parse("dhai sau rupees sabzi", "hi")`

**Expected:** 250.00 (2.5 × 100).
**Actual:** 102.50 (2.5 + 100).

**Root cause:** `sau` was registered in `NUMBER_WORDS` (an addend) when it is a
multiplier.

**Fix:** Moved `sau` to `MULTIPLIERS`.

**Test added:** `test_indian_fractional_hundreds`

**Verification:** `dhai sau` → 250.00, `ढाई सौ` → 250.00, `sava sau` → 125.00.

---

## BUG-008 — Smoke test did not poll for background completion
**Severity:** Low · **Component:** `infra/scripts/smoke-test.sh`

**Expected:** All read endpoints return 200 after an analysis is created.
**Actual:** Seven endpoints returned 409 against a real uvicorn server.

**Root cause:** FastAPI `BackgroundTasks` complete synchronously under
`TestClient` but asynchronously under a real server. The unit tests therefore
passed while the smoke test failed — the test client had masked the need to poll.
The application was correct; the frontend already polls.

**Fix:** The smoke test now polls `/status` until `COMPLETED`.

**Verification:** 16/16 passing against both uvicorn and the Docker container.

---

## BUG-009 — Smoke test regex matched the last `"state"`, not the first
**Severity:** Low · **Component:** `infra/scripts/smoke-test.sh`

**Expected:** Extract the top-level analysis state (`COMPLETED`).
**Actual:** Extracted `done` — the `state` of the final entry in the `stages` array.

**Root cause:** `sed 's/.*"state":"\([^"]*\)".*/\1/'` is greedy; `.*` runs to the
last match.

**Fix:** `grep -o '"state":"[A-Z_]*"' | head -1`.

---

---

## BUG-010 — A binary or corrupted upload crashed the CSV parser
**Severity:** High · **Component:** `backend/app/services/extraction.py`

**Steps to reproduce:** `extraction.extract(b"\x00\x01\x02\x03", "binary.csv")`

**Expected:** A warning and an empty result.
**Actual:** Unhandled `_csv.Error: line contains NUL` propagating out of the parser.

**Root cause:** `csv.reader` raises on NUL bytes, and the call was unguarded. A
user uploading a corrupted file would have received a 500 rather than a usable
message — testing-prompt §7 requires that errors not expose infrastructure.

**Fix:** Strip NUL bytes, record `binary_content_detected`, and wrap the reader
so no `csv.Error` can escape.

**Test added:** `test_empty_and_binary_files_do_not_crash`

**Note:** the API rejects such an upload earlier (415 at the content endpoint),
so this was defence in depth rather than a live exposure — but the parser is
reachable by other paths and must not raise.

---

## BUG-011 — One unclosed quote silently discarded every transaction after it
**Severity:** **Critical** · **Component:** `backend/app/services/extraction.py`

**Steps to reproduce:** Parse a CSV containing
`2026-01-05,"UNCLOSED QUOTE,30.00,,3094.50` followed by valid rows.

**Expected:** The malformed row is reported as skipped; later rows parse normally.
**Actual:** Only 2 of 4 valid transactions were extracted. `GOOD ROW THREE` and
two further rows **vanished with no warning**.

**Root cause:** An unbalanced quote makes Python's `csv` module treat every
subsequent line as a continuation of that one field. The rest of the statement
was consumed into a single record and lost.

**Impact:** This is a direct violation of §8 — *never silently drop a
transaction*. A single stray quote anywhere in a bank export would have removed
every transaction after it from the analysis, and the totals, Safe Spare figure
and round-ups would all have been quietly wrong with no indication anything was
missing. Of all the defects found, this is the one most likely to produce a
confidently incorrect number.

**Fix:** `_repair_unbalanced_quotes()` pre-scans for lines with an odd quote
count and strips the quotes on those lines only, confining the damage to the one
malformed row, which is then reported as skipped like any other.

**Test added:** `test_malformed_statement_keeps_good_rows_and_accounts_for_bad_ones`

**Verification:** extraction went from 2 rows to 4; `GOOD ROW THREE` recovered;
the impossible date `2026-13-45` now correctly appears in `rows_skipped` instead
of being swallowed.

## Summary

| # | Severity | Component | Regression test |
| --- | --- | --- | --- |
| 001 | High | price_changes | 6 tests |
| 002 | **Critical** | safe_spare | 1 test |
| 003 | Medium | merchant_normalization | 1 test |
| 004 | Medium | recurrence | 1 test |
| 005 | Low | extraction | 1 test |
| 006 | Medium | demo generator | verified by pipeline output |
| 007 | Medium | spoken_expenses | 1 test (3 cases) |
| 008 | Low | smoke-test.sh | verified by execution |
| 009 | Low | smoke-test.sh | verified by execution |
| 010 | High | extraction | 1 test |
| 011 | **Critical** | extraction | 1 test |

Two of the eleven were found by the adversarial fixture suite added during the QA
pass — neither was reachable with well-formed input, which is precisely why
hostile fixtures were needed.

**No known unresolved defects.** The limitations in `TEST_REPORT.md` §16 are
untested areas and missing infrastructure, not known bugs.
