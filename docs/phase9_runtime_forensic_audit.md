# Tiffany OS — Phase IX Independent Runtime Forensic Audit

**Date:** 2026-08-01  
**Baseline:** `origin/main` @ `e155595` — traced from source, not prior reports  
**Scope:** Async lifecycle, resource ownership, cancellation safety, operational integrity  
**Mode:** Audit only — no production changes executed

---

## 1. Executive Summary

This audit traces the **actual production runtime path** from `systemd` through every long-lived task, connection, subprocess, and shutdown hook. It does not re-audit architecture maturity (Phase VIII).

### Central question

> Can the Tiffany process start, operate, degrade, reconnect, and shut down without leaking tasks, sockets, sessions, subprocesses, DB connections, Redis clients, locks, queues, or inconsistent state?

### Answer (evidence-based)

**UNKNOWN for production VPS.** From repository tracing alone:

| Lifecycle phase | Assessment |
|---|---|
| **Cold start** | **PARTIALLY VERIFIED** — entry path is coherent; infra init is guarded |
| **Steady operation** | **THEORETICAL** — many fire-and-forget tasks; no runtime task inventory |
| **Gateway reconnect** | **THEORETICAL** — **confirmed code-path risk:** duplicate `_empty_channel_watchdog` tasks |
| **Graceful shutdown (`on_close`)** | **PARTIALLY VERIFIED** — Stripe/PG/Redis/http closed; voice background tasks **not explicitly cancelled** |
| **Launcher crash restart** | **THEORETICAL** — SIGKILL path may skip `on_close`; orphan subprocess risk in voice |
| **Deploy restart** | **PARTIALLY VERIFIED** — `deploy.sh` waits for music queue; systemd SIGTERM → SIGKILL |

**No lifecycle behavior reached VERIFIED** — no execution evidence (task counts, connection metrics, SIGTERM drill) was collected in this audit.

### Top forensic findings (code-traced)

1. **`_empty_channel_watchdog` task leak on every `on_ready`** — no dedup guard (`tiffany_voice.py:10067`).
2. **Voice disconnect paths omit `prefetch_task` cancellation** in several handlers (e.g. `_disconnect_idle`, `on_voice_state_update` bot-kick path).
3. **Dozens of unsupervised `asyncio.create_task()` fire-and-forget tasks** (TTS, moderation guard, now-playing posts, message delete).
4. **`on_disconnect` is log-only** — no resource teardown; relies on reconnect + `on_close`.
5. **Payment outbox delivers Redis side effects inside PG transaction** — can hold DB connection during cache I/O.
6. **Launcher watchdog restarts `notices.py` subprocess** without guaranteed async cleanup — partial-alive state possible.
7. **Dual `on_ready` handlers** — `notices.py` (infra once) + `tiffany_voice._rejoin_on_ready` (runs every reconnect, including Lavalink re-connect attempts).

---

## 2. Audit Methodology

1. Traced production entry: `tiffany-bot.service` → `run.sh` → `launcher.py` → `notices.py`.
2. Ripgrep for `create_task`, `@tasks.loop`, `subprocess`, `on_close`, `cancel`, pool init/close.
3. Read shutdown paths for Stripe, payments worker, postgres, redis, aiohttp sessions.
4. Mapped task ownership to module-level globals and session dataclass fields.
5. Classified each finding under VERIFIED / PARTIALLY VERIFIED / THEORETICAL / UNKNOWN.
6. Did **not** execute production SIGTERM, Stripe webhooks, or Discord load tests (per safety rules).

---

## 3. Runtime Execution Maps

### 3.1 Boot chain

```
systemd (tiffany-bot.service)
  KillMode=control-group, SIGTERM → 10s → SIGKILL
  Wants=warp-svc.service (non-blocking)
  ↓
scripts/run.sh → .venv/bin/python -u launcher.py
  ↓ fcntl lock /tmp/tiffany_launcher.lock (Linux only)
  ↓ subprocess.Popen([python, notices.py])  ← single production bot process
  ↓ sync poll loop every 10s; restart on crash (exponential backoff)
```

**Owner:** `launcher.py` owns child `Popen`; **does not** inject into child's asyncio loop.

### 3.2 `notices.py` — first `on_ready` only (`_first_ready_done`)

| Step | Function | Resources allocated | Owner | Supervisor |
|---|---|---|---|---|
| 1 | `redis_client.init_redis()` | `_redis` client OR `_memory` dict | `infra/redis_client` module global | None |
| 2 | `postgres.init_db()` | asyncpg pool (1–10) OR `None` | `infra/postgres._pool` | None |
| 3 | `postgres.run_migrations()` | SQL on pool | same connection | None |
| 4 | `stripe_server.start_stripe_server()` | aiohttp `AppRunner`, `:8080` site | `_runner` global | None |
| 4a | `start_payment_worker()` | `asyncio.Task` `_worker_task` | `infra/payments/worker` | Cancelled in `stop_payment_worker` |
| 4b | `create_task(_reconciliation_loop)` | `_reconcile_task` | `infra/stripe_server` | Cancelled in `stop_stripe_server` |
| 5 | `tiffany_voice.start_warp_monitor()` | `_warp_monitor_task` | `tiffany_voice` global | **Not cancelled on shutdown** |
| 6 | `verificar_feeds.start()` | discord.ext.tasks loop | discord.py task framework | Stops with client close (assumed) |
| 7 | `_critical_tasks_watchdog.start()` | 10-min loop | same | same |
| 8 | `_heartbeat_logger.start()` | 30-min loop | same | same |
| 9 | Cogs loaded | `OffersCog.deals_loop`, `GiveawaysCog._expire_loop` | Cog instances | `cog_unload` cancels |

**External deps opened:** optional Redis, optional PG pool, optional Stripe HTTP server.

### 3.3 `tiffany_voice.register_voice` — `on_ready` listener (runs **every** reconnect)

| Step | Guard? | Resource | Risk |
|---|---|---|---|
| Lavalink `Pool.connect` | No | wavelink node pool | **UNKNOWN** duplicate connect on reconnect |
| `create_task(_empty_channel_watchdog)` | **NO** | infinite 60s loop task | **Task leak on each reconnect** |
| `start_presence_rotation` | Yes (`_presence_rotation_task.done()`) | presence loop | OK |
| Voice auto-rejoin from `voice_state.json` | N/A | new VC sessions + workers | Restarts guild workers |

### 3.4 Gateway reconnect (`on_ready` subsequent)

**`notices.py`:** Restarts only stopped `verificar_feeds`, `_critical_tasks_watchdog`, `_heartbeat_logger`. **Does not** re-init Redis/PG/Stripe (correct — idempotent globals).

**`tiffany_voice._rejoin_on_ready`:** Still runs full body including **new watchdog task** and Lavalink connect attempt.

**`on_disconnect` / `on_resumed`:** Log only — **no resource lifecycle actions**.

### 3.5 Per-guild voice session tasks

`_GuildVoiceSession` fields:

| Task field | Created when | Cancelled when | Gap |
|---|---|---|---|
| `music_task` | yt-dlp connect | disconnect / clear / idle | Lavalink mode: not used |
| `listen_task` | STT enabled | disconnect paths | OK mostly |
| `question_task` | STT enabled | disconnect paths | OK mostly |
| `prefetch_task` | prefetch download | `_cancel_prefetch` on some paths | **Missing on several disconnect paths** |

**Queues:** `music_queue`, `question_queue` — default **unbounded** `asyncio.Queue`.

**Concurrency primitives:** `play_lock` (asyncio.Lock), `buf_lock` (threading.Lock in async STT path).

### 3.6 Stripe webhook request (in-process)

```
POST /stripe/webhook
  → webhook_timer context
  → process_stripe_event [PG transaction]
       → claim → handler → outbox.enqueue → mark_completed
  → HTTP response
```

**Worker (15s loop):** stale SQL update + outbox batch (side effect **inside** PG transaction).

---

## 4. Repository Reality

Production runtime is **one Python process** (`notices.py`) supervised by **a second process** (`launcher.py`). There is no separate payment worker OS process — payment worker is an **asyncio task inside the Discord bot event loop**.

| Component | Separate process? | Same event loop as Discord? |
|---|---|---|
| Discord Gateway | No (library) | Yes |
| Stripe aiohttp server | No | Yes |
| Payment outbox worker | No | Yes |
| Reconciliation loop | No | Yes |
| News/offers task loops | No | Yes |
| Lavalink | **Yes** (Docker, optional) | No — external JVM |
| yt-dlp / ffmpeg | **Yes** (subprocess per download/TTS) | Invoked from executor/sync |

---

## 5. Infrastructure Reality (runtime wiring)

| Resource | Open path | Close path | Close always called? |
|---|---|---|---|
| asyncpg pool | `postgres.init_db` | `postgres.close_db` | **`on_close` only** — not on gateway disconnect |
| Redis client | `init_redis` | `close_redis` | **`on_close` only** |
| Stripe AppRunner | `start_stripe_server` | `stop_stripe_server` → `runner.cleanup()` | **`on_close` only**; guarded `if _runner` |
| Payment worker task | `start_payment_worker` | `stop_payment_worker` → cancel + await | Via `stop_stripe_server` |
| Reconcile task | `create_task` | cancel in `stop_stripe_server` | **`except Exception: pass`** swallows CancelledError mishandling risk — actually catches all |
| News `http_session` | lazy in `_verificar_feeds_inner` | `on_close` + `atexit` | Partial — double-close guarded |
| Offers `http_session` | `_run_deals_cycle` | `OffersCog.on_close` | Separate global from notices |
| WARP monitor task | `start_warp_monitor` | **None found** | **Leak / orphan on shutdown** |
| Presence rotation | `start_presence_rotation` | **None found** | **Leak / orphan on shutdown** |
| Voice watchdog | `_rejoin_on_ready` | **None found** | **Multi-instance on reconnect** |

**Classification:** Close paths exist for **payment infra** — **PARTIALLY VERIFIED** (code review). Voice background globals — **THEORETICAL** leak risk.

---

## 6. Production Drift

| Item | Repo state | Runtime implication |
|---|---|---|
| Phase III ledger | On `origin/main` | Same process as Discord |
| CI | `test_smoke` only | **No lifecycle tests gate deploy** |
| `deploy.sh` | Waits for `voice_state.json` queue | Reduces mid-song SIGKILL; does not drain asyncio tasks |
| systemd | SIGTERM 10s → SIGKILL | May kill before `on_close` completes heavy voice cleanup |
| VPS env | **UNKNOWN** | Stripe/Redis/PG may be absent → degraded paths |

---

## 7. Dead Code Report (runtime-relevant)

| Code | Runtime impact |
|---|---|
| `tiffany_core/*` (except `command_visibility` via mod panel) | **Not in production lifecycle** |
| `gateway_protocol.py` | Zero imports — no runtime |
| Payment paths when `STRIPE_*` unset | `start_stripe_server` returns early — **dead at runtime** |
| STT / listen tasks when Lavalink mode | Not created — **by design bypass** |

---

## 8. Integration Report

```
┌──────────────────────────────────────────────────────────────┐
│  ONE asyncio event loop (notices.py process)                 │
│                                                              │
│  discord.py Gateway                                          │
│    ├─ @tasks.loop: news, watchdog, heartbeat                 │
│    ├─ Cogs: offers.deals_loop, giveaways._expire_loop       │
│    ├─ tiffany_voice: per-guild tasks + global background     │
│    ├─ aiohttp: stripe webhook server (:8080)                 │
│    ├─ asyncio: payment worker + reconciliation               │
│    └─ optional: asyncpg pool, redis client                 │
│                                                              │
│  launcher.py (separate OS process) — restarts notices only   │
└──────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   Lavalink (Docker)    OpenRouter HTTPS
   WARP SOCKS5          Stripe HTTPS
   PostgreSQL           Redis (optional)
```

**Integration risk:** All critical background work shares **one event loop**. A blocking call or hung await in outbox/ledger/voice download **blocks everything**.

---

## 9. Failure Injection Readiness

| Scenario | Can repo validate today? | Why not |
|---|---|---|
| kill -9 mid-webhook | ❌ | No harness |
| SIGTERM graceful | ⚠️ | Code paths exist; not executed |
| Gateway disconnect storm | ❌ | No automated reconnect task count test |
| Duplicate watchdog tasks | ⚠️ | **Detectable by static analysis** — not instrumented |
| Redis hang during outbox | ❌ | No fault injection |
| PG pool exhaustion | ❌ | No load test |
| ffmpeg subprocess orphan | ❌ | No /proc inspection test |
| Launcher restart during voice | ❌ | No integration test |
| Disk full on JSON state | ❌ | No test |

**Readiness:** **NOT READY** for empirical lifecycle validation.

---

## 10. Evidence Inflation Review

| Prior claim | Forensic result |
|---|---|
| Phase VIII: "payment worker background task" | **Accurate** — but same process, not isolated |
| "Graceful shutdown closes infra" | **Partially inflated** — voice globals not cancelled |
| "Reconnect restarts critical loops" | **Accurate** for news/watchdog only |
| "Production-grade task supervision" | **Falsified** — many unsupervised `create_task` |
| "Watchdog ensures reliability" | **Partial** — restarts loops/cogs; **masks** task leaks |

---

## 11. Hidden Risks

### 11.1 Task leaks & duplication

| ID | Location | Mechanism | Severity |
|---|---|---|---|
| T1 | `tiffany_voice.py:10067` | New `_empty_channel_watchdog` every `on_ready` | **HIGH** on reconnect-heavy networks |
| T2 | `_rejoin_on_ready` Lavalink connect | Unchecked re-connect | **MEDIUM** — **UNKNOWN** |
| T3 | Fire-and-forget TTS/moderation/now-playing tasks | No tracking | **MEDIUM** |
| T4 | `_warp_monitor_task`, `_presence_rotation_task` | Never cancelled in `on_close` | **LOW–MEDIUM** |

### 11.2 Cancellation gaps

| ID | Gap |
|---|---|
| C1 | Bot kicked from VC: cancels music/listen/question but **not `prefetch_task`** |
| C2 | `_disconnect_idle`: same omission |
| C3 | Cancelled worker tasks may leave `music_queue` items without cleanup |
| C4 | `stop_stripe_server`: `except Exception: pass` on reconcile await — hides errors |

### 11.3 Event-loop blocking

| ID | Mechanism |
|---|---|
| B1 | `run_in_executor` yt-dlp downloads (semaphore=3) — OK bounded |
| B2 | Outbox `invalidate_entitlement` **inside** PG transaction |
| B3 | `threading.Lock` in STT buffer (`buf_lock`) — cross-thread with async |
| B4 | Sync JSON writes via executor — generally OK |

### 11.4 Shutdown ordering

```
on_close (notices):
  1. stop_stripe_server (cancel reconcile + worker + aiohttp)
  2. close_redis
  3. close_db
  4. close notices http_session

NOT in on_close:
  - cancel warp monitor / presence / voice watchdog
  - cancel per-guild voice tasks
  - close offers http_session (OffersCog.on_close — order vs notices **UNKNOWN**)
  - wavelink Pool.disconnect (**UNKNOWN**)
```

### 11.5 Launcher interaction

On crash, launcher sends SIGINT → wait 10s → SIGTERM → SIGKILL. **`on_close` may not run** on SIGKILL. **Partial state:** PG connections dropped by OS, JSON files may be mid-write (mitigated by `atomic_json_dump` in some paths).

---

## 12. Unknowns

1. Actual task count after 24h gateway reconnects on VPS — **UNKNOWN**
2. Whether `OffersCog.on_close` fires before/after `notices.on_close` — **UNKNOWN**
3. Lavalink pool behavior on duplicate `Pool.connect` — **UNKNOWN**
4. Orphan ffmpeg/yt-dlp processes after bot SIGKILL — **UNKNOWN**
5. Whether systemd always delivers SIGTERM before SIGKILL in deploy — **UNKNOWN** (configured 10s)
6. Real `DATABASE_URL`/`REDIS_URL` on VPS — **UNKNOWN**

---

## 13. Missing Experiments

### P0 — Lifecycle truth (safe, staging/local)

| ID | Experiment | Success evidence | Time |
|---|---|---|---|
| L1 | Instrument `asyncio.all_tasks()` before/after simulated reconnect | Watchdog count == 1 | 2h |
| L2 | SIGTERM to local `notices.py` with STRIPE mock | PG pool closed, port 8080 free | 1h |
| L3 | Connect voice + disconnect; assert no running prefetch/music tasks | Task dump empty | 1h |
| L4 | Count OS child processes before/after voice session | No ffmpeg orphans | 1h |

### P1 — Production observability

| ID | Experiment | Evidence |
|---|---|---|
| L5 | Log task count metric every heartbeat | Grafana-less journal analysis |
| L6 | Add CI test: `_empty_channel_watchdog` idempotent start | Regression guard |

### P2 — Hardening validation

| ID | Experiment |
|---|---|
| L7 | Move outbox side effect post-commit |
| L8 | Cancel voice globals in unified shutdown hook |
| L9 | chaos: Redis slow-path during outbox |

---

## 14. Production Readiness Gates (Lifecycle)

| Gate | Status | Evidence |
|---|---|---|
| Single owner per long-lived task | ❌ | Multiple globals, fire-and-forget |
| Supervised background tasks | ❌ | Payment worker only partially |
| Clean cancel on shutdown | ⚠️ | Stripe/PG/Redis yes; voice globals no |
| Reconnect-safe task creation | ❌ | Watchdog leak |
| Bounded queues | ❌ | Unbounded music/question queues |
| Subprocess termination paths | ⚠️ | ffmpeg timeout+kill in TTS; yt-dlp **UNKNOWN** |
| No event-loop blocking in payments | ⚠️ | Outbox in TX |
| Launcher restart safety | ⚠️ | deploy waits music; SIGKILL gap |
| Lifecycle integration tests in CI | ❌ | |
| Empirical VERIFIED lifecycle | ❌ | |

---

## 15. Confidence Matrix (0–10)

| Dimension | Score | Note |
|---|---|---|
| Boot path clarity | 8 | Well-traced |
| Resource ownership clarity | 5 | Many orphan tasks |
| Cancellation safety | 4 | Gaps in voice + reconnect |
| Shutdown completeness | 5 | Payment infra OK; voice weak |
| Reconnect safety | 3 | Watchdog duplication |
| Subprocess hygiene | 4 | Partial kill paths |
| Operational observability of lifecycle | 2 | No task metrics |
| Production lifecycle evidence | 0 | Not measured |
| **Overall lifecycle confidence** | **3** | |
| Unknown surface | **8** | |

---

## 16. Final Verdict

The Tiffany production application is a **single asyncio monolith** with **explicit shutdown hooks for payment infrastructure** but **incomplete lifecycle management for voice background tasks and gateway reconnect handlers**.

**Can it run without leaks?** **UNKNOWN** — dominant risk is **accumulating `_empty_channel_watchdog` tasks** and **unsupervised fire-and-forget coroutines** under reconnect/load.

**Can it shut down cleanly?** **PARTIALLY VERIFIED** (code paths for Stripe/PG/Redis/http) — **not verified** for voice globals, subprocesses, or SIGKILL paths.

**Can it degrade safely on disconnect?** **THEORETICAL** — news loops restart; voice may duplicate watchdogs; payment server stays up (correct for webhook continuity).

---

## 17. Questions Answered

1. **Which tasks are created?** See §3 tables — payment worker, reconciliation, news/offers/giveaway loops, warp monitor, presence rotation, voice watchdog, per-guild music/listen/question/prefetch, many fire-and-forget helpers.

2. **Who owns them?** Module globals (`_*_task`), session fields, discord.ext.tasks, aiohttp AppRunner.

3. **Who supervises?** Launcher supervises **process** only; `_critical_tasks_watchdog` supervises news/offers loops; **most voice tasks unsupervised**.

4. **Who cancels?** `stop_stripe_server`, voice disconnect handlers (partial), cog_unload, task.cancel on some paths.

5. **Who restarts?** Launcher (process), watchdog (loops/cogs), `_revive_workers` (voice workers), `on_ready` reconnect (loops only).

6. **What leaks?** **THEORETICAL:** watchdog duplication, warp/presence on shutdown, prefetch on some disconnects, fire-and-forget tasks.

7. **What survives reconnect?** PG pool, Redis, Stripe server, payment tasks — **intentionally**; watchdog tasks **accumulate** — **bug risk**.

8. **What dies silently?** Failed infra init logged once; reconcile errors logged; cancelled tasks often not awaited.

9. **What blocks the event loop?** Outbox-in-transaction, excessive sync work, hung external I/O — **THEORETICAL** under failure.

10. **Partially alive state?** **YES plausible:** launcher shows running while gateway disconnected; Stripe up while Discord down; voice tasks after session pop without prefetch cancel.

---

## 18. Appendices

### Appendix A — Long-lived task inventory

| Task name | Created | Cancel/stop | Reconnect behavior |
|---|---|---|---|
| `tiffany-payment-worker` | stripe start | stop_stripe | Persists |
| `tiffany-payment-reconcile` | stripe start | stop_stripe | Persists |
| `verificar_feeds` | on_ready | discord close / restart if stopped | Restart if stopped |
| `_critical_tasks_watchdog` | on_ready | same | Restart if stopped |
| `_heartbeat_logger` | on_ready | same | Restart if stopped |
| `deals_loop` | OffersCog init | cog_unload | Watchdog restart |
| `_expire_loop` | GiveawaysCog | cog_unload | — |
| `tiffany-warp-monitor` | first on_ready | **none** | Once (guarded) |
| `tiffany-presence` | voice on_ready | **none** | Once (guarded) |
| `tiffany-voice-watchdog` | every voice on_ready | **none** | **Duplicates** |
| `tiffany-music-{gid}` | voice connect | cancel on disconnect | Revivable |
| `tiffany-question-{gid}` | STT connect | cancel on disconnect | Revivable |
| `tiffany-voice-{gid}` | STT listen | cancel on disconnect | Revivable |
| `tiffany-prefetch` | play pipeline | `_cancel_prefetch` partial | — |

### Appendix B — Shutdown path comparison

| Trigger | `on_close` runs? | Stripe stopped? | Voice tasks cancelled? |
|---|---|---|---|
| `discord_client.run()` normal exit | Expected yes | Yes | **No explicit global cancel** |
| Launcher SIGINT | Expected yes | Yes | Partial |
| Launcher SIGKILL | **No** | OS closes sockets | **No** |
| Gateway disconnect only | **No** | No | No |

### Appendix C — Code references (forensic anchors)

**Reconnect guard (notices — infra once):**

```2487:2499:notices.py
    if _first_ready_done:
        log.info("🔄 on_ready fired again (gateway reconnect) — restarting stopped loops only.")
        if not verificar_feeds.is_running():
            verificar_feeds.start()
        ...
        return
```

**Watchdog leak (no guard):**

```10067:10070:tiffany_voice.py
        asyncio.create_task(_empty_channel_watchdog(), name="tiffany-voice-watchdog")
        
        await start_presence_rotation(bot)
```

**Graceful infra shutdown:**

```2541:2554:notices.py
async def on_close():
    ...
        await stripe_server.stop_stripe_server()
        await redis_client.close_redis()
        await postgres.close_db()
```

**Payment worker stop:**

```134:142:infra/payments/worker.py
async def stop_payment_worker() -> None:
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
```

### Appendix D — Recommended forensic fixes (audit only — not implemented)

1. Guard `_empty_channel_watchdog` with module-level task + cancel on shutdown (same pattern as warp monitor).
2. Call `_cancel_prefetch(session)` in all disconnect/cleanup paths.
3. Move outbox Redis invalidate **after** PG transaction commit.
4. Unified `async def shutdown_all_background_tasks()` invoked from `on_close`.
5. CI test asserting task count stable across double `on_ready` simulation.

---

*Success metric: unsupported certainty eliminated. Lifecycle truth remains mostly UNKNOWN until L1–L4 experiments run.*
