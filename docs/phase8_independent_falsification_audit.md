# Tiffany OS — Phase VIII Independent Falsification Audit

**Date:** 2026-08-01  
**Baseline:** `origin/main` @ `e155595` (inspected directly — prior reports not trusted)  
**Stance:** Independent falsification panel — eliminate unsupported certainty  
**Rule:** If evidence does not exist → **UNKNOWN**

---

## 1. Executive Summary

This audit traced **runtime execution paths** from `launcher.py` through every adapter to terminal storage. It did **not** review architecture diagrams, README claims, or prior phase reports as evidence.

### Ground truth (repository-verified)

1. **Two parallel systems coexist in one repository** and are **not one integrated platform**:
   - **Production bot:** `launcher.py` → `notices.py` → `infra/*` → Discord Gateway, optional PG/Redis, Stripe webhook on `:8080`, `tiffany_voice.py` with direct OpenRouter HTTP.
   - **Tiffany Core OSS layer:** `tiffany_core/*` — ~30 modules, **almost entirely disconnected** from production runtime. **Single production import path found:** `mod_panel.py` → `command_visibility_syncer` (debounced slash-command tree sync when an admin toggles mod-panel features).

2. **Payment ledger Phase III is now committed and deployable** (`3a0cee2`). `origin/main:infra/stripe_server.py` imports `infra.payments.ledger`. **This reverses Phase V’s “not on origin/main” claim** — that report is **stale**.

3. **Zero capabilities reach VERIFIED** under the mandatory evidence hierarchy. No repository artifact demonstrates real Stripe webhook delivery, real PostgreSQL payment integration tests, real Redis cluster behavior, real OpenTelemetry export, crash recovery, or multi-process failure injection.

4. **CI validates almost nothing about payments or tiffany_core.** `.github/workflows/test.yml` and `deploy.yml` run **only** `python -m unittest test_smoke`. Files on `origin/main` but **never executed in CI:** `test_payments_phase3.py`, `test_phase5_adversarial.py`, `test_phase6_real_infrastructure.py`, `test_tiffany_core.py`.

5. **Default production fallback is process-local memory and JSON files** when `DATABASE_URL` / `REDIS_URL` are unset. Code explicitly logs this (`infra/postgres.py`, `infra/redis_client.py`).

### Falsification scorecard

| Claim source | Falsified? | Correct status |
|---|---|---|
| “Phase III not deployed” (Phase V) | ✅ Yes | **Stale** — now on `origin/main` |
| “Production-grade exactly-once” (Phase III doc) | ✅ Yes | **THEORETICAL** — no PG/Stripe runtime proof |
| “VERIFIED financial integrity” (Phase VI tests) | ✅ Yes | **PARTIALLY VERIFIED** — in-memory `tiffany_core`, not production ledger |
| “14k+ RPS production throughput” (Phase VI/VII) | ✅ Yes | **THEORETICAL** — asyncio loop, no network |
| “Enterprise OpenTelemetry” (tiffany_core docstrings) | ✅ Yes | **THEORETICAL** — string formatting only |
| “Real Redis / pgvector / event sourcing in prod” | ✅ Yes | **THEORETICAL** or **UNKNOWN** on VPS |

**Bottom line:** Tiffany Bot is a **working Discord monolith** with **optional** PG/Redis/Stripe wiring. Tiffany Core is a **separate, mostly unintegrated library**. Neither has **production-proven** financial integrity, distributed reliability, or enterprise observability.

---

## 2. Audit Methodology

1. **Git inspection:** `git ls-tree origin/main`, `git log`, `git show origin/main:<file>`.
2. **Import graph:** ripgrep for `from tiffany_core`, `from infra.payments`, runtime entry points.
3. **Runtime trace:** Follow `on_ready` → infra init → webhook handler → ledger → storage.
4. **CI/deploy trace:** `.github/workflows/*`, `scripts/deploy.sh`, `scripts/run.sh`, `tiffany-bot.service`.
5. **Test classification:** Read test files; identify mocks, SQLite, in-memory, `# no network`.
6. **Dead code:** Modules with zero importers outside tests.
7. **No trust:** docs, comments, TODOs, prior reports treated as **unverified claims** until traced to code + execution.

---

## 3. Runtime Execution Maps

### 3.1 Production boot path

```
systemd (tiffany-bot.service)
  └─ scripts/run.sh
       └─ launcher.py [fcntl lockfile /tmp/tiffany_launcher.lock — single instance, Linux only]
            └─ subprocess: notices.py
                 └─ discord.Client.on_ready (first connect only)
                      ├─ redis_client.init_redis()
                      │    ├─ REDIS_URL set → redis.asyncio ping
                      │    └─ else → _memory: dict[str, tuple]  [process-local RAM]
                      ├─ postgres.init_db()
                      │    ├─ DATABASE_URL set → asyncpg pool (min 1, max 10)
                      │    └─ else → pool=None, log "JSON fallback"
                      ├─ postgres.run_migrations()
                      │    └─ if pool: execute ALL schema/*.sql sorted (002, 004, …)
                      ├─ stripe_server.start_stripe_server(bot)
                      │    ├─ requires STRIPE_SECRET_KEY + STRIPE_WEBHOOK_SECRET + postgres.pool()
                      │    ├─ aiohttp :8080 POST /stripe/webhook
                      │    ├─ process_stripe_event() → infra/payments/ledger.py
                      │    ├─ asyncio task: payment worker (outbox + stale recovery)
                      │    └─ asyncio task: reconciliation loop (hourly default)
                      ├─ load_extension: offers_cog, giveaways, embed_builder
                      ├─ if STRIPE_SECRET_KEY: premium_cog
                      └─ tiffany_voice.start_warp_monitor() [if voice loaded]
```

**External infrastructure at runtime (conditional):**

| Dependency | Entry | If missing |
|---|---|---|
| Discord Gateway | `discord.py` WebSocket | Bot cannot function |
| PostgreSQL | `DATABASE_URL` | Stripe server **refused**; giveaways/embeds use JSON |
| Redis | `REDIS_URL` | In-memory `_memory` dict (not HA) |
| Stripe API | `STRIPE_*` env | Webhook server disabled |
| OpenRouter | `OPENROUTER_API_KEY` | AI/STT features fail-closed in voice |
| Lavalink | `LAVALINK_ENABLED=1` | yt-dlp fallback path |
| Cloudflare WARP | `127.0.0.1:40000` SOCKS5 | YouTube/music degraded; scripts exist, VPS state **UNKNOWN** |

### 3.2 Stripe payment request path (when env configured)

```
Stripe POST https://???/stripe/webhook   [reverse proxy: NOT IN REPO — UNKNOWN]
  ↓
infra/stripe_server._stripe_webhook_handler
  ↓ _verify_stripe_signature (SDK or HMAC fallback)
  ↓ _stripe_db_required() → 503 if no pool
  ↓ process_stripe_event (infra/payments/ledger.py)
  ↓ asyncpg conn.transaction():
       claim_event (INSERT ON CONFLICT stripe_events)
       audit.append_audit
       handler (_apply_checkout_completed | _apply_subscription_* | _apply_invoice_payment_failed)
       outbox.enqueue (discord_notify → cache invalidate payload)
       mark_completed
  ↓ HTTP 200 {status: ok|duplicate|in_flight|ignored}
  ↓ [post-commit, separate asyncio loop, 15s interval]
       worker.process_outbox_batch → premium.invalidate_entitlement (Redis/memory)
       worker.recover_stale_processing_events
  ↓ [hourly asyncio loop]
       reconciliation.run_reconciliation → Stripe API list vs subscriptions table
```

**Not in handler map:** `invoice.payment_succeeded` — explicitly short-circuited to `{status: ignored}` in `stripe_server.py` before ledger.

**Parallel unused system:** `tiffany_core/domain/idempotency.py` (`DurableIdempotencyStore` = in-memory dict) — **never imported by `infra/payments/` or production bot.**

### 3.3 AI / voice request path (production)

```
Discord message / voice
  ↓
tiffany_voice.py
  ↓ _get_openrouter_client() → openai.AsyncOpenAI(base_url="https://openrouter.ai/api/v1")
  ↓ direct HTTP to OpenRouter (chat, STT, game picks, summaries)
  ↓ state: chat_memory.json, game_history.json, voice_state.json, playlists.json, voice_stats.json
```

**Bypassed entirely:** `tiffany_core/ai/control_plane.py`, `router.py`, `semantic_cache`, `policy_engine`, `ai_provider.py`.

### 3.4 Only tiffany_core production touchpoint

```
User: t!mod-panel → toggle feature
  ↓
mod_panel.ModPanelFeaturesSelect.on_select
  ↓
command_visibility_syncer.schedule_guild_sync(bot, guild, features)
  ↓
DynamicCommandTreeSyncer._execute_sync → discord.app_commands tree manipulation
```

**Classification:** **PARTIALLY VERIFIED** — real Discord API calls when triggered; not covered by CI; no load/failure tests.

---

## 4. Repository Reality

| Area | Exists in repo | Imported by production | Executed at runtime | Validated |
|---|---|---|---|---|
| `infra/payments/ledger.py` | ✅ `origin/main` | ✅ via `stripe_server` | ⚠️ Only if STRIPE+PG env | ❌ |
| `infra/premium.py` | ✅ | ✅ | ✅ entitlement checks | ⚠️ unit-adjacent only |
| `tiffany_core/*` (28 modules) | ✅ | ❌ except `command_visibility` | ⚠️ ~1 code path | ❌ |
| `test_phase6_real_infrastructure.py` | ✅ | ❌ | ❌ (not in CI) | Self-referential |
| `gateway_protocol.py` | ✅ | ❌ **zero imports** | ❌ dead | ❌ |
| Nginx / TLS config | ❌ | — | — | — |
| Prometheus / Grafana stack | ❌ | — | — | — |
| OpenTelemetry SDK | ❌ | — | — | — |

---

## 5. Infrastructure Reality

| Infrastructure | Configured in repo | Production wiring | Runtime if env unset | Classification |
|---|---|---|---|---|
| **PostgreSQL** | `infra/postgres.py`, `schema/*.sql` | `notices.on_ready` | Pool `None`; Stripe refused | **UNKNOWN** on VPS / **THEORETICAL** for payments |
| **Redis** | `infra/redis_client.py` | premium cache, i18n, moderation flood | `_memory` dict | **UNKNOWN** on VPS |
| **SQLite** | `tiffany_core/adapters/relational_db.py` | **Not imported by bot** | Tests only | **PARTIALLY VERIFIED** (tests) |
| **JSON files** | Multiple `*_FILE` constants | notices, voice, giveaways, embeds | **Default path** | **PARTIALLY VERIFIED** (code paths exist) |
| **In-memory** | `_memory`, `_counters`, tiffany_core dicts | Always (fallback or primary) | Process dies → state lost | **PARTIALLY VERIFIED** |
| **OpenTelemetry** | Docstrings in `distributed_lock_and_telemetry.py` | ❌ no OTel SDK | — | **THEORETICAL** |
| **Prometheus** | `infra/payments/metrics.py` JSON snapshot; tiffany_core OpenMetrics strings | `/metrics` on :8080 if Stripe up | Not scraped | **THEORETICAL** |
| **Grafana** | Export helpers in tests only | ❌ | — | **ABSENT** |
| **Docker** | `docker-compose.yml` — Lavalink + optional bot profile | VPS uses **systemd** per `deploy.sh` | Lavalink optional | **PARTIALLY VERIFIED** (Lavalink container scripts) |
| **systemd** | `tiffany-bot.service`, WARP timer units | ✅ production path | — | **PARTIALLY VERIFIED** (config exists) |
| **Discord Gateway** | `discord.py` | ✅ always | — | **PARTIALLY VERIFIED** (bot runs in prod — external) |
| **Lavalink** | wavelink + `scripts/start-lavalink.sh` | Conditional | yt-dlp fallback | **UNKNOWN** reliability |
| **OpenRouter** | Direct HTTP in `tiffany_voice.py` | ✅ | Fail-closed without key | **PARTIALLY VERIFIED** |
| **Stripe** | `stripe_server.py` + ledger | Conditional on env | Disabled without secrets | **THEORETICAL** E2E |
| **Cloudflare WARP** | `scripts/warp-setup.sh`, healthcheck timer | systemd `Wants=warp-svc` | Music path | **UNKNOWN** on VPS |
| **NGINX / Traefik / TLS** | ❌ not in repo | **UNKNOWN** | — | **UNKNOWN** |
| **Kubernetes** | Mentioned in `docs/ha-architecture.md` only | ❌ | — | **ABSENT** |

---

## 6. Production Drift

| Layer | State |
|---|---|
| **Repository (local = origin/main)** | Phase III ledger committed (`3a0cee2`). Music UI at `e155595`. |
| **`origin/main`** | Includes `infra/payments/`, `schema/004_payment_reliability.sql`, audit docs. |
| **`deploy.sh`** | `git checkout origin/main -- infra/ schema/ …` — **will deploy payments code**. |
| **GitHub Actions** | Deploy runs `test_smoke` only; then SSH deploy. **Payment tests never gate deploy.** |
| **VPS runtime** | **UNKNOWN:** `DATABASE_URL`, `REDIS_URL`, `STRIPE_*`, webhook URL, TLS proxy. Cannot verify from repo alone. |
| **CI vs repo** | 4 test suites tracked; **1 executed in CI**. |
| **Docs vs code** | Phase V report claims Phase III not on `origin/main` — **false after `3a0cee2`**. |

**Code that exists but validation never runs:**

- Entire `infra/payments/ledger.py` transaction path
- `test_payments_phase3.py` (13 tests, no network)
- All `test_phase5/6_*` and `test_tiffany_core.py`

---

## 7. Dead Code Report

### 7.1 Entire folders / modules never imported by production

| Path | Importers (non-test) | Verdict |
|---|---|---|
| `tiffany_core/adapters/gateway_protocol.py` | **None** (grep: 0) | **DEAD** |
| `tiffany_core/ai/control_plane.py` | None | **DEAD** (prod) |
| `tiffany_core/ai/router.py` | None | **DEAD** (prod) |
| `tiffany_core/ai/semantic_cache_and_reflection.py` | None | **DEAD** (prod) |
| `tiffany_core/domain/idempotency.py` | None | **DEAD** (prod) — **duplicate concept** vs `infra/payments/ledger.py` |
| `tiffany_core/domain/event_sourcing_and_plugins.py` | None | **DEAD** (prod) |
| `tiffany_core/knowledge/*` | None | **DEAD** (prod) |
| `tiffany_core/security/policy_engine.py` | None | **DEAD** (prod) |
| `tiffany_core/audio/voice_engine.py` | None | **DEAD** (prod) — prod uses `tiffany_voice.py` |
| `tiffany_core/adapters/redis_cache.py` | None | **DEAD** (prod) — prod uses `infra/redis_client.py` |
| `tiffany_core/adapters/relational_db.py` | None | **DEAD** (prod) — prod uses `infra/postgres.py` |

### 7.2 Duplicate / parallel architectures

| Concern | Production path | Abandoned / parallel path |
|---|---|---|
| Idempotency | `infra/payments/ledger.claim_event` (PG) | `tiffany_core/domain/idempotency.py` (RAM dict) |
| Redis | `infra/redis_client.py` | `tiffany_core/adapters/redis_cache.py` |
| PostgreSQL | `infra/postgres.py` + `schema/` | `tiffany_core/adapters/relational_db.py` (SQLite fallback) |
| Voice | `tiffany_voice.py` + wavelink/yt-dlp | `tiffany_core/audio/*` (simulated sockets) |
| Metrics | `infra/payments/metrics.py` (in-process) | `tiffany_core/observability/metrics.py` (export strings) |

### 7.3 Experimental systems present but not operational

- `test_phase5_adversarial.py` — 900+ lines, **not in CI**
- `test_phase6_real_infrastructure.py` — claims "VERIFIED" in docstring; uses in-memory/SQLite
- `docs/open-ecosystem-strategy.md` — strategy doc, not runtime

---

## 8. Integration Report

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION RUNTIME                        │
│  launcher → notices → tiffany_voice / cogs / infra        │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
        ┌───────▼────────┐            ┌───────▼────────┐
        │  infra/        │            │  Root cogs     │
        │  postgres      │◄──SQL──────│  premium_cog   │
        │  redis_client  │◄──cache────│  offers_cog    │
        │  stripe_server │◄──HTTP─────│  (Stripe env)  │
        │  payments/*    │            │  mod_panel ────┼──► tiffany_core
        └───────┬────────┘            │   (1 import)   │    .command_visibility
                │                     └────────────────┘
        ┌───────▼────────┐
        │ External (opt) │
        │ PG, Redis,     │
        │ Stripe,        │
        │ OpenRouter,    │
        │ Discord, WARP  │
        └────────────────┘

┌─────────────────────────────────────────────────────────────┐
        │  tiffany_core/  — DISCONNECTED ISLAND               │
        │  Used by: tests, mod_panel (1 adapter)              │
        │  NOT used by: payments, voice AI, news, offers      │
└─────────────────────────────────────────────────────────────┘
```

**Integration quality:** **Fragmented.** Two billing/idempotency designs. Two Redis abstractions. Two DB layers. Enterprise AI stack unused by production bot.

---

## 9. Failure Injection Readiness

Can the **repository** validate these scenarios **today**?

| Scenario | Possible? | Why / why not |
|---|---|---|
| kill -9 mid-ledger | ❌ | No harness; no PG integration test; no chaos script |
| network partition | ❌ | No toxiproxy/netem config in repo |
| disk full | ❌ | No test fixture |
| Redis restart | ❌ | No Redis service in CI/compose for bot |
| PG restart | ❌ | No PG in CI/compose |
| Stripe retry / duplicate webhook | ❌ | No Stripe CLI automation in repo |
| Discord outage | ❌ | Would need live gateway; not automated |
| OpenRouter outage | ⚠️ | Circuit breaker in `tiffany_core` only; prod uses ad-hoc retries in `tiffany_voice` |
| TLS failures | ❌ | No TLS config in repo |
| clock skew | ❌ | No test manipulating `STRIPE_WEBHOOK_TOLERANCE_SEC` |
| packet loss | ❌ | No tooling |
| memory pressure / OOM | ❌ | No harness |
| SIGTERM | ⚠️ | systemd sends SIGTERM; `launcher.py` handler exists; **not tested** |
| SIGKILL | ❌ | No automated test |
| WAL recovery | ❌ | Requires real PG ops |
| backup restore | ❌ | No backup scripts for payment tables |

**Failure injection readiness:** **NOT READY** — repository lacks infrastructure fixtures, chaos tests, and CI services required to falsify reliability claims.

---

## 10. Evidence Inflation Review

| Report / artifact | Optimistic statement | Supported? | Missing evidence | Correct maturity |
|---|---|---|---|---|
| Phase III report | "✅ Atomic INSERT claim" under concurrent webhooks | ❌ | No PG concurrent test | **THEORETICAL** |
| Phase III report | "Production-grade in design" | ⚠️ | Design yes; ops no | **THEORETICAL** (ops) |
| Phase IV / V | Phase III not deployed | ❌ **stale after `3a0cee2`** | Was true pre-commit | Now **DEPLOYED (code)** / **UNVERIFIED (runtime)** |
| Phase VI test docstring | "Empirically proves production readiness" | ❌ | In-memory/SQLite | **PARTIALLY VERIFIED** at best |
| Phase VI audit | Downgrades all to PARTIAL/THEORETICAL | ✅ | — | **Accurate** |
| Phase VII | Dual-codebase illusion | ✅ | Import trace | **Accurate** |
| `tiffany_core/relational_db.py` docstring | "enterprise production durability" | ❌ | SQLite fallback default in tests | **THEORETICAL** |
| `idempotency.py` docstring | "Guaranteed zero duplicate side effects" | ❌ | `asyncio.Lock` + dict | **THEORETICAL** for multi-process |
| `test_phase5` | Labels tests `[VERIFIED]` | ❌ | Local asyncio only | **PARTIALLY VERIFIED** |
| Payments `/metrics` | Implies observability stack | ❌ | JSON dict, no scraper | **THEORETICAL** |

---

## 11. Hidden Risks

### 11.1 Single points of failure

| SPOF | Location | Impact |
|---|---|---|
| Single bot process | `launcher.py` + one `notices.py` | All modules share fate |
| Lockfile non-Windows | `/tmp/tiffany_launcher.lock` | No duplicate guard on Windows dev |
| Process-local Redis fallback | `infra/redis_client._memory` | Cache incoherent across restarts; premium stale |
| Process-local payment metrics | `infra/payments/metrics._counters` | Lost on restart; not cluster-safe |
| Payment worker in-process | Same asyncio loop as Discord | Bot crash stops outbox + reconciliation |
| JSON state files | `voice_state.json`, `notices_history.json`, etc. | Corruption, no transactions, race via executor |
| Global OpenRouter singleton | `tiffany_voice._openrouter_client_singleton` | Stale key if env loaded late |
| `premium_ai_guardrails` import-time env | Module-level `OPENROUTER_API_KEY` | Fail-closed if dotenv order wrong |

### 11.2 TOCTOU / concurrency (production payments)

| Issue | Detail |
|---|---|
| `in_flight` → HTTP 200 | Stripe may not retry; relies on stale recovery (**unverified**) |
| Stale timer uses `received_at` | Not time-in-`processing`; may mis-classify |
| Outbox side effect before `mark_delivered` | Same TX — rollback retries; double invalidate is idempotent (**partial**) |
| No horizontal scaling story | Two bot instances → duplicate webhook servers on :8080 (**UNKNOWN** if ever deployed) |

### 11.3 Security

| Risk | Status |
|---|---|
| Secrets via `.env` on VPS | **UNKNOWN** rotation state |
| Git history token exposure | Documented in Phase I docs — **not re-verified in git log this audit** |
| Webhook URL / TLS | **UNKNOWN** — not in repo |
| No secret scanning in CI | **CONFIRMED** absent from workflows |

---

## 12. Unknowns

1. VPS has `DATABASE_URL` set? **UNKNOWN**
2. VPS has `REDIS_URL` set? **UNKNOWN**
3. VPS has `STRIPE_*` configured and webhook server listening? **UNKNOWN**
4. Stripe Dashboard shows successful webhook deliveries? **UNKNOWN**
5. Reverse proxy routes `/stripe/webhook` → `:8080` with valid TLS? **UNKNOWN**
6. Any paying customer received premium entitlement via ledger path? **UNKNOWN**
7. Migration 004 successfully applied on production PG? **UNKNOWN**
8. WARP proxy healthy on VPS? **UNKNOWN**
9. Lavalink running in production? **UNKNOWN**
10. Real Discord bot uptime / error rates? **UNKNOWN** (no metrics in repo)

---

## 13. Missing Experiments

### P0 — Before accepting real payments

| ID | Objective | Expected evidence | Success criteria | Est. time |
|---|---|---|---|---|
| E1 | Confirm VPS env | SSH/journal logs | `DATABASE_URL`, `STRIPE_*` present; pool ready log | 30m |
| E2 | Stripe CLI E2E | `stripe listen` → webhook | Row in `stripe_events` + `subscriptions` | 2h |
| E3 | Duplicate resend | `stripe events resend` | Tier unchanged; `webhook_duplicate` > 0 | 30m |
| E4 | Webhook URL + TLS | Dashboard delivery log | ≥1 HTTP 2xx from Stripe | 1h |
| E5 | Add PG integration test to CI | GHA service container | Concurrent claim test green | 4h |

### P1 — Before public beta

| ID | Objective | Evidence | Success | Time |
|---|---|---|---|---|
| E6 | kill -9 during `processing` | journal + SQL state | Recovery or Stripe retry → consistent | 2h |
| E7 | Redis restart during premium check | Cache miss → PG read | Correct tier | 1h |
| E8 | Reconciliation drift injection | Audit log | Drift detected | 1h |
| E9 | Run `test_payments_phase3` in CI | GHA green | Gates deploy | 1h |

### P2 — Enterprise validation

| ID | Objective | Evidence | Success | Time |
|---|---|---|---|---|
| E10 | Prometheus scrape `/metrics` | Time series | Alerts on DLQ | 1d |
| E11 | Two-process webhook race | Load test | Single entitlement | 4h |
| E12 | PG failover | HA cluster | No lost commits | 1d |
| E13 | Disconnect tiffany_core from prod OR wire it | Architecture decision | Single idempotency path | 1w |

---

## 14. Production Readiness Gates

| Gate | Pass? | Evidence |
|---|---|---|
| Payment code on `origin/main` | ✅ | `git ls-tree` |
| Payment code deployed to VPS | **UNKNOWN** | Auto-deploy exists; env unknown |
| Stripe webhook delivers events | **UNKNOWN** | No repo proof |
| Exactly-once entitlement proven | ❌ | No experiment |
| CI runs payment tests | ❌ | Only `test_smoke` |
| CI runs with PostgreSQL | ❌ | |
| Observability stack live | ❌ | No Prometheus/Grafana |
| TLS termination configured | **UNKNOWN** | Not in repo |
| Secret rotation verified | **UNKNOWN** | |
| Disaster recovery tested | ❌ | |
| Single integrated architecture | ❌ | Dual stack |
| tiffany_core integrated | ❌ | ~1 import |

**Production readiness:** **FAIL** (with **UNKNOWN** on VPS config blocking final determination)

---

## 15. Confidence Matrix

Scores 0–10. **Architecture ≠ production evidence.**

| Dimension | Score | Rationale |
|---|---|---|
| Architecture Quality | 7 | Clean separation in `infra/payments/`; parallel tiffany_core creates confusion |
| Implementation Quality | 6 | Ledger code is coherent; many docstrings overclaim |
| Integration Quality | 3 | tiffany_core disconnected; dual idempotency/Redis/DB |
| Deployment Quality | 5 | GHA + systemd proven for bot; payment gating weak |
| Infrastructure Quality | **UNKNOWN** | VPS env not visible from repo |
| Operational Quality | 2 | No metrics stack, no runbooks in repo for payments |
| Production Evidence | 0 | No verified Stripe/PG/crash artifacts |
| Validation Quality | 1 | CI smoke only; rich tests unused |
| Confidence (overall) | 2 | Low — large unknown surface |
| Unknown Surface | 9 | High — most ops state invisible |

---

## 16. Final Verdict

### What survives falsification?

- Production bot **does** boot through documented path (`launcher` → `notices` → optional infra).
- Phase III ledger **is** wired in committed `stripe_server.py` (not merely documented).
- Default fallbacks to **JSON + in-memory** are **real code paths**, not accidents.
- `tiffany_core` is **mostly dead code** relative to production runtime.
- CI **does not** validate payments, tiffany_core, or failure modes.

### What is destroyed?

- Any claim of **VERIFIED** enterprise infrastructure from Phase VI tests.
- Any claim that **tiffany_core idempotency** protects Stripe billing.
- Any claim of **production-grade exactly-once** without Stripe+PG experiments.
- Phase V statement that Phase III is **not on origin/main** (obsolete).
- Any implied **Prometheus/Grafana/OpenTelemetry** production stack.
- **14k+ RPS** as production throughput (algorithmic micro-benchmark only).

### Can Tiffany safely accept real Stripe payments today?

**UNKNOWN** for VPS configuration; **NO** for proven financial integrity from repository evidence alone.

---

## 17. Questions Answered

1. **Empirically proven?** Discord bot deploy pipeline; mod-panel command visibility path; local unit tests (smoke, payments helpers). **Nothing proven for live Stripe billing.**

2. **Implementation only?** Full Phase III ledger, outbox, reconciliation, audit; most of tiffany_core; OpenMetrics string exporters.

3. **Theoretical?** Exactly-once under crash/concurrency; observability stack; tiffany_core distributed locks; semantic cache durability; gateway_protocol multi-platform abstraction.

4. **Unknown?** All VPS env, webhook delivery, TLS, customer entitlement outcomes, PG/Redis production usage.

5. **Safe for real payments today?** **NO** (proven integrity) / **UNKNOWN** (ops config).

6. **Prove exactly-once?** **NO.**

7. **Prove financial consistency?** **NO.**

8. **Prove crash recovery?** **NO.**

9. **Prove production readiness?** **NO.**

10. **Single highest-value experiment?** **Stripe CLI + real PostgreSQL on staging/VPS with committed ledger:** checkout → SQL proof → duplicate resend. ~2 hours; falsifies or confirms the entire payment architecture in one pass.

---

## 18. Appendices

### Appendix A — CI vs tracked tests

| File | On `origin/main` | In CI |
|---|---|---|
| `test_smoke.py` | ✅ | ✅ |
| `test_payments_phase3.py` | ✅ | ❌ |
| `test_tiffany_core.py` | ✅ | ❌ |
| `test_phase5_adversarial.py` | ✅ | ❌ |
| `test_phase6_real_infrastructure.py` | ✅ | ❌ |

### Appendix B — JSON runtime state files (production bot)

| File | Module | PG alternative |
|---|---|---|
| `notices_history.json` | `notices.py` | ❌ |
| `giveaways.json` | `giveaways_cog` / `infra/repositories/giveaways.py` | ✅ if PG |
| `guild_embeds.json` | `embed_builder_cog.py` | ❌ |
| `chat_memory.json` | `tiffany_voice.py` | ❌ |
| `game_history.json` | `tiffany_voice.py` | ❌ |
| `voice_state.json` | `tiffany_voice.py` | ❌ |
| `playlists.json` | `tiffany_voice.py` | ❌ |
| `voice_stats.json` | `tiffany_voice.py` | ❌ |

### Appendix C — Reality gap template (payments)

| Stage | Status |
|---|---|
| Advertised (Phase III docs) | Production-grade exactly-once ledger |
| Implemented | ✅ `infra/payments/*` on `origin/main` |
| Integrated | ✅ `stripe_server.py` imports ledger |
| Executed | **UNKNOWN** (requires STRIPE+PG env) |
| Validated | ❌ no integration tests in CI |
| Production Proven | ❌ |

### Appendix D — Git commits relevant to payments

```
3a0cee2 feat(core): update voice streaming, payments architecture, and empirical reality audit reports
9b7959d feat(premium): Integrate AI Quota System and Stripe Webhook Architecture
```

---

*Final principle: Accurate uncertainty beats impressive conclusions.*
