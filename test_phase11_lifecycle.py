"""Phase XI — lifecycle hardening tests (extends Phase X)."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from infra.voice_lifecycle import (
    OwnedBackgroundTask,
    cancel_task_bounded,
    ephemeral_task_count,
    spawn_ephemeral,
)


class TestOwnedBackgroundTaskTimeout(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_timeout_prevents_duplicate_start(self):
        owner = OwnedBackgroundTask("stubborn")
        long_task = asyncio.create_task(asyncio.sleep(3600), name="stubborn")

        owner._task = long_task
        owner._stop_timed_out = True

        started = 0

        async def _loop():
            nonlocal started
            started += 1
            await asyncio.sleep(3600)

        second = owner.start(_loop)
        self.assertIs(second, long_task)
        self.assertEqual(started, 0)

        long_task.cancel()
        try:
            await long_task
        except asyncio.CancelledError:
            pass

    async def test_stop_timeout_sets_flag(self):
        owner = OwnedBackgroundTask("timeout-test")

        async def _ignore_cancel():
            while True:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    continue

        owner.start(_ignore_cancel)
        with patch(
            "infra.voice_lifecycle.cancel_task_bounded",
            new=AsyncMock(return_value=False),
        ):
            await owner.stop(timeout=0.01)
        self.assertTrue(owner.stop_timed_out)
        self.assertTrue(owner.is_running())
        task = owner.task
        if task:
            task.cancel()


class TestSpawnEphemeralTracking(unittest.IsolatedAsyncioTestCase):
    async def test_ephemeral_tracked_until_done(self):
        gate = asyncio.Event()

        async def _work():
            await gate.wait()

        before = ephemeral_task_count()
        task = spawn_ephemeral(_work(), name="track-me")
        self.assertGreater(ephemeral_task_count(), before)
        gate.set()
        await task
        await asyncio.sleep(0)
        self.assertEqual(ephemeral_task_count(), before)

    async def test_ephemeral_failure_logged(self):
        with patch("infra.voice_lifecycle.log") as mock_log:

            async def _fail():
                raise ValueError("boom")

            spawn_ephemeral(_fail(), name="ephemeral-fail")
            await asyncio.sleep(0.05)
            mock_log.warning.assert_called()


class TestResourceLeakCycles(unittest.IsolatedAsyncioTestCase):
    async def test_100_start_stop_cycles(self):
        import tiffany_voice as tv

        bot = MagicMock()
        bot.is_closed = MagicMock(return_value=False)
        bot.wait_until_ready = AsyncMock()
        bot.guilds = []

        baseline = tv.count_owned_background_tasks()
        with patch.object(tv, "check_warp_proxy_ok", return_value=True):
            with patch.object(tv, "_set_playing_presence", new=AsyncMock(return_value=True)):
                with patch.object(tv, "refresh_presence_lines", return_value=("a",)):
                    for _ in range(100):
                        await tv.start_voice_background_tasks(bot)
                        await tv.stop_voice_background_tasks()
        self.assertEqual(tv.count_owned_background_tasks(), baseline)

    async def test_100_reconnect_simulation_cycles(self):
        import tiffany_voice as tv

        bot = MagicMock()
        bot.is_closed = MagicMock(return_value=False)
        bot.wait_until_ready = AsyncMock()
        bot.guilds = []

        with patch.object(tv, "check_warp_proxy_ok", return_value=True):
            with patch.object(tv, "_set_playing_presence", new=AsyncMock(return_value=True)):
                with patch.object(tv, "refresh_presence_lines", return_value=("a",)):
                    await tv.start_voice_background_tasks(bot)
                    for _ in range(100):
                        tv._ensure_voice_watchdog(bot)
                        await tv.start_presence_rotation(bot)
                    counts = tv.count_owned_background_tasks()
                    self.assertTrue(counts["watchdog"])
                    self.assertTrue(counts["presence"])
                    await tv.stop_voice_background_tasks()


class TestApplicationShutdownOrchestration(unittest.IsolatedAsyncioTestCase):
    async def test_on_close_sequence_idempotent(self):
        voice_shutdown = AsyncMock()
        stripe_stop = AsyncMock()
        redis_close = AsyncMock()
        pg_close = AsyncMock()
        http_close = AsyncMock()

        async def _fake_on_close():
            try:
                await voice_shutdown(MagicMock(), reason="bot_shutdown")
            except Exception:
                pass
            try:
                await stripe_stop()
            except Exception:
                pass
            try:
                await redis_close()
            except Exception:
                pass
            try:
                await pg_close()
            except Exception:
                pass
            await http_close()

        await _fake_on_close()
        await _fake_on_close()

        self.assertGreaterEqual(voice_shutdown.call_count, 2)
        self.assertGreaterEqual(stripe_stop.call_count, 2)


class TestCancelTaskBounded(unittest.IsolatedAsyncioTestCase):
    async def test_returns_false_on_timeout(self):
        task = asyncio.create_task(asyncio.sleep(3600), name="hang")
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            finished = await cancel_task_bounded(task, label="hang", timeout=0.05)
        self.assertFalse(finished)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    unittest.main()
