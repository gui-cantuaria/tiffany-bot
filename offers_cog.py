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
# CONFIGURATION
# =========================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CANAL_OFERTAS_ID = int(os.getenv("CANAL_OFERTAS_ID", "1512902840908124281"))
ID_CARGO_OFERTAS = int(os.getenv("ID_CARGO_OFERTAS", "0"))  # legacy: ping on EVERY offer (0 = disabled)
# Role ping ONLY on "ultra deals" (high discount). Default = server offers role.
ID_CARGO_ULTRA = int(os.getenv("ID_CARGO_OFERTAS_ULTRA", "1386386059390357575"))
DESCONTO_ULTRA_OFERTA = int(os.getenv("DESCONTO_ULTRA_OFERTA", "60"))  # minimum % to qualify as "ultra deal"
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

HORA_INICIO = 8
HORA_FIM = 18
FUSO_HORARIO_BR = timezone(timedelta(hours=-3))

# --- Pipeline ---
SCAN_INTERVAL_MIN = 30  # deal cycle every 30 min
POST_SPACING_SEC = 180  # 3 min between posts
MAX_POSTS_POR_CICLO = 5
DESCONTO_MINIMO = 15  # minimum discount percentage
NOTA_MINIMA_ESTRELAS = 4.4
VENDAS_MINIMAS = 30
AVALIACOES_MINIMAS = 5  # minimum user reviews (same field as sales_count)
# Promobit rarely provides stars/sales. To avoid zero offers, accept
# whitelisted trusted stores WITHOUT metrics when discount is strong enough.
DESCONTO_SEM_METRICA = 25  # minimum discount when no stars or sales data

HISTORY_FILE = "offers_history.json"

# --- Promobit ---
PROMOBIT_BASE = "https://www.promobit.com.br"
CATEGORIAS_PROMOBIT = [
    # === PC parts (scrape first — enrichment budget favors these) ===
    "/promocoes/placa-video/s/",  # slug changed on Promobit (placa-de-video → 404)
    "/promocoes/memoria-ram/s/",
    "/promocoes/processador/s/",
    "/promocoes/placa-mae/s/",
    "/promocoes/gabinete/s/",
    # SSD/pasta térmica/fonte often appear here — filtered by title to parts only
    "/promocoes/hardware-perifericos/s/",
    # === Full systems (low cap per cycle) ===
    "/promocoes/pc-gamer/s/",
    "/promocoes/notebooks/s/",
    "/promocoes/notebook-gamer/s/",
    "/promocoes/monitor/s/",
    "/promocoes/roteador-e-repetidor/s/",
    # Peripherals — low cap per cycle (variety without dominating the feed)
    "/promocoes/mouse/s/",
    "/promocoes/teclado/s/",
    "/promocoes/headset/s/",
    # Removed (404 on Promobit since Jun/2026): ssd, pasta-termica, mousepad, etc.
]

# Full whitelist (for when all affiliate programs are active)
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

# Active whitelist: only stores with configured affiliate links
# Active affiliates: Terabyte/ShopInfo (Lomadee), Amazon, Mercado Livre, Shopee, AliExpress
# Add KaBuM when Awin approves
LOJAS_WHITELIST = {
    "terabyte", "terabyteshop", "terabyte shop",
    "shopinfo", "shopinfo.com.br",
    "amazon", "amazon.com.br",
    "mercado livre", "mercadolivre",
    "shopee",
    "aliexpress",
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
_bot = None
http_session: Optional[aiohttp.ClientSession] = None
# Daily role mention counter (max 3 per day)
_mention_count_ofertas: int = 0
_mention_date_ofertas: str = ""
# Intraday dedup: same product at different prices should not repeat within the day
_posted_title_keys: set = set()
_posted_title_keys_date: str = ""
_posted_cat_counts: dict[str, int] = {}
_posted_cat_counts_date: str = ""

# =========================
# COLORS AND EMOJIS
# =========================
TIFFANY_PINK = 0xFF69B4
COR_OFERTA = TIFFANY_PINK          # default color (store without brand color)
COR_OFERTA_ALTA = TIFFANY_PINK     # kept for compatibility
# Embed bar color by discount tier — signals how good the deal is.
# Higher discount = "hotter" color.
COR_DESCONTO_ULTRA = 0xFF4500   # >= DESCONTO_ULTRA_OFERTA (default 40%): fire red
COR_DESCONTO_OTIMA = 0xFF8C00   # 30-39%: orange
COR_DESCONTO_BOA = 0xFFD700     # 20-29%: gold
# < 20% falls back to COR_OFERTA (Tiffany pink)
EMOJI_FOGO = "🔥"

CATEGORIAS_EMOJI = {
    "Hardware e periféricos": "🖥️",
    "Informática": "💻",
    "Notebook": "💻",
    "Monitor": "🖥️",
    "Processador": "⚡",
    "Placa de Vídeo": "🚀",
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
    "Gabinete": "🖥️",
    "Hardware PC": "🔧",
    "Pasta Térmica": "🌡️",
    "Fonte": "⚡",
    "Cooler": "❄️",
    "Tablet": "📱",
    "Celular": "📱",
    "TV": "📺",
    "Suporte e Acessórios": "🖥️",
}

# Maps URL slugs to display category names (PT-BR, user-facing)
_SLUG_TO_CATEGORY = {
    "hardware-perifericos": "Hardware e periféricos",
    "notebooks": "Notebook",
    "notebook-gamer": "Notebook",
    "monitor": "Monitor",
    "processador": "Processador",
    "placa-mae": "Placa-mãe",
    "placa-de-video": "Placa de Vídeo",  # legacy slug
    "placa-video": "Placa de Vídeo",
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

# Category priority for sorting (lower = higher priority)
_CATEGORY_PRIORITY = {
    "Processador": 1,
    "Placa de Vídeo": 1,
    "Memória RAM": 1,
    "Placa-mãe": 1,
    "SSD": 1,
    "Gabinete": 1,
    "Pasta Térmica": 1,
    "Fonte": 1,
    "Cooler": 1,
    "Hardware PC": 1,
    "Teclado": 6,
    "Mouse": 6,
    "Headset": 6,
    "Mousepad": 6,
    "Webcam": 6,
    "Mesa digitalizadora": 6,
    "Hardware e periféricos": 6,
    "Monitor": 4,
    "PC Gamer": 4,
    "Notebook": 4,
    "Suporte e Acessórios": 7,
    "TV": 7,
    "Tablet": 7,
    "Celular": 7,
    "Adaptadores e rede": 5,
}

# PC parts we want to surface more often (GPU/RAM were under-represented).
_PARTS_CATEGORIES = frozenset({
    "Processador", "Placa de Vídeo", "Memória RAM", "Placa-mãe", "SSD",
    "Gabinete", "Pasta Térmica", "Fonte", "Cooler", "Hardware PC",
})
_PERIPHERAL_CATEGORIES = frozenset({
    "Teclado", "Mouse", "Headset", "Webcam", "Mousepad",
    "Mesa digitalizadora", "Suporte e Acessórios",
})
# Title hints for SSD/fonte/cooler inside /hardware-perifericos/
_PARTS_TITLE_KEYWORDS = (
    "ssd", "nvme", "m.2", "m2 ", "sata iii", "hd interno",
    "memoria ram", "memória ram", "ddr4", "ddr5",
    "processador", "ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra",
    "placa de video", "placa de vídeo", "geforce", "radeon", "rtx ", "rx ", "arc a",
    "placa mae", "placa-mãe", "placa mãe", "chipset", "b650", "b550", "x670", "z790",
    "fonte ", "fonte atx", "80 plus", "psu ",
    "cooler", "water cooler", "watercooler", "pasta termica", "pasta térmica",
    "dissipador", "ventoinha", "gabinete",
)
_PERIPHERAL_TITLE_KEYWORDS = (
    "teclado", "mouse", "headset", "fone de ouvido", "fone gamer", "webcam",
    "mousepad", "pad mouse", "suporte monitor", "braco articulado", "braço articulado",
    "hub usb", "cabo hdmi", "cabo displayport", "cabo usb", "adaptador usb",
    "carregador", "capa ", "pelicula", "película", "gamer chair", "cadeira gamer",
)
_PARTS_RESERVE_CATEGORIES = (
    "Placa de Vídeo",
    "Memória RAM",
    "Processador",
    "Placa-mãe",
    "SSD",
    "Gabinete",
)
_ENRICH_CAP = 40
_ENRICH_PARTS_CAP = 22
# Max posts per category per cycle — cap heavy PC parts to 1 for variety.
_PER_CAT_POST_LIMIT: dict[str, int] = {
    "Placa de Vídeo": 1,
    "Memória RAM": 1,
    "Processador": 1,
    "Placa-mãe": 1,
    "SSD": 1,
    "Gabinete": 1,
    "Pasta Térmica": 1,
    "Fonte": 1,
    "Cooler": 1,
    "Hardware PC": 1,
    "Monitor": 1,
    "Notebook": 1,
    "PC Gamer": 1,
    "Adaptadores e rede": 1,
    "Teclado": 1,
    "Mouse": 1,
    "Headset": 1,
    "Webcam": 0,
    "Mousepad": 0,
    "Mesa digitalizadora": 0,
    "Hardware e periféricos": 0,
    "Suporte e Acessórios": 0,
    "TV": 0,
    "Tablet": 0,
    "Celular": 0,
}

# Network category (adapters/routers): Promobit has no dedicated "network adapter"
# category, so we use "roteador-e-repetidor" (groups those items) with stricter
# filters than the general rules (user request): 4.5+ rating, 100+ sales, 40%+ discount.
# No "no metrics" exception — if Promobit lacks stars/sales, network items are skipped.
CAT_REDE_NOME = "Adaptadores e rede"
REDE_NOTA_MINIMA = 4.5
REDE_VENDAS_MINIMAS = 100
REDE_DESCONTO_MINIMO = 40
# Keywords that identify a network adapter even in another category
# (e.g. a USB Wi-Fi adapter listed under hardware-perifericos).
REDE_KEYWORDS = (
    "adaptador de rede", "adaptador wireless", "adaptador wi-fi", "adaptador wifi",
    "adaptador usb wi", "adaptador usb wireless", "placa de rede", "receptor wifi",
    "receptor wi-fi", "antena wifi", "antena wi-fi", "nano usb wireless",
)

# =========================
# HISTORY / DEDUP
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
        log.exception("Failed to save offers history")
        try:
            os.remove(tmp)
        except OSError:
            pass


def _deal_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _listing_key(url: str) -> str:
    """Stable store listing ID (MLB…, ASIN…) — dedup same product with different Promobit URLs."""
    if not url:
        return ""
    u = url.lower().split("?")[0].split("#")[0]
    m = re.search(r"mercadolivre\.com\.br/(?:[^/]+/)*p/(mlb\d+)", u)
    if m:
        return f"ml:{m.group(1)}"
    m = re.search(r"mercadolivre\.com\.br/(mlb\d+)", u)
    if m:
        return f"ml:{m.group(1)}"
    m = re.search(r"amazon\.[^/]+/(?:.*/)?(?:dp|gp/product)/([a-z0-9]{10})", u)
    if m:
        return f"amz:{m.group(1)}"
    m = re.search(r"shopee\.com\.br/[^?#]*-i\.(\d+\.\d+)", u)
    if m:
        return f"shopee:{m.group(1)}"
    try:
        p = urlparse(u)
        path = re.sub(r"/+$", "", p.path or "")
        if p.netloc and len(path) > 8:
            return f"{p.netloc}{path}"[:120]
    except Exception:
        pass
    return ""


def _deal_listing_key(deal: dict) -> str:
    for raw in (deal.get("real_store_url"), deal.get("product_url"), deal.get("url")):
        key = _listing_key(raw or "")
        if key:
            return key
    return ""


def _is_duplicate(history: dict, url: str) -> bool:
    h = _deal_hash(url)
    return h in history.get("deals", {})


def _is_title_key_in_history(history: dict, key: str) -> bool:
    """Check whether a title_key already exists in persistent history (14 days)."""
    if not key:
        return False
    for v in history.get("deals", {}).values():
        if isinstance(v, dict) and v.get("tkey") == key:
            return True
    return False


def _is_listing_in_history(history: dict, listing: str) -> bool:
    if not listing:
        return False
    for v in history.get("deals", {}).values():
        if isinstance(v, dict) and v.get("listing") == listing:
            return True
    return False


def _mark_posted(history: dict, url: str, title: str, orig_tkey: str = "", listing: str = "") -> None:
    h = _deal_hash(url)
    entry = {
        "url": url,
        "title": title[:100],
        "ts": time.time(),
    }
    # Use ORIGINAL title key (pre-enrichment) so cross-cycle dedup works
    key = orig_tkey or _title_key(title)
    if key:
        entry["tkey"] = key
    if listing:
        entry["listing"] = listing
    history.setdefault("deals", {})[h] = entry
    _save_history(history)


def _clean_history(history: dict) -> None:
    """Remove entries older than 14 days."""
    cutoff = time.time() - (14 * 24 * 3600)
    deals = history.get("deals", {})
    to_remove = [k for k, v in deals.items() if v.get("ts", 0) < cutoff]
    for k in to_remove:
        del deals[k]
    if to_remove:
        log.info(f"Cleanup: {len(to_remove)} old offers removed from history.")
        _save_history(history)


# Generic category words that do not identify a specific product
_TITLE_GENERIC = frozenset({
    "notebook", "teclado", "mouse", "headset", "monitor", "processador",
    "memoria", "placa", "ssd", "webcam", "laptop", "desktop", "gamer",
    "gaming", "mecanico", "sem", "fio", "com", "para", "rgb", "led",
    "preto", "branco", "prata", "cinza", "compacto", "gamer",
})


import html as html_module

# Regex to extract model/SKU codes
_MODEL_RE = re.compile(
    r'\b(?:'
    r'[A-Za-z]{1,4}\d{2,}[A-Za-z0-9\-]*'  # B450M, RTX4050, H61M2-V2, 24MS500-B
    r'|[A-Za-z]\d+[A-Za-z]\d*'              # i7, M7, H510
    r')\b'
)
_RYZEN_RE = re.compile(r"ryzen\s*(?:\d\s+)?(\d{4}x?)\b", re.I)
_INTEL_CPU_RE = re.compile(
    r"core\s*(?:ultra\s*)?(i[3579])(?:[\s\-]*(\d{4,5}[a-z]?))?\b", re.I
)
_RTX_RE = re.compile(r"(?:geforce\s*)?(?:rtx|gtx)\s*(\d{4,5}(?:\s*(?:ti|super))?)\b", re.I)
_RX_RE = re.compile(r"(?:radeon\s*)?(?:rx)\s*(\d{4}(?:\s*xt)?)\b", re.I)
_DDR_GB_RE = re.compile(r"(\d+)\s*gb\b", re.I)
_CHIPSET_RE = re.compile(r"\b([abxzh]\d{3,4}[a-z]?(?:m)?(?:[\-_][a-z0-9]+)?)\b", re.I)
_NOTEBOOK_LINE_RE = re.compile(
    r"\b(galaxy\s*book\s*\d+|vivobook\s*\d+|tuf\s*gaming\s*f\d+|ideapad\s*\w+|"
    r"nitro\s*\d+|legion\s*\w+|pavilion\s*\d+)\b",
    re.I,
)


def _norm_title_text(title: str) -> str:
    t = unicodedata.normalize("NFD", title.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _product_fingerprint(title: str) -> str:
    """Stable product identity across Promobit title variants (same SKU, new price)."""
    raw = title or ""
    t = _norm_title_text(raw)
    if not t:
        return ""

    parts: list[str] = []

    m = _RTX_RE.search(raw) or _RX_RE.search(raw)
    if m:
        gpu = re.sub(r"\s+", "", m.group(1).lower())
        parts.append(f"gpu:{gpu}")

    m = _RYZEN_RE.search(raw)
    if m:
        parts.append(f"cpu:ryzen{m.group(1).lower()}")
    else:
        m = _INTEL_CPU_RE.search(raw)
        if m:
            suffix = (m.group(2) or m.group(1)).lower().replace(" ", "")
            parts.append(f"cpu:intel{suffix}")

    if any(k in t for k in ("memoria ram", "memória ram", "ddr4", "ddr5", "vengeance", "fury beast")):
        ddr = "ddr5" if "ddr5" in t else "ddr4" if "ddr4" in t else "ram"
        size_m = _DDR_GB_RE.search(raw)
        size = size_m.group(1) if size_m else "?"
        if "vengeance" in t:
            parts.append(f"ram:vengeance-{size}gb-{ddr}")
        else:
            words = [w for w in t.split() if w not in _TITLE_GENERIC and len(w) >= 2]
            brand = words[0] if words else "ram"
            parts.append(f"ram:{brand}-{size}gb-{ddr}")

    if any(k in t for k in ("placa mae", "placa-mãe", "placa mãe", "chipset", "motherboard")):
        for tok in _CHIPSET_RE.findall(raw):
            tok_l = tok.lower()
            if len(tok_l) >= 4 and tok_l[0] in "abxzh" and tok_l[1].isdigit():
                parts.append(f"mobo:{tok_l}")
                break

    if "gabinete" in t or "wideload" in t:
        models = [m.lower() for m in _MODEL_RE.findall(raw) if len(m) >= 4]
        if models:
            parts.append(f"case:{models[0]}")
        elif "wideload" in t:
            parts.append("case:redragon-wideload")

    if "monitor" in t:
        models = sorted({m.lower() for m in _MODEL_RE.findall(raw) if len(m) >= 4})
        if models:
            parts.append(f"mon:{models[0]}")

    m = _NOTEBOOK_LINE_RE.search(raw)
    if m:
        slug = re.sub(r"\s+", "-", m.group(1).lower())
        parts.append(f"nb:{slug}")

    return " ".join(parts)


def _title_key(title: str) -> str:
    """Build a product key for intraday and cross-day dedup."""
    fp = _product_fingerprint(title)
    if fp:
        return fp

    t = _norm_title_text(title)
    models = sorted(set(m.lower() for m in _MODEL_RE.findall(title)))
    words = [w for w in t.split() if len(w) >= 2 and w not in _TITLE_GENERIC]
    brand = words[0] if words else ""

    if models:
        core = sorted(set(([brand] if brand else []) + models))
        return " ".join(core)

    return " ".join(sorted(set(words[:5])))

def _sanitize_title(title: str) -> str:
    """Strip HTML entities and escapes from the title."""
    t = html_module.unescape(title)
    t = t.replace('\\"', '"')
    # Collapse duplicate spaces
    t = re.sub(r'\s+', ' ', t).strip()
    # Remove consecutive duplicate word (MOUSE MOUSE → MOUSE)
    t = re.sub(r'\b(\w+)\s+\1\b', r'\1', t, flags=re.IGNORECASE)
    return t


def _is_valid_coupon(code: str) -> bool:
    """Return True if the text looks like a real coupon code.
    Real coupons: alphanumeric, no spaces, 3-25 characters.
    Rejects descriptive text like '200 off abaixo do preço'."""
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
                log.warning(f"HTTP {resp.status} fetching {url}")
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            log.error(f"Failed to fetch {url}: {e}")
    return None


def _parse_deals_from_html(html: str, category_url: str) -> list[dict]:
    """Extract deals from a Promobit category page using JSON-LD and HTML."""
    soup = BeautifulSoup(html, "html.parser")
    deals = []

    # Try JSON-LD extraction (Schema.org Product data)
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

    # Fallback: parse HTML cards if JSON-LD returned nothing
    if not deals:
        deals = _parse_deals_from_cards(soup)

    return deals


def _extract_from_jsonld(product: dict) -> Optional[dict]:
    """Extract deal data from a Promobit JSON-LD product entry."""
    title = product.get("name", "").strip()
    image = product.get("image", "")

    if isinstance(image, list):
        image = image[0] if image else ""

    # offers may be a list or dict
    offers_raw = product.get("offers", [])
    if isinstance(offers_raw, list):
        offer = offers_raw[0] if offers_raw else {}
    elif isinstance(offers_raw, dict):
        # AggregateOffer with sub-offers
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

    # Use higher resolution (600px) instead of thumbnail (120/268px)
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
    """Fallback: parse Promobit HTML deal cards."""
    deals = []
    # Promobit uses article or div with offer data
    cards = soup.select("article, [data-offer-id], .promotionCard, .offer-card")
    for card in cards:
        try:
            # Title
            title_el = card.select_one("h2, h3, .offer-title, [class*='title']")
            title = title_el.get_text(strip=True) if title_el else ""

            # Link
            link_el = card.select_one("a[href*='/oferta/']")
            url = ""
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else urljoin(PROMOBIT_BASE, href)

            # Image
            img_el = card.select_one("img[src*='promobit'], img[data-src*='promobit']")
            image = ""
            if img_el:
                image = img_el.get("src") or img_el.get("data-src") or ""

            # Price
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
    """Convert Brazilian price text to float."""
    if not text:
        return None
    # Strip R$, spaces, thousands separators; swap comma for dot
    cleaned = re.sub(r"[R$\s]", "", text)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


async def _enrich_deal(session: aiohttp.ClientSession, deal: dict) -> dict:
    """Fetch the individual Promobit deal page and extract serverOffer (Next.js JSON)."""
    url = deal.get("url")
    if not url:
        return deal
    html = await _fetch_page(session, url)
    if not html:
        return deal

    soup = BeautifulSoup(html, "html.parser")

    # Promobit uses Next.js — full data lives in an inline JSON <script>
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

    # Status — reject expired/closed offers before any further processing
    status = str(server_offer.get("offerStatus") or server_offer.get("status") or "").lower()
    if status in ("expired", "expirada", "encerrada", "inactive", "unavailable", "sold_out"):
        deal["expired"] = True
        return deal

    # Store
    if server_offer.get("storeName"):
        deal["store"] = server_offer["storeName"]

    # Original price
    old_price = server_offer.get("offerOldPrice")
    try:
        if old_price and float(old_price) > 0:
            deal["original_price"] = float(old_price)
    except (ValueError, TypeError):
        pass

    # Current price (may differ from listing)
    cur_price = server_offer.get("offerPrice")
    try:
        if cur_price:
            deal["price"] = float(cur_price)
    except (ValueError, TypeError):
        pass

    # Discount — ALWAYS recalculate from real prices (original vs current)
    # for accuracy. Promobit's offerDiscontPercentage may be stale or wrong,
    # so it is only used as a last fallback.
    try:
        if deal.get("original_price") and deal.get("price") and deal["original_price"] > deal["price"]:
            deal["discount_pct"] = round((1 - deal["price"] / deal["original_price"]) * 100, 1)
        else:
            disc = server_offer.get("offerDiscontPercentage")
            if disc:
                deal["discount_pct"] = float(disc)
    except (ValueError, TypeError):
        pass

    # 30-day historical low — Promobit exposes this on some products
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

    # Coupon (may come as string, dict, or list)
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

    # Image (higher resolution)
    photo = server_offer.get("offerPhoto")
    if photo:
        if photo.startswith("/"):
            deal["image"] = f"https://i.promobit.com.br/600{photo}"
        elif photo.startswith("http"):
            deal["image"] = photo

    # Buy link: canonical Promobit deal page (always 200).
    # The old /redirect/oferta/{slug}/ was discontinued (404) and the real
    # "Go to store" button is JS-generated — unreachable server-side. Sending
    # users to the deal page guarantees a valid link (coupon + store button).
    offer_slug = server_offer.get("offerSlug", "")
    if offer_slug:
        deal["store_url"] = f"{PROMOBIT_BASE}/oferta/{offer_slug}/"

    # Promobit community product rating
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

    # Tags (e.g. Frete Grátis)
    tags = server_offer.get("offerTags") or []
    deal["tags"] = tags

    # Installments (best effort — Promobit keys vary; only show when present).
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
                interest_free = server_offer.get("offerInstallmentInterestFree") \
                    or server_offer.get("offerInterestFree")
                deal["installments"] = f"{n}x de {v_str}{' sem juros' if interest_free else ''}"
    except (ValueError, TypeError):
        pass

    # DIRECT store link: Promobit sometimes exposes the product URL (aliasUrl).
    # When present, resolve to the final store (to send the user straight to
    # the store with affiliate tracking). Coupon-only deals lack this — fall back to search.
    alias = server_offer.get("aliasUrl")
    if isinstance(alias, str) and alias.startswith("http"):
        await _resolve_product_url(session, deal, alias)

    # Buyer-oriented clean title — strips technical spec dumps
    deal["title"] = await _ai_clean_title(session, _sanitize_title(deal["title"]), deal.get("category", ""))

    return deal


_TITLE_SPECS_BY_CATEGORY = {
    "Memória RAM":
        "brand + line (e.g. Kingston Fury Beast) | type (DDR4/DDR5) • total capacity (e.g. 16GB) • kit (e.g. 2x8GB) • frequency (e.g. 3200MHz) • latency (e.g. CL16) • form factor (DIMM/SO-DIMM)",
    "Placa de Vídeo":
        "brand + line + full model (e.g. NVIDIA GeForce RTX 4070 Super / AMD Radeon RX 7800 XT) | VRAM (e.g. 12GB GDDR6X) • boost clock (e.g. 2505MHz) • TDP (e.g. 200W) • size (e.g. Dual/Triple fan) • OC version if any",
    "SSD":
        "brand + model | capacity (e.g. 512GB) • interface (SATA / M.2 NVMe / PCIe Gen4) • read speed (e.g. 3500MB/s) • write speed if available",
    "Processador":
        "brand + full model (e.g. Ryzen 5 5600X) | socket (AM4/AM5/LGA1700) • cores/threads (e.g. 6C/12T) • base/boost freq (e.g. 3.7/4.6GHz) • TDP if available",
    "Placa-mãe":
        "brand + model | socket (e.g. AM5/LGA1700) • chipset (e.g. B650/Z790) • form factor (ATX/mATX/ITX) • RAM slots • M.2 slots if available",
    "Monitor":
        "brand + model | size (e.g. 27'') • resolution (e.g. Full HD 1920×1080 / QHD / 4K) • panel (IPS/VA/TN) • refresh (e.g. 144Hz) • response (e.g. 1ms) • curved/flat • ports (e.g. HDMI+DP) • sync (FreeSync/G-Sync) if available",
    "Teclado":
        "brand + model | type (Mechanical/Membrane/Silicone) • layout (60%/TKL/100%/ABNT2/US) • switch (e.g. Red/Blue/Brown) if mechanical • connectivity (USB/Wireless/Bluetooth) • backlight (RGB/White/None)",
    "Mouse":
        "brand + model | max DPI (e.g. 25600 DPI) • sensor (optical/laser) • connectivity (USB/Wireless/Bluetooth) • programmable buttons • weight if available",
    "Headset":
        "brand + model | connectivity (USB/3.5mm P2/Wireless/Bluetooth) • type (Over-ear/On-ear/In-ear) • drivers (e.g. 50mm) • mic (removable/integrated/none) • impedance if available",
    "Webcam":
        "brand + model | resolution (e.g. 1080p/4K) • FPS (e.g. 30fps/60fps) • autofocus (yes/no) • field of view (e.g. 90°) • connection (USB-A/USB-C)",
    "Notebook":
        "brand + model | CPU (e.g. Core i5-1335U / Ryzen 7 5825U) • RAM (e.g. 16GB DDR5) • storage (e.g. 512GB SSD NVMe) • screen (e.g. 15.6'' IPS FHD 144Hz) • GPU (e.g. RTX 4060 / integrated) • OS (Win 11/Linux) • weight if available",
    "PC Gamer":
        "CPU (e.g. Ryzen 5 5600) • GPU (e.g. RTX 4060) • RAM (e.g. 16GB DDR4) • storage (e.g. 512GB NVMe) • OS (Win 11/Linux)",
    "Mesa digitalizadora":
        "brand + model | active area (e.g. A5 152×95mm) • pen pressure (e.g. 8192 levels) • resolution (LPI) • connectivity (USB/Bluetooth) • compatibility (Windows/Mac/Android)",
    "Adaptadores e rede":
        "brand + model | type (Router/Repeater/USB Adapter) • standard (e.g. Wi-Fi 6 AX3000) • bands (Dual-band/Tri-band) • speed (e.g. 2400+600Mbps) • ports (e.g. 4x Gigabit)",
    "Gabinete":
        "brand + model | tower type (Full Tower/Mid Tower/Mini Tower/Mini ITX) • supported form factor (ATX/mATX/ITX) • side panel (tempered glass/acrylic/none) • cable management (yes/no) • color",
    "Fonte":
        "brand + model | wattage (e.g. 650W) • certification (80 Plus Bronze/Gold/Platinum) • modular (full/semi/no) • form factor (ATX/SFX)",
    "Cooler":
        "brand + model | type (air/AIO liquid) • socket support (AM4/AM5/LGA1700) • fan size (e.g. 120mm) • TDP rating if available",
    "Hardware PC":
        "brand + model | main specs (capacity, speed, socket, interface) separated by spaces",
}

_TITLE_SPECS_DEFAULT = (
    "brand + model | main technical specs separated by • "
    "(capacity, speed, connectivity, dimensions — whatever is relevant)"
)


async def _ai_clean_title(session: aiohttp.ClientSession, title: str, category: str) -> str:
    """Rewrite long titles into 'Brand Model | spec • spec • spec' format.
    Only runs for titles >70 chars. Cost: ~80 tokens/call."""
    if len(title) <= 70:
        return title
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return title

    specs_guide = _TITLE_SPECS_BY_CATEGORY.get(category, _TITLE_SPECS_DEFAULT)
    prompt = (
        f"Product: {title}\n"
        f"Category: {category}\n\n"
        "Rewrite as a technical deal title in Brazilian Portuguese (max 120 characters).\n"
        "Required format: Brand Model followed by specs separated ONLY by spaces.\n"
        "Monitor example: Samsung Odyssey G5 27 QHD 2560x1440 165Hz 1ms VA HDMI DisplayPort FreeSync\n"
        "RAM example: Kingston Fury Beast DDR4 16GB 2x8GB 3200MHz CL16 DIMM\n"
        "Notebook example: ASUS Vivobook S14 Core Ultra 7 16GB DDR5 512GB NVMe 14 IPS FHD Linux\n"
        f"Specs to include for this category: {specs_guide}\n"
        "Rules:\n"
        "- Use ONLY specs present in the original title\n"
        "- No periods, commas, slashes, dashes, or any separator symbols — spaces only\n"
        "- No descriptions, adjectives, or phrases (e.g. no 'ideal for', 'excellent', 'perfect')\n"
        "- Keep technical units attached to values (e.g. 512GB 3200MHz 144Hz 1ms)\n"
        "- Reply with ONLY the title, no quotes or explanations"
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
                    log.debug(f"AI title: {title[:50]}... → {cleaned}")
                    return cleaned
    except Exception as e:
        log.debug(f"AI title cleanup failed ({e}), keeping original")
    return title


# Recognized store domains (to validate whether a link points to the real store)
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
    """Resolve a Promobit product URL (aliasUrl) to the final store page.
    If already a store link, use directly; if a redirect (promoby.me/promobit),
    follow to the store. Result stored in deal['product_url']."""
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
        log.debug(f"Failed to resolve product_url from {alias[:60]}: {e}")


def _store_search_url(store: str, title: str) -> Optional[str]:
    """Build a direct store search URL (fallback when no product link exists).
    Ensures the user goes DIRECTLY to the store, never to Promobit."""
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
    """Attempt (B): fetch stars/sales directly from the store page. Best effort."""
    store_url = deal.get("store_url")
    if not store_url:
        return deal

    try:
        # Follow Promobit redirect to the real store
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
            # Capture real store URL (post-Promobit redirect)
            deal["real_store_url"] = str(resp.url)
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        # Stars — only fetch if Promobit did not provide them
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

        # Sales / reviews — only fetch if Promobit did not provide them
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
        log.debug(f"Failed to fetch store rating: {e}")

    return deal


# =========================
# FILTERS
# =========================

def _normalize_store(store: str) -> str:
    return store.lower().strip().replace("!", "")


def _store_allowed(store: str) -> bool:
    norm = _normalize_store(store)
    # Exact match or word match (avoids "amazonas" matching "amazon")
    if norm in LOJAS_WHITELIST:
        return True
    # Check whether a whitelist store name is a prefix of the normalized name
    # e.g. "kabum" matches "kabum informatica"
    for allowed in LOJAS_WHITELIST:
        if norm.startswith(allowed):
            return True
    return False


def _is_rede(deal: dict) -> bool:
    """True if the deal is network/adapter (network category or title indicates adapter)."""
    if (deal.get("category") or "") == CAT_REDE_NOME:
        return True
    title = (deal.get("title") or "").lower()
    return any(k in title for k in REDE_KEYWORDS)


# Keywords indicating non-IT products (appliances, kitchen, hygiene, toys, etc.).
# Promobit sometimes lists these inside PC categories
# (e.g. "Pipoqueira Disney Mickey Mouse" under /mouse/). Reject by title.
_IRRELEVANT_KEYWORDS = (
    "pipoqueira", "liquidificador", "fritadeira", "air fryer", "airfryer",
    "frigideira", "geladeira", "fogao", "fogão", "microondas", "micro-ondas",
    "cafeteira", "ventilador", "aspirador", "batedeira", "sanduicheira",
    "ferro de passar", "secador de cabelo", "chapinha", "barbeador", "depilador",
    "brinquedo", "boneca", "boneco", "lego", "fralda", "shampoo", "perfume",
    "espremedor", "purificador", "umidificador", "aquecedor", "climatizador",
    "torradeira", "chaleira", "panela eletrica", "panela elétrica", "panela de",
    "escova de dente", "garrafa termica", "garrafa térmica",
)


_OBSOLETE_KEYWORDS = (
    "ddr2 ", " ddr2", "lga775", "lga1150", "lga1151", "lga1155",
    "am3+", "am3 ", " fm2",
)

def _is_spam_title(title: str) -> bool:
    """True if the title looks like spam or a generic listing."""
    words = title.lower().split()
    # Consecutive duplicate word (MOUSE MOUSE)
    for i in range(len(words) - 1):
        if words[i] == words[i+1] and len(words[i]) >= 3:
            return True
    return False

def _title_has_parts_keyword(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in _PARTS_TITLE_KEYWORDS)


def _title_has_peripheral_keyword(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in _PERIPHERAL_TITLE_KEYWORDS)


def _infer_part_category(title: str) -> str:
    """Best-effort category for misc hardware listings."""
    t = (title or "").lower()
    if any(k in t for k in ("ssd", "nvme", "m.2", "m2 ", "sata iii")):
        return "SSD"
    if any(k in t for k in ("fonte ", "fonte atx", "80 plus", "psu ")):
        return "Fonte"
    if any(k in t for k in ("pasta termica", "pasta térmica")):
        return "Pasta Térmica"
    if any(k in t for k in ("cooler", "water cooler", "watercooler", "dissipador", "ventoinha")):
        return "Cooler"
    if any(k in t for k in ("memoria ram", "memória ram", "ddr4", "ddr5")):
        return "Memória RAM"
    if any(k in t for k in ("placa de video", "placa de vídeo", "geforce", "radeon", "rtx ", "rx ")):
        return "Placa de Vídeo"
    if any(k in t for k in ("processador", "ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra")):
        return "Processador"
    if any(k in t for k in ("placa mae", "placa-mãe", "placa mãe", "chipset")):
        return "Placa-mãe"
    if "gabinete" in t:
        return "Gabinete"
    return "Hardware PC"


def _normalize_deal_category(deal: dict) -> None:
    """Reclassify mixed hardware listings into PC part categories when possible."""
    cat = deal.get("category") or ""
    title = deal.get("title") or ""
    if cat != "Hardware e periféricos":
        return
    if _title_has_peripheral_keyword(title) and not _title_has_parts_keyword(title):
        deal["category"] = cat  # stays — will be filtered out
        return
    if _title_has_parts_keyword(title):
        deal["category"] = _infer_part_category(title)


def _is_pc_part_deal(deal: dict) -> bool:
    return (deal.get("category") or "") in _PARTS_CATEGORIES


def _is_peripheral_deal(deal: dict) -> bool:
    cat = deal.get("category") or ""
    if cat in _PERIPHERAL_CATEGORIES:
        return True
    if cat == "Hardware e periféricos":
        title = deal.get("title") or ""
        if _title_has_parts_keyword(title):
            return False
        return True
    return False


def _is_irrelevant(deal: dict) -> bool:
    """True if the title indicates a non-IT/PC product or spam/obsolete hardware."""
    title = (deal.get("title") or "").lower()
    if any(k in title for k in _IRRELEVANT_KEYWORDS):
        return True
    if any(k in title for k in _OBSOLETE_KEYWORDS):
        return True
    if _is_spam_title(deal.get("title", "")):
        return True
    # Drop pure peripherals/accessories from mixed hardware category.
    if _is_peripheral_deal(deal):
        return True
    return False


_MARKETPLACE_STORES = {"shopee", "aliexpress"}

def _is_marketplace(store: str) -> bool:
    return _normalize_store(store) in _MARKETPLACE_STORES

def _passes_filters(deal: dict) -> tuple[bool, str]:
    """Check whether the deal passes filters. Returns (passed, reason)."""
    # Expired/closed on Promobit
    if deal.get("expired"):
        return False, "offer expired/closed"

    # Must have an image
    if not deal.get("image"):
        return False, "no image"

    # Product outside IT scope (appliance, toy, etc.)
    if _is_irrelevant(deal):
        return False, "irrelevant/spam/obsolete product"

    # Inflated "was" price check
    lowest = deal.get("lowest_price_30d")
    orig = deal.get("original_price")
    if lowest and orig and orig > lowest * 3:
        return False, f"inflated was price: original R${orig:.0f} > 3× 30d_low R${lowest:.0f}"

    # Discount must be >= 15% and <= 100% (reject absurd/negative values)
    disc = deal.get("discount_pct", 0)
    if not disc or disc < DESCONTO_MINIMO or disc > 100:
        return False, f"discount {disc}% out of range ({DESCONTO_MINIMO}-100%)"

    # Store must be on the whitelist
    if not _store_allowed(deal.get("store", "")):
        return False, f"store '{deal.get('store')}' not on whitelist"

    stars = deal.get("stars")
    sales = deal.get("sales_count")

    # Network/adapters: stricter dedicated filters. Requires real metrics
    # (4.5+ stars AND 100+ sales) and 40%+ discount — no "no metrics" fallback.
    if _is_rede(deal):
        if disc < REDE_DESCONTO_MINIMO:
            return False, f"[network] discount {disc}% < {REDE_DESCONTO_MINIMO}%"
        if stars is None or stars < REDE_NOTA_MINIMA:
            return False, f"[network] stars {stars} < {REDE_NOTA_MINIMA}"
        if sales is None or sales < REDE_VENDAS_MINIMAS:
            return False, f"[network] sales {sales} < {REDE_VENDAS_MINIMAS}"
        return True, "ok (network)"

    # Stars/sales check (cascade A→B→C)
    if stars is not None and stars < NOTA_MINIMA_ESTRELAS:
        return False, f"stars {stars} < {NOTA_MINIMA_ESTRELAS}"

    if sales is not None and sales < VENDAS_MINIMAS:
        return False, f"sales {sales} < {VENDAS_MINIMAS}"

    if sales is not None and sales < AVALIACOES_MINIMAS:
        return False, f"reviews {sales} < {AVALIACOES_MINIMAS}"

    # No quality data (Promobit lacked stars and sales): since the store
    # already passed the whitelist (trusted), accept when discount is strong enough.
    if stars is None and sales is None:
        max_disc = 50 if _is_marketplace(deal.get("store", "")) else DESCONTO_SEM_METRICA
        if disc > 70:
            return False, f"discount {disc}% > 70% without metrics (suspicious)"
        if disc >= max_disc:
            if _is_marketplace(deal.get("store", "")):
                return False, f"marketplace without metrics and discount {disc}% >= {max_disc}%"
            return True, "ok (no metrics, high discount)"
        return False, f"no metrics and discount {disc}% < {max_disc}%"

    return True, "ok"


# =========================
# SCORE AND SORTING
# =========================

def _deal_score(deal: dict) -> float:
    """Composite score: discount × quality × log(popularity).
    PC parts get a modest boost; categories already posted today are penalized."""
    disc = deal.get("discount_pct") or 0
    stars = deal.get("stars") or 4.0      # neutral when missing
    sales = deal.get("sales_count") or 10  # low when missing
    score = disc * stars * math.log10(max(sales, 10))
    if _is_pc_part_deal(deal):
        score *= 1.12
    elif (deal.get("category") or "") in {"Monitor", "Notebook", "PC Gamer"}:
        score *= 0.95
    cat = deal.get("category") or ""
    posted_today = _posted_cat_counts.get(cat, 0)
    if posted_today >= 2:
        score *= 0.25
    elif posted_today >= 1:
        score *= 0.55
    return score


def _interleave_by_store(deals: list) -> list:
    """Reorder so the same store is never posted back-to-back."""
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
            # All remaining deals are from the same store — post anyway
            result.append(remaining.pop(0))
            last_store = _normalize_store(result[-1].get("store", ""))
    return result


def _cat_post_limit(cat: str, default: int = 2) -> int:
    return _PER_CAT_POST_LIMIT.get(cat, default)


def _pick_enrichment_batch(candidates: list, cap: int = _ENRICH_CAP) -> list:
    """Reserve enrichment slots for PC parts before anything else."""
    parts: list = []
    secondary: list = []
    for deal in candidates:
        cat = deal.get("category") or ""
        if cat in _PARTS_CATEGORIES or (
            cat == "Hardware e periféricos" and _title_has_parts_keyword(deal.get("title", ""))
        ):
            parts.append(deal)
        elif cat in {
            "Monitor", "Notebook", "PC Gamer", "Adaptadores e rede",
            "Teclado", "Mouse", "Headset",
        }:
            secondary.append(deal)
        # Peripherals and junk hardware are skipped entirely.

    selected: list = []
    per_cat: dict[str, int] = {}
    for deal in parts:
        if len(selected) >= _ENRICH_PARTS_CAP:
            break
        cat = deal.get("category") or "?"
        if per_cat.get(cat, 0) >= 4:
            continue
        selected.append(deal)
        per_cat[cat] = per_cat.get(cat, 0) + 1

    remaining = max(0, cap - len(selected))
    if remaining:
        selected.extend(secondary[:remaining])
    return selected[:cap]


def _pop_best_for_store(items: list, store_counts: dict[str, int], max_per_store: int) -> tuple[dict | None, int]:
    """Pop best item from list respecting per-store cap. Returns (item, index) or (None, -1)."""
    for i, item in enumerate(items):
        store = _normalize_store(item.get("store", ""))
        if store_counts.get(store, 0) < max_per_store:
            return items.pop(i), i
    return None, -1


def _select_diverse(deals: list, limit: int, max_per_cat: int = 2, max_per_store: int = 2) -> list:
    """Select deals prioritizing PC parts, then limited monitors/systems.
    Peripherals are excluded via _PER_CAT_POST_LIMIT=0."""
    from collections import OrderedDict
    by_cat: "OrderedDict[str, list]" = OrderedDict()
    for d in deals:
        by_cat.setdefault(d.get("category", "") or "?", []).append(d)

    selected: list = []
    counts: dict[str, int] = {}
    store_counts: dict[str, int] = {}

    def _try_add(cat: str) -> bool:
        if counts.get(cat, 0) >= _cat_post_limit(cat, max_per_cat):
            return False
        items = by_cat.get(cat) or []
        if not items:
            return False
        item, _ = _pop_best_for_store(items, store_counts, max_per_store)
        if item is None:
            return False
        selected.append(item)
        counts[cat] = counts.get(cat, 0) + 1
        store = _normalize_store(item.get("store", ""))
        store_counts[store] = store_counts.get(store, 0) + 1
        return True

    # Phase 1: reserve core PC parts (GPU/RAM/CPU/mobo/SSD/case)
    for cat in _PARTS_RESERVE_CATEGORIES:
        if len(selected) >= limit:
            break
        _try_add(cat)

    # Phase 2: round-robin remaining part categories (fonte, cooler, pasta, hardware pc)
    parts_cats = [c for c in by_cat if c in _PARTS_CATEGORIES and c not in _PARTS_RESERVE_CATEGORIES]
    progressed = True
    while len(selected) < limit and progressed:
        progressed = False
        for cat in parts_cats:
            if len(selected) >= limit:
                break
            if _try_add(cat):
                progressed = True

    # Phase 3: at most one monitor/notebook/PC gamer/network if slots remain
    for cat in ("Monitor", "Notebook", "PC Gamer", "Adaptadores e rede"):
        if len(selected) >= limit:
            break
        _try_add(cat)

    # Phase 4: at most one peripheral (mouse/keyboard/headset) for variety
    for cat in ("Mouse", "Teclado", "Headset"):
        if len(selected) >= limit:
            break
        _try_add(cat)

    # Phase 5: fill any leftover slots with best remaining parts only
    fill_cats = list(_PARTS_RESERVE_CATEGORIES) + parts_cats
    progressed = True
    while len(selected) < limit and progressed:
        progressed = False
        for cat in fill_cats:
            if len(selected) >= limit:
                break
            if _try_add(cat):
                progressed = True

    # Safety net: if filters passed but category caps blocked everything, post best anyway
    if not selected and deals:
        remaining = sorted(deals, key=lambda d: -_deal_score(d))
        for deal in remaining[:limit]:
            selected.append(deal)

    return selected


# =========================
# EMBED FORMATTING
# =========================

def _format_price_line(deal: dict) -> str:
    """Format the price line with emphasis."""
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
    """Build embed description focused on what the buyer needs to know."""
    lines = []

    # 1) Highlighted price
    lines.append(_format_price_line(deal))

    # 2) Savings
    if deal.get("original_price") and deal.get("price"):
        savings = deal["original_price"] - deal["price"]
        if savings > 0:
            eco = f"R$ {savings:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"Economize **{eco}** nessa compra")

    # Details block (cupom, frete, tags, etc.)
    details = []

    # Coupon (real codes only, not descriptive text)
    if deal.get("coupon"):
        details.append(f"🏷️ Cupom: {deal['coupon']}")

    # Installments — verb + condition makes it clearer
    if deal.get("installments"):
        details.append(f"💳 Parcele em {deal['installments']}")

    # Offer expiration
    if deal.get("expiration"):
        details.append(f"⏰ Oferta válida até {deal['expiration']}")

    # Tags: highlight free shipping (decisive for buyers), skip "Parcelado"
    # (already shown above when available), show the rest as context
    tags = deal.get("tags") or []
    tag_names = [
        (t.get("name", "") if isinstance(t, dict) else str(t)).strip()
        for t in tags
    ]
    tag_names = [n for n in tag_names if n]
    has_frete_gratis = any("frete" in n.lower() and "grát" in n.lower() for n in tag_names)
    if has_frete_gratis:
        details.append("✅ Frete grátis")
    # Other relevant tags
    _TAGS_IGNORE = {"app", "nacional", "internacional", "cupom", "promoção", "oferta"}
    _TAGS_MAP = {
        "app": "📱 Cupom no app da loja",
        "taxa inclusa": "🏷️ Taxa inclusa",
    }
    others = []
    for n in tag_names:
        nl = n.lower()
        if "frete" in nl or "parcelado" in nl:
            continue
        if nl in _TAGS_IGNORE:
            mapped = _TAGS_MAP.get(nl)
            if mapped:
                details.append(mapped)
            continue
        others.append(n)
    if others:
        details.extend(others[:2])

    if details:
        lines.append("")
        lines.extend(details)

    return "\n".join(lines)


async def _download_image(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """Download image and return bytes. Returns None on failure."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                log.debug(f"Image HTTP {resp.status}: {url[:80]}")
                return None
            data = await resp.read()
            if len(data) < 1000:  # image too small
                return None
            return data
    except Exception as e:
        log.debug(f"Failed to download image: {e}")
        return None


def _store_destination(deal: dict) -> Optional[str]:
    """Best DIRECT store destination (no affiliate yet):
    1) resolved Promobit product link; 2) store search by name."""
    if deal.get("product_url"):
        return deal["product_url"]
    return _store_search_url(deal.get("store", ""), deal.get("title", ""))


def _buy_url(deal: dict) -> str:
    """Final buy URL with affiliate, always pointing DIRECTLY to the store.
    Order: direct product → store search → no link (never falls back to Promobit)."""
    store = deal.get("store", "")
    dest = _store_destination(deal)
    if dest and dest.startswith("http"):
        return affiliate_config.build_affiliate_url(store, dest)
    return ""


def _cor_embed(deal: dict) -> int:
    """Embed bar color by discount tier: higher discount = hotter color,
    signaling at a glance how good the deal is."""
    disc = deal.get("discount_pct") or 0
    if disc >= DESCONTO_ULTRA_OFERTA:
        return COR_DESCONTO_ULTRA
    if disc >= 30:
        return COR_DESCONTO_OTIMA
    if disc >= 20:
        return COR_DESCONTO_BOA
    return COR_OFERTA


def _build_view(deal: dict) -> Optional[discord.ui.View]:
    """Real Discord buy button (link). Returns None when no valid URL exists
    — embed falls back to a text CTA field.
    Note: Discord always renders link buttons in gray (cannot be colored);
    emphasis comes from text (discount) + highlighted CTA in the embed body."""
    buy_url = _buy_url(deal)
    if not buy_url.startswith("http"):
        return None
    disc = deal.get("discount_pct") or 0
    label = f"COMPRAR COM {disc:.0f}% OFF" if disc else "COMPRAR COM DESCONTO"
    view = discord.ui.View(timeout=None)  # link buttons do not fire interactions
    view.add_item(discord.ui.Button(
        label=label[:80],
        emoji="🛒",
        style=discord.ButtonStyle.link,
        url=buy_url,
    ))
    return view


def _build_embed(deal: dict) -> discord.Embed:
    """Build the deal embed."""
    cor = _cor_embed(deal)
    category = deal.get("category") or "Oferta"
    store = deal.get("store", "Loja")

    cat_emoji = CATEGORIAS_EMOJI.get(category, "🖥️")
    for cat_key, emoji in CATEGORIAS_EMOJI.items():
        if cat_key.lower() in category.lower():
            cat_emoji = emoji
            break

    clean_title = _sanitize_title(deal["title"][:200])
    title = f"{EMOJI_FOGO} {clean_title}"

    desc = _format_description(deal)
    buy_url = _buy_url(deal)

    if len(desc) > 4096:
        desc = desc[:4093] + "..."

    embed = discord.Embed(
        title=title[:256],
        url=buy_url if buy_url.startswith("http") else None,
        description=desc,
        color=cor,
    )

    embed.set_author(
        name=f"Via {store} • Oferta {cat_emoji}",
        icon_url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png",
    )

    # Image — set at post time (_build_embed does not set here
    # to avoid double set_image if download fails)
    # CTA: normally becomes a real BUTTON (see _build_view, attached on send).
    # Text field is only a fallback when no usable URL exists.
    if not buy_url.startswith("http"):
        embed.add_field(
            name="",
            value="👉 **Confira a oferta na loja**",
            inline=False,
        )

    # Subtle footer — price may change at any time
    embed.set_footer(text="Preço sujeito a alterações")

    return embed


# =========================
# MAIN CYCLE
# =========================

_cycle_running = False  # guard against parallel runs

async def _run_deals_cycle() -> None:
    """Run a full collect-and-publish cycle."""
    global http_session, _cycle_running
    if _cycle_running:
        log.warning("Previous cycle still running, skipping this one.")
        return
    _cycle_running = True
    try:
        await _run_deals_cycle_inner()
    finally:
        _cycle_running = False

async def _run_deals_cycle_inner() -> None:
    """Core offers cycle logic."""
    global http_session

    if http_session and not http_session.closed:
        pass  # Reuse existing session
    else:
        if http_session and http_session.closed:
            http_session = None
        http_session = aiohttp.ClientSession()

    history = _load_history()
    _clean_history(history)

    log.info("=== Starting offers cycle ===")

    all_deals: list[dict] = []

    # Collect from all categories
    for cat_path in CATEGORIAS_PROMOBIT:
        url = PROMOBIT_BASE + cat_path
        html = await _fetch_page(http_session, url)
        if not html:
            continue

        deals = _parse_deals_from_html(html, cat_path)
        # Extract category name from path
        cat_slug = cat_path.strip("/").split("/")[-2]
        cat_name = _SLUG_TO_CATEGORY.get(cat_slug, cat_slug.replace("-", " ").title())
        for d in deals:
            d["category"] = cat_name
            _normalize_deal_category(d)

        log.info(f"  {cat_path}: {len(deals)} deals found")
        all_deals.extend(deals)

        await asyncio.sleep(2)  # Respect Promobit rate limit

    log.info(f"Raw total: {len(all_deals)} deals collected")

    # Reset intraday dedup when the day rolls over
    global _posted_title_keys, _posted_title_keys_date, _posted_cat_counts, _posted_cat_counts_date
    today_br = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
    if today_br != _posted_title_keys_date:
        _posted_title_keys = set()
        _posted_title_keys_date = today_br
    if today_br != _posted_cat_counts_date:
        _posted_cat_counts = {}
        _posted_cat_counts_date = today_br

    # Dedup by URL (14-day history) + intraday by product + store listing ID
    candidates = []
    _cycle_keys: set[str] = set()  # dedup within the same cycle
    _cycle_urls: set[str] = set()  # URL dedup within cycle (cross-category)
    _cycle_listings: set[str] = set()
    for deal in all_deals:
        if deal["url"] in _cycle_urls:
            continue
        _cycle_urls.add(deal["url"])
        if _is_duplicate(history, deal["url"]):
            continue
        listing = _listing_key(deal.get("url", ""))
        if listing and (
            listing in _cycle_listings
            or _is_listing_in_history(history, listing)
        ):
            log.debug(f"  Dedup store listing (early): {deal['title'][:60]}")
            continue
        if listing:
            _cycle_listings.add(listing)
        key = _title_key(deal["title"])
        if key and (key in _posted_title_keys or key in _cycle_keys or _is_title_key_in_history(history, key)):
            log.debug(f"  Dedup similar product (intraday or history): {deal['title'][:60]}")
            continue
        if key:
            _cycle_keys.add(key)
        candidates.append(deal)

    log.info(f"After dedup: {len(candidates)} candidates")

    # Cheap pre-filter (no network) BEFORE enrichment: drop known stores
    # outside the whitelist to avoid wasting enrichment budget on deals that
    # would be rejected anyway. Keeps whitelist stores and unknown stores
    # (store name only revealed during enrichment).
    pre_candidates = []
    dropped_store_filter = 0
    for deal in candidates:
        store = deal.get("store") or ""
        if store and not _store_allowed(store):
            dropped_store_filter += 1
            continue
        pre_candidates.append(deal)
    # Prioritize by (1) category priority — so parts (CPU/GPU/RAM) get enrichment
    # slots before monitor/motherboard — and (2) confirmed store.
    pre_candidates.sort(key=lambda d: (
        _CATEGORY_PRIORITY.get(d.get("category", ""), 99),
        0 if (d.get("store") and _store_allowed(d.get("store", ""))) else 1,
    ))
    log.info(
        f"Store pre-filter: {len(pre_candidates)} to enrich "
        f"({dropped_store_filter} dropped by whitelist before enrichment)"
    )

    # Enrich each deal (fetch details)
    enriched = []
    enrich_batch = _pick_enrichment_batch(pre_candidates)
    for deal in enrich_batch:
        try:
            # Save ORIGINAL title key before enrichment mutates the title
            deal["_orig_tkey"] = _title_key(deal["title"])
            _normalize_deal_category(deal)
            deal = await asyncio.wait_for(_enrich_deal(http_session, deal), timeout=30.0)
            await asyncio.sleep(1.5)

            # Always resolve real store URL (needed for affiliates)
            # + try to fetch rating if still missing
            if deal.get("store_url") and not deal.get("real_store_url"):
                deal = await asyncio.wait_for(_try_fetch_store_rating(http_session, deal), timeout=20.0)
                await asyncio.sleep(1)
            enriched.append(deal)
        except asyncio.TimeoutError:
            log.warning(f"Timeout enriching deal {deal.get('title', '?')[:50]}")
        except Exception as e:
            log.warning(f"Failed to enrich deal {deal.get('title', '?')[:50]}: {e}")

    # Apply filters
    approved = []
    rejections: dict[str, int] = {}
    _seen_listings: set[str] = set()
    for deal in enriched:
        passed, reason = _passes_filters(deal)
        if not passed:
            bucket = re.sub(r"\d+([.,]\d+)?", "N", reason)
            rejections[bucket] = rejections.get(bucket, 0) + 1
            continue
        listing = _deal_listing_key(deal)
        if listing and (listing in _seen_listings or _is_listing_in_history(history, listing)):
            log.debug(f"  Dedup store listing (7d): {deal['title'][:60]}")
            continue
        if listing:
            _seen_listings.add(listing)
        approved.append(deal)

    log.info(f"After filters: {len(approved)} approved")
    if not approved:
        log.warning(
            f"No deals passed filters this cycle "
            f"(enriched={len(enriched)}, raw={len(all_deals)}, candidates={len(candidates)})"
        )
    # Diagnostic: rejection reason summary (visible even at LOG_LEVEL=INFO)
    if rejections:
        summary = " · ".join(
            f"{n}× {reason}" for reason, n in sorted(rejections.items(), key=lambda x: -x[1])
        )
        log.info(f"Rejection reasons ({sum(rejections.values())}): {summary}")

    # Sort: category priority (parts > peripherals > other) then composite score
    approved.sort(
        key=lambda d: (
            _CATEGORY_PRIORITY.get(d.get("category", ""), 99),
            -_deal_score(d),
        )
    )
    # Diversify by category: parts reserved first; monitors/peripherals capped lower.
    approved = _select_diverse(approved, MAX_POSTS_POR_CICLO, max_per_cat=2)
    approved = _interleave_by_store(approved)
    parts_posted = sum(1 for d in approved if _is_pc_part_deal(d))
    log.info(
        f"Selection: {len(approved)} to post "
        f"({parts_posted} peças de PC, {len(approved) - parts_posted} outros)"
    )

    # Post
    channel = _bot.get_channel(CANAL_OFERTAS_ID)
    if not channel:
        log.error(f"Channel {CANAL_OFERTAS_ID} not found!")
        return

    posted = 0
    for deal in approved[:MAX_POSTS_POR_CICLO]:
        embed = _build_embed(deal)

        # Download image and attach as file
        file = None
        if deal.get("image"):
            img_data = await _download_image(http_session, deal["image"])
            if img_data:
                file = discord.File(io.BytesIO(img_data), filename="oferta.jpg")
                embed.set_image(url="attachment://oferta.jpg")
            else:
                # Fallback: try direct URL in embed
                embed.set_image(url=deal["image"])

        try:
            global _mention_count_ofertas, _mention_date_ofertas
            content = None
            guild = getattr(channel, "guild", None)
            # Ping role only on the first 3 ULTRA DEALS of the day
            today_br = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
            if today_br != _mention_date_ofertas:
                _mention_date_ofertas = today_br
                _mention_count_ofertas = 0
            
            cargo_id = ID_CARGO_ULTRA or ID_CARGO_OFERTAS
            is_ultra = deal.get("discount_pct", 0) >= DESCONTO_ULTRA_OFERTA
            
            if is_ultra and cargo_id and _mention_count_ofertas < 3 and guild and guild.get_role(cargo_id):
                content = f"<@&{cargo_id}>"
                _mention_count_ofertas += 1

            view = _build_view(deal)
            if view is not None:
                msg = await channel.send(content=content, embed=embed, file=file, view=view)
            else:
                msg = await channel.send(content=content, embed=embed, file=file)

            # Mark as posted AFTER successful send
            # Use original title key (pre-enrichment) for consistent cross-cycle dedup
            _orig_tkey = deal.get("_orig_tkey") or _title_key(deal["title"])
            _listing = _deal_listing_key(deal)
            _mark_posted(history, deal["url"], deal["title"], orig_tkey=_orig_tkey, listing=_listing)
            _posted_title_keys.add(_orig_tkey)
            cat = deal.get("category") or "?"
            _posted_cat_counts[cat] = _posted_cat_counts.get(cat, 0) + 1

            posted += 1
            log.info(f"  🛒 Posted: {deal['title'][:60]} ({deal.get('discount_pct', 0):.0f}% OFF)")

            if posted < MAX_POSTS_POR_CICLO:
                await asyncio.sleep(POST_SPACING_SEC)

        except Exception as e:
            log.error(f"  Failed to post deal: {e}")

    log.info(f"=== Cycle finished: {posted} deals posted ===")


# =========================
# TASKS LOOP
# =========================

# =========================
# COG WRAPPER
# =========================

_cog_loaded = False


class OffersCog(commands.Cog):
    """Offers cog — publishes deals automatically."""
    
    def __init__(self, bot: commands.Bot):
        global _bot
        _bot = bot
        self.bot = bot
        self.deals_loop.start()
    
    def cog_unload(self):
        self.deals_loop.cancel()
    
    @tasks.loop(minutes=SCAN_INTERVAL_MIN)
    async def deals_loop(self):
        now_br = datetime.now(FUSO_HORARIO_BR)
        if not (HORA_INICIO <= now_br.hour < HORA_FIM):
            log.info(f"Outside business hours ({now_br.hour}h). Skipping cycle.")
            return
        try:
            await _run_deals_cycle()
        except Exception as e:
            log.exception(f"Offers cycle error: {e}")
    
    @deals_loop.before_loop
    async def _before_deals_loop(self):
        await self.bot.wait_until_ready()
        log.info("Offers cog ready — running first cycle now (loop waits %s min before next).", SCAN_INTERVAL_MIN)
        now_br = datetime.now(FUSO_HORARIO_BR)
        if HORA_INICIO <= now_br.hour < HORA_FIM:
            try:
                await _run_deals_cycle()
            except Exception as e:
                log.exception(f"Offers first cycle error: {e}")
        else:
            log.info(f"Outside business hours ({now_br.hour}h) — first cycle deferred to next loop tick.")
    
    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"✅ Offers Cog loaded — bot: {self.bot.user}")
        progs = affiliate_config.active_programs()
        if progs:
            log.info(f"💰 Active affiliates: {', '.join(progs)}")
        else:
            log.warning("⚠️ No affiliate program configured in .env")
    
    @commands.Cog.listener()
    async def on_disconnect(self):
        log.warning("⚠️ [Offers] Bot disconnected from Discord.")
    
    @commands.Cog.listener()
    async def on_close(self):
        global http_session
        if http_session and not http_session.closed:
            await http_session.close()
            http_session = None
        log.info("🔌 [Offers] HTTP session closed.")

async def setup(bot: commands.Bot):
    global _cog_loaded
    if _cog_loaded:
        log.warning("offers_cog already loaded — ignoring duplicate extension.")
        return
    _cog_loaded = True
    await bot.add_cog(OffersCog(bot))
