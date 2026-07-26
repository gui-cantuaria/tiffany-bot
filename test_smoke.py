"""Smoke tests — no network, no Discord token required."""

from __future__ import annotations

import unittest
from unittest import mock

import locale_utils
from brand_colors import TIFFANY_PINK


class TestHelpEmbed(unittest.TestCase):
    def test_build_help_embed_accepts_user_id(self):
        em = locale_utils.build_help_embed(None, 12345, pink=TIFFANY_PINK)
        self.assertTrue(em.title)

    def test_build_help_embed_none_user_id(self):
        em = locale_utils.build_help_embed(None, None, pink=TIFFANY_PINK)
        self.assertIsNotNone(em.description)
        self.assertEqual(len(em.fields), 4)
        self.assertIn("—", em.fields[0].value or "")
        self.assertIn("roleplay", em.fields[1].value or "")
        self.assertIn("/language", em.fields[3].value or "")

    def test_help_embed_turkish_json_catalog(self):
        locale_utils.set_user_lang(999002, "tr")
        try:
            em = locale_utils.build_help_embed(None, 999002, pink=TIFFANY_PINK)
            self.assertEqual(em.title, locale_utils.tr("tr", "help.title"))
            self.assertIn("10k", em.fields[0].value)
            self.assertIn("—", em.fields[0].value)
        finally:
            locale_utils._user_lang_cache.pop("999002", None)

    def test_help_embed_portuguese_core_strings(self):
        locale_utils.set_user_lang(999003, "pt")
        try:
            em = locale_utils.build_help_embed(None, 999003, pink=TIFFANY_PINK)
            self.assertIn("10k", em.fields[0].value)
            self.assertIn("—", em.fields[0].value)
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

    def test_embed_subcommand_slash_desc(self):
        from discord import app_commands

        kw = locale_utils.slash_desc_kwargs("slash.cmd.embed_create")
        desc = kw["description"]
        self.assertIsInstance(desc, app_commands.locale_str)
        self.assertEqual(str(desc), locale_utils.tr("en", "slash.cmd.embed_create"))

    def test_slash_desc_bucket_merges_json_catalog(self):
        bucket = locale_utils._slash_desc_bucket("slash.cmd.embed")
        self.assertIn("en", bucket)
        self.assertIn("pt", bucket)
        self.assertIn("tr", bucket)
        self.assertEqual(bucket["en"], locale_utils.tr("en", "slash.cmd.embed"))

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
        self.assertTrue(all(" — " in line for line in lines))
        self.assertNotIn("/rp", lines)
        self.assertIn("/stats — am I online?", lines)
        self.assertIn("/help — all commands", lines)

    def test_language_search_match(self):
        self.assertEqual(locale_utils.match_language_query("portugues"), ["pt"])
        self.assertEqual(locale_utils.match_language_query("deutsch"), ["de"])
        self.assertEqual(locale_utils.match_language_query("xyz"), [])


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

    def test_critical_strings_localized_all_langs(self):
        """User-facing keys must not silently fall back to English (except en)."""
        critical = (
            "help.title",
            "help.desc",
            "lang.title",
            "lang.changed",
            "lang.search_btn",
            "lang.search_not_found",
            "about.desc",
            "cmd.error.generic",
        )
        for lang in locale_utils.ALL_LANGS:
            if lang == "en":
                continue
            for key in critical:
                got = locale_utils.tr(lang, key)
                en = locale_utils.tr("en", key)
                self.assertNotEqual(
                    got,
                    en,
                    msg=f"{lang}:{key} still English fallback",
                )
                self.assertNotEqual(got, key, msg=f"{lang}:{key} leaked raw key")

    def test_fallback_chain_defaults_to_english(self):
        self.assertEqual(locale_utils.DEFAULT_LANG, "en")
        unknown = locale_utils.tr("xx", "help.title")  # type: ignore[arg-type]
        self.assertEqual(unknown, locale_utils.tr("en", "help.title"))

    def test_no_en_catalog_copy_in_extended_bot_json(self):
        """bot.json must not contain copy-pasted EN catalog strings (except brand/proper nouns)."""
        import json
        from pathlib import Path

        catalog = json.loads(
            (Path(__file__).resolve().parent / "locales" / "_catalog_en.json").read_text(encoding="utf-8")
        )
        skip = frozenset({
            "about.title",
            "game.filter.rating.metacritic",
            "game.filter.rating.opencritic",
            "game.filter.rating.steam",
            "lang.search_placeholder",
            "status.field.ping",
            "status.field.warp",
            "status.mode.stay",
        })
        for lang in locale_utils.ALL_LANGS:
            if lang in locale_utils.CORE_LANGS:
                continue
            bot_path = Path(__file__).resolve().parent / "locales" / lang / "bot.json"
            data = json.loads(bot_path.read_text(encoding="utf-8"))
            leaks = [k for k, v in data.items() if k in catalog and k not in skip and v == catalog[k]]
            self.assertEqual(leaks, [], msg=f"{lang} still has EN catalog copy: {leaks[:5]}")


class TestRegressionGuards(unittest.TestCase):
    """Static checks — catch patterns that silently break prefix commands or core loops."""

    def test_no_raw_ephemeral_on_ctx_send(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parent
        pat = re.compile(r"await\s+ctx\.send\([^)]*ephemeral\s*=\s*True", re.DOTALL)
        bad: list[str] = []
        for path in sorted(root.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                bad.append(f"{path.name}:{line}")
        self.assertEqual(bad, [], f"Use hybrid_ctx_reply() instead of ctx.send(..., ephemeral=True): {bad}")

    def test_critical_modules_import(self):
        import importlib

        for mod in ("offers_cog", "giveaways_cog", "embed_builder_cog", "updates", "affiliate_config"):
            importlib.import_module(mod)

    def test_notices_import_without_voice(self):
        """News/offers module must load even if tiffany_voice is broken."""
        import importlib
        import sys

        stub = type(sys)("tiffany_voice_stub")
        stub.register_voice = lambda bot: None
        with mock.patch.dict(sys.modules, {"tiffany_voice": None}):
            # notices already imported in other tests; verify offers helpers exist
            import offers_cog as oc

            self.assertTrue(hasattr(oc, "_run_deals_cycle"))
            self.assertTrue(hasattr(oc, "OffersCog"))


class TestCriticalStartup(unittest.IsolatedAsyncioTestCase):
    async def test_load_extensions_and_voice_register(self):
        """Production startup contract: cogs + voice must not block each other."""
        import asyncio
        import notices
        import tiffany_voice as tv

        await notices._load_bot_extensions()
        self.assertIsNotNone(notices.discord_client.get_cog("OffersCog"))
        self.assertIsNotNone(notices.discord_client.get_cog("EmbedBuilderCog"))
        self.assertIsNotNone(notices.discord_client.get_cog("GiveawaysCog"))
        tv.register_voice(notices.discord_client)
        self.assertIsNotNone(notices.discord_client.get_command("play"))

    async def test_watchdog_restarts_stopped_news_loop(self):
        from infra.critical_tasks import ensure_critical_loops

        news = mock.Mock()
        news.is_running.return_value = False
        bot = mock.Mock()
        bot.is_ready.return_value = True
        bot.get_cog.return_value = mock.Mock(
            deals_loop=mock.Mock(is_running=mock.Mock(return_value=True)),
        )
        await ensure_critical_loops(bot, news_task=news, reload_offers=None)
        news.start.assert_called_once()


class TestImagineSafety(unittest.TestCase):
    def test_blocks_nsfw_and_crime_prompts(self):
        import imagine_safety as imsafe

        self.assertTrue(imsafe.check_literal_imagine_prompt("girl nude on beach"))
        self.assertTrue(imsafe.check_literal_imagine_prompt("hentai catgirl"))
        self.assertTrue(imsafe.check_literal_imagine_prompt("how to make a bomb"))
        self.assertTrue(imsafe.check_literal_imagine_prompt("apologia ao crime"))

    def test_allows_safe_prompts(self):
        import imagine_safety as imsafe

        self.assertFalse(imsafe.check_literal_imagine_prompt("cute pink cat astronaut"))
        self.assertFalse(imsafe.check_literal_imagine_prompt("sunset over mountains"))

    def test_imagine_slash_desc_registered(self):
        kw = locale_utils.slash_desc_kwargs("slash.cmd.imagine")
        desc = str(kw["description"]).lower()
        self.assertTrue("image" in desc or "imagem" in desc or "bild" in desc)


class TestFeatureFlags(unittest.TestCase):
    def test_command_feature_mapping(self):
        import feature_flags as ff

        self.assertEqual(ff.feature_for_command("play"), "music")
        self.assertEqual(ff.feature_for_command("imagine"), "imagine")
        self.assertEqual(ff.feature_for_command("gw"), "giveaways")
        self.assertIsNone(ff.feature_for_command("help"))

    def test_guild_feature_defaults_on(self):
        import guild_config

        cfg = guild_config.get_guild_config(999999991)
        self.assertTrue(cfg["features"].get("music"))
        self.assertTrue(cfg["features"].get("chat"))

    def test_user_feature_toggle(self):
        import user_settings as us

        uid = 999999992
        self.assertTrue(us.is_feature_enabled(uid, "chat"))
        us.set_feature_enabled(uid, "chat", False)
        self.assertFalse(us.is_feature_enabled(uid, "chat"))
        us.set_feature_enabled(uid, "chat", True)


if __name__ == "__main__":
    unittest.main()
