"""Smoke tests — no network, no Discord token required."""

from __future__ import annotations

import unittest

import locale_utils
from brand_colors import TIFFANY_PINK


class TestHelpEmbed(unittest.TestCase):
    def test_build_help_embed_accepts_user_id(self):
        em = locale_utils.build_help_embed(None, 12345, pink=TIFFANY_PINK)
        self.assertTrue(em.title)

    def test_build_help_embed_none_user_id(self):
        em = locale_utils.build_help_embed(None, None, pink=TIFFANY_PINK)
        self.assertIsNotNone(em.description)

    def test_help_embed_turkish_json_catalog(self):
        locale_utils.set_user_lang(999002, "tr")
        try:
            em = locale_utils.build_help_embed(None, 999002, pink=TIFFANY_PINK)
            self.assertEqual(em.title, locale_utils.tr("tr", "help.title"))
            self.assertIn("10.000", em.fields[0].value)
        finally:
            locale_utils._user_lang_cache.pop("999002", None)

    def test_help_embed_portuguese_core_strings(self):
        locale_utils.set_user_lang(999003, "pt")
        try:
            em = locale_utils.build_help_embed(None, 999003, pink=TIFFANY_PINK)
            self.assertIn("10.000", em.fields[0].value)
            self.assertIn("/giveaway", em.fields[3].value)
        finally:
            locale_utils._user_lang_cache.pop("999003", None)


class TestResolveLang(unittest.TestCase):
    def test_user_pref_overrides_default(self):
        locale_utils.set_user_lang(999001, "es")
        try:
            lang = locale_utils.resolve_lang(None, 999001)
            self.assertEqual(lang, "es")
        finally:
            locale_utils._user_lang_cache.pop("999001", None)

    def test_guild_locale_not_used_without_user_pref(self):
        """Interactive output ignores server locale — defaults to en."""
        lang = locale_utils.resolve_lang(None, None)
        self.assertEqual(lang, "en")

    def test_discord_locale_fallback(self):
        lang = locale_utils.resolve_lang(None, None, discord_locale="fr")
        self.assertEqual(lang, "fr")


class TestUpdatesEmbed(unittest.TestCase):
    def test_build_updates_embed_has_title(self):
        import updates as upd

        upd.reload_updates_cache()
        em = upd.build_updates_embed(None, 12345, pink=TIFFANY_PINK)
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

    def test_hybrid_desc_includes_en_help(self):
        kw = locale_utils.hybrid_desc_kwargs("slash.cmd.play")
        self.assertEqual(kw["help"], locale_utils.tr("en", "slash.cmd.play"))
        self.assertIn("description", kw)

    def test_localized_cmd_help_uses_user_lang(self):
        locale_utils.set_user_lang(999003, "de")
        try:
            class _Cmd:
                name = "play"
            text = locale_utils.localized_cmd_help("de", _Cmd())
            self.assertEqual(text, locale_utils.tr("de", "slash.cmd.play"))
        finally:
            locale_utils._user_lang_cache.pop("999003", None)


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


class TestRoleplayIntensity(unittest.TestCase):
    def test_normalize_intensity_defaults(self):
        import roleplay_config as rp

        self.assertEqual(rp.normalize_intensity(None), "medium")
        self.assertEqual(rp.normalize_intensity("alta"), "high")
        self.assertEqual(rp.normalize_intensity("baixo"), "low")

    def test_build_roleplay_prompt_high_intensity(self):
        import roleplay_config as rp

        prompt = rp.build_roleplay_prompt(
            "pt",
            {"tone": "witty", "humor": "high", "energy": "sharp", "intensity": "high"},
        )
        self.assertIn("PERSONALITY INTENSITY: HIGH", prompt)
        self.assertIn("exaggerate the preset", prompt)

    def test_set_intensity_persists(self):
        import roleplay_config as rp

        uid = 999004
        rp.reset_profile(uid)
        try:
            rp.set_intensity(uid, "high")
            profile = rp.get_profile(uid)
            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertEqual(profile.get("intensity"), "high")
            rp.set_intensity(uid, "low")
            profile = rp.get_profile(uid)
            assert profile is not None
            self.assertEqual(profile.get("intensity"), "low")
        finally:
            rp.reset_profile(uid)


class TestVolumeHelpers(unittest.TestCase):
    def test_volume_mappings(self):
        import tiffany_voice as tv

        self.assertAlmostEqual(tv.volume_to_ffmpeg(100), 0.35)
        self.assertAlmostEqual(tv.volume_to_ffmpeg(50), 0.175)
        self.assertEqual(tv.volume_to_lavalink(100), 1000)
        self.assertEqual(tv.volume_to_lavalink(150), 1500)

    def test_presence_lines_from_slash_tree(self):
        import notices
        import tiffany_voice as tv

        tv.register_voice(notices.discord_client)
        lines = tv.presence_lines_for(notices.discord_client)
        self.assertGreaterEqual(len(lines), 25)
        self.assertTrue(all(line.startswith("/") for line in lines))
        self.assertNotIn("/rp", lines)
        self.assertIn("/stats", lines)
        self.assertIn("/help", lines)


class TestVolumeEmbed(unittest.TestCase):
    def test_build_volume_embed(self):
        em = locale_utils.build_volume_embed("pt", current=80, pink=TIFFANY_PINK)
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


class TestI18nLoader(unittest.TestCase):
    def test_json_volume_overlay(self):
        from infra import i18n_loader
        i18n_loader.ensure_loaded()
        pt_title = i18n_loader.lookup("pt", "volume.client_title")
        self.assertIsNotNone(pt_title)
        self.assertIn("🎧", pt_title or "")
        pt_body = i18n_loader.lookup("pt", "volume.client_body")
        self.assertIn("Discord", pt_body or "")
        ja_title = i18n_loader.lookup("ja", "volume.title")
        self.assertTrue(ja_title)
        self.assertNotEqual(ja_title, "Volume")

    def test_all_sixteen_languages_in_picker(self):
        self.assertEqual(len(locale_utils.ALL_LANGS), 16)
        self.assertEqual(len(locale_utils.LANGUAGE_SELECT_OPTIONS), 16)
        values = {opt[0] for opt in locale_utils.LANGUAGE_SELECT_OPTIONS}
        self.assertEqual(values, set(locale_utils.ALL_LANGS))

    def test_extended_lang_help_not_english_fallback(self):
        from infra import i18n_loader
        i18n_loader.ensure_loaded()
        ja_help = locale_utils.tr("ja", "help.title")
        self.assertIn("Tiffany", ja_help)
        self.assertNotEqual(ja_help, locale_utils.tr("en", "help.title"))
        about_lang = locale_utils.tr("de", "about.language.body")
        self.assertIn("16", about_lang)

    def test_hindi_help_not_english_fallback(self):
        from infra import i18n_loader
        i18n_loader.ensure_loaded()
        hi_help = locale_utils.tr("hi", "help.title")
        self.assertIn("Tiffany", hi_help)
        self.assertNotEqual(hi_help, locale_utils.tr("en", "help.title"))


if __name__ == "__main__":
    unittest.main()
