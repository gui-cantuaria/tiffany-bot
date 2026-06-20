# Offers Bot Technical Reference

Detailed reference for offers.py internals. Only needed when modifying scraping, filters, or embed formatting.

## Embed Layout
- Author: `Via {store} • Oferta {cat_emoji}`
- Title: `🔥 {product} — {discount}% OFF`
- Description line 1: `~~R$ original~~ → **R$ current** (-X%)`
- Description line 2: `Você economiza R$ X` (no emoji)
- Details block: `🏷️ Cupom: \`code\``, `💳 installments`, `⏰ Expira: date`, `⭐ N/5 (N avaliações)`, tags
- CTA: `## [COMPRAR COM X% OFF](url)` (heading link, no emoji)
- Button: `🛒 COMPRAR COM X% OFF` (Discord link button)
- Footer: `Preço sujeito a alterações`
- Thread: `🛒 {store}: {title[:70]}`

## Schedule
- Hours: 8h-18h SP, 30min cycle, max 5 posts per cycle, 3min spacing
- First cycle runs immediately on startup

## Category Variety / Prioritization
- Enrichment ordering by `_CATEGORY_PRIORITY` (CPU/GPU/RAM = priority 1)
- Diversification: round-robin across categories, max 2 per category per cycle
- Accessories demoted to priority 4

## Filters
- Discount: 15-100%
- Image required
- Relevance filter (`_is_irrelevant`): rejects non-IT products
- Stars >= 4.3, sales >= 50
- Active whitelist: Terabyte, ShopInfo, Amazon, Mercado Livre, Shopee, AliExpress
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
