# Tiffany Payment Security Hardening Report

**Phase:** 2 — Security Hardening Review  
**Baseline:** Stripe Security Audit (Phase 1)  
**Date:** 2026-08-01  
**Status:** Prepared improvements **not committed** (per phase rules)

---

## 1. Executive Summary

Tiffany's payment stack is **architecturally sound at the webhook verification layer** but **not production-ready** as an end-to-end billing subsystem.

| Dimension | Verdict |
|---|---|
| Stripe secrets in current repo | ✅ No real secrets in tracked files |
| Git history | ❌ Discord/OpenRouter tokens in old `.env` |
| Webhook signature verification | ✅ Implemented (SDK + HMAC fallback) |
| Atomic idempotency | ❌ Was TOCTOU + no-op without PostgreSQL → **prepared fix** |
| Financial integrity | ⚠️ Metadata trust, tier fallback, cancelled_at bug |
| Operational deployment | ❌ Webhook URL misconfigured; HTTP :8080 |
| Open-source boundary | ⚠️ Billing logic public; secrets must stay in env |
| Observability | ❌ No payment metrics; minimal structured logs |
| Production readiness | **NO** |

**Prepared (uncommitted) reversible changes:**

- `infra/stripe_server.py` — atomic claim/release idempotency, event allowlist, payload limits, fail-closed without PG, payment_status gate
- `infra/premium.py` — `cancelled_at IS NULL` in entitlement query
- `scripts/setup_stripe_products.py` — removed argv secret injection
- `.dockerignore` — expanded secret exclusions
- `.env.example` — documented new webhook tuning vars

---

## 2. Security Improvements

### Implemented in working tree (not committed)

| Improvement | File | Effect |
|---|---|---|
| Atomic idempotency | `stripe_server.py` | `INSERT … ON CONFLICT … RETURNING` before handler; DELETE claim on failure |
| Fail-closed without DB | `stripe_server.py` | Refuses webhooks if `DATABASE_URL` unset when Stripe enabled |
| Event allowlist | `stripe_server.py` | Rejects unknown event types with 400 |
| Payload size cap | `stripe_server.py` | 256 KiB default (`STRIPE_WEBHOOK_MAX_BODY_BYTES`) |
| Payment status gate | `stripe_server.py` | Ignores checkout unless `payment_status == paid` |
| PII-safe errors | `stripe_server.py` | Metadata no longer echoed in exceptions |
| Cancelled sub filter | `premium.py` | Entitlements exclude `cancelled_at IS NOT NULL` |
| No argv secrets | `setup_stripe_products.py` | Prevents shell-history leak |

### Still required (manual / infra)

- Rotate `[REDACTED_SECRET]` webhook signing secret (Dashboard screenshot exposure)
- Rotate Discord + OpenRouter tokens (Git history)
- Fix Stripe Dashboard URL → `https://tiffanybot.com/stripe/webhook` → proxy `:8080`
- Enable TLS at reverse proxy
- Add gitleaks to CI

---

## 3. Financial Integrity Review

### Trust boundaries

| Input | Trusted? | Risk |
|---|---|---|
| Stripe webhook signature | ✅ Yes | Primary auth |
| Checkout session metadata | ⚠️ Partial | Only safe if **all** checkouts created via `create_checkout_url()` |
| Payment Links in `premium_cog.py` | ❌ No metadata | Purchases won't map to Discord guilds |
| Event payload tier resolution | ⚠️ | Unknown `price_id` → fallback tier `"premium"` |
| `customer.subscription.updated` | ⚠️ | `past_due` immediately revokes (may be early vs Stripe grace) |

### Double-activation scenarios (before fix)

| Scenario | Could duplicate premium? |
|---|---|
| Stripe retry after handler failure | ⚠️ Yes — old mark-after-handler pattern |
| Concurrent duplicate delivery | ⚠️ Yes — TOCTOU on check-then-process |
| No PostgreSQL | ⚠️ Yes — idempotency disabled entirely |
| `_upsert_subscription` alone | ✅ Idempotent (ON CONFLICT) |
| `_provision_guild_config` merge | ✅ Mostly idempotent |

### After prepared atomic claim fix

| Scenario | Result |
|---|---|
| Concurrent delivery | ✅ One INSERT wins |
| Handler failure | ✅ Claim released → Stripe retries |
| Handler success + crash before response | ✅ Claim retained → no reprocessing |
| Crash mid-handler | ⚠️ Claim retained → event lost until manual intervention (needs processing status column for full safety) |

**Recommendation:** add `status` column (`processing`/`completed`/`failed`) in future migration for crash recovery without manual DELETE.

---

## 4. Idempotency Review

### Previous design (audit baseline)

```
check stripe_events SELECT
    ↓ (race window)
execute handler
    ↓
INSERT stripe_events
```

**Failures:**

1. Two concurrent requests both pass SELECT
2. Without PG: `_is_event_processed` → always False
3. Handler succeeds, mark fails → duplicate on retry
4. Silent exception in `_is_event_processed` → returns False

### Prepared design

```
verify signature
    ↓
INSERT stripe_events ON CONFLICT DO NOTHING RETURNING
    ↓ (only winner proceeds)
execute handler
    ↓ on failure
DELETE stripe_events WHERE event_id = ?
    ↓
return 500 (Stripe retries)
```

**Is idempotency guaranteed?**

- **With PostgreSQL:** ✅ Concurrent duplicate delivery prevented at claim boundary
- **Without PostgreSQL:** ✅ Server refuses to start / returns 503
- **Across process crash mid-handler:** ⚠️ Not fully guaranteed — event marked claimed but handler incomplete
- **Financial double-charge:** N/A — Tiffany does not charge; Stripe does. Risk is **double entitlement grant**, mitigated by upsert idempotency + atomic claim

---

## 5. Webhook Security Review

| Control | Before | After (prepared) |
|---|---|---|
| Signature verification | ✅ SDK + HMAC | ✅ |
| Timestamp tolerance | ✅ 300s fixed | ✅ Configurable |
| Replay protection | ✅ | ✅ |
| Event structure validation | ⚠️ Partial | ✅ Requires id + type |
| Event allowlist | ❌ | ✅ |
| Invalid JSON | ⚠️ Generic error | ✅ Explicit 400 |
| Payload size limit | ❌ | ✅ 256 KiB |
| payment_status check | ❌ | ✅ |
| Logging secrets | ✅ Safe | ✅ |
| Exception metadata leak | ⚠️ meta in ValueError | ✅ Redacted |
| Authorization beyond signature | N/A | N/A (correct for Stripe) |
| HTTPS termination | ❌ External | ❌ Still required at proxy |
| IP allowlist | ❌ | Optional hardening |

### Handler gaps (unchanged — document as risks)

- `invoice.payment_succeeded` allowlisted but **no handler** → returns `ignored` (OK if subscription.updated covers renewals)
- `past_due` triggers immediate cancel — may cause revenue/support issues
- No webhook IP verification (Stripe publishes IP ranges — optional)

---

## 6. Secrets Management Review

| Location | Status |
|---|---|
| `.env` | ✅ Gitignored |
| `.env.example` | ✅ Placeholders only |
| `stripe_server.py` | ✅ Env vars only |
| `setup_stripe_products.py` | ✅ Fixed — no argv |
| Logs | ✅ No secret logging found |
| Docker `COPY . .` | ⚠️ `.dockerignore` excludes `.env` — improved |
| CI/CD | ✅ No Stripe secrets in workflows |
| Git history | ❌ Discord/OpenRouter in old `.env` |
| Dashboard screenshot | ❌ `[REDACTED_SECRET]` exposed operationally |

---

## 7. Deployment Security Review

| Item | Status |
|---|---|
| Reverse proxy to `/stripe/webhook` | ❌ Dashboard shows root URL only |
| HTTPS | ❌ Bot listens HTTP :8080 |
| Firewall | ⚠️ `0.0.0.0` bind — expose only via proxy |
| `deploy.sh` includes `infra/` | ✅ |
| `deploy.sh` includes `config/pricing.json` | ❌ Missing |
| `premium_cog.py` loaded in production | ❌ Not in `_load_bot_extensions` |
| Startup validation | ✅ Prepared — PG required when Stripe enabled |
| Health check | ⚠️ `/health` unauthenticated (low risk) |

---

## 8. Open Source Boundary Review

| Component | Classification | Rationale |
|---|---|---|
| `_verify_stripe_signature` | **PUBLIC & SAFE** | Generic pattern |
| Webhook handler flow | **PUBLIC & SAFE** | No secrets |
| `create_checkout_url` | **PUBLIC & SAFE** | Uses env vars |
| `PACKAGE_DEFAULTS` | **PRIVATE** | Commercial packaging rules |
| `config/pricing.json` | **PRIVATE** | Pricing strategy |
| `infra/premium.py` tier logic | **PRIVATE** | Monetization |
| `premium_ai_guardrails.py` | **PRIVATE** | Commercial content rules |
| `subscription.py` discount logic | **PRIVATE** | Partner promo rules |
| Stripe Price IDs (live) | **SECRET/CONFIDENTIAL** | Env only |
| `schema/002_stripe_premium.sql` | **PUBLIC & SAFE** | Generic schema |
| `scripts/setup_stripe_products.py` | **PRIVATE** | Ops tooling |

**Safe to publish:** signature verification, handler structure, SQL schema, env var documentation.  
**Must remain private:** pricing, package defaults, promo logic, live price maps, production `.env`.

---

## 9. Observability Review

| Signal | Present? |
|---|---|
| Webhook received (type + event_id) | ✅ |
| Signature failures | ✅ |
| Handler exceptions | ✅ |
| Subscription upsert success | ✅ |
| Payment failure warnings | ✅ |
| Metrics (Prometheus) | ❌ |
| Audit trail per guild purchase | ⚠️ DB only |
| Webhook latency | ❌ |
| Duplicate detection counter | ❌ |
| Stripe API call failures | ⚠️ log.warning only |

**Never log:** card data, full customer objects, signing secrets, Authorization headers.

---

## 10. Reliability Review

| Failure mode | Behavior |
|---|---|
| Stripe unavailable (API retrieve) | ⚠️ Falls back to metadata tier `"premium"` |
| PostgreSQL down | ✅ Prepared: 503 on webhook; startup refuses server |
| Redis down | ⚠️ Premium cache miss → PG read; invalidate no-op |
| Duplicate webhook | ✅ Prepared: atomic claim |
| Process crash mid-handler | ⚠️ Claim stuck — needs status column or ops runbook |
| Stripe retry after 500 | ✅ Prepared: claim released on handler error |
| Webhook URL wrong | ❌ 0 deliveries (observed) |
| `premium_cog` Payment Links | ❌ No metadata → no entitlement |

---

## 11. Additional Vulnerabilities Found (beyond Phase 1 audit)

| ID | Severity | Finding |
|---|---|---|
| V1 | **High** | `get_entitlement()` ignored `cancelled_at` — cancelled subs could still grant access |
| V2 | **High** | `premium_cog.py` uses static Payment Links without Discord metadata — billing pipeline disconnected |
| V3 | **High** | Unknown Stripe price → tier `"premium"` over-grants |
| V4 | **Medium** | `past_due` status revokes immediately — may not match Stripe dunning |
| V5 | **Medium** | `subscription.py` references `discord.utils` without importing `discord` — discount path crashes |
| V6 | **Medium** | No automated tests for Stripe webhook/idempotency |
| V7 | **Medium** | `telemetry_ai_usage` table referenced but no migration |
| V8 | **Low** | Health endpoint exposes internal service name |
| V9 | **Low** | Docker default Lavalink password in compose |

---

## 12. Recommended Code Improvements

### Prepared in working tree (review before commit)

- [x] Atomic idempotency claim/release
- [x] Fail-closed without PostgreSQL
- [x] Event allowlist + payload limits
- [x] `payment_status == paid` gate
- [x] `cancelled_at IS NULL` in premium lookup
- [x] Remove argv secret from setup script
- [x] Expand `.dockerignore`

### Still to implement

- [ ] Wire `premium_cog` to `create_checkout_url()` with metadata (not Payment Links)
- [ ] Load `premium_cog` in `notices.py` when Stripe configured
- [ ] Reject unknown `price_id` instead of tier fallback `"premium"`
- [ ] Separate grace period for `past_due` vs `canceled`
- [ ] Add `invoice.payment_succeeded` handler or remove from Dashboard subscription
- [ ] Transaction wrapping: subscription upsert + guild config in single DB transaction
- [ ] `stripe_events.status` column for crash recovery
- [ ] Unit tests: signature verification, claim race, handler failure release
- [ ] Add `config/` to `deploy.sh` checkout list

---

## 13. Recommended Documentation Improvements

- [ ] `docs/stripe-webhook-deployment.md` — nginx/Caddy snippet for `/stripe/webhook` → `:8080`
- [ ] Runbook: rotate webhook secret without downtime
- [ ] Runbook: stuck `stripe_events` claim after crash
- [ ] Explicit matrix: which checkout flows include Discord metadata
- [ ] Production checklist: PG + Stripe + proxy + rotated secrets

---

## 14. Production Readiness Assessment

| Question | Answer |
|---|---|
| Is the Stripe integration production-ready? | **No** |
| Is it financially safe? | **Not yet** — entitlement gaps + disconnected checkout UI |
| Is idempotency actually guaranteed? | **After prepared fix: mostly yes** with PG; crash mid-handler remains edge case |
| Can duplicate webhooks cause side effects? | **Before fix: yes.** **After prepared fix: unlikely** with PG |
| Are payment secrets adequately protected? | **In code: yes.** **Operationally: no** (screenshot + Git history) |
| Safe to publish payment layer as OSS? | **Partial** — handler yes; pricing/package defaults no |
| Implement before next production deploy? | Atomic idempotency, PG requirement, entitlement fix, checkout metadata wiring, webhook URL fix, credential rotation |

---

## 15. Remaining Risks

1. Operational secret exposure (screenshot) — **P0**
2. Git history token exposure — **P0**
3. Webhook endpoint misconfiguration — **P0**
4. Payment Links without metadata — **P1**
5. Crash mid-handler stuck claims — **P1**
6. Tier fallback over-grant — **P1**
7. No payment integration tests — **P1**
8. Public repo contains commercial billing rules — **P2** (strategic, not credential)

---

## 16. P0 / P1 / P2 Priorities

### P0 — Before accepting money

1. Rotate `[REDACTED_SECRET]` webhook signing secret
2. Rotate Discord + OpenRouter tokens (Git history)
3. Fix Stripe webhook URL + HTTPS reverse proxy
4. Enable `DATABASE_URL` on VPS
5. Deploy prepared idempotency + fail-closed changes
6. Fix `get_entitlement` cancelled filter (prepared)

### P1 — Before calling billing "production"

7. Connect `/premium` to `create_checkout_url()` with metadata
8. Reject unknown price IDs (fail closed)
9. Add webhook integration tests
10. Review `past_due` revocation policy
11. Add `config/` to deploy checkout

### P2 — Hardening & OSS boundary

12. Move pricing/package defaults to private repo
13. gitleaks in CI
14. Payment metrics + audit dashboard
15. `stripe_events.status` for crash recovery
16. Git history cleanup

---

## 17. Safe Next Steps

1. **Review** uncommitted changes in `infra/stripe_server.py`, `infra/premium.py`, `.dockerignore`, `setup_stripe_products.py`
2. **Rotate** credentials manually in Stripe/Discord/OpenRouter (authorized operator)
3. **Configure** nginx: `location /stripe/webhook { proxy_pass http://127.0.0.1:8080; }`
4. **Verify** end-to-end with Stripe CLI: `stripe listen --forward-to localhost:8080/stripe/webhook`
5. **Test** duplicate delivery with same `event_id`
6. **Commit** only after review + rotation complete

---

## Final Answers

| Question | Answer |
|---|---|
| Production-ready? | **No** |
| Financially safe? | **Not yet** |
| Idempotency guaranteed? | **Only with PostgreSQL + prepared atomic claim; not 100% under crash** |
| Duplicate webhooks cause side effects? | **Mitigated by prepared fix; was yes before** |
| Secrets protected? | **In repo yes; operationally no until rotation** |
| Safe to publish as OSS? | **Handler/verification yes; billing rules and pricing no** |
| Files remain private? | `config/pricing.json`, `PACKAGE_DEFAULTS`, premium panels, guardrails, live env |
| Before next deploy? | P0 list above |

---

*We measure what matters. We prove before we claim. We build only what the evidence justifies.*
