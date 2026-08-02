# Tiffany OS — Phase X Runtime Lifecycle Hardening Report

**Date:** 2026-08-01  
**Baseline:** uncommitted working tree (Phase X patch)  
**Scope:** P10.1–P10.7 minimal lifecycle hardening — no feature work, no architecture rewrite  
**Mode:** Implementation + local tests only — **no production deploy**

---

## 1. Executive Summary

Phase X implements a **narrow lifecycle hardening patch** addressing the highest-confidence findings from `docs/phase9_runtime_forensic_audit.md`. The patch introduces explicit task ownership for process-wide voice workers, a canonical session cleanup routine, shutdown integration, reconnect idempotency guards, and a small outbox transaction-boundary fix.

| Area | Before | After | Local evidence |
|---|---|---|---|
| Empty-channel watchdog | New `create_task` on every voice `on_ready` | `OwnedBackgroundTask` singleton + idempotent `_ensure_voice_watchdog` | **Demonstrated** (Test 1, 2, 7) |
| Global voice tasks | No unified stop path | `start_voice_background_tasks` / `stop_voice_background_tasks` | **Demonstrated** (Test 1, 5, 7) |
| Session cleanup | Duplicated cancel logic; prefetch often not awaited | `cleanup_voice_session_tasks` + `disconnect_voice_guild` | **Demonstrated** (Test 3) |
| Graceful shutdown | Voice tasks not stopped in `on_close` | `shutdown_voice_runtime` before Stripe/PG/Redis | **Partially demonstrated** (Test 5 — voice only) |
| Outbox side effects in PG TX | `_deliver_discord_notify` inside transaction | Fetch in short TX; deliver + mark outside | **Demonstrated** (outbox unit test) |
| Fire-and-forget visibility | Many bare `create_task` | `spawn_ephemeral` for TTS/moderation/now-playing/delete | **Partially demonstrated** (Test 6) |

**Production readiness impact:** Reduces reconnect task leak and shutdown orphan risk. Full VPS/SIGTERM validation remains **out of scope** for this patch.

---

## 2. Confirmed Phase IX Findings

| ID | Finding | Code path (pre-patch) | Status |
|---|---|---|---|
| F1 | Duplicate `_empty_channel_watchdog` on reconnect | `register_voice` nested watchdog + `_rejoin_on_ready` `create_task` | **Fixed** |
| F2 | Voice background tasks not cancelled on shutdown | `notices.on_close` — Stripe/PG/Redis only | **Fixed** |
| F3 | Prefetch not cancelled on several disconnect paths | `_disconnect_idle`, bot-kick path, queue-empty | **Fixed** via canonical cleanup |
| F4 | Unsupervised fire-and-forget tasks | TTS, moderation, now-playing, delete-later | **Partially fixed** |
| F5 | Outbox delivery inside PG transaction | `process_outbox_batch` loop body inside `conn.transaction()` | **Fixed** (Outcome B) |
| F6 | Dual `on_ready` handlers re-init resources | `notices.on_ready` + `tiffany_voice._rejoin_on_ready` | **Mitigated** (idempotent guards) |

---

## 3. Rejected or Corrected Findings

| Phase IX claim | Verdict | Evidence |
|---|---|---|
| PostgreSQL/Redis duplicated on every reconnect | **Rejected for infra init** | `notices.on_ready` uses `_first_ready_done`; reconnect branch returns early before `init_redis`/`init_db`/`start_stripe_server` |
| Cogs loaded repeatedly on reconnect | **Rejected** | Cogs loaded once at module import / first ready; reconnect only restarts `@tasks.loop` feeds |
| `_empty_channel_watchdog` at line 10067 only | **Corrected** | Watchdog was nested inside `register_voice` **and** started from `_rejoin_on_ready`; both paths patched |
| All prefetch paths omit cancel | **Corrected** | `_cancel_prefetch` existed but sync-only; teardown now **awaits** prefetch in `cleanup_voice_session_tasks` |

---

## 4. Files Changed

| File | Change |
|---|---|
| `infra/voice_lifecycle.py` | **New** — `OwnedBackgroundTask`, `cancel_task_bounded`, `spawn_ephemeral` |
| `tiffany_voice.py` | Watchdog/presence/warp ownership; `cleanup_voice_session_tasks`, `disconnect_voice_guild`, `shutdown_voice_runtime`; unified disconnect paths |
| `notices.py` | First ready → `start_voice_background_tasks`; `on_close` → `shutdown_voice_runtime` before infra |
| `infra/payments/worker.py` | Outbox fetch in short TX; deliver/mark outside |
| `infra/stripe_server.py` | Reconcile task shutdown logs non-cancellation errors |
| `test_phase10_lifecycle.py` | **New** — 9 lifecycle tests |

---

## 5. Watchdog Lifecycle — Before and After

### Before

```python
# Inside register_voice (nested) AND _rejoin_on_ready:
asyncio.create_task(_empty_channel_watchdog(), name="tiffany-voice-watchdog")
```

- No strong reference retained at module level
- Every Discord reconnect via `_rejoin_on_ready` could spawn another watchdog
- No shutdown cancellation

### After

```python
_voice_watchdog = OwnedBackgroundTask("tiffany-voice-watchdog")

def _ensure_voice_watchdog(bot):
    _voice_watchdog.start(lambda: _empty_channel_watchdog_loop(bot))
```

| Property | Implementation |
|---|---|
| Singleton | `OwnedBackgroundTask.start` reuses running task |
| Strong reference | Module global `_voice_watchdog` |
| Owner | `tiffany_voice` module |
| Exception visibility | `_on_done` logs `log.error` |
| Shutdown | `stop_voice_background_tasks` → `await _voice_watchdog.stop()` |
| Restart after failure | Stale ref cleared in `_on_done`; next `start` creates new task |

**Maturity:** PARTIALLY VERIFIED (local asyncio tests)

---

## 6. Global Task Ownership

| Task | Owner | Start | Stop | Supervision |
|---|---|---|---|---|
| `_voice_watchdog` | `tiffany_voice._voice_watchdog` | `_ensure_voice_watchdog` / `start_voice_background_tasks` | `stop_voice_background_tasks` | `OwnedBackgroundTask._on_done` |
| `_warp_monitor_bg` | `tiffany_voice._warp_monitor_bg` | `start_warp_monitor` | `stop_warp_monitor` | same |
| `_presence_rotation_bg` | `tiffany_voice._presence_rotation_bg` | `start_presence_rotation` | `stop_presence_rotation` | same |
| Payment worker loop | `infra/payments/worker` | `start_payment_worker` | `stop_payment_worker` | loop try/except (unchanged) |
| Stripe reconcile | `infra/stripe_server._reconcile_task` | `start_stripe_server` | `stop_stripe_server` | improved cancel logging |

**Who cancels and awaits process-wide voice tasks:** `stop_voice_background_tasks()` called from `shutdown_voice_runtime()` and test teardown.

---

## 7. Session Cleanup Design

### Canonical routines

1. **`cleanup_voice_session_tasks(session, guild_id, reason)`** — idempotent; cancels and **awaits** (bounded):
   - `prefetch_task`
   - `music_task`
   - `listen_task`
   - `question_task`

2. **`disconnect_voice_guild(guild, vc, bot, reason, ...)`** — pops session, calls cleanup, clears voice state, disconnects VC/player.

3. **`cleanup_all_voice_sessions(bot, reason)`** — iterates all guild sessions on shutdown.

### Contract

- Safe when `session is None`
- Safe when called twice (tasks already `None` / `done`)
- Prefetch cancellation awaited with 5s timeout via `cancel_task_bounded`
- Logs: `log.debug("Voice session tasks cleaned guild=%s reason=%s", ...)`

### Not owned by session cleanup

- Ephemeral TTS (`spawn_ephemeral`) — bounded lifetime, logged on failure
- `_cancel_prefetch()` sync helper — still used mid-playback (non-teardown); cancels without await

---

## 8. Disconnect Path Matrix

| Disconnect path | Entry | Cleanup routine | Prefetch cancelled? | Patch |
|---|---|---|---|---|
| Idle watchdog (60s) | `_empty_channel_watchdog_loop` | `disconnect_voice_guild` | Yes (awaited) | Applied |
| Empty channel watchdog | same | `disconnect_voice_guild` | Yes | Applied |
| Queue empty 3 min | `_play_worker` | `disconnect_voice_guild` | Yes | Applied |
| Listen empty channel | `_listen_loop` | `disconnect_voice_guild` | Yes | Applied |
| Voice command leave | listen action `leave` | `disconnect_voice_guild` or `cleanup_voice_session_tasks` | Yes | Applied |
| Bot kicked (voice state) | `on_voice_state_update` | `cleanup_voice_session_tasks` | Yes (awaited) | Applied |
| Empty channel 60s (voice state) | `on_voice_state_update` | `disconnect_voice_guild` | Yes | Applied |
| `t!clear` / cmd clear | `_cmd_clear` | `disconnect_voice_guild` + `_cancel_prefetch` before | Yes | Applied |
| Listen loop ended (VC gone) | `listen_loop` finally | `cleanup_voice_session_tasks` | Yes | Applied |
| Process shutdown | `shutdown_voice_runtime` | `cleanup_all_voice_sessions` | Yes | Applied |
| Guild removal | No explicit handler | Relies on voice state events / watchdog | Indirect | **Residual risk** |
| Lavalink node disconnect | Fallback to yt-dlp | No session teardown | N/A | Unchanged |

---

## 9. Shutdown Sequence

**Actual order in `notices.on_close`:**

```
1. shutdown_voice_runtime(bot)
   ├── cleanup_all_voice_sessions (cancel session tasks, disconnect VCs)
   ├── stop_voice_background_tasks (watchdog, presence, warp)
   └── _disconnect_lavalink_pool
2. stripe_server.stop_stripe_server (payment worker + reconcile + HTTP site)
3. redis_client.close_redis
4. postgres.close_db
5. http_session.close (module global)
```

**Justification:** Stop accepting new voice work and release Discord voice resources before closing payment/DB connections that outbox delivery may still reference during normal operation. HTTP session closed last for any in-flight webhook retries.

| Property | Status |
|---|---|
| Idempotent `on_close` | try/except per subsystem — partial |
| Bounded cancellation | 5s via `TASK_CANCEL_TIMEOUT_SEC` |
| One failure doesn't block rest | Each step wrapped in try/except |
| SIGTERM compatible | Depends on Discord.py calling `on_close` — **not locally drilled** |
| SIGKILL | **No cleanup possible** (documented) |

---

## 10. Reconnect Initialization Matrix

| Action | Process startup | First `on_ready` | Reconnect `on_ready` | Resume |
|---|---|---|---|---|
| `init_redis` / `init_db` | — | Once (`_first_ready_done`) | Skipped | Skipped |
| `start_stripe_server` | — | Once | Skipped | Skipped |
| `start_voice_background_tasks` | — | Once (notices) | Skipped (notices early return) | Skipped |
| `_connect_lavalink_once` | — | Via `_rejoin_on_ready` | Via `_rejoin_on_ready` | Idempotent flag |
| `_ensure_voice_watchdog` | — | start_voice + rejoin | rejoin only (noop if running) | noop |
| `start_presence_rotation` | — | start_voice + rejoin | rejoin (noop if running) | noop |
| Voice auto-rejoin | — | `_rejoin_on_ready` | Same listener fires | Same |
| `@tasks.loop` feeds | — | Started | Restarted if stopped | N/A |

---

## 11. Fire-and-Forget Classification

| Location | Pattern | Class | Action |
|---|---|---|---|
| `_voice_watchdog`, warp, presence | `OwnedBackgroundTask` | **A — Process-owned** | Fixed |
| `session.music_task`, `listen_task`, `question_task` | `create_task` + session field | **B — Session-owned** | Cancelled in cleanup |
| `session.prefetch_task` | `create_task` in `_prefetch_track` | **B — Session-owned** | Awaited in cleanup |
| TTS, moderation, now-playing, delete-later | `spawn_ephemeral(...)` | **C — Short-lived** | Logged on failure |
| Prefetch warm wrapper `t!play` idle | `asyncio.create_task(_prefetch_track(...))` | **C — Short-lived wrapper** | **Not changed** — outer task completes quickly; inner prefetch registered on session |
| Payment reconcile | `create_task(_reconciliation_loop)` | **A — Process-owned** | Stop in `stop_stripe_server` (pre-existing) |
| `notices.on_close` http | `loop.create_task(http_session.close())` | **C** | Pre-existing |

---

## 12. Outbox Transaction Investigation

**Outcome: B — Confirmed and safely fixable**

### Original risk

`process_outbox_batch` ran `_deliver_discord_notify` (which may call `premium.invalidate_entitlement` → Redis) **inside** `async with conn.transaction()`, holding a PG connection during external I/O.

### Patch

```python
async with pool.acquire() as conn:
    async with conn.transaction():
        rows = list(await fetch_pending_batch(conn, limit=limit))
# deliver + mark_delivered per row — each mark in its own acquire, outside fetch TX
```

### Limitations

- **At-least-once delivery** unchanged — crash after deliver but before `mark_delivered` may redeliver
- `mark_delivered` / `mark_failed` no longer share TX with fetch — acceptable for outbox semantics
- No lease/claim model — **Phase XI follow-up** if duplicate side effects become observable

**Maturity:** PARTIALLY VERIFIED (unit test with fake pool)

---

## 13. Tests Added

| Test | File | Validates |
|---|---|---|
| Test 1 — Repeated start single instance | `test_phase10_lifecycle.py` | Watchdog owner idempotency |
| Test 2 — Restart after failure | same | Failure clears ref; safe restart |
| Test 3 — Session cleanup | same | All session tasks cancelled + cleared; idempotent |
| Test 4 — Disconnect paths | Code matrix (§8) | All terminal paths reach canonical cleanup |
| Test 5 — Graceful shutdown | `TestGracefulShutdown` | Background tasks stop after `shutdown_voice_runtime` |
| Test 6 — Ephemeral failure | `TestSpawnEphemeral` | Exception logged |
| Test 7 — Resource growth | `TestResourceGrowthCycles` | 3 start/stop cycles → baseline |
| Outbox TX boundary | `TestOutboxSideEffectOutsideTransaction` | deliver/mark outside fetch TX |

---

## 14. Test Results

```
py -m pytest test_phase10_lifecycle.py -v     → 9 passed
py -m unittest test_smoke -v                  → 45 passed
py -m pytest test_payments_phase3.py -v       → 13 passed
```

**Not run:** Full Discord integration, Lavalink, VPS SIGTERM drill, production webhook load.

---

## 15. Remaining Risks

| Risk | Severity | Notes |
|---|---|---|
| Launcher SIGKILL without `on_close` | HIGH | `launcher.py` restart path — unchanged |
| Guild removal without voice event | MEDIUM | No `on_guild_remove` voice cleanup |
| Music task exceptions unobserved | LOW | Session tasks lack done callbacks |
| `_cancel_prefetch` sync on hot path | LOW | Intentional; teardown uses awaited path |
| Outbox duplicate delivery on crash window | MEDIUM | Pre-existing semantics |
| Lavalink reconnect edge cases | MEDIUM | `_lavalink_pool_connected` flag only |

---

## 16. Remaining Unknowns

- Actual task count on VPS after 24h reconnect cycles
- SIGTERM → `on_close` latency under load
- Orphan ffmpeg subprocess count after forced kill
- Whether outbox redelivery produces duplicate Discord notifications in production

---

## 17. Production Readiness Impact

**Positive:** Eliminates highest-confidence watchdog duplication; adds deterministic voice shutdown hook; reduces prefetch/listen/music task leaks on disconnect.

**Neutral:** No user-facing behavior change intended.

**Requires staging/VPS before claiming VERIFIED:**
- SIGTERM shutdown drill
- Reconnect soak test (task inventory)
- Outbox delivery under real Stripe events

---

## 18. Follow-up Recommendations (Phase XI)

1. **Outbox lease/claim model** — separate fetch claim from delivery; idempotent consumer keys
2. **`OwnedBackgroundTask` for Stripe reconcile** — symmetry with voice
3. **`on_guild_remove` voice cleanup** — explicit session teardown
4. **Session task done callbacks** — log music/listen loop crashes without blocking cleanup
5. **VPS lifecycle instrumentation** — periodic `count_owned_background_tasks()` debug log (dev flag)

---

## 19. Per-Fix Evidence Table

| Fix | Original risk | Code path | Patch | Evidence | Limitations | Maturity |
|---|---|---|---|---|---|---|
| P10.1 Watchdog singleton | Task leak on reconnect | `_rejoin_on_ready`, nested watchdog | `OwnedBackgroundTask` | Tests 1,2,7 | `_rejoin_on_ready` still calls `_ensure_voice_watchdog` (noop) | PARTIALLY VERIFIED |
| P10.2 Global task ownership | No stop path | warp/presence globals | `start/stop_voice_background_tasks` | Tests 1,5,7 | Payment worker unchanged | PARTIALLY VERIFIED |
| P10.3 Prefetch cleanup | Orphan prefetch downloads | disconnect handlers | Awaited cancel in `cleanup_voice_session_tasks` | Test 3 | Sync `_cancel_prefetch` on play path | PARTIALLY VERIFIED |
| P10.4 Session unification | Duplicated cancel | multiple handlers | `disconnect_voice_guild` | Test 3, matrix | cmd_clear still calls `_cancel_prefetch` redundantly | PARTIALLY VERIFIED |
| P10.5 Fire-and-forget | Unobserved exceptions | TTS, moderation, etc. | `spawn_ephemeral` | Test 6 | Not all `create_task` converted | PARTIALLY VERIFIED |
| P10.6 Shutdown | Voice orphans on exit | `notices.on_close` | `shutdown_voice_runtime` first | Test 5 (voice only) | Full infra chain not mocked end-to-end | THEORETICAL (full stack) |
| P10.7 Reconnect idempotency | Duplicate workers | dual on_ready | `_first_ready_done` + owned tasks | Test 1,7 | Lavalink reconnect attempts each ready | PARTIALLY VERIFIED |
| Outbox TX | Long PG TX during Redis | `worker.process_outbox_batch` | Short fetch TX | Unit test | At-least-once unchanged | PARTIALLY VERIFIED |

---

*End of Phase X report. No commit, push, or deploy performed.*
