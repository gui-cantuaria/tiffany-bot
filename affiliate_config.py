"""
Affiliate link configuration per store.
Each store has its own tag/parameter injection logic.
Values are read from .env — if missing, the original URL is kept unchanged.
"""

import os
import re
from typing import List
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

# =========================
# TAGS/IDs FROM .env
# =========================
AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "")
MERCADOLIVRE_ID = os.getenv("MERCADOLIVRE_AFFILIATE_ID", "")  # matt_word (label, e.g. username)
# matt_tool is the numeric tracking id from the ML affiliate portal — REQUIRED for
# commission attribution (matt_word alone does NOT track). Find it in any link the
# "Gerador de links" produces: ...?matt_word=you&matt_tool=NNNNNNNN
MERCADOLIVRE_TOOL_ID = os.getenv("MERCADOLIVRE_TOOL_ID", "")
AWIN_PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID", "")
MAGALU_SLUG = os.getenv("MAGALU_LOJA_SLUG", "")
TERABYTE_ID = os.getenv("TERABYTE_AFFILIATE_ID", "")
SHOPINFO_ID = os.getenv("SHOPINFO_AFFILIATE_ID", "")
SHOPINFO_PARAM = os.getenv("SHOPINFO_PARAM_NAME", "ref")
ALIEXPRESS_ID = os.getenv("ALIEXPRESS_AFFILIATE_ID", "")
SHOPEE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "")
LOMADEE_SOURCE_ID = os.getenv("LOMADEE_SOURCE_ID", "")
LOMADEE_APP_TOKEN = os.getenv("LOMADEE_APP_TOKEN", "")

# Awin advertiser IDs (fixed per store)
AWIN_ADVERTISER_KABUM = 23202
AWIN_ADVERTISER_TERABYTE = 22825
AWIN_ADVERTISER_PICHAU = 25037


def _add_param(url: str, key: str, value: str) -> str:
    """Add or replace a query parameter on the URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params[key] = [value]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _awin_deeplink(url: str, advertiser_id: int, publisher_id: str) -> str:
    """Build an Awin deeplink that redirects through Awin for commission."""
    if not publisher_id:
        return url
    from urllib.parse import quote
    return (
        f"https://www.awin1.com/cread.php"
        f"?awinmid={advertiser_id}"
        f"&awinaffid={publisher_id}"
        f"&ued={quote(url, safe='')}"
    )


def _lomadee_deeplink(url: str, source_id: str) -> str:
    """Build a Lomadee deeplink that redirects through Lomadee for commission."""
    if not source_id:
        return url
    from urllib.parse import quote
    return (
        f"https://redir.lomadee.com/v2/deeplink"
        f"?sourceId={source_id}"
        f"&url={quote(url, safe='')}"
    )


def _magalu_url(url: str, slug: str) -> str:
    """Convert a Magalu product URL to the partner storefront URL."""
    if not slug:
        return url
    parsed = urlparse(url)
    path = parsed.path
    return f"https://www.magazinevoce.com.br/{slug}{path}"


def build_affiliate_url(store_name: str, real_url: str, guild_tags: dict = None) -> str:
    """Given store name and real URL (post-redirect), return the affiliate URL."""
    if not real_url:
        return real_url

    guild_tags = guild_tags or {}
    
    def _t(key: str, default: str) -> str:
        return guild_tags.get(key) or default

    amz_tag = _t("amazon_tag", AMAZON_TAG)
    ml_id = _t("mercadolivre_id", MERCADOLIVRE_ID)
    ml_tool_id = _t("mercadolivre_tool_id", MERCADOLIVRE_TOOL_ID)
    awin_pub_id = _t("awin_publisher_id", AWIN_PUBLISHER_ID)
    magalu_slug = _t("magalu_slug", MAGALU_SLUG)
    tera_id = _t("terabyte_id", TERABYTE_ID)
    shopinfo_id = _t("shopinfo_id", SHOPINFO_ID)
    aliex_id = _t("aliexpress_id", ALIEXPRESS_ID)
    shopee_id = _t("shopee_id", SHOPEE_ID)
    loma_id = _t("lomadee_source_id", LOMADEE_SOURCE_ID)

    norm = store_name.lower().strip() if store_name else ""
    domain = urlparse(real_url).netloc.lower()

    # --- Amazon ---
    if "amazon" in domain and amz_tag:
        return _add_param(real_url, "tag", amz_tag)

    # --- KaBuM (via Awin) ---
    if "kabum" in domain and awin_pub_id:
        return _awin_deeplink(real_url, AWIN_ADVERTISER_KABUM, awin_pub_id)

    # --- Mercado Livre (matt_tool = tracking id, matt_word = label) ---
    if "mercadolivre" in domain and (ml_tool_id or ml_id):
        out = real_url
        if ml_id:
            out = _add_param(out, "matt_word", ml_id)
        if ml_tool_id:
            out = _add_param(out, "matt_tool", ml_tool_id)
        return out

    # --- Magazine Luiza / Magalu ---
    if ("magazineluiza" in domain or "magalu" in domain) and magalu_slug:
        return _magalu_url(real_url, magalu_slug)

    # --- Terabyte (Lomadee > Awin > direct param) ---
    if "terabyte" in domain:
        if loma_id:
            return _lomadee_deeplink(real_url, loma_id)
        if awin_pub_id:
            return _awin_deeplink(real_url, AWIN_ADVERTISER_TERABYTE, awin_pub_id)
        if tera_id:
            return _add_param(real_url, "p", tera_id)

    # --- Pichau (via Awin) ---
    if "pichau" in domain and awin_pub_id:
        return _awin_deeplink(real_url, AWIN_ADVERTISER_PICHAU, awin_pub_id)

    # --- ShopInfo (Lomadee > direct param) ---
    if "shopinfo" in domain:
        if loma_id:
            return _lomadee_deeplink(real_url, loma_id)
        if shopinfo_id:
            return _add_param(real_url, SHOPINFO_PARAM, shopinfo_id)

    # --- AliExpress (simple param fallback) ---
    if "aliexpress" in domain and aliex_id:
        return _add_param(real_url, "aff_fcid", aliex_id)

    # --- Shopee (redirect with aff_id) ---
    if "shopee" in domain and shopee_id:
        from urllib.parse import quote
        return f"https://s.shopee.com.br/an_redir?origin_link={quote(real_url, safe='')}&aff_id={shopee_id}"

    # No affiliate program configured for this store
    return real_url


def has_any_affiliate() -> bool:
    """Return True if at least one affiliate program is configured."""
    return bool(
        AMAZON_TAG or MERCADOLIVRE_ID or MERCADOLIVRE_TOOL_ID or AWIN_PUBLISHER_ID
        or MAGALU_SLUG or TERABYTE_ID or SHOPINFO_ID or ALIEXPRESS_ID
        or SHOPEE_ID or LOMADEE_SOURCE_ID
    )


def active_programs() -> List[str]:
    """List active program names (for log/debug)."""
    progs = []
    if AMAZON_TAG:
        progs.append(f"Amazon ({AMAZON_TAG})")
    if MERCADOLIVRE_TOOL_ID or MERCADOLIVRE_ID:
        progs.append(f"Mercado Livre (word={MERCADOLIVRE_ID or '-'}, tool={MERCADOLIVRE_TOOL_ID or '-'})")
    if AWIN_PUBLISHER_ID:
        progs.append(f"Awin/KaBuM/Terabyte ({AWIN_PUBLISHER_ID})")
    if MAGALU_SLUG:
        progs.append(f"Magalu ({MAGALU_SLUG})")
    if TERABYTE_ID:
        progs.append(f"Terabyte ({TERABYTE_ID})")
    if SHOPINFO_ID:
        progs.append(f"ShopInfo ({SHOPINFO_ID})")
    if ALIEXPRESS_ID:
        progs.append(f"AliExpress ({ALIEXPRESS_ID})")
    if SHOPEE_ID:
        progs.append(f"Shopee ({SHOPEE_ID})")
    if LOMADEE_SOURCE_ID:
        progs.append(f"Lomadee/Terabyte ({LOMADEE_SOURCE_ID})")
    return progs
