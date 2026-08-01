# Tiffany Payments — Phase IV Independent Production Validation Report

**Date:** 2026-08-01  
**Mode:** Evidence-only — no new implementation  
**Baseline audited:** Phase III working tree (local, largely **uncommitted**)  
**Production VPS baseline:** commit `8b2dbed` — **does not include Phase III ledger**

---

## 1. Executive Summary

Phase III payment reliability is **IMPLEMENTED in local working tree** but **NOT VERIFIED under real infrastructure**.

| Layer | Status |
|---|---|
| Code exists | ✅ Local only (`infra/payments/`, migration 004, ledger refactor) |
| Deployed to production | ❌ **NOT on VPS** (git status: untracked/uncommitted) |
| CI validation | ❌ `test_payments_phase3.py` **not in CI** (only `test_smoke`) |
| PostgreSQL integration tests | ❌ **None** |
| Stripe CLI / live webhook tests | ❌ **NOT VERIFIED** |
| Production webhook deliveries | ❌ **0 events** (Dashboard misconfiguration, Phase I) |

**Final verdict:** Architecture claims are **THEORETICAL** until empirical experiments run. **Do not accept customer payments** on Phase III claims alone.

---

## 2. Claim Verification Matrix

| Phase III Claim | Implementation | Verification | Status |
|---|---|---|---|
| Atomic idempotency (`INSERT … ON CONFLICT`) | `ledger.claim_event` | No PG test, not deployed | **THEORETICAL** |
| State machine (received→completed) | `ledger.process_stripe_event` | No integration test | **THEORETICAL** |
| Transactional outbox | `payment_outbox` + `worker.py` | No test, not deployed | **THEORETICAL** |
| Append-only audit trail | `payment_audit_log` | No test, migration unapplied in prod | **THEORETICAL** |
| Fail-closed tier resolution | `tiers.py` | 5 unit tests, no CI | **PARTIALLY VERIFIED** |
| Metadata validation | `tiers.validate_discord_metadata` | 4 unit tests, no CI | **PARTIALLY VERIFIED** |
| Stale processing recovery (600s) | `claim_event` + `worker.recover_stale` | No time-based test | **THEORETICAL** |
| Reconciliation job | `reconciliation.py` | Never executed in audit | **THEORETICAL** |
| Webhook signature verification | `stripe_server._verify_stripe_signature` | Pre-Phase III prod path only | **PARTIALLY VERIFIED** (design) |
| `/premium` → checkout metadata | `premium_cog.py` | Not deployed, no E2E | **IMPLEMENTED / UNVERIFIED** |
| Metrics (no fake KPIs) | `metrics.py` | 1 counter unit test | **PARTIALLY VERIFIED** |
| Exactly-once premium grant | Full ledger path | **NOT VERIFIED** | **UNKNOWN** |
| Crash recovery | Single PG transaction | No kill -9 test | **THEORETICAL** |
| Discord side-effect recovery | Outbox worker | No Discord failure test | **THEORETICAL** |
| Reconciliation repair | Documented as detect-only | Code confirms no auto-repair | **IMPLEMENTED (detect only) / UNVERIFIED** |

**Rule applied:** Implementation ≠ verification. Unit tests on helper functions ≠ ledger verification.

---

## 3. Financial Integrity Matrix

| Financial action | Duplicate possible? | Evidence | Status |
|---|---|---|---|
| Premium activation | Unknown | No E2E | **UNKNOWN** |
| Subscription cancel | Upsert idempotent in SQL | Code review only | **THEORETICAL** |
| Tier grant on unknown price | Blocked in code | Unit test on `resolve_tier` | **PARTIALLY VERIFIED** |
| Grant via Payment Link (no metadata) | Still possible if old links used | `/premium` fixed locally, not deployed | **RISK — UNVERIFIED** |
| Double webhook concurrent delivery | Designed prevention via PG | No concurrent test | **THEORETICAL** |
| Lost event (never processed) | Possible if webhook URL wrong | Dashboard shows 0 deliveries | **VERIFIED RISK** |
| Audit trail for every grant | Designed | No runtime proof | **THEORETICAL** |

**Tiffany does not charge cards** — double-charge is Stripe's domain. Double **entitlement** is Tiffany's domain — **unproven safe**.

---

## 4. Exactly-Once Validation

### Designed mechanism (code review)

1. Verify Stripe signature (pre-ledger)
2. Single `async with conn.transaction()` wrapping:
   - `claim_event` (INSERT ON CONFLICT)
   - business handlers (subscription upsert)
   - outbox enqueue
   - `mark_completed`
3. On exception: transaction rollback + `mark_failed` (best-effort UPDATE)

### Verification status

| Property | Verified? | Notes |
|---|---|---|
| Exactly-once processing | ❌ | Requires PG + concurrent webhook test |
| Atomic state transitions | ❌ | Single transaction — plausible, not tested |
| Crash recovery | ❌ | No kill -9 during handler |
| Duplicate webhook protection | ❌ | No `stripe events resend` test |
| Replay safety (timestamp) | ⚠️ | 300s tolerance — design only |
| Stale processing recovery | ❌ | 600s threshold — no clock test |

**Dependency:** All exactly-once claims **require PostgreSQL** with migration `004_payment_reliability.sql` applied. Without PG: server refuses start (designed fail-closed) — **not verified on VPS**.

**Unit test coverage of ledger:** **Zero tests** in `test_payments_phase3.py` for `ledger.py`.

---

## 5. Transactional Outbox Validation

| Question | Answer | Evidence |
|---|---|---|
| Messages can be lost? | **Possible** if worker never runs | Worker starts with stripe server — not deployed |
| Duplicate deliveries? | **Possible** if `mark_delivered` fails after side effect | No idempotency key on outbox consumer |
| Worker crash inconsistent state? | Outbox row stays `pending` | Designed retry — not tested |
| Retries safe? | Backoff + dead-letter at 8 attempts | Code only |
| Ordering guaranteed? | **No** | `FOR UPDATE SKIP LOCKED`, no ordering key |
| Discord failures recoverable? | Cache invalidate retried | No Discord API in outbox today — only cache |

**Failure modes not validated:**

- Outbox delivered but cache invalidate fails repeatedly → dead-letter, entitlement stale until manual fix
- Duplicate outbox rows for same event (prevented: one enqueue per successful transaction — not tested)
- Worker and webhook same process — VPS kill stops both

---

## 6. Stripe Validation

| Scenario | Executed? |
|---|---|
| Stripe CLI forward | ❌ **NOT VERIFIED** |
| Webhook retries | ❌ **NOT VERIFIED** |
| Duplicated events | ❌ **NOT VERIFIED** |
| Delayed events | ❌ **NOT VERIFIED** |
| Replay attacks (bad signature) | ❌ **NOT VERIFIED** (unit-level only) |
| payment_failed | ❌ **NOT VERIFIED** |
| Subscription upgrade/downgrade | ❌ **NOT VERIFIED** |
| Cancellation | ❌ **NOT VERIFIED** |
| Resumed subscription | ❌ **NOT VERIFIED** |
| checkout.session.completed E2E | ❌ **NOT VERIFIED** |
| Live Dashboard webhook URL | ❌ Misconfigured (`https://tiffanybot.com` root) |

**Production Stripe webhook metrics:** 0 deliveries (user screenshot, Phase I audit).

---

## 7. PostgreSQL Validation

| Scenario | Tested? |
|---|---|
| Concurrent transactions (2 webhooks, same event_id) | ❌ |
| Row locks (`FOR UPDATE SKIP LOCKED`) | ❌ |
| Deadlocks | ❌ |
| Transaction rollback on handler error | ❌ (design: yes) |
| Crash recovery / WAL | ❌ |
| Process kill mid-transaction | ❌ |
| Migration 004 applied | ❌ **UNKNOWN on VPS** |
| `stripe_events.status` columns exist | Required — **unverified** |

**Mocks/SQLite:** None used. **Real asyncpg integration tests:** None exist.

**CI:** No PostgreSQL service in GitHub Actions workflows.

---

## 8. Failure Injection Coverage

| Scenario | Validated? | Operational risk |
|---|---|---|
| kill -9 during handler | ❌ | **HIGH** |
| PostgreSQL restart mid-webhook | ❌ | **HIGH** |
| Redis restart | ❌ | **MEDIUM** (cache stale, not financial source of truth) |
| Stripe API outage during checkout retrieve | ❌ | **MEDIUM** |
| Discord API outage | ❌ | **LOW** (outbox only invalidates cache) |
| Network partition VPS ↔ Stripe | ❌ | **HIGH** |
| Disk full on PG | ❌ | **HIGH** |
| Database corruption | ❌ | **CRITICAL** |
| Clock skew (replay tolerance) | ❌ | **MEDIUM** |
| Duplicate webhook storm (100× same event) | ❌ | **HIGH** |
| Webhook delivery after 24h | ❌ | **MEDIUM** |
| VPS reboot during transaction | ❌ | **HIGH** |
| Migration missing → runtime crash | ❌ | **HIGH** (uncommitted code) |
| Webhook secret rotated without VPS update | ❌ | **HIGH** |
| Wrong webhook URL (0 deliveries) | ✅ **Observed** | **CRITICAL** |

---

## 9. Missing Experiments (required before production)

### P0 — Must run before any live payment

1. **Deploy Phase III to staging** with `DATABASE_URL` + migration 004
2. **Fix webhook URL** → `https://<domain>/stripe/webhook` → `:8080`
3. **Stripe CLI:** `stripe listen --forward-to localhost:8080/stripe/webhook`
4. **Complete test checkout** → verify `subscriptions` row + `payment_audit_log` + outbox delivered
5. **`stripe events resend evt_...`** → confirm duplicate returns `already_processed`, no double tier
6. **Concurrent resend** (2 terminals) → confirm one winner
7. **Rotate `[REDACTED_SECRET]`** after any exposure

### P1 — Before calling system production-grade

8. kill -9 bot during `processing` state → verify stale recovery or Stripe retry
9. `systemctl restart postgresql` during webhook
10. Reconciliation run with intentional drift (cancel sub in Stripe only)
11. Unknown price_id event → confirm rejection + audit entry
12. Add `test_payments_phase3` + PG integration job to CI

### P2 — Operational maturity

13. Prometheus scrape of `/metrics`
14. Outbox dead-letter alert
15. Reconciliation auto-repair policy (if desired)

---

## 10. Operational Risks

1. **CRITICAL:** Phase III not deployed — production still on pre-ledger code
2. **CRITICAL:** Webhook never delivers — payments cannot activate premium
3. **CRITICAL:** Signing secret exposure — rotation unverified
4. **HIGH:** No PG integration tests — exactly-once is faith-based
5. **HIGH:** Uncommitted code — VPS deploy script updated locally but code not on `origin/main`
6. **MEDIUM:** Reconciliation detects only — drift persists until manual fix
7. **MEDIUM:** Outbox has no Discord DM — user unaware of activation

---

## 11. Remaining Unknowns

- Does migration 004 apply cleanly on production PG?
- Does `claim_event` work when `stripe_events` has legacy rows (pre-status column)?
- Concurrent duplicate webhooks under real asyncpg pool pressure?
- Behavior when Stripe sends events out of order (deleted before completed)?
- WAL recovery after hard VPS power loss?
- False positive rate of reconciliation drift detection?
- End-to-end trace: Stripe charge ID → audit log → guild entitlement in Discord command?

---

## 12. Production Readiness

| Criterion | Met? |
|---|---|
| Exactly-once proven | ❌ |
| Outbox proven | ❌ |
| Audit trail proven | ❌ |
| Reconciliation proven | ❌ |
| Stripe E2E proven | ❌ |
| Security credentials rotated | ❌ |
| Webhook operational | ❌ |
| Code on production VPS | ❌ |

**Production readiness: NO**

---

## 13. Required Evidence Before Production

Accept customer payments only after **documented evidence** of:

1. Screenshot/log: Stripe Dashboard webhook delivery success ≥1 event
2. SQL query: matching row in `subscriptions` + `payment_audit_log` for that `event_id`
3. Log: `webhook_duplicate` metric increment on resend without second activation
4. Rotated secrets deployed to VPS `.env`
5. CI green including payment tests
6. Commit on `origin/main` deployed via GitHub Actions

---

## 14. Final Verdict

### What has been proven?

- Tier/metadata **validation logic** rejects bad input (unit tests, not in CI)
- Production webhook is **misconfigured** (0 deliveries) — **verified operational failure**
- Phase III code **exists locally** — verified by repository inspection
- Pre-Phase III Stripe handler had **known idempotency gaps** — verified by Phase I–II audit

### What is only implemented?

- Payment ledger with PG transaction boundary
- State machine columns and audit/outbox tables
- Outbox worker and reconciliation loop
- Fail-closed tier resolution in webhook path
- `/premium` checkout metadata wiring (local)
- Metrics endpoint

### What remains theoretical?

- Exactly-once premium activation
- Crash and stale recovery
- Outbox eventual delivery guarantees
- Reconciliation drift detection accuracy
- End-to-end Stripe → Discord entitlement flow
- All "production-grade" claims in Phase III report

### What experiments must still run?

**Minimum viable proof (≈2–4 hours on staging):**

```bash
# 1. Staging with DATABASE_URL + migration 004
# 2. stripe listen --forward-to localhost:8080/stripe/webhook
# 3. Complete /premium checkout in test mode
# 4. Verify SQL:
#    SELECT * FROM stripe_events WHERE event_id = 'evt_...';
#    SELECT * FROM payment_audit_log ORDER BY created_at DESC LIMIT 5;
#    SELECT tier FROM subscriptions WHERE subject_id = <guild_id>;
# 5. stripe events resend evt_... — expect already_processed, tier unchanged
```

Until this passes with saved logs: **Phase III is implemented, not verified.**

---

*Evidence overrides implementation. Architecture overrides nothing.*
