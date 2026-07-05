"""Unit tests for game_recommendations filter parsing (no Discord / network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from game_recommendations import GameFilters, _regex_parse_filters


def test_steam_only_and_max_price():
    f = _regex_parse_filters("terror multiplayer até 10 reais na steam")
    assert f.stores == ["steam"]
    assert f.max_price_brl == 10.0
    assert f.multiplayer is True
    assert "terror" in f.genres


def test_both_stores_default():
    f = _regex_parse_filters("rpg indie grátis")
    assert set(f.stores) == {"steam", "epic"}
    assert f.free_only is True


def test_epic_only():
    f = _regex_parse_filters("aventura na epic até 25 reais")
    assert f.stores == ["epic"]
    assert f.max_price_brl == 25.0


def test_min_rating():
    f = _regex_parse_filters("nota 85 metacritic")
    assert f.min_rating == 85.0


def test_developer_studio():
    f = _regex_parse_filters("estúdio Supergiant roguelike")
    assert f.developers
    assert "Supergiant" in f.developers[0]


def test_language_pt():
    f = _regex_parse_filters("legendas português")
    assert f.language_pt is True


def test_steam_reviews_not_in_regex_fallback():
    f = _regex_parse_filters("reviews muito positivas")
    assert f.min_steam_reviews is None


def test_single_player():
    f = _regex_parse_filters("jogo solo rpg")
    assert f.single_player is True


def test_returns_game_filters_instance():
    f = _regex_parse_filters("fps steam")
    assert isinstance(f, GameFilters)


if __name__ == "__main__":
    tests = [
        test_steam_only_and_max_price,
        test_both_stores_default,
        test_epic_only,
        test_min_rating,
        test_developer_studio,
        test_language_pt,
        test_steam_reviews_not_in_regex_fallback,
        test_single_player,
        test_returns_game_filters_instance,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"\n{len(tests)} passed")
