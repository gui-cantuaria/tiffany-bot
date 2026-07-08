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
    assert offers_cog._PER_CAT_POST_LIMIT.get("Mouse", 99) == 0


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


if __name__ == "__main__":
    import sys

    tests = [
        test_store_allowed_whitelist,
        test_primary_hardware_categories,
        test_deal_score_prefers_hardware,
        test_pick_enrichment_batch_hardware_first,
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
