# Tiffany Payments — Phase V Independent Production Audit

**Date:** 2026-08-01  
**Auditor stance:** Independent Staff/Principal Engineer — attempt to **falsify** all claims  
**Method:** Direct repository inspection + local test execution — **no trust in prior reports**  
**Production baseline:** `origin/main` @ `8b2dbed` (HEAD at audit time)  
**Working tree:** Phase III ledger exists **locally, uncommitted**

---

## Executive Summary

Tiffany Payments has **two distinct codebases** in this repository:

| Codebase | Path | Relation to live bot |
|---|---|---|
| **Tiffany Bot (production path)** | `infra/stripe_server.py`, `infra/premium.py`, `schema/002_*` | ✅ Tracked; **deployed on VPS** via GitHub Actions |
| **Phase III ledger (uncommitted)** | `infra/payments/*`, `schema/004_*` | ❌ **Untracked** — **not on `origin/main`**, **not on VPS** |
| **Tiffany Core OSS (separate)** | `tiffany_core/*`, `test_phase5_*`, `test_phase6_*` | ❌ **Not wired into bot runtime** — **not payment evidence** |

**Critical finding:** Production runs the **pre-ledger** webhook handler (`9b7959d` architecture) with check-then-process idempotency, `"premium"` tier fallback, and cache invalidation **inside** the webhook path. Phase III claims **do not apply to production** until committed and deployed.

**Evidence executed during this audit:**
- `py -m pytest test_payments_phase3.py` → **13/13 passed** (helper modules only; no PG/Stripe)
- Git inspection: `infra/payments/` is `??` untracked
- `origin/main:infra/stripe_server.py` inspected via `git show`
- CI workflows inspected: **only `test_smoke`**

**No runtime evidence found for:** Stripe CLI, webhook deliveries, PostgreSQL integration tests, concurrent claims, crash recovery, staging deployment of Phase III.

**Verdict:** Tiffany **cannot safely accept real Stripe payments today** with proven financial consistency or exactly-once entitlement processing.

---

## Mandatory Subsystem Answers

For each subsystem: **Implemented? | Committed? | Deployed? | Executed? | Measured? | Observed? | Verified?**

| Subsystem | Impl | Commit | Deploy | Exec | Meas | Obs | Verified |
|---|---|---|---|---|---|---|---|
| Stripe SDK integration | ✅ local + prod | ✅ | ⚠️ prod old code | ❌ E2E | ❌ | ❌ | **NO** |
| Webhook HTTP server (:8080) | ✅ | ✅ | ⚠️ if env set | ❌ deliveries | ❌ | ❌ 0 events | **NO** |
| Signature verification | ✅ | ✅ | ⚠️ | ❌ live | ❌ | ❌ | **PARTIAL** (code only) |
| Ledger (`infra/payments/`) | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| State machine | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Idempotency (atomic claim) | ✅ local | ❌ | ❌ prod=TOCTOU | ❌ | ❌ | ❌ | **NO** |
| Transactional outbox | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Audit trail | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Reconciliation | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Premium activation | ✅ | ✅ | ⚠️ | ❌ E2E | ❌ | ❌ | **NO** |
| PostgreSQL / asyncpg | ✅ code | ✅ pool | **UNKNOWN** VPS | ❌ int tests | ❌ | ❌ | **UNKNOWN** |
| Migrations (002) | ✅ | ✅ | ⚠️ if PG+startup | ⚠️ auto on boot | ❌ | ❌ | **UNKNOWN** |
| Migration 004 | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Deploy pipeline | ✅ GHA | ✅ | ✅ bot deploys | ✅ GHA runs | ❌ pay | ⚠️ bot up | **PARTIAL** |
| Docker payment stack | ⚠️ optional | ✅ | ❌ systemd prod | ❌ | ❌ | ❌ | **NO** |
| Reverse proxy / HTTPS | ❌ docs only | ❌ | ❌ | ❌ | ❌ | ❌ URL wrong | **NO** |
| Metrics `/metrics` | ✅ local | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Prometheus | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **ABSENT** |
| Grafana | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **ABSENT** |
| Alerting | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **ABSENT** |
| Security rotation | 📋 documented | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |
| Disaster recovery tests | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **NO** |

---

## Production Readiness Gates

Every capability appears **once**. Evidence column cites repository facts only.

| Capability | VERIFIED | PARTIALLY VERIFIED | THEORETICAL | UNKNOWN | Evidence |
|---|---|---|---|---|---|
| Webhook signature verification (design) | | ✅ | | | HMAC + SDK in `stripe_server.py`; no live bad/good sig test |
| Production webhook endpoint reachable | | | | ✅ | Dashboard 0 deliveries (Phase I screenshot cited in docs); URL misconfig |
| Atomic idempotency claim | | | ✅ | | Phase III `ledger.claim_event`; untracked; never run on PG |
| Production idempotency (check-then-mark) | | | ✅ | | `origin/main`: `_is_event_processed` → handler → `_mark_event_processed` |
| Exactly-once entitlement processing | | | | ✅ | No concurrent/resend experiment |
| State machine persistence | | | ✅ | | `004_payment_reliability.sql` untracked |
| Single-transaction financial mutation | | | ✅ | | Code review `process_stripe_event`; no PG test |
| Transaction rollback on handler error | | | ✅ | | asyncpg transaction in code; not demonstrated |
| Duplicate webhook storm | | | | ✅ | No load test |
| Crash recovery (kill -9) | | | | ✅ | No experiment |
| Stale processing recovery | | | ✅ | | 600s logic in ledger + worker; not time-tested |
| Transactional outbox | | | ✅ | | Tables + worker untracked |
| Outbox retry / dead-letter | | | ✅ | | Constants in code; not executed |
| Outbox ordering | | | | ✅ | `ORDER BY created_at` only; no cross-partition guarantee |
| Discord side-effect via outbox | | | ✅ | | Cache invalidate only; no DM; not run |
| Append-only audit trail | | | ✅ | | `payment_audit_log` untracked |
| Reconciliation drift detection | | | ✅ | | Detect-only; `corrections` always `[]` |
| Reconciliation auto-repair | | | | ✅ | Explicitly not implemented |
| Fail-closed tier resolution | | ✅ | | | 13 unit tests local; not in CI |
| Metadata validation | | ✅ | | | Unit tests; no forged checkout E2E |
| Production tier `"premium"` fallback | | | ✅ | | `origin/main` checkout handler |
| `cancelled_at` entitlement filter | | | ✅ | | Local `premium.py` diff; prod unverified |
| Stripe CLI / test checkout E2E | | | | ✅ | No logs or artifacts |
| `checkout.session.completed` live | | | | ✅ | |
| `customer.subscription.updated` live | | | | ✅ | |
| `invoice.payment_failed` live | | | | ✅ | |
| PostgreSQL real instance for payments | | | | ✅ | `DATABASE_URL` optional; VPS state unknown |
| asyncpg concurrent transactions | | | | ✅ | |
| Row locking (`SKIP LOCKED`) | | | | ✅ | |
| Migrations on bot startup | | | ✅ | | `postgres.run_migrations()` runs all `schema/*.sql` |
| Migration 004 applied anywhere | | | | ✅ | File untracked on remote |
| GitHub Actions payment tests | | | | ✅ | CI = `test_smoke` only |
| Phase III deployed to VPS | | | | ✅ | Untracked files not on `origin/main` |
| systemd bot process | | ✅ | | | Deploy workflow + `deploy.sh` evidence |
| Docker bot for payments | | | | ✅ | Profile `docker-bot`; prod uses systemd |
| HTTPS / reverse proxy to :8080 | | | | ✅ | Documented gap; no nginx/Caddy in repo |
| In-process metrics JSON | | | ✅ | | `/metrics` in local stripe_server only |
| Prometheus scraping | | | | ✅ | Not configured |
| Grafana dashboards | | | | ✅ | Not configured |
| Payment alerting | | | | ✅ | Not configured |
| Secret rotation completed | | | | ✅ | Recommended in docs; no proof |
| Git history secret exposure | | ✅ | | | Old `.env` tokens in history (Phase I) |
| No duplicate entitlement (proven) | | | | ✅ | |
| No entitlement loss (proven) | | | | ✅ | |
| Financial consistency (proven) | | | | ✅ | |

---

## Exactly-Once Audit

| Scenario | Production (`origin/main`) | Phase III (local) | Empirical evidence |
|---|---|---|---|
| Atomic claim | ❌ SELECT then INSERT after handler | ✅ INSERT ON CONFLICT in TX | **NONE** |
| Transaction boundary | ❌ Handler outside idempotency TX | ✅ Single `conn.transaction()` | **NONE** |
| Rollback on failure | ⚠️ Partial; mark after success | ✅ TX rollback | **NONE** |
| Duplicate webhooks | ⚠️ TOCTOU race possible | ✅ Designed safe | **NONE** |
| Crash mid-handler | ⚠️ Mark-after-handler gap | ✅ TX atomicity | **NONE** |
| Worker restart | N/A | Same process as bot | **NONE** |
| Stale recovery | ❌ | ✅ 600s + worker | **NONE** |
| Network retry (Stripe) | Returns 500 on error | Returns 500 + `mark_failed` | **NONE** |
| Concurrent processing | ❌ | ✅ claim collision paths | **NONE** |
| DB contention / deadlocks | ❌ | ❌ not tested | **NONE** |
| Multiple deliveries | ❌ | Designed | **NONE** |

**`in_flight` HTTP 200 risk (Phase III):** duplicate delivery while status=`processing` returns 200 `in_flight` — Stripe may **not** retry; stuck state depends on stale recovery (unverified).

**Conclusion:** Exactly-once is **NOT PROVEN** in any environment.

---

## PostgreSQL Audit

| Claim | Demonstrated? |
|---|---|
| Real PostgreSQL | **UNKNOWN** on VPS |
| Real asyncpg pool | Code exists; pool init in `postgres.py` |
| Real transactions | **NOT DEMONSTRATED** for payments |
| Row locking | **NOT DEMONSTRATED** |
| Deadlocks | **NOT DEMONSTRATED** |
| Rollback | **NOT DEMONSTRATED** |
| WAL / restart recovery | **NOT DEMONSTRATED** |
| Migrations 002 | **THEORETICAL** (auto-run if PG present) |
| Migration 004 | **NOT ON REMOTE** |
| Concurrent workers | **NOT DEMONSTRATED** |

CI has **no PostgreSQL service**. All payment ledger tests: **zero**.

---

## Stripe Audit

| Test | Executed? |
|---|---|
| Stripe CLI | ❌ |
| checkout.session.completed | ❌ |
| invoice.payment_succeeded | Ignored by design (early return) |
| customer.subscription.updated | ❌ |
| Duplicate webhook | ❌ |
| Late webhook (>24h) | ❌ |
| Out-of-order events | ❌ |
| Signature validation (live) | ❌ |
| payment_status == paid gate | Local code only |
| Metadata integrity E2E | ❌ |
| Production endpoint | ❌ misconfigured |
| Dashboard delivery evidence | ❌ **0 events** |

---

## Outbox Audit

| Question | Status |
|---|---|
| Real worker running | **THEORETICAL** (uncommitted) |
| Real retries | **THEORETICAL** |
| Crash recovery | **UNKNOWN** |
| Duplicate delivery | Side effect idempotent (cache); **not tested** |
| Ordering | Best-effort `created_at`; **not guaranteed** |
| Dead-letter | Code path exists; **not tested** |
| Discord failures | No Discord API call — cache only |
| Redis failures | Invalidate may fail; **not tested** |
| Worker restart | In-process asyncio task; dies with bot |

---

## Deployment Audit

| Item | Finding |
|---|---|
| GitHub Actions deploy | ✅ Runs on push to `main` |
| `deploy.sh` | Checks out `infra/` from `origin/main` — **Phase III `infra/payments/` absent on remote** |
| Migration execution | Bot startup `run_migrations()` — **004 not on VPS until committed** |
| Production VPS | Bot deploys; payment module version = **pre-ledger** |
| `DATABASE_URL` | Optional; **VPS value unknown** |
| Reverse proxy | **Not in repo**; webhook URL wrong per docs |
| HTTPS | **Not verified** |
| systemd | ✅ Production mode (`DEPLOY_MODE=systemd`) |
| Stripe server start | Conditional on `STRIPE_*` + PG pool |

---

## Metrics & Observability Audit

| Layer | Tiffany Bot Payments | Notes |
|---|---|---|
| Implemented | Local `/metrics` JSON snapshot | Untracked |
| Exported | In-process only | Not Prometheus format |
| Scraped | ❌ | |
| Stored | ❌ | |
| Visualized | ❌ | No Grafana |
| Alerted | ❌ | |

**Prometheus:** ABSENT for payments.  
**Grafana:** ABSENT for payments.  
(Lavalink has prometheus config in `lavalink/application.yml` — **unrelated to payments**.)

---

## Disaster Recovery Audit

**No evidence found** for any of:

kill -9, SIGTERM mid-ledger, PostgreSQL restart, Redis restart, Stripe outage, Discord outage, network partition, disk full, clock skew, backup restore, rollback drill.

All **unverified**. Ranked by operational risk in Failure Injection section of Phase IV (still valid).

---

## Financial Integrity Audit

| Property | Proven? |
|---|---|
| No duplicate entitlement | ❌ |
| No entitlement loss | ❌ |
| Audit trail completeness | ❌ |
| Event ordering | ❌ |
| Subscription consistency | ❌ |
| Reconciliation correctness | ❌ |

**Production-specific risks (verified by code on `origin/main`):**
- Tier fallback `"premium"` on unknown price
- TOCTOU idempotency
- Payment Links without metadata → no guild mapping
- Webhook never delivered → **paid users may not activate**

---

## Security Audit

| Control | Status |
|---|---|
| Webhook secret in repo | ✅ No real secrets in tracked files |
| Git history | ⚠️ **PARTIAL** — old `.env` with Discord/OpenRouter tokens |
| Dashboard secret exposure | ⚠️ Documented; rotation **not verified** |
| Logs / PII | Metadata not echoed in Phase III errors (local) |
| `.env.example` | Documents tuning vars (local) |
| Docker build context | `.dockerignore` expanded locally |
| Secret scanning CI | ❌ **Not implemented** (gitleaks mentioned in docs only) |
| Production secrets | **UNKNOWN** |

---

## Inflation Review (Phases I–IV + adjacent reports)

| Report | Inflated claim | Missing evidence | Correct maturity |
|---|---|---|---|
| Phase I | Webhook "implemented" | 0 deliveries, wrong URL | **PARTIAL** — code yes, ops no |
| Phase II | "Atomic idempotency implemented" | Uncommitted; not deployed | **THEORETICAL** until deploy + test |
| Phase II | "Production readiness NO" | — | ✅ **Correct** |
| Phase III | Table with ✅ on concurrent duplicates | No PG test | Should be **THEORETICAL** |
| Phase III | "Production-grade in design" | — | Acceptable if "design" qualified |
| Phase III | "Adversarial unit tests" | No ledger tests | **PARTIAL** — helpers only |
| Phase IV | Downgrades to THEORETICAL | — | ✅ **Correct** |
| Phase VI (`tiffany_core`) | "VERIFIED financial integrity" | In-memory dict, not Stripe | **PARTIAL** — **not Tiffany Bot payments** |
| `test_phase6_*` docstrings | "Empirically proves production readiness" | SQLite/mocks | **Misleading** for payments |

**Anti-pattern identified:** Treating `test_phase5_adversarial.py` / `test_phase6_real_infrastructure.py` as payment validation — they test **`tiffany_core`**, not `infra/payments/`.

---

## Required Experiments Roadmap

### P0 — Before accepting real payments

| # | Objective | Expected evidence | Success criteria | Time |
|---|---|---|---|---|
| 1 | Commit + deploy Phase III | Files on VPS | `infra/payments/` present; bot starts | 1h |
| 2 | Enable PG + migration 004 | SQL tables exist | `\d payment_outbox` OK | 30m |
| 3 | Fix webhook URL + HTTPS | Dashboard deliveries | ≥1 event 2xx | 1h |
| 4 | Stripe CLI forward | Logs + DB rows | checkout → subscription row | 1h |
| 5 | Resend duplicate event | Metrics + tier unchanged | `already_processed`; no double tier | 30m |
| 6 | Rotate exposed secrets | New whsec works | Old sig rejected | 30m |

### P1 — Before public beta

| # | Objective | Evidence | Success | Time |
|---|---|---|---|---|
| 7 | Concurrent resend (2 clients) | One winner | Single audit activation | 1h |
| 8 | kill -9 during processing | Recovery or retry | Eventually consistent | 2h |
| 9 | Reconciliation with drift | Drift row logged | Detection accurate | 1h |
| 10 | CI: PG integration job | GHA green | Ledger claim tests | 4h |
| 11 | Unknown price rejection | Audit entry | No entitlement change | 30m |

### P2 — Enterprise-grade

| # | Objective | Evidence | Success | Time |
|---|---|---|---|---|
| 12 | Prometheus + alerts | Scrape `/metrics` | Alert on outbox DLQ | 1d |
| 13 | PG failover drill | WAL recovery | No lost commits | 1d |
| 14 | Webhook storm 100× | Stable latency | No duplicate grants | 2h |
| 15 | Backup restore | RPO/RTO doc | Restored consistency | 1d |

---

## Final Questions (Explicit Answers)

1. **What has been empirically proven?**  
   - Tier/metadata unit tests pass locally (13 tests).  
   - Production deploy pipeline runs for the **bot** (not Phase III payments).  
   - Webhook endpoint is **operationally broken** (0 deliveries) — proven failure mode via prior audit docs, not re-measured live in this audit.

2. **What only exists as implementation?**  
   - Phase III ledger, outbox, audit, reconciliation, metrics endpoints — **local uncommitted**.  
   - Phase II hardening in modified `stripe_server.py` — **uncommitted**.  
   - Production `origin/main` webhook handler — **committed, deployed, unverified E2E**.

3. **What remains theoretical?**  
   - Exactly-once, crash recovery, stale recovery, outbox delivery, reconciliation accuracy, atomic claim under concurrency.

4. **What remains unknown?**  
   - Whether VPS has `DATABASE_URL`, Stripe env vars, PG migrations applied, or any successful payment activation in prod.

5. **Can Tiffany safely accept real Stripe payments today?**  
   **NO.**

6. **Can Tiffany prove exactly-once processing?**  
   **NO.**

7. **Can Tiffany prove financial consistency?**  
   **NO.**

8. **Can Tiffany prove crash recovery?**  
   **NO.**

9. **Can Tiffany prove production readiness?**  
   **NO.**

10. **Single experiment eliminating the most uncertainty?**  
    **Stripe CLI + real PostgreSQL + deployed Phase III:**  
    `stripe listen --forward-to localhost:8080/stripe/webhook` → complete test checkout → SQL verify `stripe_events`, `subscriptions`, `payment_audit_log` → `stripe events resend` → confirm idempotency.  
    **~2 hours**; falsifies or confirms the entire Phase III architecture in one pass.

---

## What Has Been Proven vs Not

| | |
|---|---|
| **Proven** | Helper validation logic (unit tests); deploy automation for bot code; production uses **legacy** stripe handler |
| **Implemented only** | Phase III ledger stack (local); metrics endpoint; fail-closed tiers |
| **Theoretical** | Exactly-once, outbox, reconciliation, stale recovery |
| **Unknown** | VPS DATABASE_URL, live webhook health, any paying customer entitlement path |

---

*Evidence overrides implementation. Unknown overrides speculation.*
