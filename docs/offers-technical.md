# Offers Bot Technical Reference

Detailed reference for `offers_cog.py` internals (the active offers module, loaded as a Cog by `notices.py`). Only needed when modifying scraping, filters, or embed formatting.

## Embed Layout
- Author: `Via {store} • Oferta {cat_emoji}`
- Title: `🔥 {product}` (title links to affiliate URL)
- Description line 1: `~~R$ original~~ → **R$ current** (-X%)`
- Description line 2: `Economize R$ X nessa compra`
- Details block: `🏷️ Cupom: code`, `💳 installments`, `⏰ Expira: date`, `✅ Frete grátis`, event tags (e.g. Prime Day)
- Button: `COMPRAR COM X% OFF` (Discord link button)
- Footer: `Preço sujeito a alterações`
- Thread: `🛒 {store}: {title[:70]}`

## Schedule
- Hours: 8h-18h SP, 30min cycle, max 5 posts per cycle, 3min spacing
- First cycle runs immediately on startup

## Category Variety / Prioritization
- Feed focus: **PC hardware** — parts, notebooks, monitors, prebuilt systems
- Enrichment ordering by `_CATEGORY_PRIORITY` (parts + Monitor/Notebook/PC Gamer = priority 1)
- Selection: parts reserved first, then monitors/notebooks/systems, then round-robin fill
- Per cycle: up to 2 monitors / 2 notebooks / 2 PC gamer; parts capped at 1 each for variety
- Peripherals (mouse, teclado, headset) **not scraped** and **not posted** (`_PER_CAT_POST_LIMIT=0`)
- Network adapters: optional, stricter filters, max 1/cycle

## Filters
- Discount: 15-100%
- Image required
- Relevance filter (`_is_irrelevant`): rejects non-IT products
- Stars >= 4.3, sales >= 50
- Active whitelist: Terabyte, ShopInfo, Amazon, Mercado Livre, Shopee, AliExpress
- **Pending (commented out in code — not posted until re-enabled):** KaBuM, Magalu, Pichau — affiliate helpers exist in `affiliate_config.py` but `_store_allowed()` rejects them today
- Enrichment: parallel batch (`OFFERS_ENRICH_CONCURRENCY`, default 4) with short delay per slot — replaces sequential `sleep(1.5)` loop
- At least one quality metric, or discount >= 25% if no data (`DESCONTO_SEM_METRICA`)
- Rede/adaptadores: stricter filters (stars >= 4.5, sales >= 100, discount >= 40%)

## Role Mentions
- Cap: first 3 offers per day get mention
- Cargo: `ID_CARGO_OFERTAS_ULTRA` env var

## Affiliate Links (affiliate_config.py)
| Store | Method | Env var |
|---|---|---|
| Amazon | `?tag=` param | `AMAZON_AFFILIATE_TAG` |
| Mercado Livre | `?matt_word=` param | `MERCADOLIVRE_AFFILIATE_ID` |
| KaBuM | Awin deeplink | `AWIN_PUBLISHER_ID` |
| Terabyte | Lomadee > Awin > param | `LOMADEE_SOURCE_ID` / `AWIN_PUBLISHER_ID` |
| Pichau | Awin deeplink | `AWIN_PUBLISHER_ID` |
| ShopInfo | Lomadee > param | `LOMADEE_SOURCE_ID` / `SHOPINFO_AFFILIATE_ID` |
| Shopee | Redirect `s.shopee.com.br/an_redir` | `SHOPEE_AFFILIATE_ID` |
| AliExpress | `?aff_fcid=` param | `ALIEXPRESS_AFFILIATE_ID` |
