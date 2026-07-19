"""Unit tests for offers_cog filter helpers (no network, no .env required)."""
from __future__ import annotations

import offers_cog


def test_store_allowed_whitelist():
    assert offers_cog._store_allowed("Terabyte")
    assert offers_cog._store_allowed("Amazon")
    assert not offers_cog._store_allowed("KaBuM!")


def test_primary_hardware_categories():
    assert "Monitor" in offers_cog._PRIMARY_HARDWARE_CATEGORIES
    assert "Notebook" in offers_cog._PRIMARY_HARDWARE_CATEGORIES
    assert offers_cog._PER_CAT_POST_LIMIT.get("Monitor", 0) >= 1
    # Peripherals are now enabled (volume); low-value ones stay off.
    assert offers_cog._PER_CAT_POST_LIMIT.get("Mouse", 0) >= 1
    assert offers_cog._PER_CAT_POST_LIMIT.get("Mousepad", 99) == 0


def test_deal_score_prefers_hardware():
    gpu = {"category": "Placa de Vídeo", "discount_pct": 20, "title": "RTX 4060"}
    mouse = {"category": "Mouse", "discount_pct": 40, "title": "Mouse Gamer RGB"}
    assert offers_cog._deal_score(gpu) > offers_cog._deal_score(mouse)


def test_pick_enrichment_batch_hardware_first():
    deals = [
        {"title": "Mouse barato", "category": "Mouse", "store": "Terabyte", "discount_pct": 50},
        {"title": "Monitor 27", "category": "Monitor", "store": "Terabyte", "discount_pct": 25},
        {"title": "Notebook gamer", "category": "Notebook", "store": "Amazon", "discount_pct": 15},
    ]
    batch = offers_cog._pick_enrichment_batch(deals)
    cats = [d.get("category") for d in batch[:2]]
    assert "Monitor" in cats or "Notebook" in cats


def test_monitor_dedup_similar_sizes():
    """AOC 22" and AOC 21.5" 120hz should produce the same title key (same product)."""
    key1 = offers_cog._title_key("Monitor Aoc 22 120hz 1ms Gaming Hdmi 22b35hm23 Preto")
    key2 = offers_cog._title_key("Monitor AOC 21.5 120hz 1ms Gaming Hdmi")
    assert key1 == key2, f"Expected same key, got {key1!r} vs {key2!r}"


def test_monitor_dedup_different_products():
    """Different brand or refresh rate should produce different keys."""
    key_aoc = offers_cog._title_key("Monitor AOC 22 120hz 1ms Gaming")
    key_lg = offers_cog._title_key("Monitor LG 22 120hz 1ms Gaming")
    assert key_aoc != key_lg, "Different brands should differ"
    key_144 = offers_cog._title_key("Monitor AOC 22 144hz 1ms Gaming")
    assert key_aoc != key_144, "Different refresh rates should differ"


if __name__ == "__main__":
    import sys

    tests = [
        test_store_allowed_whitelist,
        test_primary_hardware_categories,
        test_deal_score_prefers_hardware,
        test_pick_enrichment_batch_hardware_first,
        test_monitor_dedup_similar_sizes,
        test_monitor_dedup_different_products,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    sys.exit(1 if failed else 0)
