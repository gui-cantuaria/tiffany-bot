"""
Configuracao de links de afiliado por loja.
Cada loja tem sua propria logica de injecao de tag/parametro.
Variaveis lidas do .env — se nao existir, o link original e mantido.
"""

import os
import re
from typing import List
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

# =========================
# TAGS/IDs DO .env
# =========================
AMAZON_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "")
MERCADOLIVRE_ID = os.getenv("MERCADOLIVRE_AFFILIATE_ID", "")
AWIN_PUBLISHER_ID = os.getenv("AWIN_PUBLISHER_ID", "")
MAGALU_SLUG = os.getenv("MAGALU_LOJA_SLUG", "")
TERABYTE_ID = os.getenv("TERABYTE_AFFILIATE_ID", "")
SHOPINFO_ID = os.getenv("SHOPINFO_AFFILIATE_ID", "")
SHOPINFO_PARAM = os.getenv("SHOPINFO_PARAM_NAME", "ref")
ALIEXPRESS_ID = os.getenv("ALIEXPRESS_AFFILIATE_ID", "")

# Awin advertiser IDs (fixos por loja)
AWIN_ADVERTISER_KABUM = 23202
AWIN_ADVERTISER_TERABYTE = 22825
AWIN_ADVERTISER_PICHAU = 25037


def _add_param(url: str, key: str, value: str) -> str:
    """Adiciona ou substitui um query param na URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params[key] = [value]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _awin_deeplink(url: str, advertiser_id: int) -> str:
    """Gera deeplink da Awin: redireciona via Awin com comissao."""
    if not AWIN_PUBLISHER_ID:
        return url
    from urllib.parse import quote
    return (
        f"https://www.awin1.com/cread.php"
        f"?awinmid={advertiser_id}"
        f"&awinaffid={AWIN_PUBLISHER_ID}"
        f"&ued={quote(url, safe='')}"
    )


def _magalu_url(url: str) -> str:
    """Converte URL do Magalu para a lojinha do Parceiro Magalu."""
    if not MAGALU_SLUG:
        return url
    # Extrair o path do produto e remontar na lojinha
    parsed = urlparse(url)
    path = parsed.path
    return f"https://www.magazinevoce.com.br/{MAGALU_SLUG}{path}"


def build_affiliate_url(store_name: str, real_url: str) -> str:
    """Recebe o nome da loja e a URL real (pos-redirect), retorna URL com afiliado."""
    if not real_url:
        return real_url

    norm = store_name.lower().strip() if store_name else ""
    domain = urlparse(real_url).netloc.lower()

    # --- Amazon ---
    if "amazon" in domain and AMAZON_TAG:
        return _add_param(real_url, "tag", AMAZON_TAG)

    # --- KaBuM (via Awin) ---
    if "kabum" in domain and AWIN_PUBLISHER_ID:
        return _awin_deeplink(real_url, AWIN_ADVERTISER_KABUM)

    # --- Mercado Livre ---
    if "mercadolivre" in domain and MERCADOLIVRE_ID:
        return _add_param(real_url, "matt_word", MERCADOLIVRE_ID)

    # --- Magazine Luiza / Magalu ---
    if ("magazineluiza" in domain or "magalu" in domain) and MAGALU_SLUG:
        return _magalu_url(real_url)

    # --- Terabyte (via Awin ou param direto) ---
    if "terabyte" in domain:
        if AWIN_PUBLISHER_ID:
            return _awin_deeplink(real_url, AWIN_ADVERTISER_TERABYTE)
        if TERABYTE_ID:
            return _add_param(real_url, "p", TERABYTE_ID)

    # --- Pichau (via Awin) ---
    if "pichau" in domain and AWIN_PUBLISHER_ID:
        return _awin_deeplink(real_url, AWIN_ADVERTISER_PICHAU)

    # --- ShopInfo ---
    if "shopinfo" in domain and SHOPINFO_ID:
        return _add_param(real_url, SHOPINFO_PARAM, SHOPINFO_ID)

    # --- AliExpress (param simples como fallback) ---
    if "aliexpress" in domain and ALIEXPRESS_ID:
        return _add_param(real_url, "aff_fcid", ALIEXPRESS_ID)

    # --- Shopee: precisa de API, nao da pra injetar param simples ---
    # Implementar quando tiver SHOPEE_APP_ID e SHOPEE_APP_SECRET

    # Sem afiliado configurado para essa loja
    return real_url


def has_any_affiliate() -> bool:
    """Retorna True se pelo menos um programa de afiliado esta configurado."""
    return bool(
        AMAZON_TAG or MERCADOLIVRE_ID or AWIN_PUBLISHER_ID
        or MAGALU_SLUG or TERABYTE_ID or SHOPINFO_ID or ALIEXPRESS_ID
    )


def active_programs() -> List[str]:
    """Lista nomes dos programas ativos (para log/debug)."""
    progs = []
    if AMAZON_TAG:
        progs.append(f"Amazon ({AMAZON_TAG})")
    if MERCADOLIVRE_ID:
        progs.append(f"Mercado Livre ({MERCADOLIVRE_ID})")
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
    return progs
