# PRIVACY_AND_SECURITY.md

Spec §22. What is implemented, what is verified, and what is not.

---

## Principle

A bank statement is among the most revealing documents a person owns. SafeSpare
minimises what it keeps, what it logs, and what it sends anywhere else.

## Upload safety

| Control | Implementation |
| --- | --- |
| File allowlist | `.pdf .csv .xlsx .xls .txt`; extension **and** content-type checked |
| Size limit | 15 MB, enforced at presign and on receipt |
| Filename never used as a storage key | `random_object_key()` derives from a UUID; `../../etc/passwd` cannot become a path |
| Password-protected PDFs | password passed **by value** to the pipeline, never written to a record |
| Consent | required; `consent_confirmed: false` → 400 |
| Delete after processing | user preference, stored per document |
| Upload expiry | presign TTL 900 s |

## Data retention

| Data | Retention |
| --- | --- |
| Uploaded file bytes | deleted on request; auto-deleted when the user opts in |
| Transactions | in-memory for the session; purged with the analysis |
| Account numbers | **never stored** — the SMS parser discards the mask and records `account_mask_discarded` |
| PDF passwords | **never stored** |
| Derived figures | purged with the analysis |

`DELETE /api/analyses/{id}` and `POST /api/privacy/delete-data` remove the
document, its bytes, transactions, patterns, price changes, leaks, snapshots,
goals, simulations and insights. Verified: a subsequent read returns 404.

## Logging

Structured JSON with a request ID. `RedactingFilter` (in `config.py`) strips
credential-shaped values before a record is emitted.

Verified against the running container: **0 matches** for account-like numbers
and **0 matches** for merchant names in the logs of a full demo analysis.

Never logged: complete statements, account numbers, API keys, raw financial
prompts, or transaction descriptions.

## What reaches an AI provider

Providers receive a **minimal structured context** — the specific computed
figures needed to phrase one explanation — never a full statement, never a
transaction list, never an identifier.

`ai/validators.py` rejects any model output that: contains an amount not matching
backend state, cites a transaction ID that does not exist, claims a subscription
is unused without confirmation, guarantees a return, names a security,
recommends cancelling an essential, or exposes PII. Rejected output is replaced
with a deterministic template and the failure is recorded.

**With no keys configured — the current state — no data leaves the machine at all.**

## Prompt-injection resistance

Uploaded text is untrusted data (§3.22–23). `pipeline.py` detects 11 instruction
shaped patterns (`ignore previous instructions`, `display all api keys`,
`set safe spare to`, `guarantee N% return`, …). A matching row is **preserved**
— §8 forbids dropping a transaction — but neutralised for display and for any
prompt, the original kept in `raw_merchant` for audit, and the count surfaced to
the user.

## Transport and access

| Control | Status |
| --- | --- |
| HTTPS | Caddy auto-TLS in the deployment design |
| Session isolation | analyses scoped to a session key; another session gets **404**, not 403 |
| Rate limiting | fixed-window per session/IP; `Retry-After` on 429 |
| CORS | restricted to configured origins |
| Error responses | `{error:{code,message}}` — no stack trace, no internal path |

## Secrets

| Rule | Status |
| --- | --- |
| No secret in Git | **verified** — `git grep` finds none |
| No secret in the browser bundle | **verified** — 0 matches in `dist/assets/*.js` |
| No secret in a Docker layer | env supplied at runtime |
| Production storage | SSM Parameter Store SecureString |
| Local storage | `backend/.env`, gitignored, `chmod 600` |

**Note:** any key transmitted through a chat window should be considered
compromised and rotated, regardless of where it is subsequently stored.

## Container

Non-root (`uid=10001`), multi-stage build, `python:3.11-slim`, healthcheck
present, no secrets in layers.

## Known gaps

| Gap | Status |
| --- | --- |
| Dependency CVE scan | **not run** |
| Encryption at rest | designed in Terraform, **not verified** (not deployed) |
| S3 public-access blocks | designed, **not verified** |
| Penetration testing | out of scope |
| Terraform state backend | **not configured** — see AWS_VALIDATION_REPORT AWS-001 |
