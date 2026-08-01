# Tiffany Payments — Phase III Report

**Date:** 2026-08-01  
**Scope:** Financial reliability, exactly-once processing, operational integrity  
**Status:** Implemented in working tree — **not committed** (per phase rules)

---

## Executive Summary

Phase III transforms Tiffany's Stripe integration from a **monolithic webhook handler** into a **durable payment ledger** with:

- Explicit **state machine** on `stripe_events`
- **Append-only audit trail** (`payment_audit_log`)
- **Transactional outbox** (`payment_outbox`) for Discord cache invalidation
- **Automatic reconciliation** job (Stripe ↔ PostgreSQL)
- **Real in-process metrics** (no fabricated KPIs)
- **Fail-closed tier resolution** (no `"premium"` fallback grants)
- **Adversarial unit tests** (`test_payments_phase3.py`)

**Verdict:** Architecture is now **production-grade in design**. **Operational production readiness remains NO** until P0 infra fixes from Phase I–II (webhook URL, credential rotation, PG on VPS, checkout wiring).

---

## Architecture Review

```
Stripe POST /stripe/webhook
        ↓
Signature verification (stripe_server.py)
        ↓
infra.payments.ledger.process_stripe_event()
        ↓
┌──────────────── PostgreSQL TRANSACTION ────────────────┐
│ claim_event (INSERT … ON CONFLICT)                     │
│ audit: event_validated                                 │
│ apply handler (subscription upsert / cancel / audit)   │
│ outbox.enqueue (discord_notify)                        │
│ mark_completed                                         │
│ audit: event_completed                                 │
└────────────────────────────────────────────────────────┘
        ↓ (async, post-commit)
Payment worker → outbox delivery → premium cache invalidate
        ↓ (periodic)
Reconciliation loop → Stripe API vs subscriptions table
```

**Key separation:** Discord API calls are **not** inside DB transactions. Cache invalidation runs via outbox worker after commit.

---

## Exactly-Once Processing Results

| Scenario | Phase II | Phase III |
|---|---|---|
| Concurrent duplicate webhooks | TOCTOU race | ✅ Atomic INSERT claim |
| Retry after handler failure | DELETE claim | ✅ status=failed + retry on redelivery |
| Crash mid-handler | Stuck claim | ✅ Stale recovery → retry_pending (600s) |
| No PostgreSQL | Silent no-op | ✅ Fail-closed (503 / server refused) |
| Unknown price_id | Grant `"premium"` | ✅ Reject — no entitlement change |
| Duplicate premium upsert | Idempotent SQL | ✅ Idempotent SQL + audit trail |

**Can Tiffany grant Premium twice?** Unlikely with PG + atomic claim. Upsert is idempotent; audit logs every activation.

**Can Tiffany charge twice?** Tiffany does not charge — Stripe does. Double charge risk is Stripe-side; we prevent double **entitlement** grants.

---

## State Machine Review

Persisted on `stripe_events.status`:

| State | Meaning |
|---|---|
| `received` | Claimed, processing started |
| `validated` | Passed business pre-checks |
| `processing` | Handler executing |
| `completed` | Terminal success |
| `failed` | Handler error — Stripe may retry |
| `retry_pending` | Stale/crashed recovery |
| `dead_letter` | Reserved for future max-retry policy |

Migration: `schema/004_payment_reliability.sql`

---

## Outbox Review

| Field | Purpose |
|---|---|
| `payment_outbox.delivery_type` | `discord_notify`, extensible |
| `status` | pending → delivered / dead_letter |
| `attempt_count` + `next_retry_at` | Exponential backoff |

Worker: `infra/payments/worker.py` — runs every 15s with `FOR UPDATE SKIP LOCKED`.

**Gap:** No DM/email to purchaser yet — outbox currently invalidates Redis entitlement cache and logs. Extend payload handlers when Discord notify UX is defined.

---

## Reconciliation Results

`infra/payments/reconciliation.py` — hourly loop (configurable):

- Lists active Stripe subscriptions vs local `subscriptions` rows
- Detects `orphan_local_active` and `missing_local`
- Writes drift to `payment_reconciliation_runs` + audit log
- **Does not auto-correct** yet — drift is logged for operator review

**Gap:** Auto-correction policies need explicit business rules before enabling.

---

## Audit Trail Results

Every activation, revocation, validation, completion, payment failure, and reconciliation run writes to `payment_audit_log` with:

- `provider_event_id`, `correlation_id`, `trace_id`
- `guild_id`, `user_id`, `stripe_subscription_id`
- `previous_state`, `new_state`, `action`, `reason`, `result`

**Can every Premium activation be audited?** Yes — when processing succeeds through the ledger.

**Can every payment be traced Stripe → Discord?** Partially — audit + subscriptions row + outbox payload. Full trace requires checkout metadata (not Payment Links).

---

## Security Findings

| Control | Status |
|---|---|
| Signature verification | ✅ |
| Replay protection | ✅ |
| Event allowlist | ✅ |
| Payload size limit | ✅ |
| payment_status == paid | ✅ |
| Metadata validation | ✅ |
| Unknown price rejection | ✅ **New** |
| No tier fallback | ✅ **New** |
| past_due grace | ✅ **New** — not in revoke set |
| Log sanitization | ✅ |

---

## Reliability Findings

| Failure | Recovery |
|---|---|
| Handler exception | mark_failed + Stripe retry |
| Stale processing | Auto retry_pending after 600s |
| Outbox delivery fail | Backoff + dead_letter at 8 attempts |
| PG unavailable | 503 webhook, server won't start |
| Stripe API down (reconcile) | Run marked failed, logged |
| VPS reboot | Stripe retries uncompleted events; outbox pending redelivered |

---

## Observability Findings

Real counters at `GET /metrics` and in `/health`:

- `webhook_received`, `webhook_duplicate`, `webhook_completed`, `webhook_failed`
- `tier_rejected_unknown`, `metadata_rejected`
- `outbox_enqueued`, `outbox_delivered`, `outbox_dead_letter`
- `reconciliation_drift`, `stale_processing_recovered`

**Not yet:** Prometheus exporter, OpenTelemetry traces, webhook latency histograms.

---

## Failure Injection Results

| Test | Method | Result |
|---|---|---|
| Unknown price | `test_payments_phase3.py` | ✅ Rejected |
| Forged metadata | unit tests | ✅ Rejected |
| past_due policy | unit test | ✅ Not revoked |
| Concurrent claim | **Not run** — requires PG integration test | ⚠️ Pending |
| Crash mid-transaction | Design: PG rollback | ✅ Theoretical |
| Stripe outage during checkout retrieve | Logged warning; metadata path required | ⚠️ |

---

## Remaining Risks

1. **P0:** Webhook URL misconfigured on Dashboard — zero deliveries
2. **P0:** Signing secret exposed — rotate `[REDACTED_SECRET]`
3. **P0:** Git history tokens — rotate Discord/OpenRouter
4. **P1:** `premium_cog` still uses Payment Links without metadata
5. **P1:** Reconciliation detects but does not auto-heal
6. **P1:** No integration tests with real PostgreSQL
7. **P2:** Outbox does not send Discord DMs yet
8. **P2:** `deploy.sh` missing `config/`, `infra/payments/`

---

## P0 / P1 / P2 Issues

### P0
- Rotate all compromised credentials
- Fix webhook URL + HTTPS proxy
- Enable `DATABASE_URL` on VPS
- Deploy Phase III + migration 004

### P1
- Wire `/premium` → `create_checkout_url()`
- PG integration tests for concurrent claims
- Reconciliation auto-correction policy
- Add `infra/payments/` to deploy checkout

### P2
- Prometheus metrics export
- Discord purchase confirmation DM via outbox
- Git history cleanup
- `stripe_events` dead_letter automation

---

## Recommended Improvements

1. Commit Phase III after P0 credential rotation
2. Add `test_payments_phase3.py` to CI
3. Stripe CLI end-to-end test checklist
4. Runbook: stuck `processing` events
5. Move `PACKAGE_DEFAULTS` to private repo (OSS boundary)

---

## Final Questions

| Question | Answer |
|---|---|
| Can Tiffany lose payment events? | **Possible** if webhook URL wrong or PG down before claim. After claim, event is durable. |
| Can Tiffany grant Premium twice? | **Very unlikely** with atomic claim + idempotent upsert. |
| Can Tiffany charge twice? | **N/A** — Stripe charges; not controlled here. |
| Recover after crashes? | **Yes** — stale recovery + Stripe retries + outbox redelivery. |
| Recover after PostgreSQL failure? | **Partial** — webhooks return 503; no silent grants. |
| Recover after Discord API failure? | **Yes** — outbox retries cache invalidation. |
| Recover after Stripe outage? | **Reconciliation logs drift**; webhooks queue at Stripe. |
| Reconcile automatically? | **Detects** drift; auto-correct not enabled. |
| Audit every activation? | **Yes** via `payment_audit_log`. |
| Trace Stripe → Discord? | **Partial** — requires metadata checkout flow. |
| Prove financial correctness? | **Not yet** — needs integration tests + live webhook proof. |
| Production ready? | **NO** |

**Highest financial risk:** Webhook never delivers + Payment Links bypass metadata → users pay without entitlement.

**Cheapest experiment reducing uncertainty:** Stripe CLI `stripe listen --forward-to localhost:8080/stripe/webhook` + duplicate `stripe events resend` — proves exactly-once in ~30 minutes.

---

## Files Added/Modified (uncommitted)

| Path | Purpose |
|---|---|
| `schema/004_payment_reliability.sql` | State machine, audit, outbox tables |
| `infra/payments/*` | Ledger, tiers, audit, outbox, worker, reconciliation, metrics |
| `infra/stripe_server.py` | Thin HTTP layer |
| `test_payments_phase3.py` | Adversarial unit tests |
| `.env.example` | New tuning vars |

---

*We measure what matters. We prove before we claim. We build only what the evidence justifies.*
