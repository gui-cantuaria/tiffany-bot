# Tiffany OS — Phase XI Lifecycle & Outbox Hardening Report

**Date:** 2026-08-02  
**Scope:** Remediation of Phase X remaining risks + outbox lease/claim + validation + atomic commit  
**Mode:** Local verification only — **committed, NOT pushed, NOT deployed**

---

## 1. Executive Summary

Phase XI closes the highest-risk gaps left after Phase X:

| Area | Phase X state | Phase XI fix | Maturity |
|---|---|---|---|
| Outbox concurrency | Fetch outside TX but no atomic claim | `claim_batch` + lease_owner + lease_until | **VERIFIED LOCALLY** |
| Cancel timeout orphans | `stop()` cleared ref on timeout | Retains ref, `stop_timed_out`, blocks duplicate start | **VERIFIED LOCALLY** |
| `spawn_ephemeral` | Done callback only | Strong-ref set until completion | **VERIFIED LOCALLY** |
| Session task failures | Unobserved music/listen crashes | `register_session_task` + `_set_session_task` | **VERIFIED LOCALLY** |
| Launcher import side effects | Import started bots | `main()` guard | **VERIFIED LOCALLY** |
| Launcher child cleanup | SIGINT to process only | Unix process group (`start_new_session` + `killpg`) | **PARTIALLY VERIFIED** (Unix tests skip on Windows) |
| CI lifecycle tests | Smoke only | Phase 10/11 + outbox + payments + launcher | **VERIFIED LOCALLY** (workflow updated) |

---

## 2. Outbox Delivery Semantics

### Internal state (PostgreSQL)

- **Claim:** `pending → processing` inside a short transaction with `FOR UPDATE SKIP LOCKED`
- **Lease:** `lease_owner` (worker ID) + `lease_until` set atomically at claim
- **Complete:** `mark_delivered` / `mark_failed` require matching `lease_owner` and `status = processing`
- **Stale recovery:** `recover_stale_leases` returns expired `processing` rows to `pending`

This yields **exactly-once internal state transitions per lease** (only the lease owner can complete).

### External side effects (Redis cache invalidation)

- Delivery remains **at-least-once**
- Duplicate external effects are possible if:
  - worker crashes after side effect but before `mark_delivered`
  - stale lease is reclaimed and another worker redelivers
- Consumer (`premium.invalidate_entitlement`) should be treated as **idempotent**

**We do NOT claim exactly-once external delivery.**

---

## 3. Task Ownership Model

| Task class | Owner | Supervision |
|---|---|---|
| Watchdog / WARP / presence | `OwnedBackgroundTask` globals | start/stop + `_on_done` error log |
| Music / listen / question | Session via `_set_session_task` | `register_session_task` done callback |
| TTS / moderation / now-playing | `spawn_ephemeral` | Tracked set + warning log on failure |
| Payment worker | `worker._worker_task` | loop try/except + cancel on stop |

### Cancel timeout behavior

`OwnedBackgroundTask.stop()`:
1. Calls `cancel_task_bounded` (returns `False` on timeout)
2. If finished → clear ref
3. If not finished → set `stop_timed_out`, **keep ref**, log critical
4. `start()` refuses duplicate while prior task alive

---

## 4. Files Changed

| File | Change |
|---|---|
| `schema/005_outbox_lease.sql` | **New** — processing status, lease columns, index |
| `infra/payments/constants.py` | `OUTBOX_PROCESSING`, lease timing constants |
| `infra/payments/outbox.py` | `claim_batch`, lease-guarded mark/recover |
| `infra/payments/worker.py` | Claim-deliver-mark pipeline, stale lease recovery |
| `infra/voice_lifecycle.py` | Timeout semantics, ephemeral tracking, `register_session_task` |
| `tiffany_voice.py` | `_set_session_task` for all music/listen/question workers |
| `launcher.py` | `main()` guard, Unix process groups for shutdown |
| `.github/workflows/test.yml` | Lifecycle + outbox + payments tests in CI |
| `test_outbox_concurrency.py` | **New** — adversarial lease tests |
| `test_phase11_lifecycle.py` | **New** — timeout, 100 cycles, shutdown order |
| `test_launcher_signals.py` | **New** — import safety + Unix session tests |
| `test_phase10_lifecycle.py` | Updated for `claim_batch` API |

---

## 5. Shutdown Behavior

**`notices.on_close` order (unchanged from Phase X):**
1. `shutdown_voice_runtime`
2. `stop_stripe_server`
3. `close_redis`
4. `close_db`
5. `http_session.close`

**Launcher shutdown (Unix):** SIGINT → wait 10s → SIGTERM → wait 10s → SIGKILL to **process group**.

**SIGKILL:** Cannot run cleanup hooks — documented limitation.

---

## 6. tiffany_voice.py Regression Audit (P0.8)

Phase XI changes in `tiffany_voice.py` are limited to:
- `_set_session_task` helper
- Replacing `asyncio.create_task` with supervised assignment for music/listen/question workers

**No changes** to playback logic, queue, autoplay, loop, shuffle, nightcore, TTS/STT content, presence lines, or WARP check logic.

**Maturity:** PARTIALLY VERIFIED — smoke tests pass; no dedicated playback regression suite.

---

## 7. Tests Added / Updated

| Suite | Tests | Result |
|---|---|---|
| `test_phase10_lifecycle.py` | 9 | PASS |
| `test_phase11_lifecycle.py` | 8 | PASS |
| `test_outbox_concurrency.py` | 6 | PASS |
| `test_launcher_signals.py` | 2 (2 skip Windows) | PASS/SKIP |
| `test_payments_phase3.py` | 13 | PASS |
| `test_smoke` | 45 | PASS |

**Total focused lifecycle suite:** 36 passed, 2 skipped  
**Smoke:** 45 passed

---

## 8. Remaining Risks

| Risk | Maturity |
|---|---|
| SIGKILL / systemd hard kill | THEORETICAL — no local SIGKILL drill |
| Real PostgreSQL concurrent workers | THEORETICAL — in-memory fake only |
| Real Redis duplicate invalidation | THEORETICAL |
| Discord reconnect soak | THEORETICAL |
| Lavalink failure modes | THEORETICAL |
| VPS process group + ffmpeg orphan count | UNKNOWN — requires staging |
| Playback regression under load | PARTIALLY VERIFIED (smoke only) |

---

## 9. Production Readiness

**Not claimed.** This phase proves local correctness of lifecycle and outbox lease semantics. Staging/VPS evidence still required for production readiness sign-off.

---

*Committed locally. NOT pushed. NOT deployed.*
