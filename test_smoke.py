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


if __name__ == "__main__":
    unittest.main()
