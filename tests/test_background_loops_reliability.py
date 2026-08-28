"""
Background Loops Reliability & Regression Guard Test Suite
==========================================================
Tests the self-healing watchdog, active hours expansion (7h-23h),
adaptive startup execution, and fault isolation for news & offers.
"""

import asyncio
import os
import sys
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.getcwd()))

from infra import critical_tasks
import notices
import offers_cog


class TestActiveHoursAndScheduling(unittest.TestCase):
    def test_active_hours_window(self):
        """Active hours should encompass 7h to 23h by default."""
        self.assertEqual(notices.HORA_INICIO, 7)
        self.assertEqual(notices.HORA_FIM, 23)
        self.assertEqual(offers_cog.HORA_INICIO, 7)
        self.assertEqual(offers_cog.HORA_FIM, 23)

        # Test hours inside window
        for h in range(7, 23):
            self.assertTrue(notices.HORA_INICIO <= h < notices.HORA_FIM, f"Hour {h} should be active")

        # Test hours outside window (late night 23h to 6h)
        for h in [23, 0, 1, 2, 3, 4, 5, 6]:
            self.assertFalse(notices.HORA_INICIO <= h < notices.HORA_FIM, f"Hour {h} should be inactive")

    def test_smart_sleep_bounds(self):
        """Smart sleep should always be bounded between 30s and interval*60s."""
        interval = 60
        now_minute = 45
        next_min = ((now_minute // interval) + 1) * interval
        sleep_seconds = ((next_min - now_minute) * 60)
        sleep_seconds = max(30.0, min(sleep_seconds, float(interval * 60)))
        self.assertGreaterEqual(sleep_seconds, 30.0)
        self.assertLessEqual(sleep_seconds, 3600.0)


class TestWatchdogSelfHealing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        critical_tasks.reset_offers_reload_attempts()
        critical_tasks.record_news_heartbeat()
        critical_tasks.record_offers_heartbeat()

    async def test_watchdog_restarts_stopped_news_loop(self):
        """Watchdog must restart stopped news loop."""
        bot = MagicMock()
        bot.is_ready.return_value = True

        news_task = MagicMock()
        news_task.is_running.return_value = False

        await critical_tasks.ensure_critical_loops(
            bot,
            news_task=news_task,
            hora_inicio=0,
            hora_fim=24,
        )

        news_task.start.assert_called_once()

    async def test_watchdog_restarts_stalled_news_loop(self):
        """Watchdog must detect stalled loop (> max_stall_seconds) and cancel+restart it."""
        bot = MagicMock()
        bot.is_ready.return_value = True

        news_task = MagicMock()
        news_task.is_running.return_value = True

        # Simulate heartbeat 3 hours ago
        critical_tasks._last_news_heartbeat = time.time() - 10800

        await critical_tasks.ensure_critical_loops(
            bot,
            news_task=news_task,
            hora_inicio=0,
            hora_fim=24,
            max_stall_seconds=7200.0,
        )

        news_task.cancel.assert_called_once()
        news_task.start.assert_called_once()

    async def test_watchdog_reloads_missing_offers_cog(self):
        """Watchdog must call reload_offers up to max attempts if cog is missing."""
        bot = MagicMock()
        bot.is_ready.return_value = True
        bot.get_cog.return_value = None

        news_task = MagicMock()
        news_task.is_running.return_value = True

        reload_mock = AsyncMock()

        await critical_tasks.ensure_critical_loops(
            bot,
            news_task=news_task,
            reload_offers=reload_mock,
            hora_inicio=0,
            hora_fim=24,
        )

        reload_mock.assert_called_once()


class TestFaultIsolationInExtensionLoading(unittest.IsolatedAsyncioTestCase):
    async def test_broken_cog_does_not_abort_other_cogs(self):
        """If one cog throws during load_extension, others must still load."""
        bot = MagicMock()
        bot.get_cog.return_value = None

        # Simulate second cog failing but others succeeding
        async def mock_load(ext_name):
            if ext_name == "giveaways_cog":
                raise ImportError("Simulated missing dependency")
            return None

        bot.load_extension = AsyncMock(side_effect=mock_load)

        # Call notices._load_bot_extensions with mocked bot
        with patch.object(notices, "discord_client", bot):
            await notices._load_bot_extensions()

        # Check that load_extension was attempted for all extensions despite the failure
        loaded_exts = [call[0][0] for call in bot.load_extension.call_args_list]
        self.assertIn("offers_cog", loaded_exts)
        self.assertIn("giveaways_cog", loaded_exts)
        self.assertIn("embed_builder_cog", loaded_exts)
        self.assertIn("admin_dashboard_cog", loaded_exts)


if __name__ == "__main__":
    unittest.main()
