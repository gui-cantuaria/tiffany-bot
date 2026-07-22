import asyncio
import aiohttp
import game_recommendations as gr

async def main():
    async with aiohttp.ClientSession() as session:
        filters = gr.GameFilters(multiplayer=True, max_price_brl=30.0, genres=['horror'])
        detail = await gr._steam_app_details(session, 967050)
        po = detail.get("price_overview") or {}
        cents = po.get("final")
        is_free = bool(detail.get("is_free"))
        print("Cents:", cents, "_price_ok_brl:", gr._price_ok_brl(is_free, cents, filters))
        genres = [g.get("description", "") for g in (detail.get("genres") or []) if g.get("description")]
        categories = detail.get("categories") or []
        tags = [c.get("description", "") for c in categories if c.get("description")]
        print("Genres/Tags:", genres, tags)
        print("_genre_ok:", gr._genre_ok(genres, tags, filters, title="Pacify"))
        print("_multiplayer_ok:", gr._multiplayer_ok(categories, tags, filters))

asyncio.run(main())
