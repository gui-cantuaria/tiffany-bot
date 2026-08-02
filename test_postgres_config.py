"""Unit tests for PostgreSQL connection configuration (SSL / URL parsing)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from infra.postgres import _parse_database_url, resolve_pool_connect_args


class TestPostgresConfig(unittest.TestCase):
    def test_url_ssl_disable_stripped_from_dsn(self) -> None:
        url = "postgresql://u:p@127.0.0.1:5433/db?ssl=disable"
        clean, kwargs = _parse_database_url(url)
        self.assertEqual(clean, "postgresql://u:p@127.0.0.1:5433/db")
        self.assertEqual(kwargs, {"ssl": False})

    def test_production_url_has_no_implicit_ssl_disable(self) -> None:
        url = "postgresql://u:p@db.example.com:5432/tiffany"
        with patch.dict(os.environ, {}, clear=True):
            clean, kwargs = resolve_pool_connect_args(url)
        self.assertEqual(clean, url)
        self.assertEqual(kwargs, {})

    def test_database_ssl_disable_env_overrides_clean_url(self) -> None:
        url = "postgresql://u:p@127.0.0.1:5433/tiffany_test"
        with patch.dict(os.environ, {"DATABASE_SSL": "disable"}, clear=True):
            clean, kwargs = resolve_pool_connect_args(url)
        self.assertNotIn("ssl=disable", clean)
        self.assertEqual(kwargs, {"ssl": False})

    def test_database_ssl_require_uses_ssl_context(self) -> None:
        url = "postgresql://u:p@db.example.com:5432/tiffany"
        with patch.dict(os.environ, {"DATABASE_SSL": "require"}, clear=True):
            _clean, kwargs = resolve_pool_connect_args(url)
        self.assertIn("ssl", kwargs)
        self.assertIsNotNone(kwargs["ssl"])

    def test_env_disable_wins_over_url_query(self) -> None:
        url = "postgresql://u:p@127.0.0.1:5433/db?ssl=disable"
        with patch.dict(os.environ, {"DATABASE_SSL": "require"}, clear=True):
            _clean, kwargs = resolve_pool_connect_args(url)
        self.assertIn("ssl", kwargs)
        self.assertIsNotNone(kwargs["ssl"])


if __name__ == "__main__":
    unittest.main()
