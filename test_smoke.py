"""Smoke tests — no network, no Discord token required."""

from __future__ import annotations

import unittest

import locale_utils


class TestHelpEmbed(unittest.TestCase):
    def test_build_help_embed_accepts_user_id(self):
        em = locale_utils.build_help_embed(None, 12345, pink=0xFF69B4)
        self.assertTrue(em.title)

    def test_build_help_embed_none_user_id(self):
        em = locale_utils.build_help_embed(None, None, pink=0xFF69B4)
        self.assertIsNotNone(em.description)


class TestResolveLang(unittest.TestCase):
    def test_user_pref_overrides_default(self):
        locale_utils.set_user_lang(999001, "es")
        try:
            lang = locale_utils.resolve_lang(None, 999001)
            self.assertEqual(lang, "es")
        finally:
            locale_utils._user_lang_cache.pop("999001", None)


class TestUpdatesEmbed(unittest.TestCase):
    def test_build_updates_embed_has_title(self):
        import updates as upd

        upd.reload_updates_cache()
        em = upd.build_updates_embed(None, 12345, pink=0xFF69B4)
        self.assertTrue(em.title)


class TestOffersCategoryFilter(unittest.TestCase):
    def test_panel_token_matches_category(self):
        import offers_cog as oc

        self.assertTrue(
            oc._deal_matches_guild_categories("Placa de Vídeo", ["hardware", "monitores"])
        )
        self.assertFalse(
            oc._deal_matches_guild_categories("Placa de Vídeo", ["jogos"])
        )

    def test_offer_posting_reserve_blocks_duplicate(self):
        import offers_cog as oc

        history: dict = {"deals": {}}
        deal = {"url": "https://promobit.com.br/x", "title": "GPU Test"}
        self.assertTrue(oc._try_reserve_deal(history, deal))
        self.assertFalse(oc._try_reserve_deal(history, deal))
        self.assertTrue(oc._is_duplicate(history, deal["url"]))
        oc._release_deal_posting(history, deal)
        self.assertFalse(oc._is_duplicate(history, deal["url"]))


class TestSlashLocalizations(unittest.TestCase):
    def test_slash_desc_has_localizations(self):
        from discord import app_commands

        kw = locale_utils.slash_desc_kwargs("slash.cmd.play")
        self.assertIn("description", kw)
        desc = kw["description"]
        self.assertIsInstance(desc, app_commands.locale_str)
        self.assertEqual(str(desc), locale_utils.tr("en", "slash.cmd.play"))


class TestRoleplayHistory(unittest.TestCase):
    def test_isolated_history_roundtrip(self):
        import roleplay_config as rp

        uid = 999002
        rp.clear_history(uid)
        try:
            self.assertEqual(rp.get_history_messages(uid), [])
            rp.add_history_turn(uid, "oi", "e aí!")
            msgs = rp.get_history_messages(uid)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["content"], "oi")
            rp.clear_history(uid)
            self.assertEqual(rp.get_history_messages(uid), [])
        finally:
            rp.clear_history(uid)


class TestVolumeHelpers(unittest.TestCase):
    def test_volume_mappings(self):
        import tiffany_voice as tv

        self.assertAlmostEqual(tv.volume_to_ffmpeg(100), 0.35)
        self.assertAlmostEqual(tv.volume_to_ffmpeg(50), 0.175)
        self.assertEqual(tv.volume_to_lavalink(100), 1000)
        self.assertEqual(tv.volume_to_lavalink(150), 1500)


class TestVolumeEmbed(unittest.TestCase):
    def test_build_volume_embed(self):
        em = locale_utils.build_volume_embed("pt", current=80, pink=0xFF69B4)
        self.assertIn("80", em.description or "")


class TestNewsHistoryDedup(unittest.TestCase):
    def test_queued_allows_post_but_blocks_collection(self):
        import notices

        h: dict = {}
        link = "https://example.com/news-1"
        dedupe = "abc123"
        notices.historico_set(h, link, dedupe, "queued")
        self.assertTrue(notices.historico_check(h, link, dedupe))
        self.assertFalse(notices.historico_blocks_post(h, link, dedupe))

    def test_posted_blocks_post(self):
        import notices

        h: dict = {}
        link = "https://example.com/news-2"
        notices.historico_set(h, link, None, "posted")
        self.assertTrue(notices.historico_blocks_post(h, link, None))

    def test_queued_title_not_self_dup_before_post(self):
        import notices

        h: dict = {}
        titulo = "Anthropic lança modelo Claude Opus 5 com foco em custo-benefício"
        notices.historico_set(h, "https://example.com/a", "hash1", "queued")
        self.assertFalse(notices.title_is_dup(h, titulo))
        notices._register_posted_dedup(h, {"titulo": titulo, "resumo": "Resumo teste."})
        self.assertTrue(notices.title_is_dup(h, titulo))


if __name__ == "__main__":
    unittest.main()
