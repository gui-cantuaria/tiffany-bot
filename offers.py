import discord
from discord.ext import tasks, commands
import os
import re
import json
import time
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin

import io
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import affiliate_config

# =========================
# CONFIGURAÇÕES
# =========================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CANAL_OFERTAS_ID = int(os.getenv("CANAL_OFERTAS_ID", "1512902840908124281"))
ID_CARGO_OFERTAS = int(os.getenv("ID_CARGO_OFERTAS", "0"))
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

HORA_INICIO = 8
HORA_FIM = 18
FUSO_HORARIO_BR = timezone(timedelta(hours=-3))

# --- Pipeline ---
SCAN_INTERVAL_MIN = 45
POST_SPACING_SEC = 180  # 3 min entre posts
MAX_POSTS_POR_CICLO = 5
DESCONTO_MINIMO = 15  # percentual mínimo
NOTA_MINIMA_ESTRELAS = 4.2
VENDAS_MINIMAS = 20

HISTORY_FILE = "offers_history.json"

# --- Promobit ---
PROMOBIT_BASE = "https://www.promobit.com.br"
CATEGORIAS_PROMOBIT = [
    "/promocoes/hardware-perifericos/s/",
    "/promocoes/notebooks/s/",
    "/promocoes/notebook-gamer/s/",
    "/promocoes/monitor/s/",
    "/promocoes/processador/s/",
    "/promocoes/placa-mae/s/",
    "/promocoes/pc-gamer/s/",
]

# Whitelist completa (para quando todos os afiliados estiverem ativos)
# LOJAS_WHITELIST_FULL = {
#     "kabum", "kabum!",
#     "terabyte", "terabyteshop",
#     "magalu", "magazine luiza",
#     "pichau", "pichau informática",
#     "amazon", "amazon.com.br",
#     "mercado livre", "mercadolivre",
#     "shopinfo",
#     "shopee",
#     "aliexpress",
# }

# Whitelist ativa: apenas lojas com link de afiliado configurado
LOJAS_WHITELIST = {
    "terabyte", "terabyteshop",
    "shopinfo",
    "amazon", "amazon.com.br",
}

# =========================
# LOGGING
# =========================
_log_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

os.makedirs("logs", exist_ok=True)
_file_handler = RotatingFileHandler(
    "logs/offers.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)

log = logging.getLogger("tiffany-offers")
log.setLevel(logging.INFO)
log.addHandler(_console_handler)
log.addHandler(_file_handler)

# =========================
# DISCORD CLIENT
# =========================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="t$", intents=intents)
http_session: Optional[aiohttp.ClientSession] = None

# =========================
# CORES E EMOJIS
# =========================
TIFFANY_PINK = 0xFF69B4
COR_OFERTA = TIFFANY_PINK
COR_OFERTA_ALTA = TIFFANY_PINK
EMOJI_FOGO = "🔥"

CATEGORIAS_EMOJI = {
    "Hardware e periféricos": "🖥️",
    "Informática": "💻",
    "Notebook": "💻",
    "Monitor": "🖥️",
    "Processador": "⚡",
    "Placa-mãe": "🔧",
    "PC Gamer": "🎮",
}

# Mapeia slugs de URL para nomes corretos de categoria
_SLUG_TO_CATEGORY = {
    "hardware-perifericos": "Hardware e periféricos",
    "notebooks": "Notebook",
    "notebook-gamer": "PC Gamer",
    "monitor": "Monitor",
    "processador": "Processador",
    "placa-mae": "Placa-mãe",
    "pc-gamer": "PC Gamer",
}

# =========================
# HISTÓRICO / DEDUP
# =========================

def _load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"deals": {}}


def _save_history(history: dict) -> None:
    tmp = f"{HISTORY_FILE}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        os.replace(tmp, HISTORY_FILE)
    except Exception:
        log.exception("Erro ao salvar histórico de ofertas")
        try:
            os.remove(tmp)
        except OSError:
            pass


def _deal_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _is_duplicate(history: dict, url: str) -> bool:
    h = _deal_hash(url)
    return h in history.get("deals", {})


def _mark_posted(history: dict, url: str, title: str) -> None:
    h = _deal_hash(url)
    history.setdefault("deals", {})[h] = {
        "url": url,
        "title": title[:100],
        "ts": time.time(),
    }
    _save_history(history)


def _clean_history(history: dict) -> None:
    """Remove entradas com mais de 7 dias."""
    cutoff = time.time() - (7 * 24 * 3600)
    deals = history.get("deals", {})
    to_remove = [k for k, v in deals.items() if v.get("ts", 0) < cutoff]
    for k in to_remove:
        del deals[k]
    if to_remove:
        log.info(f"Limpeza: {len(to_remove)} ofertas antigas removidas do histórico.")
        _save_history(history)


# =========================
# SCRAPING PROMOBIT
# =========================

async def _fetch_page(session: aiohttp.ClientSession, url: str, retries: int = 2) -> Optional[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    for attempt in range(retries + 1):
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return await resp.text()
                if resp.status in (429, 503) and attempt < retries:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                log.warning(f"HTTP {resp.status} ao acessar {url}")
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            log.error(f"Erro ao buscar {url}: {e}")
    return None


def _parse_deals_from_html(html: str, category_url: str) -> list[dict]:
    """Extrai ofertas da página de categoria do Promobit usando JSON-LD e HTML."""
    soup = BeautifulSoup(html, "html.parser")
    deals = []

    # Tenta extrair JSON-LD (Schema.org Product data)
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                for item in data.get("itemListElement", []):
                    product = item.get("item", {})
                    if product.get("@type") != "Product":
                        continue
                    deal = _extract_from_jsonld(product)
                    if deal:
                        deals.append(deal)
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        deal = _extract_from_jsonld(entry)
                        if deal:
                            deals.append(deal)
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    # Fallback: parse HTML cards se JSON-LD não retornou nada
    if not deals:
        deals = _parse_deals_from_cards(soup)

    return deals


def _extract_from_jsonld(product: dict) -> Optional[dict]:
    """Extrai dados de um produto do JSON-LD do Promobit."""
    title = product.get("name", "").strip()
    image = product.get("image", "")

    if isinstance(image, list):
        image = image[0] if image else ""

    # offers pode ser lista ou dict
    offers_raw = product.get("offers", [])
    if isinstance(offers_raw, list):
        offer = offers_raw[0] if offers_raw else {}
    elif isinstance(offers_raw, dict):
        # AggregateOffer com sub-offers
        inner = offers_raw.get("offers", [])
        if isinstance(inner, list) and inner:
            offer = inner[0]
        else:
            offer = offers_raw
    else:
        offer = {}

    price = offer.get("price") or offer.get("lowPrice")
    high_price = offer.get("highPrice")
    url = offer.get("url") or product.get("url", "")
    seller = offer.get("seller", {})
    store_name = seller.get("name", "") if isinstance(seller, dict) else ""

    if not title or not price or not url:
        return None

    try:
        price = float(price)
    except (ValueError, TypeError):
        return None

    original_price = None
    discount_pct = None
    if high_price:
        try:
            original_price = float(high_price)
            if original_price > price:
                discount_pct = round((1 - price / original_price) * 100, 1)
        except (ValueError, TypeError):
            pass

    # Usar resolução maior (600px) em vez do thumbnail (120/268px)
    if isinstance(image, str) and "i.promobit.com.br/" in image:
        image = re.sub(r"i\.promobit\.com\.br/\d+/", "i.promobit.com.br/600/", image)

    return {
        "title": title,
        "price": price,
        "original_price": original_price,
        "discount_pct": discount_pct,
        "store": store_name,
        "image": image,
        "url": url if url.startswith("http") else urljoin(PROMOBIT_BASE, url),
        "coupon": None,
        "expiration": None,
        "stars": None,
        "sales_count": None,
        "store_url": None,
    }


def _parse_deals_from_cards(soup: BeautifulSoup) -> list[dict]:
    """Fallback: parse de cards HTML do Promobit."""
    deals = []
    # Promobit usa article ou div com data de oferta
    cards = soup.select("article, [data-offer-id], .promotionCard, .offer-card")
    for card in cards:
        try:
            # Título
            title_el = card.select_one("h2, h3, .offer-title, [class*='title']")
            title = title_el.get_text(strip=True) if title_el else ""

            # Link
            link_el = card.select_one("a[href*='/oferta/']")
            url = ""
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else urljoin(PROMOBIT_BASE, href)

            # Imagem
            img_el = card.select_one("img[src*='promobit'], img[data-src*='promobit']")
            image = ""
            if img_el:
                image = img_el.get("src") or img_el.get("data-src") or ""

            # Preço
            price_el = card.select_one("[class*='price'], .offer-price, .promo-price")
            price = _parse_price(price_el.get_text() if price_el else "")

            if title and url and price:
                deals.append({
                    "title": title,
                    "price": price,
                    "original_price": None,
                    "discount_pct": None,
                    "store": "",
                    "image": image,
                    "url": url,
                    "coupon": None,
                    "expiration": None,
                    "stars": None,
                    "sales_count": None,
                    "store_url": None,
                })
        except Exception:
            continue
    return deals


def _parse_price(text: str) -> Optional[float]:
    """Converte texto de preço brasileiro para float."""
    if not text:
        return None
    # Remove R$, espaços, pontos de milhar, troca vírgula por ponto
    cleaned = re.sub(r"[R$\s]", "", text)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _enrich_deal(session: aiohttp.ClientSession, deal: dict) -> dict:
    """Busca a página individual da oferta no Promobit e extrai serverOffer (Next.js JSON)."""
    url = deal.get("url")
    if not url:
        return deal
    html = await _fetch_page(session, url)
    if not html:
        return deal

    soup = BeautifulSoup(html, "html.parser")

    # Promobit usa Next.js — dados completos ficam num <script> JSON inline
    server_offer = None
    for script in soup.find_all("script"):
        text = script.string or ""
        if "oldPrice" not in text or not text.strip().startswith("{"):
            continue
        try:
            data = json.loads(text)
            server_offer = data.get("props", {}).get("pageProps", {}).get("serverOffer")
        except (json.JSONDecodeError, AttributeError):
            pass
        if server_offer:
            break

    if not server_offer:
        return deal

    # Loja
    if server_offer.get("storeName"):
        deal["store"] = server_offer["storeName"]

    # Preço original
    old_price = server_offer.get("offerOldPrice")
    try:
        if old_price and float(old_price) > 0:
            deal["original_price"] = float(old_price)
    except (ValueError, TypeError):
        pass

    # Preço atualizado (pode diferir do listado)
    cur_price = server_offer.get("offerPrice")
    try:
        if cur_price:
            deal["price"] = float(cur_price)
    except (ValueError, TypeError):
        pass

    # Desconto
    disc = server_offer.get("offerDiscontPercentage")
    try:
        if disc:
            deal["discount_pct"] = float(disc)
        elif deal.get("original_price") and deal.get("price") and deal["original_price"] > deal["price"]:
            deal["discount_pct"] = round((1 - deal["price"] / deal["original_price"]) * 100, 1)
    except (ValueError, TypeError):
        pass

    # Cupom (pode vir como string, dict ou lista)
    coupon = server_offer.get("offerCoupon")
    if coupon:
        if isinstance(coupon, dict):
            coupon = coupon.get("code") or coupon.get("name") or ""
        elif isinstance(coupon, list):
            coupon = coupon[0] if coupon else ""
            if isinstance(coupon, dict):
                coupon = coupon.get("code") or coupon.get("name") or ""
        if isinstance(coupon, str) and coupon.strip():
            deal["coupon"] = coupon.strip()

    # Imagem (melhor resolução)
    photo = server_offer.get("offerPhoto")
    if photo:
        if photo.startswith("/"):
            deal["image"] = f"https://i.promobit.com.br/600{photo}"
        elif photo.startswith("http"):
            deal["image"] = photo

    # Link para a loja (redirect do Promobit)
    offer_slug = server_offer.get("offerSlug", "")
    if offer_slug:
        deal["store_url"] = f"{PROMOBIT_BASE}/redirect/oferta/{offer_slug}/"

    # Avaliação do produto na comunidade Promobit
    review_rate = server_offer.get("reviewRate")
    if review_rate is not None:
        try:
            deal["stars"] = float(review_rate)
        except (ValueError, TypeError):
            pass

    total_reviews = server_offer.get("totalReviews")
    if total_reviews:
        try:
            deal["sales_count"] = int(float(total_reviews))
        except (ValueError, TypeError):
            pass

    # Tags (ex: Frete Grátis)
    tags = server_offer.get("offerTags") or []
    deal["tags"] = tags

    return deal


async def _try_fetch_store_rating(session: aiohttp.ClientSession, deal: dict) -> dict:
    """Tentativa (B): buscar estrelas/vendas direto na página da loja. Best effort."""
    store_url = deal.get("store_url")
    if not store_url:
        return deal

    try:
        # Segue o redirect do Promobit para a loja real
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        async with session.get(
            store_url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                return deal
            # Capturar URL real da loja (pos-redirect do Promobit)
            deal["real_store_url"] = str(resp.url)
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        # Estrelas — só buscar se o Promobit não forneceu
        if deal.get("stars") is None:
            for sel in [
                "[itemprop='ratingValue']", "[data-rating]",
                "[class*='rating'] [class*='value']", "[class*='stars']",
            ]:
                el = soup.select_one(sel)
                if el:
                    raw = el.get("content") or el.get("data-rating") or el.get_text()
                    m = re.search(r"(\d+[.,]\d+)", raw)
                    if m:
                        deal["stars"] = float(m.group(1).replace(",", "."))
                        break

        # Vendas / reviews — só buscar se o Promobit não forneceu
        if deal.get("sales_count") is None:
            for sel in [
                "[itemprop='reviewCount']", "[class*='review-count']",
                "[class*='sold']", "[class*='vendido']",
            ]:
                el = soup.select_one(sel)
                if el:
                    raw = el.get("content") or el.get_text()
                    m = re.search(r"(\d+)", raw.replace(".", ""))
                    if m:
                        deal["sales_count"] = int(m.group(1))
                        break

    except Exception as e:
        log.debug(f"Erro ao buscar rating da loja: {e}")

    return deal


# =========================
# FILTROS
# =========================

def _normalize_store(store: str) -> str:
    return store.lower().strip().replace("!", "")


def _store_allowed(store: str) -> bool:
    norm = _normalize_store(store)
    # Match exato ou por palavra (evita "amazonas" casar com "amazon")
    if norm in LOJAS_WHITELIST:
        return True
    # Verificar se alguma loja da whitelist é o início do nome normalizado
    # Ex: "kabum" casa com "kabum informatica"
    for allowed in LOJAS_WHITELIST:
        if norm.startswith(allowed):
            return True
    return False


def _passes_filters(deal: dict) -> tuple[bool, str]:
    """Verifica se a oferta passa nos filtros. Retorna (passed, reason)."""
    # Deve ter imagem
    if not deal.get("image"):
        return False, "sem imagem"

    # Deve ter desconto >= 15% e <= 100% (rejeita valores absurdos/negativos)
    disc = deal.get("discount_pct", 0)
    if not disc or disc < DESCONTO_MINIMO or disc > 100:
        return False, f"desconto {disc}% fora do range ({DESCONTO_MINIMO}-100%)"

    # Loja deve estar na whitelist
    if not _store_allowed(deal.get("store", "")):
        return False, f"loja '{deal.get('store')}' não está na whitelist"

    # Verificação de estrelas/vendas (cascata A→B→C)
    stars = deal.get("stars")
    sales = deal.get("sales_count")

    if stars is not None and stars < NOTA_MINIMA_ESTRELAS:
        return False, f"estrelas {stars} < {NOTA_MINIMA_ESTRELAS}"

    if sales is not None and sales < VENDAS_MINIMAS:
        return False, f"vendas {sales} < {VENDAS_MINIMAS}"

    # Sem dados de qualidade: precisa de pelo menos estrelas OU vendas para aprovar
    if stars is None and sales is None:
        return False, "sem dados de qualidade (stars e sales ausentes)"

    return True, "ok"


# =========================
# FORMATAÇÃO EMBED
# =========================

def _format_price_line(deal: dict) -> str:
    """Formata a linha de preço com destaque."""
    price_new = f"R$ {deal['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    parts = []

    if deal.get("original_price"):
        price_old = f"R$ {deal['original_price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        parts.append(f"~~{price_old}~~ → **{price_new}**")
    else:
        parts.append(f"**{price_new}**")

    if deal.get("discount_pct") and 0 < deal["discount_pct"] <= 100:
        parts.append(f"(-{deal['discount_pct']:.0f}%)")

    return " ".join(parts)


def _format_description(deal: dict) -> str:
    """Monta a descrição do embed."""
    lines = []

    # Linha de preço
    lines.append(_format_price_line(deal))
    lines.append("")

    # Specs do título (o título do Promobit geralmente contém as specs)
    lines.append(f"📦 {deal['title']}")
    lines.append("")

    # Cupom
    if deal.get("coupon"):
        lines.append(f"🏷️ Cupom: **{deal['coupon']}**")

    # Expiração
    if deal.get("expiration"):
        lines.append(f"⏰ Expira: {deal['expiration']}")

    # Estrelas e vendas (só exibe se tiver dados reais)
    if deal.get("stars") and deal.get("sales_count"):
        lines.append(f"⭐ {deal['stars']}/5 ({deal['sales_count']} avaliações)")

    # Tags (ex: Frete Grátis)
    tags = deal.get("tags") or []
    if tags:
        tags_str = " • ".join(t.get("name", str(t)) if isinstance(t, dict) else str(t) for t in tags[:3])
        lines.append(f"🔖 {tags_str}")

    return "\n".join(lines)


async def _download_image(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """Baixa imagem e retorna bytes. Retorna None se falhar."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                log.debug(f"Imagem HTTP {resp.status}: {url[:80]}")
                return None
            data = await resp.read()
            if len(data) < 1000:  # imagem muito pequena
                return None
            return data
    except Exception as e:
        log.debug(f"Erro ao baixar imagem: {e}")
        return None


def _build_embed(deal: dict) -> discord.Embed:
    """Constrói o embed da oferta."""
    discount = deal.get("discount_pct", 0)
    cor = COR_OFERTA_ALTA if discount >= 40 else COR_OFERTA

    # Título: emoji + produto resumido + desconto
    title = f"{EMOJI_FOGO} {deal['title'][:200]} — {discount:.0f}% OFF"

    desc = _format_description(deal)
    if len(desc) > 4096:
        desc = desc[:4093] + "..."
    # URL unificada para título e CTA (evita inconsistência)
    raw_url = deal.get("real_store_url") or deal.get("store_url") or deal.get("url", "")
    buy_url = affiliate_config.build_affiliate_url(deal.get("store", ""), raw_url)

    embed = discord.Embed(
        title=title[:256],
        url=buy_url,
        description=desc,
        color=cor,
    )

    # Author line
    store = deal.get("store", "Loja")
    cat_emoji = "🖥️"
    for cat_key, emoji in CATEGORIAS_EMOJI.items():
        if cat_key.lower() in deal.get("category", "").lower():
            cat_emoji = emoji
            break

    embed.set_author(
        name=f"Via {store} • Oferta {cat_emoji}",
        icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png",
    )

    # Imagem — definida no momento de postar (_build_embed não seta aqui
    # para evitar set_image duplo se o download falhar)
    embed.add_field(
        name="",
        value=f"👉 **[COMPRAR COM DESCONTO]({buy_url})**",
        inline=False,
    )

    # Footer sutil (indica afiliado quando aplicavel)
    if buy_url != raw_url:
        embed.set_footer(text="Oferta verificada automaticamente | Link de afiliado")
    else:
        embed.set_footer(text="Oferta verificada automaticamente")

    return embed


# =========================
# CICLO PRINCIPAL
# =========================

_cycle_running = False  # guard contra execuções paralelas

async def _run_deals_cycle() -> None:
    """Executa um ciclo completo de coleta e publicação."""
    global http_session, _cycle_running
    if _cycle_running:
        log.warning("Ciclo anterior ainda rodando, pulando este.")
        return
    _cycle_running = True
    try:
        await _run_deals_cycle_inner()
    finally:
        _cycle_running = False

async def _run_deals_cycle_inner() -> None:
    """Lógica real do ciclo de ofertas."""
    global http_session

    if http_session and not http_session.closed:
        pass  # Reutilizar sessão existente
    else:
        if http_session and http_session.closed:
            http_session = None
        http_session = aiohttp.ClientSession()

    history = _load_history()
    _clean_history(history)

    log.info("=== Iniciando ciclo de ofertas ===")

    all_deals: list[dict] = []

    # Coleta de todas as categorias
    for cat_path in CATEGORIAS_PROMOBIT:
        url = PROMOBIT_BASE + cat_path
        html = await _fetch_page(http_session, url)
        if not html:
            continue

        deals = _parse_deals_from_html(html, cat_path)
        # Extrai nome da categoria do path
        cat_slug = cat_path.strip("/").split("/")[-2]
        cat_name = _SLUG_TO_CATEGORY.get(cat_slug, cat_slug.replace("-", " ").title())
        for d in deals:
            d["category"] = cat_name

        log.info(f"  {cat_path}: {len(deals)} ofertas encontradas")
        all_deals.extend(deals)

        await asyncio.sleep(2)  # Respeitar rate limit do Promobit

    log.info(f"Total bruto: {len(all_deals)} ofertas coletadas")

    # Dedup e filtro
    candidates = []
    for deal in all_deals:
        if _is_duplicate(history, deal["url"]):
            continue
        candidates.append(deal)

    log.info(f"Após dedup: {len(candidates)} candidatas")

    # Enriquecer cada oferta (buscar detalhes)
    enriched = []
    for deal in candidates[:20]:  # Limitar para não abusar
        try:
            deal = await asyncio.wait_for(_enrich_deal(http_session, deal), timeout=30.0)
            await asyncio.sleep(1.5)

            # Sempre resolver URL real da loja (necessário para afiliados)
            # + tenta buscar rating se ainda não tem
            if deal.get("store_url") and not deal.get("real_store_url"):
                deal = await asyncio.wait_for(_try_fetch_store_rating(http_session, deal), timeout=20.0)
                await asyncio.sleep(1)
            enriched.append(deal)
        except asyncio.TimeoutError:
            log.warning(f"Timeout ao enriquecer oferta {deal.get('title', '?')[:50]}")
        except Exception as e:
            log.warning(f"Erro ao enriquecer oferta {deal.get('title', '?')[:50]}: {e}")

    # Aplicar filtros
    approved = []
    for deal in enriched:
        passed, reason = _passes_filters(deal)
        if passed:
            approved.append(deal)
        else:
            log.debug(f"  Rejeitada: {deal['title'][:50]} — {reason}")

    log.info(f"Após filtros: {len(approved)} aprovadas")

    # Ordenar por desconto (maior primeiro)
    approved.sort(key=lambda d: d.get("discount_pct", 0), reverse=True)

    # Postar
    channel = bot.get_channel(CANAL_OFERTAS_ID)
    if not channel:
        log.error(f"Canal {CANAL_OFERTAS_ID} não encontrado!")
        return

    posted = 0
    for deal in approved[:MAX_POSTS_POR_CICLO]:
        embed = _build_embed(deal)

        # Baixar imagem e anexar como arquivo
        file = None
        if deal.get("image"):
            img_data = await _download_image(http_session, deal["image"])
            if img_data:
                file = discord.File(io.BytesIO(img_data), filename="oferta.jpg")
                embed.set_image(url="attachment://oferta.jpg")
            else:
                # Fallback: tentar URL direto no embed
                embed.set_image(url=deal["image"])

        try:
            content = None
            if ID_CARGO_OFERTAS:
                guild = getattr(channel, "guild", None)
                if guild and guild.get_role(ID_CARGO_OFERTAS):
                    content = f"<@&{ID_CARGO_OFERTAS}>"
            msg = await channel.send(content=content, embed=embed, file=file)

            # Marcar como postado DEPOIS de enviar com sucesso
            _mark_posted(history, deal["url"], deal["title"])

            try:
                thread_name = f"🛒 {deal.get('store', 'Oferta')}: {deal['title'][:70]}"[:100]
                await msg.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440,
                )
            except Exception as e:
                log.warning(f"Erro ao criar thread: {e}")

            posted += 1
            log.info(f"  🛒 Postada: {deal['title'][:60]} ({deal.get('discount_pct', 0):.0f}% OFF)")

            if posted < MAX_POSTS_POR_CICLO:
                await asyncio.sleep(POST_SPACING_SEC)

        except Exception as e:
            log.error(f"  Erro ao postar oferta: {e}")

    log.info(f"=== Ciclo finalizado: {posted} ofertas postadas ===")


# =========================
# TASKS LOOP
# =========================

@tasks.loop(minutes=SCAN_INTERVAL_MIN)
async def deals_loop():
    """Loop principal que roda a cada 30 minutos."""
    agora = datetime.now(FUSO_HORARIO_BR)

    if not (HORA_INICIO <= agora.hour < HORA_FIM):
        log.info(f"Fora do horário ({agora.hour}h). Pulando ciclo.")
        return

    try:
        await _run_deals_cycle()
    except Exception as e:
        log.exception(f"Erro no ciclo de ofertas: {e}")


@deals_loop.before_loop
async def _before_deals_loop():
    await bot.wait_until_ready()
    log.info("Bot de ofertas pronto. Executando primeiro ciclo imediatamente.")
    # Executar primeiro ciclo imediatamente (sem esperar o intervalo de 30min)
    agora = datetime.now(FUSO_HORARIO_BR)
    if HORA_INICIO <= agora.hour < HORA_FIM:
        try:
            await _run_deals_cycle()
        except Exception as e:
            log.exception(f"Erro no primeiro ciclo de ofertas: {e}")


# =========================
# EVENTOS
# =========================

@bot.event
async def on_ready():
    log.info(f"✅ Deals bot conectado como {bot.user} (ID: {bot.user.id})")
    # Log de programas de afiliado ativos
    progs = affiliate_config.active_programs()
    if progs:
        log.info(f"💰 Afiliados ativos: {', '.join(progs)}")
    else:
        log.warning("⚠️ Nenhum programa de afiliado configurado no .env")
    if not deals_loop.is_running():
        deals_loop.start()


@bot.event
async def on_disconnect():
    log.warning("⚠️ Bot desconectado do Discord.")


@bot.event
async def on_close():
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()
        http_session = None
    log.info("🔌 Sessão HTTP fechada. Bot desligando.")


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        log.error("DISCORD_TOKEN não configurado!")
        exit(1)

    log.info("🛒 Iniciando Tiffany Deals Bot...")
    bot.run(DISCORD_TOKEN, log_handler=None)
