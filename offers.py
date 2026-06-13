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
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse, quote_plus

import io
import math
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
ID_CARGO_OFERTAS = int(os.getenv("ID_CARGO_OFERTAS", "0"))  # legado: marca em TODA oferta (0 = desligado)
# Cargo marcado SÓ nas "ultra ofertas" (desconto alto). Default = cargo de ofertas do servidor.
ID_CARGO_ULTRA = int(os.getenv("ID_CARGO_OFERTAS_ULTRA", "1386386059390357575"))
DESCONTO_ULTRA_OFERTA = int(os.getenv("DESCONTO_ULTRA_OFERTA", "60"))  # % mínimo para ser "ultra oferta"
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

HORA_INICIO = 8
HORA_FIM = 18
FUSO_HORARIO_BR = timezone(timedelta(hours=-3))

# --- Pipeline ---
SCAN_INTERVAL_MIN = 30  # ciclo de ofertas a cada 30 min
POST_SPACING_SEC = 180  # 3 min entre posts
MAX_POSTS_POR_CICLO = 5
DESCONTO_MINIMO = 15  # percentual mínimo
NOTA_MINIMA_ESTRELAS = 4.4
VENDAS_MINIMAS = 30
AVALIACOES_MINIMAS = 5  # mínimo de avaliações de usuários (mesmo campo que sales_count)
# Promobit raramente fornece estrelas/vendas. Para não travar em 0 ofertas, aceita
# oferta de loja confiável (whitelist) SEM métrica desde que o desconto seja bom.
DESCONTO_SEM_METRICA = 25  # percentual mínimo quando não há estrelas nem vendas

HISTORY_FILE = "offers_history.json"

# --- Promobit ---
PROMOBIT_BASE = "https://www.promobit.com.br"
CATEGORIAS_PROMOBIT = [
    # === Peças de PC (prioridade máxima) ===
    "/promocoes/processador/s/",
    "/promocoes/placa-de-video/s/",
    "/promocoes/memoria-ram/s/",
    "/promocoes/placa-mae/s/",
    "/promocoes/ssd/s/",
    "/promocoes/gabinete/s/",
    "/promocoes/pasta-termica/s/",
    # === Periféricos ===
    "/promocoes/monitor/s/",
    "/promocoes/teclado/s/",
    "/promocoes/mouse/s/",
    "/promocoes/headset/s/",
    "/promocoes/mousepad/s/",
    "/promocoes/webcam/s/",
    "/promocoes/mesa-digitalizadora/s/",
    "/promocoes/braco-articulado-para-monitor/s/",
    # === Hardware geral ===
    "/promocoes/hardware-perifericos/s/",
    "/promocoes/pc-gamer/s/",
    "/promocoes/roteador-e-repetidor/s/",
    # === Outros ===
    "/promocoes/notebooks/s/",
    "/promocoes/notebook-gamer/s/",
    "/promocoes/televisao/s/",
    "/promocoes/tablet/s/",
    "/promocoes/celular/s/",
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
# Lojas com afiliado ativo: Terabyte/ShopInfo (Lomadee), Amazon, Mercado Livre
# Adicionar KaBuM e AliExpress quando Awin aprovar
LOJAS_WHITELIST = {
    "terabyte", "terabyteshop", "terabyte shop",
    "shopinfo", "shopinfo.com.br",
    "amazon", "amazon.com.br",
    "mercado livre", "mercadolivre",
    "shopee",
    # "aliexpress",  # pendente: KYC + API do Portals não configurados
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
# Contador diário de menções ao cargo (máx 3 por dia)
_mention_count_ofertas: int = 0
_mention_date_ofertas: str = ""
# Dedup intraday: evita o mesmo produto aparecer várias vezes no dia com preços diferentes
_posted_title_keys: set = set()
_posted_title_keys_date: str = ""

# =========================
# CORES E EMOJIS
# =========================
TIFFANY_PINK = 0xFF69B4
COR_OFERTA = TIFFANY_PINK          # cor padrão (loja sem cor de marca definida)
COR_OFERTA_ALTA = TIFFANY_PINK     # mantido por compatibilidade
# Cor da barra do embed pela faixa de desconto — sinaliza o quão boa é a oferta.
# Quanto maior o desconto, mais "quente" a cor.
COR_DESCONTO_ULTRA = 0xFF4500   # >= DESCONTO_ULTRA_OFERTA (padrão 40%): vermelho-fogo
COR_DESCONTO_OTIMA = 0xFF8C00   # 30-39%: laranja
COR_DESCONTO_BOA = 0xFFD700     # 20-29%: dourado
# < 20% cai em COR_OFERTA (rosa Tiffany)
EMOJI_FOGO = "🔥"

CATEGORIAS_EMOJI = {
    "Hardware e periféricos": "🖥️",
    "Informática": "💻",
    "Notebook": "💻",
    "Monitor": "🖥️",
    "Processador": "⚡",
    "Placa de Vídeo": "🎮",
    "Placa-mãe": "🔧",
    "PC Gamer": "🎮",
    "Adaptadores e rede": "📡",
    "Teclado": "⌨️",
    "Mouse": "🖱️",
    "Headset": "🎧",
    "Webcam": "📷",
    "SSD": "💾",
    "Memória RAM": "🧩",
    "Mesa digitalizadora": "🎨",
    "Gabinete": "🗄️",
    "Mousepad": "🖱️",
    "Pasta Térmica": "🔧",
    "Tablet": "📱",
    "Celular": "📱",
    "TV": "📺",
    "Suporte e Acessórios": "🖥️",
}

# Mapeia slugs de URL para nomes corretos de categoria
_SLUG_TO_CATEGORY = {
    "hardware-perifericos": "Hardware e periféricos",
    "notebooks": "Notebook",
    "notebook-gamer": "Notebook",
    "monitor": "Monitor",
    "processador": "Processador",
    "placa-mae": "Placa-mãe",
    "placa-de-video": "Placa de Vídeo",
    "pc-gamer": "PC Gamer",
    "roteador-e-repetidor": "Adaptadores e rede",
    "teclado": "Teclado",
    "mouse": "Mouse",
    "headset": "Headset",
    "webcam": "Webcam",
    "ssd": "SSD",
    "memoria-ram": "Memória RAM",
    "mesa-digitalizadora": "Mesa digitalizadora",
    "gabinete": "Gabinete",
    "mousepad": "Mousepad",
    "pasta-termica": "Pasta Térmica",
    "tablet": "Tablet",
    "celular": "Celular",
    "televisao": "TV",
    "braco-articulado-para-monitor": "Suporte e Acessórios",
}

# Prioridade de categoria para ordenação (menor = mais prioritário)
_CATEGORY_PRIORITY = {
    "Processador": 1,
    "Placa de Vídeo": 1,
    "Memória RAM": 1,
    "Placa-mãe": 1,
    "SSD": 1,
    "Gabinete": 1,
    "Pasta Térmica": 1,
    "Monitor": 2,
    "Teclado": 2,
    "Mouse": 2,
    "Headset": 2,
    "Mousepad": 2,
    "Webcam": 2,
    "Mesa digitalizadora": 2,
    "Suporte e Acessórios": 2,
    "Hardware e periféricos": 2,
    "PC Gamer": 3,
    "Notebook": 3,
    "TV": 4,
    "Tablet": 4,
    "Celular": 4,
    "Adaptadores e rede": 5,
}

# Categoria de rede (adaptadores/roteadores): o Promobit não tem categoria só de
# "adaptador de rede", então usamos "roteador-e-repetidor" (que agrupa esses itens)
# e aplicamos filtros PRÓPRIOS, mais rígidos que os gerais (pedido do usuário):
# nota 4.5+, 100+ vendas e 40%+ de desconto. Sem exceção de "sem métrica": se o
# Promobit não trouxer estrelas/vendas, o item de rede NÃO é postado.
CAT_REDE_NOME = "Adaptadores e rede"
REDE_NOTA_MINIMA = 4.5
REDE_VENDAS_MINIMAS = 100
REDE_DESCONTO_MINIMO = 40
# Palavras que identificam um adaptador de rede mesmo em outra categoria
# (ex.: um adaptador USB Wi-Fi listado em hardware-perifericos).
REDE_KEYWORDS = (
    "adaptador de rede", "adaptador wireless", "adaptador wi-fi", "adaptador wifi",
    "adaptador usb wi", "adaptador usb wireless", "placa de rede", "receptor wifi",
    "receptor wi-fi", "antena wifi", "antena wi-fi", "nano usb wireless",
)

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


# Palavras genéricas de categoria que não identificam o produto específico
_TITLE_GENERIC = frozenset({
    "notebook", "teclado", "mouse", "headset", "monitor", "processador",
    "memoria", "placa", "ssd", "webcam", "laptop", "desktop", "gamer",
    "gaming", "mecanico", "sem", "fio", "com", "para", "rgb", "led",
    "preto", "branco", "prata", "cinza", "compacto", "gamer",
})


def _title_key(title: str) -> str:
    """Gera chave de produto para dedup intraday.
    Remove palavras genéricas de categoria, mantém marca + modelo.
    Ex: 'Samsung Galaxy Book4 i5 512GB...' → 'samsung galaxy book4'"""
    t = unicodedata.normalize("NFD", title.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    words = [w for w in t.split() if len(w) >= 2 and w not in _TITLE_GENERIC]
    return " ".join(words[:3])


def _is_valid_coupon(code: str) -> bool:
    """Retorna True se o texto parece um código de cupom real.
    Cupons reais: alfanumérico, sem espaços, 3-25 caracteres.
    Rejeita textos descritivos como '200 off abaixo do preço'."""
    if not code:
        return False
    code = code.strip()
    if len(code) < 3 or len(code) > 25:
        return False
    return bool(re.match(r'^[A-Za-z0-9\-_]+$', code))


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

    # Status — rejeitar ofertas encerradas/expiradas antes de qualquer processamento
    status = (server_offer.get("offerStatus") or server_offer.get("status") or "").lower()
    if status in ("expired", "expirada", "encerrada", "inactive", "unavailable", "sold_out"):
        deal["expired"] = True
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

    # Desconto — SEMPRE recalcular a partir dos preços reais (original vs atual)
    # para garantir precisão. O campo offerDiscontPercentage do Promobit pode estar
    # desatualizado ou incorreto, então só é usado como último fallback.
    try:
        if deal.get("original_price") and deal.get("price") and deal["original_price"] > deal["price"]:
            deal["discount_pct"] = round((1 - deal["price"] / deal["original_price"]) * 100, 1)
        else:
            disc = server_offer.get("offerDiscontPercentage")
            if disc:
                deal["discount_pct"] = float(disc)
    except (ValueError, TypeError):
        pass

    # Menor preço histórico (30 dias) — Promobit expõe em alguns produtos
    lowest_raw = (server_offer.get("offerLowestPrice")
                  or server_offer.get("lowestPrice")
                  or server_offer.get("offerMinPrice")
                  or server_offer.get("minPrice"))
    try:
        if lowest_raw:
            lp = float(lowest_raw)
            if lp > 0:
                deal["lowest_price_30d"] = lp
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
        if isinstance(coupon, str) and _is_valid_coupon(coupon):
            deal["coupon"] = coupon.strip()

    # Imagem (melhor resolução)
    photo = server_offer.get("offerPhoto")
    if photo:
        if photo.startswith("/"):
            deal["image"] = f"https://i.promobit.com.br/600{photo}"
        elif photo.startswith("http"):
            deal["image"] = photo

    # Link de compra: página canônica da oferta no Promobit (sempre 200).
    # O antigo /redirect/oferta/{slug}/ foi descontinuado (dava 404) e o botão
    # real "Ir à loja" é gerado via JS — inacessível pelo servidor. Mandar para
    # a página da oferta garante link válido (usuário vê cupom + botão da loja).
    offer_slug = server_offer.get("offerSlug", "")
    if offer_slug:
        deal["store_url"] = f"{PROMOBIT_BASE}/oferta/{offer_slug}/"

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

    # Parcelamento (best effort — chaves variam no Promobit; só exibe se vier).
    inst_n = (server_offer.get("offerInstallmentAmount")
              or server_offer.get("offerInstallment")
              or server_offer.get("offerInstallments")
              or server_offer.get("offerInstallmentQuantity"))
    inst_v = (server_offer.get("offerInstallmentPrice")
              or server_offer.get("offerInstallmentValue"))
    try:
        if inst_n and inst_v:
            n = int(float(inst_n))
            v = float(inst_v)
            if n >= 2 and v > 0:
                v_str = f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                sem_juros = server_offer.get("offerInstallmentInterestFree") \
                    or server_offer.get("offerInterestFree")
                deal["installments"] = f"{n}x de {v_str}{' sem juros' if sem_juros else ''}"
    except (ValueError, TypeError):
        pass

    # Link DIRETO da loja: o Promobit às vezes expõe a URL do produto (aliasUrl).
    # Quando existir, resolvemos para a loja final (para mandar o usuário direto à
    # loja com a comissão dele). Ofertas de cupom não têm — aí cai na busca por nome.
    alias = server_offer.get("aliasUrl")
    if isinstance(alias, str) and alias.startswith("http"):
        await _resolve_product_url(session, deal, alias)

    # Título limpo orientado ao comprador — remove dump de specs técnicas
    deal["title"] = await _ai_clean_title(session, deal["title"], deal.get("category", ""))

    return deal


_TITLE_SPECS_POR_CATEGORIA = {
    "Memória RAM":
        "marca + linha (ex: Kingston Fury Beast) | tipo (DDR4/DDR5) • capacidade total (ex: 16GB) • kit (ex: 2x8GB) • frequência (ex: 3200MHz) • latência (ex: CL16) • form factor (DIMM/SO-DIMM)",
    "Placa de Vídeo":
        "marca + linha + modelo completo (ex: NVIDIA GeForce RTX 4070 Super / AMD Radeon RX 7800 XT) | VRAM (ex: 12GB GDDR6X) • clock boost (ex: 2505MHz) • TDP (ex: 200W) • tamanho (ex: Dual/Triple fan) • versão OC se houver",
    "SSD":
        "marca + modelo | capacidade (ex: 512GB) • interface (SATA / M.2 NVMe / PCIe Gen4) • velocidade leitura (ex: 3500MB/s) • velocidade escrita se disponível",
    "Processador":
        "marca + modelo completo (ex: Ryzen 5 5600X) | socket (AM4/AM5/LGA1700) • núcleos/threads (ex: 6C/12T) • freq. base/boost (ex: 3.7/4.6GHz) • TDP se disponível",
    "Placa-mãe":
        "marca + modelo | socket (ex: AM5/LGA1700) • chipset (ex: B650/Z790) • form factor (ATX/mATX/ITX) • slots RAM • M.2 slots se disponível",
    "Monitor":
        "marca + modelo | tamanho (ex: 27'') • resolução (ex: Full HD 1920×1080 / QHD / 4K) • painel (IPS/VA/TN) • taxa (ex: 144Hz) • resposta (ex: 1ms) • curvado/plano • portas (ex: HDMI+DP) • sync (FreeSync/G-Sync) se disponível",
    "Teclado":
        "marca + modelo | tipo (Mecânico/Membrana/Silicioso) • layout (60%/TKL/100%/ABNT2/US) • switch (ex: Switch Red/Azul/Brown) se mecânico • conectividade (USB/Sem fio/Bluetooth) • retroiluminação (RGB/Branco/Sem)",
    "Mouse":
        "marca + modelo | DPI máximo (ex: 25600 DPI) • sensor (óptico/laser) • conectividade (USB/Sem fio/Bluetooth) • botões programáveis • peso se disponível",
    "Headset":
        "marca + modelo | conectividade (USB/P2 3.5mm/Sem fio/Bluetooth) • tipo (Over-ear/On-ear/In-ear) • drivers (ex: 50mm) • microfone (removível/integrado/sem) • impedância se disponível",
    "Webcam":
        "marca + modelo | resolução (ex: 1080p/4K) • FPS (ex: 30fps/60fps) • autofoco (sim/não) • campo visual (ex: 90°) • conexão (USB-A/USB-C)",
    "Notebook":
        "marca + modelo | CPU (ex: Core i5-1335U / Ryzen 7 5825U) • RAM (ex: 16GB DDR5) • armazenamento (ex: 512GB SSD NVMe) • tela (ex: 15.6'' IPS FHD 144Hz) • GPU (ex: RTX 4060 / integrada) • SO (Win 11/Linux) • peso se disponível",
    "PC Gamer":
        "CPU (ex: Ryzen 5 5600) • GPU (ex: RTX 4060) • RAM (ex: 16GB DDR4) • armazenamento (ex: 512GB NVMe) • SO (Win 11/Linux)",
    "Mesa digitalizadora":
        "marca + modelo | área ativa (ex: A5 152×95mm) • pressão da caneta (ex: 8192 níveis) • resolução (LPI) • conectividade (USB/Bluetooth) • compatibilidade (Windows/Mac/Android)",
    "Adaptadores e rede":
        "marca + modelo | tipo (Roteador/Repetidor/Adaptador USB) • padrão (ex: Wi-Fi 6 AX3000) • bandas (Dual-band/Tri-band) • velocidade (ex: 2400+600Mbps) • portas (ex: 4x Gigabit)",
    "Gabinete":
        "marca + modelo | tipo de torre (Full Tower/Mid Tower/Mini Tower/Mini ITX) • form factor suportado (ATX/mATX/ITX) • janela lateral (vidro temperado/acrílico/sem janela) • gerenciamento de cabos (sim/não) • cor",
}

_TITLE_SPECS_PADRAO = (
    "marca + modelo | specs técnicas principais separadas por • "
    "(capacidade, velocidade, conectividade, dimensões — o que for relevante)"
)


async def _ai_clean_title(session: aiohttp.ClientSession, title: str, category: str) -> str:
    """Reescreve o título com specs técnicas no formato 'Marca Modelo | spec • spec • spec'.
    Só aciona para títulos longos (>70 chars). Custo: ~80 tokens/chamada."""
    if len(title) <= 70:
        return title
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return title

    specs_guia = _TITLE_SPECS_POR_CATEGORIA.get(category, _TITLE_SPECS_PADRAO)
    prompt = (
        f"Produto: {title}\n"
        f"Categoria: {category}\n\n"
        "Reescreva como título técnico de oferta em português (máximo 120 caracteres).\n"
        "Formato obrigatório: Marca Modelo seguido das specs separadas APENAS por espaço.\n"
        "Exemplo monitor: Samsung Odyssey G5 27 QHD 2560x1440 165Hz 1ms VA HDMI DisplayPort FreeSync\n"
        "Exemplo RAM: Kingston Fury Beast DDR4 16GB 2x8GB 3200MHz CL16 DIMM\n"
        "Exemplo notebook: ASUS Vivobook S14 Core Ultra 7 16GB DDR5 512GB NVMe 14 IPS FHD Linux\n"
        f"Specs a incluir para esta categoria: {specs_guia}\n"
        "Regras:\n"
        "- Use APENAS specs presentes no título original\n"
        "- Sem pontos, vírgulas, barras, traços ou qualquer símbolo separador — apenas espaços\n"
        "- Sem descrições, adjetivos ou frases (ex: sem 'ideal para', 'excelente', 'perfeito')\n"
        "- Mantenha unidades técnicas coladas ao valor (ex: 512GB 3200MHz 144Hz 1ms)\n"
        "- Responda APENAS com o título, sem aspas nem explicações"
    )
    try:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "google/gemini-3.1-flash-lite",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 60,
                "temperature": 0.1,
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                cleaned = data["choices"][0]["message"]["content"].strip().strip('"').strip("'")
                if 10 <= len(cleaned) <= 120:
                    log.debug(f"Título AI: {title[:50]}... → {cleaned}")
                    return cleaned
    except Exception as e:
        log.debug(f"AI title cleanup falhou ({e}), mantendo original")
    return title


# Domínios de loja reconhecidos (para validar se um link aponta para a loja real)
_STORE_DOMAINS = (
    "mercadolivre.com", "mercadolibre.com", "amazon.com", "terabyteshop.com",
    "shopinfo.com", "kabum.com", "pichau.com", "magazineluiza.com",
    "magazinevoce.com", "aliexpress.com", "shopee.com",
)


def _is_store_domain(url: str) -> bool:
    try:
        dom = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(sd in dom for sd in _STORE_DOMAINS)


async def _resolve_product_url(session: aiohttp.ClientSession, deal: dict, alias: str) -> None:
    """Resolve a URL de produto do Promobit (aliasUrl) para a loja final.
    Se já for um link de loja, usa direto; se for redirect (promoby.me/promobit),
    segue até a loja. Resultado vai em deal['product_url']."""
    if _is_store_domain(alias):
        deal["product_url"] = alias
        return
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        async with session.get(
            alias, headers=headers, allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            final = str(resp.url)
            if _is_store_domain(final):
                deal["product_url"] = final
    except Exception as e:
        log.debug(f"Falha ao resolver product_url de {alias[:60]}: {e}")


def _store_search_url(store: str, title: str) -> Optional[str]:
    """Monta URL de busca direta na loja (fallback quando não há link de produto).
    Garante que o usuário vai DIRETO à loja, nunca ao Promobit."""
    norm = (store or "").lower().strip()
    q = (title or "").strip()
    if not q:
        return None
    if "mercado" in norm:
        slug = re.sub(r"[^\w\s-]", "", q.lower())
        slug = re.sub(r"\s+", "-", slug.strip())
        return f"https://lista.mercadolivre.com.br/{slug}" if slug else None
    if "amazon" in norm:
        return f"https://www.amazon.com.br/s?k={quote_plus(q)}"
    if "terabyte" in norm:
        return f"https://www.terabyteshop.com.br/busca?str={quote_plus(q)}"
    if "shopinfo" in norm:
        return f"https://www.shopinfo.com.br/busca?q={quote_plus(q)}"
    if "shopee" in norm:
        return f"https://shopee.com.br/search?keyword={quote_plus(q)}"
    if "aliexpress" in norm:
        return f"https://pt.aliexpress.com/wholesale?SearchText={quote_plus(q)}"
    return None


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


def _is_rede(deal: dict) -> bool:
    """True se a oferta é de rede/adaptador (categoria de rede ou título indica adaptador)."""
    if (deal.get("category") or "") == CAT_REDE_NOME:
        return True
    title = (deal.get("title") or "").lower()
    return any(k in title for k in REDE_KEYWORDS)


def _passes_filters(deal: dict) -> tuple[bool, str]:
    """Verifica se a oferta passa nos filtros. Retorna (passed, reason)."""
    # Oferta encerrada/expirada no Promobit
    if deal.get("expired"):
        return False, "oferta expirada/encerrada"

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

    stars = deal.get("stars")
    sales = deal.get("sales_count")

    # Rede/adaptadores: filtros próprios e mais rígidos. Exige métricas reais
    # (4.5+ estrelas E 100+ vendas) e 50%+ de desconto — sem fallback "sem métrica".
    if _is_rede(deal):
        if disc < REDE_DESCONTO_MINIMO:
            return False, f"[rede] desconto {disc}% < {REDE_DESCONTO_MINIMO}%"
        if stars is None or stars < REDE_NOTA_MINIMA:
            return False, f"[rede] estrelas {stars} < {REDE_NOTA_MINIMA}"
        if sales is None or sales < REDE_VENDAS_MINIMAS:
            return False, f"[rede] vendas {sales} < {REDE_VENDAS_MINIMAS}"
        return True, "ok (rede)"

    # Verificação de estrelas/vendas (cascata A→B→C)
    if stars is not None and stars < NOTA_MINIMA_ESTRELAS:
        return False, f"estrelas {stars} < {NOTA_MINIMA_ESTRELAS}"

    if sales is not None and sales < VENDAS_MINIMAS:
        return False, f"vendas {sales} < {VENDAS_MINIMAS}"

    if sales is not None and sales < AVALIACOES_MINIMAS:
        return False, f"avaliações {sales} < {AVALIACOES_MINIMAS}"

    # Sem dados de qualidade (Promobit não trouxe estrelas nem vendas): como a loja
    # já passou pela whitelist (é confiável), aceita desde que o desconto seja bom.
    if stars is None and sales is None:
        if disc >= DESCONTO_SEM_METRICA:
            return True, "ok (sem métrica, desconto alto)"
        return False, f"sem métrica e desconto {disc}% < {DESCONTO_SEM_METRICA}%"

    return True, "ok"


# =========================
# SCORE E ORDENAÇÃO
# =========================

def _deal_score(deal: dict) -> float:
    """Score composto: desconto × qualidade × log(popularidade).
    Usado para rankear dentro da mesma prioridade de categoria."""
    disc = deal.get("discount_pct") or 0
    stars = deal.get("stars") or 4.0      # neutro se sem dados
    sales = deal.get("sales_count") or 10  # baixo se sem dados
    return disc * stars * math.log10(max(sales, 10))


def _interleave_by_store(deals: list) -> list:
    """Reordena para nunca postar duas seguidas da mesma loja."""
    result = []
    remaining = list(deals)
    last_store = None
    while remaining:
        for i, d in enumerate(remaining):
            if _normalize_store(d.get("store", "")) != last_store:
                result.append(remaining.pop(i))
                last_store = _normalize_store(result[-1].get("store", ""))
                break
        else:
            # Todas restantes são da mesma loja — postar assim mesmo
            result.append(remaining.pop(0))
            last_store = _normalize_store(result[-1].get("store", ""))
    return result


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
    """Monta a descrição do embed focada no que o comprador precisa saber."""
    lines = []

    # 1) Preço em destaque
    lines.append(_format_price_line(deal))

    # 2) Economia — valor em negrito reforça o benefício
    if deal.get("original_price") and deal.get("price"):
        economia = deal["original_price"] - deal["price"]
        if economia > 0:
            eco = f"R$ {economia:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"Economize **{eco}** nessa compra")

    # 3) Variação de preço histórico (30 dias)
    lowest = deal.get("lowest_price_30d")
    current = deal.get("price")
    if lowest and current:
        lowest_fmt = f"R$ {lowest:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if current <= lowest * 1.02:  # dentro de 2% do mínimo = menor preço histórico
            lines.append(f"🏆 **Menor preço em 30 dias!**")
        elif current > lowest * 1.1:  # mais de 10% acima do mínimo = já esteve mais barato
            lines.append(f"📉 Já esteve mais barato: {lowest_fmt}")

    # 4) Tudo que o comprador precisa antes de clicar
    detalhes = []

    # Cupom (só códigos reais, não textos descritivos)
    if deal.get("coupon"):
        detalhes.append(f"🏷️ Cupom: `{deal['coupon']}`")

    # Parcelamento — verbo + condição deixa mais claro
    if deal.get("installments"):
        detalhes.append(f"💳 Parcele em {deal['installments']}")

    # Validade da oferta
    if deal.get("expiration"):
        detalhes.append(f"⏰ Oferta válida até {deal['expiration']}")

    # Tags: destaca Frete Grátis (decisivo pro comprador), descarta "Parcelado"
    # (já mostrado acima se disponível), exibe o resto como contexto
    tags = deal.get("tags") or []
    tag_names = [
        (t.get("name", "") if isinstance(t, dict) else str(t)).strip()
        for t in tags
    ]
    tag_names = [n for n in tag_names if n]
    has_frete_gratis = any("frete" in n.lower() and "grát" in n.lower() for n in tag_names)
    if has_frete_gratis:
        detalhes.append("✅ Frete grátis")
    # Demais tags relevantes (exceto "Parcelado" já tratado e "Frete Grátis" já tratado)
    outros = [n for n in tag_names if "frete" not in n.lower() and "parcelado" not in n.lower()]
    if outros:
        detalhes.append(" • ".join(outros[:2]))

    # Avaliação — mostra nota + número de pessoas, linguagem natural
    stars = deal.get("stars")
    sales = deal.get("sales_count")
    if stars and sales:
        stars_fmt = f"{stars:.1f}".replace(".", ",")
        detalhes.append(f"⭐ {stars_fmt} de 5 · {sales} compradores avaliaram")
    elif stars:
        stars_fmt = f"{stars:.1f}".replace(".", ",")
        detalhes.append(f"⭐ Nota {stars_fmt} de 5")

    if detalhes:
        lines.append("")
        lines.extend(detalhes)

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


PRICE_MONITORS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_monitors.json")


def _load_price_monitors() -> list:
    try:
        with open(PRICE_MONITORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _monitor_matches(keyword: str, title: str) -> bool:
    """True se todas as palavras do alerta estão no título (case-insensitive)."""
    kw_words = keyword.lower().split()
    title_l = title.lower()
    return all(w in title_l for w in kw_words)


async def _notify_price_alerts(deal: dict, msg) -> None:
    """Envia DM para usuários que têm alerta de preço matching com esta oferta."""
    monitors = _load_price_monitors()
    if not monitors:
        return
    title = deal.get("title", "")
    disc = deal.get("discount_pct", 0)
    store = deal.get("store", "")
    buy_url = _buy_url(deal)
    notified: set[int] = set()

    for m in monitors:
        user_id = m.get("user_id")
        keyword = m.get("keyword", "")
        if not user_id or not keyword:
            continue
        if user_id in notified:
            continue
        if not _monitor_matches(keyword, title):
            continue
        try:
            user = await bot.fetch_user(user_id)
            if not user:
                continue
            price_str = ""
            if deal.get("price"):
                price_str = f"R$ {deal['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            desc = f"🔔 **Alerta:** `{keyword}`\n\n**{title[:120]}**\n"
            if price_str:
                desc += f"💰 {price_str}"
                if disc:
                    desc += f" (-{disc:.0f}%)"
                desc += "\n"
            if store:
                desc += f"🏪 {store}\n"
            if buy_url:
                desc += f"\n[Ver oferta]({buy_url})"
            elif msg.jump_url:
                desc += f"\n[Ver no Discord]({msg.jump_url})"
            em = discord.Embed(description=desc, color=0xFF4500)
            em.set_footer(text="Use t$alerta list para gerenciar seus alertas")
            await user.send(embed=em)
            notified.add(user_id)
            log.info(f"  🔔 DM de alerta enviada para user {user_id} (keyword: {keyword})")
        except Exception as e:
            log.debug(f"  Falha ao enviar DM de alerta para {user_id}: {e}")


def _store_destination(deal: dict) -> Optional[str]:
    """Melhor destino DIRETO na loja (sem afiliado ainda):
    1) link de produto resolvido do Promobit; 2) busca na loja pelo nome."""
    if deal.get("product_url"):
        return deal["product_url"]
    return _store_search_url(deal.get("store", ""), deal.get("title", ""))


def _buy_url(deal: dict) -> str:
    """URL final de compra com afiliado, sempre apontando DIRETO para a loja.
    Ordem: produto direto → busca na loja → sem link (nunca cai no Promobit)."""
    store = deal.get("store", "")
    dest = _store_destination(deal)
    if dest and dest.startswith("http"):
        return affiliate_config.build_affiliate_url(store, dest)
    return ""


def _cor_embed(deal: dict) -> int:
    """Cor da barra do embed pela faixa de desconto: quanto maior o desconto,
    mais 'quente' a cor — sinaliza de relance o quão boa é a oferta."""
    disc = deal.get("discount_pct") or 0
    if disc >= DESCONTO_ULTRA_OFERTA:
        return COR_DESCONTO_ULTRA
    if disc >= 30:
        return COR_DESCONTO_OTIMA
    if disc >= 20:
        return COR_DESCONTO_BOA
    return COR_OFERTA


def _build_view(deal: dict) -> Optional[discord.ui.View]:
    """Botão de compra real do Discord (link). Retorna None se não houver URL válida
    — nesse caso o embed cai no campo de texto de fallback.
    Obs.: o Discord renderiza botões de link sempre em cinza (não dá para colorir);
    o destaque vem do texto (desconto) + da CTA em destaque no corpo do embed."""
    buy_url = _buy_url(deal)
    if not buy_url.startswith("http"):
        return None
    disc = deal.get("discount_pct") or 0
    label = f"COMPRAR COM {disc:.0f}% OFF" if disc else "COMPRAR COM DESCONTO"
    view = discord.ui.View(timeout=None)  # link buttons não disparam interação
    view.add_item(discord.ui.Button(
        label=label[:80],
        emoji="🛒",
        style=discord.ButtonStyle.link,
        url=buy_url,
    ))
    return view


def _build_embed(deal: dict) -> discord.Embed:
    """Constrói o embed da oferta."""
    discount = deal.get("discount_pct", 0)
    cor = _cor_embed(deal)

    # Título: emoji + nome completo do produto (desconto já aparece na descrição)
    title = f"{EMOJI_FOGO} {deal['title'][:200]}"

    desc = _format_description(deal)
    # URL unificada para título e botão (evita inconsistência)
    buy_url = _buy_url(deal)

    # CTA em DESTAQUE dentro do corpo: heading clicável (grande e em negrito).
    # Reforça o botão (que o Discord só renderiza em cinza) com alta visibilidade.
    if buy_url.startswith("http"):
        cta_txt = f"COMPRAR COM {discount:.0f}% OFF" if discount else "COMPRAR COM DESCONTO"
        desc += f"\n\n## [{cta_txt}]({buy_url})"

    if len(desc) > 4096:
        desc = desc[:4093] + "..."

    embed = discord.Embed(
        title=title[:256],
        url=buy_url if buy_url.startswith("http") else None,
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
    # CTA: normalmente vira um BOTÃO real (ver _build_view, anexado no envio).
    # Só usamos campo de texto como fallback quando não há URL utilizável.
    if not buy_url.startswith("http"):
        embed.add_field(
            name="",
            value="👉 **Confira a oferta na loja**",
            inline=False,
        )

    # Footer sutil — preço pode mudar a qualquer momento
    embed.set_footer(text="Preço sujeito a alterações")

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

    # Resetar dedup intraday se virou o dia
    global _posted_title_keys, _posted_title_keys_date
    hoje_br = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
    if hoje_br != _posted_title_keys_date:
        _posted_title_keys = set()
        _posted_title_keys_date = hoje_br

    # Dedup por URL (histórico 7 dias) + intraday por produto (mesmo produto, preço diferente)
    candidates = []
    for deal in all_deals:
        if _is_duplicate(history, deal["url"]):
            continue
        key = _title_key(deal["title"])
        if key and key in _posted_title_keys:
            log.debug(f"  Dedup intraday (produto similar já postado): {deal['title'][:60]}")
            continue
        candidates.append(deal)

    log.info(f"Após dedup: {len(candidates)} candidatas")

    # Triagem barata (sem rede) ANTES de enriquecer: descarta lojas já conhecidas
    # que estão fora da whitelist, para não gastar o orçamento de enriquecimento com
    # ofertas que seriam rejeitadas de qualquer jeito. Mantém lojas da whitelist e as
    # de loja ainda desconhecida (que só é revelada no enriquecimento).
    pre_candidates = []
    descartadas_loja = 0
    for deal in candidates:
        store = deal.get("store") or ""
        if store and not _store_allowed(store):
            descartadas_loja += 1
            continue
        pre_candidates.append(deal)
    # Prioriza quem já tem loja da whitelist confirmada (garante vaga dentro do limite)
    pre_candidates.sort(key=lambda d: 0 if (d.get("store") and _store_allowed(d.get("store", ""))) else 1)
    log.info(
        f"Triagem de loja: {len(pre_candidates)} a enriquecer "
        f"({descartadas_loja} descartadas por whitelist antes de enriquecer)"
    )

    # Enriquecer cada oferta (buscar detalhes)
    enriched = []
    for deal in pre_candidates[:20]:  # Limitar para não abusar
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
    rejeicoes: dict[str, int] = {}
    for deal in enriched:
        passed, reason = _passes_filters(deal)
        if passed:
            approved.append(deal)
        else:
            # Agrupa motivos trocando números por "N" (ex: "estrelas 3.8 < 4.2" → "estrelas N < N")
            bucket = re.sub(r"\d+([.,]\d+)?", "N", reason)
            rejeicoes[bucket] = rejeicoes.get(bucket, 0) + 1
            log.debug(f"  Rejeitada: {deal['title'][:50]} — {reason}")

    log.info(f"Após filtros: {len(approved)} aprovadas")
    # Diagnóstico: resumo dos motivos de rejeição (visível mesmo com LOG_LEVEL=INFO)
    if rejeicoes:
        resumo = " · ".join(
            f"{n}× {motivo}" for motivo, n in sorted(rejeicoes.items(), key=lambda x: -x[1])
        )
        log.info(f"Motivos de rejeição ({sum(rejeicoes.values())}): {resumo}")

    # Ordenar: prioridade de categoria (peças > periféricos > outros) e depois score composto
    approved.sort(
        key=lambda d: (
            _CATEGORY_PRIORITY.get(d.get("category", ""), 99),
            -_deal_score(d),
        )
    )
    # Variar lojas: evitar back-to-back da mesma loja
    approved = _interleave_by_store(approved)

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
            global _mention_count_ofertas, _mention_date_ofertas
            content = None
            guild = getattr(channel, "guild", None)
            # Menciona o cargo apenas nas 3 primeiras ofertas do dia
            hoje_br = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
            if hoje_br != _mention_date_ofertas:
                _mention_date_ofertas = hoje_br
                _mention_count_ofertas = 0
            cargo_id = ID_CARGO_ULTRA or ID_CARGO_OFERTAS
            if cargo_id and _mention_count_ofertas < 3 and guild and guild.get_role(cargo_id):
                content = f"<@&{cargo_id}>"
                _mention_count_ofertas += 1

            view = _build_view(deal)
            if view is not None:
                msg = await channel.send(content=content, embed=embed, file=file, view=view)
            else:
                msg = await channel.send(content=content, embed=embed, file=file)

            # Marcar como postado DEPOIS de enviar com sucesso
            _mark_posted(history, deal["url"], deal["title"])
            _posted_title_keys.add(_title_key(deal["title"]))

            # Notificar usuários com alerta de preço matching
            await _notify_price_alerts(deal, msg)

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
    log.info("Bot de ofertas pronto. Primeiro ciclo será executado imediatamente pelo loop.")


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
