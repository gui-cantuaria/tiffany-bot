#!/usr/bin/env python3
"""Dry-run offers pipeline: scrape → enrich → filter → select."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DISCORD_TOKEN", "x")

import aiohttp
import offers_cog as oc


async def main() -> None:
    session = aiohttp.ClientSession()
    oc.http_session = session
    all_deals: list = []

    print("=== Category fetch ===")
    for cat_path in oc.CATEGORIAS_PROMOBIT:
        url = oc.PROMOBIT_BASE + cat_path
        html = await oc._fetch_page(session, url)
        if not html:
            print(f"FAIL {cat_path}")
            continue
        deals = oc._parse_deals_from_html(html, cat_path)
        cat_slug = cat_path.strip("/").split("/")[-2]
        cat_name = oc._SLUG_TO_CATEGORY.get(cat_slug, cat_slug)
        for d in deals:
            d["category"] = cat_name
            oc._normalize_deal_category(d)
        print(f"OK {cat_path}: {len(deals)} raw")
        all_deals.extend(deals)
        await asyncio.sleep(0.5)

    print(f"\nTotal raw: {len(all_deals)}")

    pre = [
        d for d in all_deals
        if not (d.get("store") and not oc._store_allowed(d.get("store", "")))
    ]
    print(f"After store pre-filter: {len(pre)}")

    batch = oc._pick_enrichment_batch(pre)
    print(f"Enrichment batch: {len(batch)}")

    enriched: list = []
    for deal in batch[:12]:
        try:
            deal["_orig_tkey"] = oc._title_key(deal["title"])
            oc._normalize_deal_category(deal)
            d = await asyncio.wait_for(oc._enrich_deal(session, deal), timeout=30.0)
            enriched.append(d)
            print(
                f"  enrich OK: {d['title'][:55]} | "
                f"store={d.get('store')} disc={d.get('discount_pct')} "
                f"stars={d.get('stars')} sales={d.get('sales_count')} "
                f"cat={d.get('category')}"
            )
        except Exception as e:
            print(f"  enrich ERR: {deal.get('title', '?')[:40]}: {e}")
        await asyncio.sleep(1)

    approved: list = []
    rejections: dict[str, int] = {}
    for deal in enriched:
        passed, reason = oc._passes_filters(deal)
        if passed:
            approved.append(deal)
        else:
            rejections[reason] = rejections.get(reason, 0) + 1

    print(f"\nApproved after filters: {len(approved)}")
    for reason, n in sorted(rejections.items(), key=lambda x: -x[1]):
        print(f"  {n}x {reason}")

    selected = oc._select_diverse(approved, oc.MAX_POSTS_POR_CICLO, max_per_cat=2)
    print(f"Selected to post: {len(selected)}")
    if approved and not selected:
        print("BUG: approved>0 but selected=0")
        print("  categories:", sorted({d.get("category") for d in approved}))

    await session.close()


if __name__ == "__main__":
    asyncio.run(main())
