"""Phase X — runtime lifecycle hardening tests (local only, no production services)."""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from infra.voice_lifecycle import OwnedBackgroundTask, cancel_task_bounded, spawn_ephemeral


class TestOwnedBackgroundTask(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_start_single_instance(self):
        owner = OwnedBackgroundTask("test-watchdog")
        started = 0

        async def _loop():
            nonlocal started
            started += 1
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        owner.start(_loop)
        owner.start(_loop)
        await asyncio.sleep(0)
        self.assertEqual(started, 1)
        self.assertTrue(owner.is_running())
        await owner.stop()
        self.assertFalse(owner.is_running())

    async def test_restart_after_failure(self):
        owner = OwnedBackgroundTask("test-fail")

        async def _boom():
            raise RuntimeError("watchdog exploded")

        owner.start(_boom)
        await asyncio.sleep(0.05)
        self.assertFalse(owner.is_running())

        async def _ok():
            await asyncio.sleep(3600)

        owner.start(_ok)
        self.assertTrue(owner.is_running())
        await owner.stop()


class TestCancelTaskBounded(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_await_clears_task(self):
        async def _worker():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(_worker(), name="test-worker")
        await cancel_task_bounded(task, label="test-worker", timeout=1.0)
        self.assertTrue(task.done())


class TestSpawnEphemeral(unittest.IsolatedAsyncioTestCase):
    async def test_ephemeral_failure_is_logged(self):
        with patch("infra.voice_lifecycle.log") as mock_log:

            async def _fail():
                raise ValueError("boom")

            spawn_ephemeral(_fail(), name="ephemeral-fail")
            await asyncio.sleep(0.05)
            mock_log.warning.assert_called()


@dataclass
class _FakeSession:
    music_task: Optional[asyncio.Task] = None
    listen_task: Optional[asyncio.Task] = None
    question_task: Optional[asyncio.Task] = None
    prefetch_task: Optional[asyncio.Task] = None
    prefetch_key: str = ""
    prefetch_bundle: Optional[tuple] = None
    text_channel_id: int = 0


class TestVoiceSessionCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_cancels_all_session_tasks(self):
        import tiffany_voice as tv

        session = _FakeSession()

        async def _hang():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        session.music_task = asyncio.create_task(_hang(), name="tiffany-music-1")
        session.listen_task = asyncio.create_task(_hang(), name="tiffany-listen-1")
        session.question_task = asyncio.create_task(_hang(), name="tiffany-question-1")
        session.prefetch_task = asyncio.create_task(_hang(), name="tiffany-prefetch")

        await tv.cleanup_voice_session_tasks(session, guild_id=42, reason="test")
        await tv.cleanup_voice_session_tasks(session, guild_id=42, reason="test_again")

        self.assertIsNone(session.music_task)
        self.assertIsNone(session.listen_task)
        self.assertIsNone(session.question_task)
        self.assertIsNone(session.prefetch_task)

        names = {t.get_name() for t in asyncio.all_tasks() if not t.done()}
        self.assertFalse(any(n.startswith("tiffany-music-1") for n in names))
        self.assertFalse(any(n.startswith("tiffany-prefetch") for n in names))


class TestRepeatedReadyIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_background_tasks_singleton(self):
        import tiffany_voice as tv

        bot = MagicMock()
        bot.is_closed = MagicMock(return_value=False)
        bot.wait_until_ready = AsyncMock()
        bot.guilds = []

        with patch.object(tv, "check_warp_proxy_ok", return_value=True):
            with patch.object(tv, "_set_playing_presence", new=AsyncMock(return_value=True)):
                with patch.object(tv, "refresh_presence_lines", return_value=("a",)):
                    await tv.start_voice_background_tasks(bot)
                    await tv.start_voice_background_tasks(bot)
                    await tv.start_voice_background_tasks(bot)

        counts = tv.count_owned_background_tasks()
        self.assertTrue(counts["watchdog"])
        self.assertTrue(counts["warp_monitor"])
        self.assertTrue(counts["presence"])

        await tv.stop_voice_background_tasks()
        counts_after = tv.count_owned_background_tasks()
        self.assertFalse(counts_after["watchdog"])
        self.assertFalse(counts_after["warp_monitor"])
        self.assertFalse(counts_after["presence"])


class TestOutboxSideEffectOutsideTransaction(unittest.IsolatedAsyncioTestCase):
    async def test_deliver_runs_outside_fetch_transaction(self):
        import infra.payments.worker as worker

        calls: list[str] = []

        class FakeConn:
            def __init__(self):
                self.in_tx = False

            async def fetchval(self, *a, **k):
                return 0

            def transaction(self):
                return _FakeTx(self)

        class _FakeTx:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                self._conn.in_tx = True
                return self._conn

            async def __aexit__(self, *a):
                self._conn.in_tx = False

        fake_pool = MagicMock()
        fake_pool.fetchval = AsyncMock(return_value=0)
        fake_pool.acquire = MagicMock(return_value=_FakeAcquire(FakeConn()))

        row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "delivery_type": "discord_notify",
            "payload": {"kind": "premium_activated", "guild_id": 1, "user_id": 2, "tier": "ultimate"},
            "attempt_count": 0,
            "provider_event_id": "evt_1",
            "correlation_id": None,
            "trace_id": "t",
        }

        async def _fetch_batch(conn, *, limit=20):
            calls.append("fetch")
            assert conn.in_tx is True
            return [row]

        async def _deliver(payload):
            calls.append("deliver")

        async def _mark_delivered(conn, outbox_id):
            calls.append("mark")
            assert conn.in_tx is False

        with patch("infra.postgres.pool", return_value=fake_pool):
            with patch("infra.payments.metrics.set_gauge"):
                with patch.object(worker.outbox_mod, "fetch_pending_batch", side_effect=_fetch_batch):
                    with patch.object(worker, "_deliver_discord_notify", side_effect=_deliver):
                        with patch.object(worker.outbox_mod, "mark_delivered", side_effect=_mark_delivered):
                            with patch.object(worker.outbox_mod, "mark_failed", new=AsyncMock()):
                                n = await worker.process_outbox_batch()
        self.assertEqual(n, 1)
        self.assertEqual(calls, ["fetch", "deliver", "mark"])


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        pass


class TestGracefulShutdown(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_stops_background_tasks(self):
        import tiffany_voice as tv

        bot = MagicMock()
        bot.is_closed = MagicMock(return_value=False)
        bot.wait_until_ready = AsyncMock()
        bot.guilds = []

        with patch.object(tv, "check_warp_proxy_ok", return_value=True):
            with patch.object(tv, "_set_playing_presence", new=AsyncMock(return_value=True)):
                with patch.object(tv, "refresh_presence_lines", return_value=("a",)):
                    await tv.start_voice_background_tasks(bot)

        with patch.object(tv, "cleanup_all_voice_sessions", new=AsyncMock()):
            with patch.object(tv, "_disconnect_lavalink_pool", new=AsyncMock()):
                await tv.shutdown_voice_runtime(bot, reason="test_shutdown")

        counts = tv.count_owned_background_tasks()
        self.assertFalse(counts["watchdog"])
        self.assertFalse(counts["warp_monitor"])
        self.assertFalse(counts["presence"])


class TestResourceGrowthCycles(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_start_stop_returns_to_baseline(self):
        import tiffany_voice as tv

        bot = MagicMock()
        bot.is_closed = MagicMock(return_value=False)
        bot.wait_until_ready = AsyncMock()
        bot.guilds = []

        baseline = tv.count_owned_background_tasks()
        with patch.object(tv, "check_warp_proxy_ok", return_value=True):
            with patch.object(tv, "_set_playing_presence", new=AsyncMock(return_value=True)):
                with patch.object(tv, "refresh_presence_lines", return_value=("a",)):
                    for _ in range(3):
                        await tv.start_voice_background_tasks(bot)
                        await tv.stop_voice_background_tasks()
        self.assertEqual(tv.count_owned_background_tasks(), baseline)


if __name__ == "__main__":
    unittest.main()
