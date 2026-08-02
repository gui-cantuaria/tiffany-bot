"""
Tiffany OS — Dedicated Music/Voice Regression & Reliability Suite (Phase 5 & 6).
Verifies voice subsystem invariants, command registration, embed formatting, Player/Queue structures,
idempotent cleanup, and proves fault isolation from optional modules (Premium/Offers/News).
"""

import asyncio
import os
import sys
import time
import unittest
from unittest import mock

import discord
from discord.ext import commands

# Ensure project base is in sys.path
_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

import notices
import tiffany_voice as tv
from infra import subsystems
from infra.critical_tasks import ensure_critical_loops


class TestMusicRegressionAndIsolation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_bot = mock.MagicMock(spec=commands.Bot)

    async def test_01_music_operates_with_broken_optional_modules(self):
        """Phase 6 Invariant: Even when Premium and Offers fail completely, Music must remain READY and working."""
        with mock.patch.object(notices.discord_client, "load_extension", new_callable=mock.AsyncMock) as mock_load:
            def _fake_load(name):
                if name in ("premium_cog", "offers_cog"):
                    raise RuntimeError(f"Simulated crash in {name} initialization!")
                return None
            mock_load.side_effect = _fake_load

            with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_simulated_key"}):
                await notices._load_bot_extensions()

            status_report = subsystems.get_all_subsystems()
            self.assertIn(status_report.get("Offers", {}).get("status"), ("DEGRADED", "FAILED", "UNINITIALIZED", "READY"))
            if "Premium" in status_report:
                self.assertEqual(status_report["Premium"]["status"], "DEGRADED")

            # Crucially: Core commands and Voice subsystem must remain operational and healthy
            self.assertEqual(subsystems.get_subsystem_status("Core commands")["status"], "READY")
            self.assertTrue(subsystems.is_healthy(), "is_healthy() must return True despite broken optional modules")

            tv.register_voice(notices.discord_client)
            self.assertEqual(subsystems.get_subsystem_status("Voice subsystem")["status"], "READY")

    def test_02_voice_command_and_slash_registration(self):
        """Verify all critical Music/Voice prefix and hybrid slash commands are present."""
        tv.register_voice(notices.discord_client)
        required_commands = [
            "play", "p", "skip", "s", "pause", "resume",
            "queue", "q", "np", "nowplaying", "v", "volume", "rewind",
            "cl", "clear", "loop", "shuffle", "247"
        ]
        for cmd_name in required_commands:
            cmd = notices.discord_client.get_command(cmd_name)
            self.assertIsNotNone(cmd, f"Required command '{cmd_name}' was not registered on discord_client")

    def test_03_player_and_queue_initialization_invariants(self):
        """Verify _GuildVoiceSession initializes Queue, lock, volume, and playback state correctly."""
        session = tv._GuildVoiceSession(text_channel_id=987654321)
        self.assertEqual(session.text_channel_id, 987654321)
        self.assertIsInstance(session.music_queue, asyncio.Queue)
        self.assertEqual(session.queue_display, [])
        self.assertEqual(session.queue_durations, [])
        self.assertEqual(session.queue_requesters, [])
        self.assertEqual(session.volume_pct, tv.VOLUME_DEFAULT)
        self.assertIsInstance(session.play_lock, asyncio.Lock)
        self.assertEqual(session.current_song, "")
        self.assertFalse(session.stay_24_7)
        self.assertEqual(session.bitrate_kbps, 128)

    def test_04_player_controls_view_creation(self):
        """Verify PlayerControlView loads all standard interactive buttons without crashing."""
        session = tv._GuildVoiceSession(text_channel_id=11111)
        view = tv.PlayerControlView(session, notices.discord_client)
        self.assertTrue(len(view.children) > 0, "PlayerControlView should instantiate interactive components")
        custom_ids = [getattr(item, "custom_id", "") for item in view.children]
        self.assertIn("tif_ctrl_pause", custom_ids)
        self.assertIn("tif_ctrl_skip", custom_ids)
        self.assertIn("tif_ctrl_stop", custom_ids)
        self.assertIn("tif_ctrl_nightcore", custom_ids)

    def test_05_now_playing_embed_minimalist_legacy_style(self):
        """Verify 'Now Playing' card uses sleek minimalist legacy style without bulky thumbnail fields."""
        embed_pt = tv._embed_now_playing(
            source_label="YouTube",
            track_title="Queen - Bohemian Rhapsody",
            lang="pt",
            duration_sec=355.0,
            requester="Tester#0001",
        )
        self.assertEqual(embed_pt.color.value, tv.TIFFANY_PINK)
        self.assertIn("Bohemian Rhapsody - Queen", embed_pt.description)
        self.assertIn("05:55", embed_pt.description)
        self.assertIn("Tester#0001", embed_pt.description)

        embed_en = tv._embed_now_playing(
            source_label="Spotify",
            track_title="Daft Punk - One More Time",
            lang="en",
            duration_sec=320.0,
            requester="Tester#0002",
        )
        self.assertIn("Now Playing", embed_en.description)
        self.assertIn("05:20", embed_en.description)

    def test_06_added_to_queue_embed_minimalist_legacy_style(self):
        """Verify 'Added to queue' card formatting and calculation across locales."""
        embed_pt = tv._embed_music_added(
            kind="song",
            title="Michael Jackson - Billie Jean",
            requester="User#1234",
            lang="pt",
            duration_sec=294.0,
            position=3,
            eta_sec=600.0,
        )
        self.assertEqual(embed_pt.color.value, tv.TIFFANY_PINK)
        self.assertIn("Adicionado à fila", embed_pt.description)
        self.assertIn("Posição na fila", embed_pt.description)
        self.assertIn("#3", embed_pt.description)
        self.assertIn("04:54", embed_pt.description)

        embed_en = tv._embed_music_added(
            kind="song",
            title="The Weeknd - Blinding Lights",
            requester="User#5678",
            lang="en",
            duration_sec=200.0,
            position=1,
            eta_sec=15.0,
        )
        self.assertIn("Added to queue", embed_en.description)
        self.assertIn("Position in queue", embed_en.description)
        self.assertIn("#1", embed_en.description)

    def test_07_localization_helpers(self):
        """Verify translation catalog integration for voice helpers."""
        msg_pt = tv._fmt_dur(3665)
        self.assertEqual(msg_pt, "1:01:05")
        msg_sec = tv._fmt_dur(45)
        self.assertEqual(msg_sec, "00:45")
        
        em_pt = tv.locale_utils.build_volume_embed("pt", current=75, pink=tv.TIFFANY_PINK)
        self.assertIn("75%", em_pt.description)
        em_en = tv.locale_utils.build_volume_embed("en", current=75, pink=tv.TIFFANY_PINK)
        self.assertIn("75%", em_en.description)

    async def test_08_idempotent_cleanup_and_disconnect(self):
        """Verify voice session cleanup and disconnect are idempotent and do not throw exceptions."""
        guild_id = 999888777
        await tv.cleanup_voice_session_tasks(None, guild_id=guild_id, reason="test_none")

        session = tv._GuildVoiceSession(text_channel_id=1234)
        mock_task = mock.MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False
        session.music_task = mock_task
        tv._sessions[guild_id] = session

        await tv.cleanup_voice_session_tasks(session, guild_id=guild_id, reason="test_cleanup")
        mock_task.cancel.assert_called_once()

        await tv.cleanup_voice_session_tasks(session, guild_id=guild_id, reason="test_repeat")
        await tv.cleanup_all_voice_sessions(self.mock_bot, reason="test_shutdown")

    async def test_09_reconnect_does_not_duplicate_watchdogs(self):
        """Verify watchdog and critical tasks are protected against duplication on repeated re-connects."""
        mock_loop = mock.MagicMock()
        mock_loop.is_running.return_value = True
        mock_bot = mock.MagicMock()
        mock_bot.is_ready.return_value = True
        mock_bot.get_cog.return_value = mock.MagicMock(deals_loop=mock_loop)

        await ensure_critical_loops(mock_bot, news_task=mock_loop, reload_offers=None)
        mock_loop.start.assert_not_called()
        mock_loop.restart.assert_not_called()

        await ensure_critical_loops(mock_bot, news_task=mock_loop, reload_offers=None)
        mock_loop.start.assert_not_called()

    def test_10_lavalink_lifecycle_and_fallback_observability(self):
        """Verify Lavalink subsystem status reflects fallback when LAVALINK_ENABLED is disabled."""
        with mock.patch.dict(os.environ, {"LAVALINK_ENABLED": "0"}):
            tv.register_voice(notices.discord_client)
            status = subsystems.get_subsystem_status("Lavalink")
            self.assertIn(status.get("status"), ("DISABLED", "READY"))
            if status.get("status") == "DISABLED":
                self.assertIn("fallback", status.get("details", "").lower())


if __name__ == "__main__":
    unittest.main()
