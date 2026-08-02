# Tiffany OS — Phase XII Real Infrastructure Validation Report

**Date:** 2026-08-02 (continued session)  
**Baseline commit:** `0b88e8c042caaffbde52cf0a995274a4fcb6dc2f` (Phase XI)  
**Branch:** `main` (1 commit ahead of `origin/main`; Phase XII artifacts + fixes uncommitted)  
**Environment:** Windows 10, Python 3.13.11, Docker Desktop **running**  
**Mode:** Real infrastructure validation — **no commit, no push, no deploy**

---

## 1. Executive Summary

Phase XII adds **real infrastructure integration tests** (PostgreSQL 16 + Redis 7 via Docker Compose), **multiprocess outbox workers**, a **CI integration workflow**, and documents what was empirically proven vs. still outstanding.

| Area | Phase XII outcome | Maturity |
|---|---|---|
| Baseline Phase XI unit tests | 36 passed (2 skipped on Windows) | **VERIFIED LOCALLY** |
| Smoke tests | 45 passed | **VERIFIED LOCALLY** |
| Real PostgreSQL 16.14 | 5 integration tests green | **VERIFIED LOCALLY** |
| Real Redis 7.4.10 | 5 integration tests green | **VERIFIED LOCALLY** |
| Multiprocess outbox (3 OS processes) | 3 tests green (claim partition, hang/kill/reclaim, lease guard) | **VERIFIED LOCALLY** |
| Stripe idempotency (PG ledger) | 2 tests green (`claim_event` duplicate + concurrent) | **VERIFIED LOCALLY** |
| Stripe CLI E2E (HTTP webhook) | Stripe CLI **not installed** | **NOT TESTED** |
| Discord / Lavalink | No staging bot session | **UNKNOWN** |
| Soak (1h+) | Not run | **NOT TESTED** |
| CI integration job | Workflow added; not pushed | **THEORETICAL** until Actions run |
| Unix launcher tests | 2 skipped on Windows | **THEORETICAL** until Linux CI |

**Central finding:** PostgreSQL lease semantics, Redis cache/invalidation, and multiprocess outbox coordination are **proven on real infrastructure** on this workstation. Full payment webhook E2E and Discord/Lavalink remain unproven.

---

## 2. Baseline State

### Git

```
Branch: main @ 0b88e8c (Phase XI)
Ahead of origin/main: 1 commit
Working tree: Phase XII files + infra/postgres.py fix (uncommitted)
```

### Phase XI test suite (rechecked 2026-08-02)

```text
pytest test_phase10 + test_phase11 + test_outbox + test_launcher + test_payments_phase3
→ 36 passed, 2 skipped (10.7s)

unittest test_smoke → 45 passed (4.8s)
```

Skipped (expected on Windows):

- `test_sigterm_maps_to_keyboard_interrupt_on_unix`
- `test_start_bot_uses_new_session_on_unix`

### Integration suite (real infra)

```text
docker compose -f docker-compose.integration.yml up -d --wait
→ tiffany-integration-pg (healthy, :5433)
→ tiffany-integration-redis (healthy, :6380)

TIFFANY_INTEGRATION_TESTS=1 pytest tests/integration -v
→ 15 passed, 0 failed (5.5s)
```

---

## 3. Infrastructure Evidence

### Docker containers

| Service | Image | Version (measured) | Port |
|---|---|---|---|
| PostgreSQL | `postgres:16-alpine` | **16.14** | 5433→5432 |
| Redis | `redis:7-alpine` | **7.4.10** | 6380→6379 |

### Fixes applied during validation (real bugs, not assertion weakening)

1. **Session-scoped event loop** (`tests/integration/conftest.py`) — asyncpg pool bound to one loop; multiple `asyncio.run()` caused `Event loop is closed`.
2. **`ssl=disable` URL parsing** (`infra/postgres.py`) — asyncpg rejects `?ssl=disable` in DSN; parsed to `ssl=False` kwarg.
3. **Worker subprocess `sys.path`** (`scripts/integration_outbox_worker.py`) — `ModuleNotFoundError: infra` when spawned from `scripts/`.
4. **Short lease in hang test** — production `OUTBOX_LEASE_SEC=120`; integration hang worker uses 1s lease so stale reclaim is testable without waiting 2 minutes.

---

## 4. PostgreSQL Real Validation (P12.3) — VERIFIED LOCALLY

| Test | Result |
|---|---|
| `test_pool_and_migrations` | PASS — schema/*.sql applied |
| `test_transaction_commit_rollback` | PASS |
| `test_skip_locked_two_sessions` | PASS — `FOR UPDATE SKIP LOCKED` |
| `test_lease_guarded_mark_delivered` | PASS — wrong owner rejected |
| `test_stale_lease_recovery` | PASS — expired lease → pending |

**Evidence:** Real asyncpg pool against Docker PostgreSQL 16.14.

---

## 5. Redis Real Validation (P12.6) — VERIFIED LOCALLY

| Test | Result |
|---|---|
| `test_ping_and_version` | PASS |
| `test_cache_set_get_delete` | PASS |
| `test_entitlement_invalidation_real_redis` | PASS |
| `test_reconnect_after_client_close` | PASS |
| `test_memory_fallback_disabled_when_redis_up` | PASS — `_USE_MEMORY` false when Redis connected |

**Production note:** `infra/redis_client.py` still falls back to in-memory when Redis unavailable — integration tests reject that path when `REDIS_URL` is set.

---

## 6. Outbox Concurrency Results (P12.4) — VERIFIED LOCALLY

| Test | Result |
|---|---|
| `test_three_workers_claim_30_rows_exclusively` | PASS — 3 subprocess workers, 30 unique claims, 0 duplicates |
| `test_crash_hang_then_stale_reclaim` | PASS — hang worker killed, stale lease recovered, second worker delivers |
| `test_original_owner_cannot_mark_after_reclaim` | PASS |

**Semantics (unchanged):**

| Layer | Guarantee |
|---|---|
| PostgreSQL state | Lease-guarded; one owner per processing row |
| External side effects | At-least-once |
| Consumer | Must be idempotent |

---

## 7. Crash Recovery Results (P12.5)

| Scenario | Test | Local result |
|---|---|---|
| A — worker hang + kill before deliver | `test_crash_hang_then_stale_reclaim` | **VERIFIED LOCALLY** (Windows `kill()`) |
| B — side effect before mark | Not isolated | NOT TESTED |
| C — SIGKILL mid-TX | Not run | NOT TESTED |

---

## 8. Stripe CLI E2E Results (P12.7) — NOT TESTED

```text
stripe --version → command not found (Windows dev machine)
```

No empirical evidence for HTTP webhook → ledger → outbox → Redis invalidate chain.

---

## 9. Duplicate Webhook Results (P12.8)

### PostgreSQL ledger (without Stripe CLI) — VERIFIED LOCALLY

| Test | Result |
|---|---|
| `test_duplicate_event_id_returns_duplicate` | PASS |
| `test_concurrent_claim_one_wins` | PASS |

### Full HTTP webhook path

**NOT TESTED** — requires Stripe CLI + running `stripe_server`.

---

## 10. Failure Injection Results (P12.9)

| Scenario | Evidence |
|---|---|
| Invalid signature | Unit-level in stripe_server (not re-run this session) | PARTIALLY VERIFIED (code) |
| Duplicate event (PG) | Integration test | **VERIFIED LOCALLY** |
| PG unavailable during webhook | Not injected | UNKNOWN |
| Redis unavailable during invalidate | Memory fallback in code | THEORETICAL |

---

## 11. Process Lifecycle Results (P12.10)

| Test | Evidence |
|---|---|
| Launcher Unix signals | Skipped on Windows | THEORETICAL until CI Linux |
| Multiprocess outbox workers | 3 subprocess workers | **VERIFIED LOCALLY** |
| SIGTERM bot shutdown | Not drilled | UNKNOWN |

---

## 12. Discord / Lavalink Results (P12.11)

**NO EMPIRICAL EVIDENCE.** Classification: **UNKNOWN**

---

## 13. Soak Test Results (P12.12)

**NOT TESTED** — 1h minimum soak not run.

Phase XI **100 start/stop cycles** (mocked WARP/presence): **VERIFIED LOCALLY** (unit only).

---

## 14. Observability Results (P12.13)

`GET /health`, `GET /metrics` — **NOT TESTED** against running `stripe_server` in Phase XII.

---

## 15. CI Integration Results (P12.14)

Workflow `.github/workflows/integration.yml` added but **not pushed**.

Status: **THEORETICAL** until push + GitHub Actions green on `ubuntu-latest`.

---

## 16. Staging Readiness

| Gate | Status |
|---|---|
| Real PG/Redis integration green locally | **Yes** |
| Multiprocess outbox green locally | **Yes** |
| Stripe CLI E2E | **No** |
| Discord/Lavalink drill | **No** |
| 1h soak | **No** |
| CI integration job green | **No** (not pushed) |

**Tiffany ready for controlled staging?** **Closer** — core persistence/cache/outbox proven locally; still need CI green + Stripe CLI + Discord drill before staging cutover.

**Ready for controlled production?** **No**

---

## 17. VERIFIED Capabilities (local, this session)

| Capability | Evidence |
|---|---|
| Phase XI unit tests | 36 passed, 2 skipped (Unix) |
| Smoke tests | 45 passed |
| PostgreSQL pool + migrations | Docker PG 16.14 |
| SKIP LOCKED + lease guards | Integration tests |
| Redis cache + reconnect | Docker Redis 7.4.10 |
| Multiprocess outbox (3 workers) | Subprocess workers |
| Stale lease reclaim after worker kill | Hang/kill/reclaim test |
| Stripe `claim_event` idempotency | PG integration tests |
| Integration fail-closed without Docker | Verified in prior session |

---

## 18. PARTIALLY VERIFIED Capabilities

| Capability | Gap |
|---|---|
| Payment metrics endpoints | Code only; not HTTP-tested |
| Launcher process groups | Unix tests; not run on Windows |
| Crash mid-transaction (SIGKILL) | Not drilled |

---

## 19. THEORETICAL Capabilities

- CI integration job pass on Ubuntu (workflow not yet run)
- Full Stripe HTTP webhook → entitlement path
- Redis HA / fail-closed production mode

---

## 20. UNKNOWN Capabilities

- Discord reconnect task counts
- Lavalink player cleanup
- VPS SIGTERM → `on_close` latency
- ffmpeg subprocess orphans after kill
- 1h+ soak resource growth

---

## 21. Production Blockers (remaining)

1. **Stripe CLI E2E** not demonstrated
2. **Discord/Lavalink staging drill** not done
3. **Soak test** not done
4. **Phase XI + XII not pushed** — VPS lacks lease migration + integration CI
5. **Redis memory fallback** — HA risk if Redis down in production
6. **CI integration job** not yet green on GitHub Actions

---

## 22. Phase XII Artifacts (uncommitted)

| Path | Purpose |
|---|---|
| `docker-compose.integration.yml` | PG 16 + Redis 7 |
| `tests/integration/*` | Real infra tests |
| `scripts/integration_outbox_worker.py` | Multiprocess worker subprocess |
| `scripts/run-integration-tests.ps1` | Local runner (PowerShell) |
| `.github/workflows/integration.yml` | CI integration job |
| `infra/postgres.py` | `ssl=disable` URL parsing for asyncpg |

### How to run locally

```powershell
docker compose -f docker-compose.integration.yml up -d --wait
.\scripts\run-integration-tests.ps1
```

---

## 23. Final Questions — Explicit Answers

| Question | Answer |
|---|---|
| What was proven with REAL infrastructure? | PG 16.14 pool/migrations/leases; Redis 7.4.10 cache/invalidation/reconnect; 3-process outbox; PG stripe idempotency |
| What was proven only locally (mocks)? | Phase XI unit tests; 100 mocked lifecycle cycles |
| What remains theoretical? | CI integration pass on Ubuntu; Stripe HTTP E2E |
| What remains unknown? | Discord, Lavalink, VPS SIGTERM, 1h soak |
| Why were 2 tests skipped? | Unix-only launcher tests on Windows |
| Can PostgreSQL safely coordinate multiple workers? | **Yes — verified** with 3 subprocess workers, 30 rows, zero duplicate claims |
| Can two workers claim the same outbox row? | **Prevented — verified** via SKIP LOCKED + lease UPDATE |
| Can stale leases be reclaimed? | **Yes — verified** after hang worker kill + `recover_stale_leases` |
| What happens after SIGKILL during processing? | **Partially** — hang+kill tested; mid-TX SIGKILL not drilled |
| Can duplicate Stripe webhooks duplicate entitlements? | PG ledger idempotency **verified**; HTTP path **not tested** |
| Does Redis behave after restart? | Client reconnect **verified**; server restart not drilled |
| Ready for controlled staging? | **After** CI green + Stripe CLI + Discord drill |
| Ready for controlled production? | **No** |
| Evidence still required before public launch? | CI integration green, Stripe CLI E2E, Discord/Lavalink soak, 1h staging soak, VPS SIGTERM drill |

---

*Phase XII validation complete on real Docker infrastructure locally. No commit, push, or deploy performed per instructions.*
