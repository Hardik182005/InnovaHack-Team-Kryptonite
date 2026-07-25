# JUDGE_DEMO.md — the five-minute demo

**Track:** FinTech — Problem Statement 2: Smart Expense & Micro-Investment Assistant
**One line:** *Round-up apps assume spare change is always safe. SafeSpare checks first.*

## Before you start

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000 &
cd frontend && npm run dev          # http://localhost:5173
```

Open the landing page. Have a phone ready for the mobile and voice moments.

Every figure below was produced by the real pipeline on the synthetic demo
statement. If a number differs on the day, read what is on screen — nothing is
hardcoded.

---

## 0:00–0:30 · The problem

> "Round-up apps assume spare change is always safe to invest. But even small
> automatic deductions cause harm when rent, bills and salary timing are ignored.
> If your rent is due on the 3rd and you're paid on the 28th, the £40 sitting in
> your account this morning is not spare — it's already spoken for."

**Show:** the landing headline — *"Discover what you can safely save—without
risking tomorrow's bills."*

## 0:30–1:15 · Upload and review

Click **Try Demo Statement**. The processing screen shows all nine §19 stages.

> "Six months, 195 transactions, from a CSV or a PDF — both parse identically.
> The running balance reconciles, so we know nothing was dropped."

**Show:** the extraction review table — merchant, category, confidence, source
page and row for every line. Change one category; the figures recalculate and an
audit record is written.

## 1:15–2:00 · Understand and protect

Open the **Dashboard**.

> "$19,234 in, $18,930 out. But the split that matters is $13,554 essential
> against $5,376 discretionary."

**Show:** *Bills due before your next income* — rent $1,450, insurance $128,
loan EMI $312.40, utilities, groceries.

> "$2,269 of essential bills fall due before the next salary arrives. That money
> is not available, whatever the balance says today."

## 2:00–2:45 · Safe Spare — the core

Open **Safe Spare**.

> "Here is the whole calculation, not a single opaque number."

| | |
| --- | --- |
| Latest balance | $2,880.00 |
| Expected income before next payday | $0.00 |
| Essential bills due first | −$2,269.12 |
| Projected balance | $610.88 |
| Safety buffer | −$564.76 |
| Volatility reserve | −$49.14 |
| **Safe Spare** | **$0.00** |

> "Expected income is zero because the salary *is* the next income event — we
> refuse to count money that hasn't arrived. After protecting bills, a buffer and
> a volatility reserve, nothing is safely spare this month. An ordinary round-up
> app would have taken $37.81 anyway."

## 2:45–3:30 · Leak Radar

Open **Leak Radar**.

> "CloudVault went from $9.99 to $13.99 in April — a 40% rise, with the exact
> transactions as evidence. The backend calculated that; no AI was involved."

**Show the gym** — score 18, *no cancel button*.

> "We know it's charged monthly. We do not know whether it's used — a bank
> statement cannot tell you that. So we ask instead of assuming."

Answer **"I haven't used it."** Score rises to 43, cancel appears.

Click **Cancel** — the dialog says plainly: *SafeSpare has not contacted this
merchant and cannot cancel anything for you.*

> "Try the same on rent." → **422 PROTECTED_EXPENSE.** Essential expenses can
> never receive cancellation advice, regardless of score.

## 3:30–4:15 · Redirect and simulate

> "That confirmed $49 a month changes everything."

**Show:** Safe monthly contribution $0.00 → **$49.00**. Round-ups $0.00 → **$37.81**.

Open **Goals**, create a $2,000 emergency fund over 24 months, run the scenarios.

## 4:15–4:45 · Principal vs growth, and the guardrails

**Show:** the stacked chart — *your contributions* and *illustrative growth* are
always separate bands.

> "We never blend market growth into money you actually saved. The disclaimer is
> always visible, we name no security, and nothing is ever executed."

**Optional, 20 seconds:** open `/speak` on the phone. Say *"मैंने सब्ज़ी पर 250
रुपये खर्च किए"* — it's read back in Hindi and recorded.

> "For users with no bank statement, or who can't read one: 26 languages, voice
> in and voice out."

## 4:45–5:00 · Close

Play the voice summary, then:

> **"SafeSpare does not ask users to invest more. It first determines what their
> life can safely spare."**

---

## If a judge probes

| Question | Answer |
| --- | --- |
| "Does the AI calculate this?" | No. `app/services/` is pure Python, 145 tests, no network. Models may only rephrase computed values; `ai/validators.py` rejects any output whose numbers don't match. |
| "What if the AI is down?" | Everything works. There are no keys configured right now — every refusal you saw was deterministic. |
| "Can it cancel my subscription?" | No. It drafts a message you send yourself. Every response carries `executed: false`. |
| "Is this a credit score?" | No, and Cashflow Confidence says so on screen. It uses no personal attributes — the function signature only accepts transactions. |
| "Where's the data?" | In-memory for the demo, deleted on request. Account numbers are never stored; the log scan finds zero. |
| "Is it deployed?" | Not yet — terraform and the aws CLI aren't installed here. The Docker image builds and passes 16/16 smoke tests, and the deploy script is written. |

## Recovery

| If | Do |
| --- | --- |
| Backend won't start | `cd backend && .venv/bin/python -m pytest tests/ -q` — 238 should pass |
| Demo statement missing | `python3 scripts/generate_demo_statement.py --out demo_data` |
| Frontend can't reach API | It falls back to labelled fixtures; the demo still runs |
| Voice does nothing | Chrome or Edge only; the typed path always works |
