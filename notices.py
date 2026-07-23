import discord
from discord.ext import tasks, commands
import feedparser
import os
import re
import json
import time
import io
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import html as html_lib
import hashlib
import struct
import calendar
import atexit
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin

import aiohttp
from dotenv import load_dotenv
from openai import AsyncOpenAI

try:
    import tiffany_voice
    _voice_available = True
except Exception as _ve:
    import logging as _log_tmp
    _log_tmp.getLogger("tiffany-bot").warning(
        "tiffany_voice failed to load (%s) — voice commands disabled.",
        _ve,
        exc_info=True,
    )
    tiffany_voice = None
    _voice_available = False

# =========================
# CONFIGURATION
# =========================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

try:
    CANAL_NOTICIAS_ID = int(os.getenv("CANAL_NOTICIAS_ID", "0"))
except ValueError:
    CANAL_NOTICIAS_ID = 0

try:
    CANAL_OFERTAS_ID = int(os.getenv("CANAL_OFERTAS_ID", "0"))
except ValueError:
    CANAL_OFERTAS_ID = 0

try:
    ID_CARGO_PARA_MARCAR = int(os.getenv("ID_CARGO_PARA_MARCAR", "0"))
except ValueError:
    ID_CARGO_PARA_MARCAR = 0

HORA_INICIO = 8
HORA_FIM = 18
FUSO_HORARIO_BR = timezone(timedelta(hours=-3))
MINUTO_PRE_AQUECIMENTO = 0
INTERVALO_NOTICIAS_MIN = int(os.getenv("INTERVALO_NOTICIAS_MIN", "60"))  # interval between news cycles (minutes)

# Clock-aligned schedule: every 45 min from 8:00 to before 18:00
def _build_news_schedule():
    times = []
    t = HORA_INICIO * 60
    while t < HORA_FIM * 60:
        h, m = divmod(t, 60)
        times.append(dt_time(hour=h, minute=m, tzinfo=FUSO_HORARIO_BR))
        t += INTERVALO_NOTICIAS_MIN
    return times

_NEWS_SCHEDULE = _build_news_schedule()

# --- Pipeline ---
SCAN_POR_FEED = int(os.getenv("SCAN_POR_FEED", "8"))
ENTRADAS_POR_FEED = int(os.getenv("ENTRADAS_POR_FEED", "4"))
MAX_IA_CALLS_POR_CICLO = int(os.getenv("MAX_IA_CALLS_PER_CICLO", "6"))
MAX_VISION_CALLS_POR_CICLO = int(os.getenv("MAX_VISION_CALLS_POR_CICLO", "4"))
IA_COOLDOWN_SEC = int(os.getenv("IA_COOLDOWN_SEC", "10"))
POST_SPACING_SEC = int(os.getenv("POST_SPACING_SEC", "90"))
MAX_POSTS_POR_CICLO = int(os.getenv("MAX_POSTS_POR_CICLO", "1"))

# --- Score thresholds ---
NOTA_MIN_APROVACAO = int(os.getenv("NOTA_MIN_APROVACAO", "75"))
NOTA_MIN_GAMES = int(os.getenv("NOTA_MIN_GAMES", "82"))
NOTA_URGENTE = 90

# --- Anti-dup ---
SIMHASH_TTL_HORAS = 120
SIMHASH_HAMMING_MAX = int(os.getenv("SIMHASH_HAMMING_MAX", "5"))
TITLE_IDX_TTL_HORAS = 72
TOPIC_IDX_TTL_HORAS = 48
MAX_IDADE_HORAS = int(os.getenv("MAX_IDADE_HORAS", "24"))

HISTORY_FILE = "notices_history.json"
METRICS_FILE = "notices_metrics.json"
QUEUE_FILE = "notices_queue.json"

# =========================
# LOGGING
# =========================
_log_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

_file_handler = RotatingFileHandler(
    "tiffany-bot.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)

log = logging.getLogger("tiffany-bot")
log.setLevel(logging.INFO)
log.addHandler(_console_handler)
log.addHandler(_file_handler)

# Silence noise from external libraries
logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.voice_state").setLevel(logging.WARNING)
logging.getLogger("wavelink").setLevel(logging.WARNING)

# =========================
# DISCORD + AI CLIENT
# =========================
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

intents = discord.Intents.default()
# Only enable voice intents if voice is enabled
if os.getenv("VOICE_ENABLED", "1").strip() == "1":
    intents.voice_states = True
intents.message_content = True
intents.members = True
class _TiffanyCommandTree(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if _voice_available and tiffany_voice:
            return await tiffany_voice.slash_rate_limit_check(interaction)
        return True


discord_client = commands.Bot(
    command_prefix=commands.when_mentioned_or("t!", "T!"),
    case_insensitive=True,
    intents=intents,
    help_command=None,  # /help slash command provides command help
    tree_cls=_TiffanyCommandTree,
    # Never let AI answers, summaries or external text trigger mass pings.
    # User mentions stay on (intended for the "@author" reply in voice/reroll).
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
)
ai_client = (
    AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    if OPENROUTER_API_KEY
    else None
)
http_session: Optional[aiohttp.ClientSession] = None

# --- Feed cooldown state ---
_feed_cooldown_until: dict[str, float] = {}
_FEED_COOLDOWN_MAX_ENTRIES = 200

def _set_feed_cooldown(nome_site: str) -> None:
    # Purge expired entries if dict grew too large
    if len(_feed_cooldown_until) > _FEED_COOLDOWN_MAX_ENTRIES:
        now = time.time()
        expired = [k for k, v in _feed_cooldown_until.items() if now >= v]
        for k in expired:
            del _feed_cooldown_until[k]
    _feed_cooldown_until[nome_site] = time.time() + (FEED_COOLDOWN_MIN * 60)

def _feed_em_cooldown(nome_site: str) -> bool:
    return time.time() < _feed_cooldown_until.get(nome_site, 0)

# =========================
# RSS SOURCES
# =========================
FONTES_RSS = {
    # BR
    "Adrenaline": "https://adrenaline.com.br/feed/",
    "TudoCelular": "https://www.tudocelular.com/rss/",
    "Tecnoblog": "https://tecnoblog.net/feed/",
    "Canaltech": "https://canaltech.com.br/rss/",
    "Olhar Digital": "https://olhardigital.com.br/rss/",
    "G1 Tecnologia": "https://g1.globo.com/dynamo/tecnologia/rss2.xml",
    "Convergência Digital": "https://convergenciadigital.com.br/feed/",
    "MacMagazine": "https://macmagazine.com.br/feed/",
    "Meio Bit": "https://meiobit.com/feed/",
    # EN — General
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Wired": "https://www.wired.com/feed/rss",
    "Engadget": "https://www.engadget.com/rss.xml",
    "9to5Mac": "https://9to5mac.com/feed/",
    "9to5Google": "https://9to5google.com/feed/",
    "ZDNet": "https://www.zdnet.com/news/rss.xml",
    "The Register": "https://www.theregister.com/headlines.atom",
    "Tom's Hardware": "https://www.tomshardware.com/feeds/all",
    "IEEE Spectrum": "https://spectrum.ieee.org/rss",
    # EN — Security
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "KrebsOnSecurity": "https://krebsonsecurity.com/feed/",
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Dark Reading": "https://www.darkreading.com/rss.xml",
    "Socket": "https://socket.dev/blog/rss.xml",
    # EN — AI / Dev
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "OpenAI Blog": "https://openai.com/blog/rss.xml",
    "Anthropic Blog": "https://www.anthropic.com/rss/index.xml",
    "GitHub Blog": "https://github.blog/feed/",
    "Cloudflare Blog": "https://blog.cloudflare.com/rss/",
    "Simon Willison": "https://simonwillison.net/atom/everything/",
}

FONTES_INGLES = {
    "The Verge", "TechCrunch", "Ars Technica", "Wired", "Engadget",
    "BleepingComputer", "9to5Mac", "9to5Google", "ZDNet",
    "The Register", "Tom's Hardware", "Axios Tech", "IEEE Spectrum",
    "KrebsOnSecurity", "The Hacker News", "Dark Reading", "Socket",
    "MIT Technology Review", "OpenAI Blog", "Anthropic Blog",
    "GitHub Blog", "Cloudflare Blog", "Simon Willison",
}

# =========================
# CATEGORIES
# =========================
TIFFANY_PINK = 0xFF69B4
CORES_CATEGORIA = {
    "Hardware": TIFFANY_PINK,
    "Inteligência Artificial": TIFFANY_PINK,
    "Games": TIFFANY_PINK,
    "Cibersegurança": TIFFANY_PINK,
    "Sistemas Operacionais": TIFFANY_PINK,
    "Smartphones": TIFFANY_PINK,
    "Big Techs": TIFFANY_PINK,
    "Ciência & Espaço": TIFFANY_PINK,
    "Software & Apps": TIFFANY_PINK,
    "Cloud & DevOps": TIFFANY_PINK,
    "Programação & Dev": TIFFANY_PINK,
    "Internet & Redes": TIFFANY_PINK,
    "Mídia & Streaming": TIFFANY_PINK,
    "Curiosidade Tech": TIFFANY_PINK,
    "Outros": TIFFANY_PINK,
}
COR_PADRAO = TIFFANY_PINK

# --- Feed resilience ---
FEED_COOLDOWN_MIN = 60
MAX_CANDIDATOS_POR_FONTE = int(os.getenv("MAX_CANDIDATOS_POR_FONTE", "3"))

EMOJIS_CATEGORIA = {
    "Hardware": "🖥️",
    "Smartphones": "📱",
    "Inteligência Artificial": "🤖",
    "Games": "🎮",
    "Cibersegurança": "🛡️",
    "Software & Apps": "💾",
    "Big Techs": "💼",
    "Ciência & Espaço": "🚀",
    "Curiosidade Tech": "💡",
    "Sistemas Operacionais": "🪟",
    "Internet & Redes": "🌐",
    "Cloud & DevOps": "☁️",
    "Programação & Dev": "🧑‍💻",
    "Mídia & Streaming": "📺",
    "Outros": "🔌",
}

# =========================
# KEYWORD PRE-FILTER
# =========================
KEYWORDS_TECH = {
    # AI / ML
    "inteligência artificial", "inteligencia artificial", "machine learning",
    "deep learning", "llm", "chatgpt", "openai", "gemini", "copilot",
    "anthropic", "claude", "midjourney", "stable diffusion", "neural",
    "gpt", "transformers", "nlp", "generative ai", "ia generativa",
    # Hardware
    "nvidia", "amd", "intel", "gpu", "cpu", "processador", "placa de vídeo",
    "placa de video", "rtx", "radeon", "ryzen", "chip", "semicondutor",
    "semiconductor", "tsmc", "qualcomm", "snapdragon", "apple silicon",
    # Security (keyword matching)
    "cibersegurança", "ciberseguranca", "cybersecurity", "ransomware",
    "malware", "phishing", "vulnerabilidade", "vulnerability", "cve",
    "zero-day", "0-day", "exploit", "data breach", "vazamento de dados",
    "hacker", "ddos", "firewall", "encryption", "criptografia",
    # Cloud / DevOps
    "kubernetes", "docker", "aws", "azure", "google cloud", "cloud computing",
    "devops", "ci/cd", "microservices", "serverless", "terraform",
    # Operating systems
    "windows 11", "windows 12", "linux", "macos", "android", "ios",
    "ubuntu", "kernel", "atualização de segurança", "security update",
    # Programming
    "python", "javascript", "typescript", "rust", "golang", "github",
    "gitlab", "api", "framework", "open source", "código aberto",
    "developer", "desenvolvedor", "programming", "programação",
    "react", "nextjs", "node.js",
    # Big Techs
    "google", "microsoft", "apple", "meta", "amazon", "tesla", "spacex",
    "samsung", "sony", "nintendo", "valve", "steam",
    # Mobile (flagships)
    "iphone", "galaxy s", "pixel", "ipad",
    # General
    "startup", "big tech", "algoritmo", "blockchain", "web3",
    "5g", "6g", "wi-fi", "fibra óptica", "satélite", "starlink",
    "realidade virtual", "realidade aumentada", "vr", "ar", "metaverso",
    "robô", "robot", "automação", "automation", "quantum", "quântico",
}

KEYWORDS_BLOCK = {
    # Deals / shopping
    "oferta", "desconto", "cupom", "coupon", "promoção", "promocao",
    "black friday", "prime day", "compre", "barato", "menor preço",
    "menor preco", "cashback", "afiliado", "affiliate",
    # Generic entertainment
    "horóscopo", "horoscopo", "futebol", "soccer", "nba", "nfl",
    "novela", "big brother", "reality show", "celebridade", "celebrity",
    "fofoca", "gossip", "tiktok trend", "meme",
    # Generic science (out of scope)
    "paleontologia", "arqueologia", "fóssil", "fossil",
    "dinossauro", "dinosaur",
    # Reviews / buying guides
    "análise de produto", "guia de compra", "buying guide",
    "melhor custo-benefício", "vale a pena comprar",
    "unboxing",
}

def prefiltro_keywords(titulo: str, texto: str) -> bool:
    """Return True if the article PASSES the filter (potentially tech).
    Return False if it should be rejected before AI analysis."""
    blob = f"{titulo} {texto}".lower()

    # Reject if blocked keyword found
    for kw in KEYWORDS_BLOCK:
        if kw in blob:
            return False
    # Blocked keywords with word boundary (avoid false positives from substrings)
    _BLOCK_WORD_BOUNDARY = ("review", "comparativo")
    for kw in _BLOCK_WORD_BOUNDARY:
        if re.search(rf"\b{kw}\b", blob):
            return False

    # Accept if tech keyword found
    for kw in KEYWORDS_TECH:
        if kw in blob:
            return True

    # No tech keyword found — reject
    return False

# =========================
# URL NORMALIZATION
# =========================
TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "source"}

def normalizar_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        q = parse_qsl(parts.query, keep_blank_values=True)
        q2 = [(k, v) for k, v in q
              if not k.lower().startswith(TRACKING_PREFIXES)
              and k.lower() not in TRACKING_KEYS]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q2, doseq=True), ""))
    except Exception:
        return url

# =========================
# HTML UTILS
# =========================
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style).*?>.*?</\1>")

def limpar_html(texto: str) -> str:
    texto = html_lib.unescape(texto or "")
    texto = SCRIPT_STYLE_RE.sub(" ", texto)
    texto = TAG_RE.sub(" ", texto)
    return re.sub(r"\s+", " ", texto).strip()

# =========================
# SIMHASH DEDUPLICATION
# =========================
SIMHASH_WORD_RE = re.compile(r"[a-z0-9À-ÿ]{3,}", re.IGNORECASE)

def _simhash64(text: str) -> int:
    text = (text or "").lower()
    toks = SIMHASH_WORD_RE.findall(text)
    if not toks:
        return 0
    v = [0] * 64
    for tok in toks[:200]:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        x = h & ((1 << 64) - 1)
        for i in range(64):
            bit = (x >> i) & 1
            v[i] += 1 if bit else -1
    out = 0
    for i in range(64):
        if v[i] > 0:
            out |= 1 << i
    return out

def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()

# =========================
# HISTORY (PERSISTENCE)
# =========================
def _hist_key_link(link_norm: str) -> str:
    return f"L:{link_norm}"

def _hist_key_hash(dedupe_hash: str) -> str:
    return f"H:{dedupe_hash}"

def load_history() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning(f"Failed to load history: {e}")
        return {}

def save_history(h: dict) -> None:
    # Remove entries older than 7 days
    cutoff = int(time.time()) - (7 * 86400)
    novo = {}
    # Preserve internal indexes (with pruning to prevent unbounded growth)
    if "_simhash_idx" in h:
        novo["_simhash_idx"] = _simhash_prune(h["_simhash_idx"])
    if "_title_idx" in h:
        novo["_title_idx"] = _title_idx_prune(h["_title_idx"])
    if "_entity_groups" in h:
        novo["_entity_groups"] = _entity_groups_prune(h["_entity_groups"])[-400:]
    for k, v in h.items():
        if k in ("_simhash_idx", "_title_idx", "_entity_groups", "_topic_idx"):
            continue
        if isinstance(v, dict) and "ts" in v:
            if v["ts"] > cutoff:
                novo[k] = v
        elif isinstance(v, dict) and "data" in v:
            # Backward-compat with V16 ("data" field in ISO format)
            try:
                dt = datetime.fromisoformat(v["data"])
                if dt.timestamp() > cutoff:
                    novo[k] = v
            except Exception:
                novo[k] = v
        else:
            novo[k] = v
    tmp = f"{HISTORY_FILE}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(novo, f, ensure_ascii=False, indent=2)
        os.replace(tmp, HISTORY_FILE)
    except Exception:
        log.exception("Failed to save history")
        try:
            os.remove(tmp)
        except OSError:
            pass

# =========================
# PERSISTENT METRICS
# =========================
def load_metrics() -> dict:
    if not os.path.exists(METRICS_FILE):
        return {}
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_metrics(m: dict) -> None:
    tmp = f"{METRICS_FILE}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        os.replace(tmp, METRICS_FILE)
    except Exception as e:
        log.error(f"Failed to save metrics: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass

def metric_inc(m: dict, key: str, amount: int = 1) -> None:
    hoje = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
    if "_date" not in m or m["_date"] != hoje:
        # New day: reset daily counters, preserve totals
        m["_date"] = hoje
        for k in ("posts_hoje", "ia_aprovadas_hoje", "ia_rejeitadas_hoje", "ia_calls_hoje"):
            m[k] = 0
    m[key] = m.get(key, 0) + amount
    total_key = key.replace("_hoje", "_total")
    if total_key != key:
        m[total_key] = m.get(total_key, 0) + amount

# =========================
# APPROVED QUEUE (persistence between cycles)
# =========================
def load_queue() -> list:
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_queue(q: list) -> None:
    tmp = f"{QUEUE_FILE}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=2)
        os.replace(tmp, QUEUE_FILE)
    except Exception as e:
        log.error(f"Failed to save queue: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass

def _hist_payload(status: str, extra: Optional[dict] = None) -> dict:
    payload = {"status": status, "ts": int(time.time())}
    if extra:
        payload.update(extra)
    return payload

def historico_check(h: dict, link_norm: str, dedupe_hash: Optional[str]) -> bool:
    """Return True if already processed (dedup by URL or hash)."""
    # Check V17 format (L: / H:)
    if _hist_key_link(link_norm) in h:
        return True
    if dedupe_hash and _hist_key_hash(dedupe_hash) in h:
        return True
    # Backward-compat: check bare URL (V16 format)
    if link_norm in h:
        return True
    return False

def historico_set(h: dict, link_norm: str, dedupe_hash: Optional[str], status: str, extra: Optional[dict] = None) -> None:
    payload = _hist_payload(status, extra)
    h[_hist_key_link(link_norm)] = payload
    if dedupe_hash:
        h[_hist_key_hash(dedupe_hash)] = payload

def make_dedupe_hash(titulo: str, published_ts: int) -> str:
    # No hour bucket — same title = same hash regardless of publish time
    raw = f"GLOBAL|{_normalizar_titulo(titulo)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

# =========================
# TITLE NORMALIZATION
# =========================
_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob",
    "que", "e", "ou", "mas", "se", "ao", "aos", "the", "a", "an", "of", "in",
    "on", "for", "to", "and", "or", "is", "it", "its", "with", "by", "at",
    "from", "has", "have", "had", "be", "are", "was", "were", "will", "can",
}
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

def _normalizar_titulo(titulo: str) -> str:
    """Normalize title by removing stopwords, punctuation, and extra spaces.
    'Microsoft lança atualização do Windows 11' → 'microsoft lança atualização windows 11'"""
    t = (titulo or "").lower().strip()
    t = _PUNCT_RE.sub(" ", t)
    palavras = [p for p in t.split() if p not in _STOPWORDS and len(p) > 1]
    return " ".join(palavras)

def _title_fingerprint(titulo: str) -> str:
    """Short hash of normalized title for cross-site dedup."""
    norm = _normalizar_titulo(titulo)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]

# =========================
# TOPIC/SUBJECT DEDUP
# =========================
# Words too generic to be key entities (in addition to stopwords)
_TOPIC_NOISE = {
    "novo", "nova", "novos", "novas", "lança", "lançar", "lançou", "lançamento",
    "anuncia", "anunciar", "anunciou", "revela", "revelar", "revelou", "alerta",
    "alertar", "alertou", "propõe", "propor", "modelo", "modelos", "sistema",
    "sistemas", "empresa", "empresas", "tecnologia", "agora", "pode", "vai",
    "será", "primeiro", "primeira", "global", "mundo", "mercado", "setor",
    "mais", "como", "sobre", "não", "muito", "também", "após", "até",
    "ainda", "já", "ser", "ter", "deve", "diz", "faz", "usa", "usar",
    "usar", "afirma", "diz", "says", "new", "launches", "announces",
    "reveals", "report", "could", "may", "now", "first", "big", "just",
    "get", "gets", "got", "make", "makes", "made", "says", "said",
    "plan", "plans", "feature", "update", "latest", "according",
}

def _extract_topic_keys(titulo: str) -> frozenset[str]:
    """Extract thematic keywords from the title (entities, proper nouns, technical terms).
    Returns a set of the 2-4 most significant words representing the subject."""
    norm = (titulo or "").lower().strip()
    norm = _PUNCT_RE.sub(" ", norm)
    all_noise = _STOPWORDS | _TOPIC_NOISE
    palavras = [p for p in norm.split() if p not in all_noise and len(p) > 2]
    # Prioritize: capitalized words in the original (proper nouns)
    original_words = (titulo or "").split()
    capitalized = set()
    for w in original_words:
        wl = _PUNCT_RE.sub("", w).lower()
        if w and w[0].isupper() and len(wl) > 2 and wl not in all_noise:
            capitalized.add(wl)
    # Combine: proper nouns first, then other significant words
    ordered = [p for p in palavras if p in capitalized]
    ordered += [p for p in palavras if p not in capitalized]
    # Take the 8 most significant words (more coverage for similar topic overlap)
    keys = ordered[:8]
    if len(keys) < 2:
        return frozenset()  # Too generic for topic dedup
    return frozenset(keys)

# ---- Entity-overlap dedup (replaces exact fingerprint match) ----
# Stores entity groups per article; dedup when 2+ entities match
_ENTITY_OVERLAP_MIN = int(os.getenv("ENTITY_OVERLAP_MIN", "3"))  # minimum shared entities to consider duplicate

def _get_entity_groups(h: dict) -> list:
    """Return list of {keys: [str], ts: int} from recent articles."""
    g = h.get("_entity_groups")
    return g if isinstance(g, list) else []

def _entity_groups_prune(groups: list) -> list:
    cutoff = int(time.time()) - (TOPIC_IDX_TTL_HORAS * 3600)
    return [g for g in groups if g.get("ts", 0) >= cutoff]

_entity_pruned_this_cycle = False

def _ensure_entity_pruned(h: dict) -> list:
    global _entity_pruned_this_cycle
    groups = _get_entity_groups(h)
    if not _entity_pruned_this_cycle:
        groups = _entity_groups_prune(groups)
        if len(groups) > 400:
            groups = groups[-400:]
        h["_entity_groups"] = groups
        _entity_pruned_this_cycle = True
    return groups

def topic_is_dup(h: dict, titulo: str) -> bool:
    """Check if the topic/subject was already covered (2+ entity overlap)."""
    keys = _extract_topic_keys(titulo)
    if len(keys) < _ENTITY_OVERLAP_MIN:
        return False
    groups = _ensure_entity_pruned(h)
    for g in groups:
        past_keys = set(g.get("keys", []))
        if len(keys & past_keys) >= _ENTITY_OVERLAP_MIN:
            return True
    return False

def topic_add(h: dict, titulo: str) -> None:
    """Register article entities for future dedup."""
    keys = _extract_topic_keys(titulo)
    if len(keys) < 2:
        return
    groups = _ensure_entity_pruned(h)
    groups.append({"keys": sorted(keys), "ts": int(time.time())})
    h["_entity_groups"] = groups

# SimHash index in history
def _get_simhash_index(h: dict) -> dict[str, int]:
    idx = h.get("_simhash_idx")
    return idx if isinstance(idx, dict) else {}

MAX_SIMHASH_INDEX = 500

def _simhash_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (SIMHASH_TTL_HORAS * 3600)
    pruned = {k: ts for k, ts in idx.items() if ts >= cutoff}
    # Limit size: keep only the most recent
    if len(pruned) > MAX_SIMHASH_INDEX:
        sorted_items = sorted(pruned.items(), key=lambda x: x[1], reverse=True)
        pruned = dict(sorted_items[:MAX_SIMHASH_INDEX])
    return pruned

_simhash_pruned_this_cycle = False

def _ensure_simhash_pruned(h: dict) -> dict[str, int]:
    """Prune the index only once per cycle."""
    global _simhash_pruned_this_cycle
    idx = _get_simhash_index(h)
    if not _simhash_pruned_this_cycle:
        idx = _simhash_prune(idx)
        h["_simhash_idx"] = idx
        _simhash_pruned_this_cycle = True
    return idx

def simhash_is_dup(h: dict, sh: int) -> bool:
    if sh == 0:
        return False
    idx = _ensure_simhash_pruned(h)
    for hexv in idx.keys():
        try:
            if _hamming(sh, int(hexv, 16)) <= SIMHASH_HAMMING_MAX:
                return True
        except Exception:
            continue
    return False

def simhash_add(h: dict, sh: int) -> None:
    if sh == 0:
        return
    idx = _ensure_simhash_pruned(h)
    idx[f"{sh:016x}"] = int(time.time())
    h["_simhash_idx"] = idx

# =========================
# TITLE INDEX (cross-site dedup)
# =========================
def _get_title_index(h: dict) -> dict[str, int]:
    idx = h.get("_title_idx")
    return idx if isinstance(idx, dict) else {}

MAX_TITLE_INDEX = 500

def _title_idx_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (TITLE_IDX_TTL_HORAS * 3600)
    pruned = {k: ts for k, ts in idx.items() if ts >= cutoff}
    # Limit size: keep only the most recent
    if len(pruned) > MAX_TITLE_INDEX:
        sorted_items = sorted(pruned.items(), key=lambda x: x[1], reverse=True)
        pruned = dict(sorted_items[:MAX_TITLE_INDEX])
    return pruned

_title_pruned_this_cycle = False

def _ensure_title_pruned(h: dict) -> dict[str, int]:
    """Prune the index only once per cycle."""
    global _title_pruned_this_cycle
    idx = _get_title_index(h)
    if not _title_pruned_this_cycle:
        idx = _title_idx_prune(idx)
        h["_title_idx"] = idx
        _title_pruned_this_cycle = True
    return idx

def title_is_dup(h: dict, titulo: str) -> bool:
    """Check if a normalized title was already processed (any site)."""
    fp = _title_fingerprint(titulo)
    idx = _ensure_title_pruned(h)
    return fp in idx

def title_add(h: dict, titulo: str) -> None:
    """Register title in the index for future dedup."""
    fp = _title_fingerprint(titulo)
    idx = _ensure_title_pruned(h)
    idx[fp] = int(time.time())
    h["_title_idx"] = idx

# =========================
# IMAGE EXTRACTION
# =========================
IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif)(?:\?|#|$)", re.IGNORECASE)
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
OG_IMG_RE = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\']og:image(?::\w+)?["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
OG_IMG_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\']og:image(?::\w+)?["\']',
    re.IGNORECASE | re.DOTALL,
)

def _norm_img_url(img: str, base: Optional[str] = None) -> Optional[str]:
    if not img:
        return None
    u = img.strip()
    if u.startswith("//"):
        u = "https:" + u
    # Convert HTTP to HTTPS (many sites block HTTP or redirect)
    if u.startswith("http://"):
        u = "https://" + u[7:]
    if base and u.startswith("/"):
        try:
            u = urljoin(base, u)
        except Exception:
            pass
    return u

def extrair_imagem_rss(entry, feed_url: str) -> Optional[str]:
    """Extract image URL from RSS entry (no HTTP)."""
    img = None
    try:
        if "media_content" in entry and entry.media_content and len(entry.media_content) > 0:
            img = _norm_img_url(entry.media_content[0].get("url", ""), feed_url)
        if not img and "media_thumbnail" in entry and entry.media_thumbnail and len(entry.media_thumbnail) > 0:
            img = _norm_img_url(entry.media_thumbnail[0].get("url", ""), feed_url)
        if not img and "enclosures" in entry:
            for e in entry.enclosures:
                if "image" in (e.get("type") or "") or IMG_EXT_RE.search(e.get("href") or ""):
                    img = _norm_img_url(e.get("href"), feed_url)
                    break
        if not img:
            content = ""
            if "content" in entry and entry.content and len(entry.content) > 0:
                content = entry.content[0].get("value", "")
            summary = entry.get("summary", "")
            m = IMG_SRC_RE.search(content) or IMG_SRC_RE.search(summary)
            if m:
                img = _norm_img_url(m.group(1), feed_url)
    except Exception as e:
        log.debug(f"Error extracting RSS image: {e}")
    return img

async def fetch_og_image(url: str, retries: int = 2) -> Optional[str]:
    """Fetch og:image from the page as fallback, with retry."""
    if not http_session:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    for attempt in range(retries):
        try:
            async with http_session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status >= 500:
                    continue  # retry on 5xx
                if r.status != 200:
                    return None
                raw = await r.content.read(1_000_000)  # max 1MB
                html = raw.decode("utf-8", errors="replace")
                m = OG_IMG_RE.search(html) or OG_IMG_RE_ALT.search(html)
                if m:
                    return _norm_img_url(m.group(1), url)
                return None
        except Exception as e:
            log.debug(f"og:image attempt {attempt+1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
    return None

MIN_IMG_WIDTH = 400
MIN_IMG_HEIGHT = 200

def _img_dimensions_from_bytes(data: bytes) -> Optional[Tuple[int, int]]:
    """Extract (width, height) from PNG, JPEG, or GIF headers without external libs."""
    if len(data) < 24:
        return None
    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) >= 24:
            w = struct.unpack(">I", data[16:20])[0]
            h = struct.unpack(">I", data[20:24])[0]
            return w, h
    # GIF
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w = struct.unpack("<H", data[6:8])[0]
        h = struct.unpack("<H", data[8:10])[0]
        return w, h
    # JPEG
    if data[:2] == b"\xff\xd8":
        idx = 2
        while idx < len(data) - 9:
            # Skip 0xFF padding bytes
            while idx < len(data) - 1 and data[idx] == 0xFF and data[idx + 1] == 0xFF:
                idx += 1
            if idx >= len(data) - 9 or data[idx] != 0xFF:
                break
            marker = data[idx + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h = struct.unpack(">H", data[idx + 5 : idx + 7])[0]
                w = struct.unpack(">H", data[idx + 7 : idx + 9])[0]
                return w, h
            seg_len = struct.unpack(">H", data[idx + 2 : idx + 4])[0]
            if seg_len < 2:
                break  # malformed segment
            idx += 2 + seg_len
    # WebP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8 " and len(data) >= 30:
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return w, h
        if data[12:16] == b"VP8L" and len(data) >= 25:
            bits = struct.unpack("<I", data[21:25])[0]
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
            return w, h
        # VP8X (extended WebP — most common modern format)
        if data[12:16] == b"VP8X" and len(data) >= 30:
            w = (data[24] | (data[25] << 8) | (data[26] << 16)) + 1
            h = (data[27] | (data[28] << 8) | (data[29] << 16)) + 1
            return w, h
    return None

async def validar_imagem(url: str) -> bool:
    """Check if URL is a valid image (>5KB, status 200/206, minimum dimensions)."""
    if not url:
        return False
    if not http_session:
        return bool(IMG_EXT_RE.search(url))
    try:
        async with http_session.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-32767"},
            timeout=aiohttp.ClientTimeout(total=8),
            allow_redirects=True,
        ) as r:
            if r.status not in (200, 206):
                return False
            ct = r.headers.get("Content-Type", "").lower()
            if "image/" not in ct:
                return False
            # Check total size
            cr = r.headers.get("Content-Range", "")
            if cr and "/" in cr:
                total = cr.rsplit("/", 1)[-1]
                if total.isdigit() and int(total) < 5000:
                    return False
            else:
                cl = r.headers.get("Content-Length", "")
                if cl.isdigit() and int(cl) < 5000:
                    return False
            # Read initial bytes to check dimensions
            chunk = await r.content.read(32768)
            dims = _img_dimensions_from_bytes(chunk)
            if dims:
                w, h = dims
                if w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT:
                    log.info(f"Image rejected by dimensions: {w}x{h} ({url[:80]})")
                    return False
                # Reject extreme aspect ratio (banners, cropped images)
                ratio = w / h if h > 0 else 0
                if ratio > 4.0 or ratio < 0.3:
                    log.info(f"Image rejected by aspect ratio ({ratio:.2f}): {w}x{h} ({url[:80]})")
                    return False
            return True
    except Exception as e:
        log.debug(f"Error validating image {url}: {e}")
    return False

async def extrair_imagem_completa(entry, feed_url: str) -> Optional[str]:
    """Full pipeline: RSS → HTTP validation → mandatory og:image fallback."""
    img = extrair_imagem_rss(entry, feed_url)
    # If RSS image is valid, return it
    if img and await validar_imagem(img):
        log.debug(f"Image extracted via RSS: {img[:80]}")
        return img
    
    # MANDATORY fallback: page og:image (even if RSS returned something invalid)
    link = entry.get("link")
    if link:
        log.debug(f"RSS failed, fetching og:image for: {link[:80]}")
        og = await fetch_og_image(link)
        if og and await validar_imagem(og):
            log.info(f"Image recovered via og:image: {og[:80]}")
            return og
        elif og:
            log.warning(f"og:image found but invalid: {og[:80]}")
    
    log.warning(f"No valid image found for: {entry.get('title', '?')[:60]}")
    return None


async def validar_imagem_ia(img_url: str, titulo: str) -> bool:
    """Use vision AI to verify the image matches the title."""
    if not ai_client or not img_url or not titulo:
        return True  # No AI available — assume valid (do not block)
    try:
        resp = await ai_client.chat.completions.create(
            model="google/gemini-3.1-flash-lite",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an image validator for a tech news bot. "
                        "Analyze whether the image relates to the news title. "
                        "Reply ONLY 'YES' if the image is relevant to the news topic, "
                        "or 'NO' if the image is completely irrelevant (e.g. ad, random product, "
                        "generic logo, lawn mower in a cybersecurity story, etc). "
                        "Generic tech images (keyboards, screens, servers) are acceptable "
                        "for tech news. Reply only YES or NO, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"News title: {titulo}"},
                        {"type": "image_url", "image_url": {"url": img_url}},
                    ],
                },
            ],
            max_tokens=5,
            temperature=0.0,
            timeout=15.0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        relevante = "YES" in answer or (answer.startswith("Y") and "NO" not in answer) or "SIM" in answer
        if not relevante:
            log.info(f"AI rejected image as irrelevant: {img_url[:80]} | title: {titulo[:60]}")
        return relevante
    except Exception as e:
        log.debug(f"Error in AI image validation: {e}")
        return True  # On error, do not block

# =========================
# AI ANALYSIS (OpenRouter)
# =========================
def _fix_sentence_case(text: str) -> str:
    """Convert Title Case to sentence case when detected."""
    words = text.split()
    if not words:
        return text
    long_words = [w for w in words if len(w) > 3 and not w[0].isdigit()]
    if not long_words:
        return text
    capitalized_ratio = sum(1 for w in long_words if w[0].isupper()) / len(long_words)
    if capitalized_ratio < 0.6:
        return text  # Not Title Case — leave unchanged
    # Convert to sentence case: lowercase, then capitalize after sentence-ending punctuation
    result = text.lower()
    result = result[0].upper() + result[1:] if result else result
    for punct in [". ", "! ", "? "]:
        parts = result.split(punct)
        result = punct.join(p[0].upper() + p[1:] if p else p for p in parts)
    return result


def _normalize_news_title(title: str) -> str:
    """Standardize titles to direct journalistic format (max 90 chars, sentence case)."""
    t = re.sub(r"\s+", " ", (title or "").strip())
    if not t:
        return t
    # Remove leading emoji/symbols to avoid duplicating urgency marker in embed.
    t = re.sub(r"^[^\wÀ-ÿ]+", "", t).strip()
    # Remove stray quotes and punctuation at start/end.
    t = t.strip(" -:;,.!?\"'`")
    # Strip common clickbait patterns.
    t = re.sub(r"(?i)\b(voc[eê] n[aã]o vai acreditar|imperd[ií]vel|chocante|surpreendente)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = _fix_sentence_case(t)
    
    # Keep common acronyms uppercase after normalization
    acronyms = ("IA", "EUA", "UE", "UK", "API", "CVE", "CEO", "GPU", "CPU", "AI")
    for ac in acronyms:
        t = re.sub(rf"\b{ac.lower()}\b", ac, t, flags=re.IGNORECASE)
    
    # Proper names to translate or capitalize (user-facing PT-BR output)
    proper_names = {
        "xbox": "Xbox",
        "windows": "Windows",
        "playstation": "PlayStation",
        "nintendo": "Nintendo",
        "iphone": "iPhone",
        "ipad": "iPad",
        "macbook": "MacBook",
        "android": "Android",
        "ios": "iOS",
        "google": "Google",
        "microsoft": "Microsoft",
        "apple": "Apple",
        "amazon": "Amazon",
        "meta": "Meta",
        "tesla": "Tesla",
        "facebook": "Facebook",
        "instagram": "Instagram",
        "whatsapp": "WhatsApp",
        "twitter": "Twitter",
        "linkedin": "LinkedIn",
        "discord": "Discord",
        "spotify": "Spotify",
        "netflix": "Netflix",
        "youtube": "YouTube",
        "zoom": "Zoom",
        "intel": "Intel",
        "amd": "AMD",
        "nvidia": "Nvidia",
        "samsung": "Samsung",
        "sony": "Sony",
        "reddit": "Reddit",
        "tiktok": "TikTok",
        "snapchat": "Snapchat",
        "pinterest": "Pinterest",
        # Game/character names (translate for user-facing output)
        "mr. karate": "Senhor Karatê",
        "mr.karate": "Senhor Karatê",
        "fatal fury": "Fatal Fury",
        "city of the wolves": "Cidade dos Lobos",
        "pragmata": "Pragmata",
        "re requiem": "RE: Requiem",
        "phantom blade zero": "Phantom Blade Zero",
        "gamescom": "Gamescom",
    }
    # Multi-word proper names — apply first
    multi_proper = {
        "estados unidos": "Estados Unidos",
        "reino unido": "Reino Unido",
        "coreia do sul": "Coreia do Sul",
        "coreia do norte": "Coreia do Norte",
        "nova york": "Nova York",
        "são francisco": "São Francisco",
        "silicon valley": "Silicon Valley",
        "double fine": "Double Fine",
        "call of duty": "Call of Duty",
        "world of warcraft": "World of Warcraft",
        "league of legends": "League of Legends",
        "grand theft auto": "Grand Theft Auto",
        "communications workers of america": "Communications Workers of America",
        "open ai": "OpenAI",
        "deep seek": "DeepSeek",
        "black myth": "Black Myth",
        "star wars": "Star Wars",
    }
    for lower_name, correct_name in multi_proper.items():
        t = re.sub(re.escape(lower_name), correct_name, t, flags=re.IGNORECASE)

    for lower_name, correct_name in proper_names.items():
        t = re.sub(rf"\b{re.escape(lower_name)}\b", correct_name, t, flags=re.IGNORECASE)
    
    # Ensure at least 6 words (when original has them)
    words = t.split()
    min_words = 6
    if len(words) < min_words and len(t) <= 130:
        # Short title — keep original if not too long
        pass
    else:
        # Limit length to ~3 lines max (130 chars) while preserving words
        max_len = 130
        if len(t) > max_len:
            cut = t[:max_len]
            # Cut at last space to avoid breaking a word
            last_space = cut.rfind(" ")
            if last_space >= 55:  # at least 55 chars to fit 6 words
                cut = cut[:last_space]
            # If cut has fewer than 6 words, try to recover
            if len(words) >= min_words and len(cut.split()) < min_words:
                # Back up to the 6th space
                space_count = 0
                pos = 0
                for i, ch in enumerate(t):
                    if ch == ' ':
                        space_count += 1
                        if space_count == min_words:
                            pos = i
                            break
                if pos > 0:
                    cut = t[:pos].rstrip(" ,;:-")
            t = cut.rstrip(" ,;:-") + ("" if len(t) <= max_len else "...")
        else:
            t = t  # keep original if <= max_len
    if t:
        t = t[0].upper() + t[1:]
    return t


_INSTITUTION_NOUNS = (
    "governo",
    "ministério",
    "ministerio",
    "justiça",
    "justica",
    "anatel",
    "anpd",
    "cade",
    "congresso",
    "supremo",
    "tribunal",
    "prefeitura",
    "agência",
    "agencia",
    "administração",
    "administracao",
)


def _corrigir_prefixos_estranhos(frase: str) -> str:
    s = re.sub(r"\s+", " ", (frase or "").strip())
    if not s:
        return ""

    # Avoid bad semantic constructions like "A empresa governo federal".
    if re.match(rf"(?i)^a empresa\s+(?:{'|'.join(_INSTITUTION_NOUNS)})\b", s):
        s = re.sub(r"(?i)^a empresa\s+", "O ", s, count=1)
    if re.match(rf"(?i)^a startup\s+(?:{'|'.join(_INSTITUTION_NOUNS)})\b", s):
        s = re.sub(r"(?i)^a startup\s+", "O ", s, count=1)

    return s


def _limitar_palavras(frase: str, max_palavras: int = 35) -> str:
    tokens = [t for t in (frase or "").split() if t]
    if len(tokens) <= max_palavras:
        return frase.strip()
    return " ".join(tokens[:max_palavras]).rstrip(",:;")


def _normalizar_resumo_final(texto: str) -> str:
    """
    Process summary to ensure correct format and 1000-char limit.
    Remove odd semantic constructions and ensure natural flow.
    """
    bruto = re.sub(r"\s+", " ", (texto or "").strip())
    if not bruto:
        return ""

    # Ensure trailing punctuation
    if not bruto[-1] in ".!?":
        bruto += "."

    # Limit to 1000 chars, cutting gracefully at last sentence end
    if len(bruto) > 1000:
        corte = bruto[:1000]
        ultimo_ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
        if ultimo_ponto > 400:
            bruto = corte[:ultimo_ponto + 1]
        else:
            bruto = corte.rstrip() + "..."
    
    # Fix sentence case formatting
    frases = []
    for parte in re.split(r"[.!?]+", bruto):
        parte = parte.strip()
        if not parte:
            continue
        parte = _corrigir_prefixos_estranhos(parte)
        parte = _fix_sentence_case(parte)
        if not parte:
            continue
        if not parte[0].isupper():
            parte = parte[0].upper() + parte[1:]
        if not parte.endswith("."):
            parte += "."
        frases.append(parte)
    
    resultado = " ".join(frases)
    log.info(f"Final summary: {len(resultado)} characters")
    
    return resultado if len(resultado) >= 50 else ""



_last_ai_call = 0.0
_ai_calls_this_cycle = 0
_vision_calls_this_cycle = 0

async def gerar_analise_ia(texto_base: str, titulo_original: str, nome_site: str) -> Optional[dict]:
    global _last_ai_call
    if not ai_client:
        return None

    # Cooldown between calls
    now = time.monotonic()
    wait = (_last_ai_call + IA_COOLDOWN_SEC) - now
    if wait > 0:
        await asyncio.sleep(wait)
    # Update timestamp BEFORE the call (protects against exceptions)
    _last_ai_call = time.monotonic()

    prompt = f"""Analyze the news article below and reply ONLY with valid JSON, no markdown.

OUTPUT LANGUAGE: Write "titulo", "resumo", and "categoria" in Brazilian Portuguese (PT-BR).
Keep JSON keys exactly as shown. The "reason" field (when rejecting) may be in English.

STRICT TITLE RULES (NON-NEGOTIABLE):
- The "titulo" field MUST have BETWEEN 6 AND 11 WORDS.
- SHORT AND DIRECT: must never exceed 3 lines on screen.
- TITLE TOO SHORT (< 6 words) = REJECTION. Minimum: 6 words. Maximum: 11.
- If the original title has fewer than 6 words, EXPAND it with journalistic context.
- Examples:
  ✗ "Meta processada" (2 words - REJECTED)
  ✗ "OpenAI lança GPT-5" (4 words - REJECTED)
  ✓ "Meta enfrenta processo milionário por uso indevido de livros" (9 words - ACCEPTED)
  ✓ "ChatGPT reduz alucinações em aplicações médicas e jurídicas" (8 words - ACCEPTED)

REPLY IN ONE OF TWO FORMATS:
1. IF REJECTING: {{"pular": true, "reason": "short reason"}}
2. IF APPROVING: {{"pular": false, "titulo": "...", "nota": 85, "categoria": "...", "resumo": "..."}}

═══ IMMEDIATE BLOCK RULES (pular=true) ═══
- Promotion, deal, coupon, discount, price, cashback, affiliate, buying guide, "worth buying".
- Review, product analysis, comparison, unboxing, "best value for money".
- Gossip, drama, non-tech politics, celebrity, sports, horoscope, generic entertainment.
- Generic science unrelated to tech (biology, paleontology, archaeology, pure astronomy).
- Vague content, substance-free clickbait, unsourced rumor, repetitive news.
- Mid-range/budget smartphones: Galaxy A/M, Moto G/E, Redmi Note, basic POCO, "arrived in Brazil" without innovation.
- Games: reviews, skins, cosmetics, minor patch notes, weekly events, item shop, prices, game promotions.

═══ CATEGORIES (use exactly one of these, in PT-BR) ═══
Hardware | Inteligência Artificial | Games | Cibersegurança | Sistemas Operacionais | Smartphones | Big Techs | Ciência & Espaço | Software & Apps | Cloud & DevOps | Programação & Dev | Internet & Redes | Mídia & Streaming | Curiosidade Tech | Outros

═══ SCORE SCALE (be strict) ═══
- 95-100: CATASTROPHE or GLOBAL MILESTONE. Global service outage, massive hack, new-generation launch (iPhone, Windows, new GPT).
- 85-94: HIGH RELEVANCE. Major confirmed news, critical vulnerability (high CVE), billion-dollar acquisition, mass layoffs.
- 75-84: RELEVANT. Interesting for tech enthusiasts, significant update, major platform feature.
- <75: IRRELEVANT — set pular=true.

═══ TITLE (titulo field, PT-BR) ═══
- REQUIRED: EXACTLY 6 TO 11 WORDS. NEVER FEWER THAN 6.
- SHORT AND DIRECT: must never exceed 3 lines on screen. Prefer the most concise form that still explains the fact.
- Clear, journalistic, self-explanatory. Reader understands the fact without clicking.
- In PT-BR. Common tech jargon may stay in English: "phishing", "ransomware", "zero-day", "malware", "exploit", "hacker", "Windows", "iPhone", "ChatGPT", "Google", "Android", "API", "Linux", "Wi-Fi", "Bluetooth", etc.
- BUT the title must be CLEAR and READABLE for any tech enthusiast. Forbidden:
  ✗ Portuguese-ing verbs from English: "hijacka", "bypassa", "patcha" — use: "sequestra", "burla", "corrige".
  ✗ Stacking jargon without context: "Kit de phishing Tycoon2FA hijacka contas via device-code phishing" — incomprehensible.
  ✗ Obscure tool/malware names in title: move to resumo. Ex: "Tycoon2FA" → resumo.
  ✓ GOOD: "Novo golpe de phishing rouba contas do Microsoft 365"
  ✓ GOOD: "Falha zero-day no Chrome permite execução de código remoto"
  ✓ GOOD: "Ransomware ataca hospitais nos EUA e paralisa sistemas"
- No clickbait. Sentence case: only first word and proper nouns capitalized.
- Between 50 and 110 characters. Count words BEFORE sending.
- GOOD TITLE EXAMPLES (short):
  ✓ "Meta enfrenta processo milionário por uso indevido de livros"
  ✓ "ChatGPT reduz erros em aplicações médicas e jurídicas"
  ✓ "Novo golpe de phishing rouba contas do Microsoft 365"
  ✗ "Meta processada" (BAD: only 2 words)
  ✗ "Kit de phishing Tycoon2FA hijacka contas via device-code" (BAD: Portuguese-ing verbs + obscure jargon)

═══ SUMMARY (resumo field, PT-BR) ═══
- One continuous paragraph, 4 to 6 sentences. No bullet points, no line breaks.
- Engaging tech-journalism style: contextualized, explains the fact, why it matters, and real impact.
- Structure: CONTEXT/HOOK → MAIN FACT → RELEVANT DETAIL → IMPACT or REACTION.
- Journalistic but accessible: not dry, not academic, not telegraphic. Help the reader understand why it matters.
- DO NOT repeat the same idea with different words. Each sentence must add NEW information.
- FORBIDDEN filler phrases such as:
  ✗ "pode ter implicações significativas" / "o que pode ser um grande diferencial"
  ✗ "além disso, essa novidade pode influenciar..." / "isso pode impactar o mercado"
  ✗ "a comunidade aguarda com expectativa" / "destaca a importância de..."
  ✗ Any sentence that could be pasted into ANY news without changing anything. Each sentence must contain CONCRETE FACTS from the article.
- FORBIDDEN to invent information or confuse companies/products. If the article does not mention a fact, DO NOT invent it.
- In PT-BR with impeccable grammar.
- LIMIT: between 600 and 1000 characters. Do not exceed 1000.

═══ SPECIAL FILTERS ═══
SMARTPHONES: Accept ONLY flagships (iPhone, Galaxy S/Z, Pixel Pro, Xiaomi Ultra) or real innovation.
GAMES: Accept ONLY major confirmed AAA launches, major events (TGA, E3, Nintendo Direct), studio acquisitions, or mass layoffs (100+ employees). Reject: unions, labor rights, strikes, collective bargaining, old game source leaks, mods, console hacks, cheats, balance patches, battle pass seasons, internal studio drama.
CYBERSECURITY: Prioritize critical CVE, ransomware, data breach, zero-day. Score ≥85.

Source: {nome_site}
Original Title: {titulo_original}
Article Text: {texto_base[:8000]}
"""

    modelo_principal = "google/gemini-3.1-flash-lite"
    modelo_fallback = "google/gemini-3.1-flash-lite"

    for attempt in range(3):
        modelo = modelo_principal if attempt == 0 else modelo_fallback
        log.info(f"AI attempt {attempt+1}/3 using model: {modelo}")
        try:
            response = await ai_client.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": (
                        "Reply ONLY with valid JSON, no markdown, no text outside JSON. "
                        "CRITICAL RULES: "
                        "1) Output titulo, resumo, and categoria in Brazilian Portuguese (PT-BR) — clear and readable; "
                        "common tech jargon may stay in English; never Portuguese-ize English verbs or stack obscure terms. "
                        "2) Resumo: one dense paragraph, 4-6 sentences, 600-1000 characters. "
                        "Each sentence must contain CONCRETE FACTS from the article — "
                        "FORBIDDEN generic filler (e.g. 'may have significant implications', 'highlights the importance of'). "
                        "3) NEVER invent information not present in the article."
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                timeout=60.0,
            )
            resp = response.choices[0].message.content.strip()
            # Discard absurdly large responses (avoids hang during parsing)
            if len(resp) > 50_000:
                log.error("AI response too large (%d chars), discarding", len(resp))
                continue
            # Extract JSON: find the first valid JSON object
            json_start = resp.find("{")
            data = None
            if json_start >= 0:
                depth = 0
                json_end = -1
                for i, ch in enumerate(resp[json_start:], json_start):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            json_end = i + 1
                            break
                if json_end > 0:
                    try:
                        data = json.loads(resp[json_start:json_end])
                    except json.JSONDecodeError:
                        pass
            if data:
                if isinstance(data.get("resumo"), str):
                    data["resumo"] = _normalizar_resumo_final(data["resumo"])
                    if not data["resumo"]:
                        log.warning("Empty summary after normalization, rejecting")
                        return None
                if isinstance(data.get("titulo"), str):
                    data["titulo"] = _normalize_news_title(data["titulo"])
                return data
        except Exception as e:
            log.warning(f"AI attempt {attempt+1}/3 failed ({modelo}): {e}")
            if attempt < 2:
                backoff = 2 ** (attempt + 1)
                log.info(f"Waiting {backoff}s before next attempt...")
                await asyncio.sleep(backoff)
    return None

# =========================
# ENTRY UTILS
# =========================
def entry_datetime_utc(entry) -> Optional[datetime]:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
    except Exception:
        return None

def noticia_eh_recente(entry_dt: Optional[datetime]) -> bool:
    """Return True only if the news has a date and is recent. No date = reject."""
    if not entry_dt:
        return False
    return entry_dt >= datetime.now(timezone.utc) - timedelta(hours=MAX_IDADE_HORAS)

# =========================
# POST NEWS (extracted for reuse)
# =========================
async def _baixar_imagem(url: str, retries: int = 3) -> Optional[tuple[bytes, str]]:
    """Download image and return (bytes, extension). Retries on failure.
    Validates minimum dimensions and aspect ratio to avoid cropped images/banners."""
    if not http_session or not url:
        return None
    for attempt in range(retries):
        try:
            async with http_session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as r:
                if r.status not in (200, 206):
                    log.debug(f"Image HTTP {r.status}: {url[:80]} (attempt {attempt+1})")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                ct = r.headers.get("Content-Type", "").lower()
                if "image/" not in ct:
                    log.debug(f"Image invalid Content-Type ({ct}): {url[:80]}")
                    return None
                # Check Content-Length before download (reject > 10MB)
                cl_header = r.headers.get("Content-Length", "")
                expected_size = int(cl_header) if cl_header.isdigit() else 0
                if expected_size > 10 * 1024 * 1024:
                    log.debug(f"Image too large ({expected_size} bytes): {url[:80]}")
                    return None
                data = await r.read()  # read full response (no truncation)
                if len(data) > 10 * 1024 * 1024:
                    log.debug(f"Image too large ({len(data)} bytes): {url[:80]}")
                    return None
                if len(data) < 5000:
                    log.debug(f"Image too small ({len(data)} bytes): {url[:80]}")
                    return None
                # Verify integrity: Content-Length vs bytes received
                if expected_size and len(data) < expected_size:
                    log.warning(f"Incomplete image ({len(data)}/{expected_size} bytes): {url[:80]}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                # Validate full image dimensions (avoids cropped/corrupted images)
                dims = _img_dimensions_from_bytes(data)
                if dims:
                    w, h = dims
                    if w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT:
                        log.warning(f"Downloaded image rejected: {w}x{h} < {MIN_IMG_WIDTH}x{MIN_IMG_HEIGHT} ({url[:80]})")
                        return None
                    # Reject extreme aspect ratio (thin banners, very tall images)
                    ratio = w / h if h > 0 else 0
                    if ratio > 4.0 or ratio < 0.3:
                        log.warning(f"Image rejected by aspect ratio ({ratio:.2f}): {w}x{h} ({url[:80]})")
                        return None
                else:
                    # Could not extract dimensions — reject (possibly corrupted image)
                    log.warning(f"Image rejected: cannot extract dimensions ({url[:80]})")
                    return None
                # Validate magic bytes and EOF integrity
                if data[:2] == b'\xff\xd8':
                    ext = "jpg"
                    # JPEG must end with FFD9 (End of Image)
                    if data[-2:] != b'\xff\xd9':
                        log.warning(f"Truncated JPEG (no EOF marker): {url[:80]}")
                        if attempt < retries - 1:
                            await asyncio.sleep(2)
                        continue
                elif data[:4] == b'\x89PNG':
                    ext = "png"
                    # PNG must end with IEND chunk
                    if b'IEND' not in data[-20:]:
                        log.warning(f"Truncated PNG (no IEND): {url[:80]}")
                        if attempt < retries - 1:
                            await asyncio.sleep(2)
                        continue
                elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                    ext = "webp"
                elif data[:4] == b'GIF8':
                    ext = "gif"
                else:
                    # Fallback from content-type
                    ext = "jpg"
                    if "png" in ct:
                        ext = "png"
                    elif "webp" in ct:
                        ext = "webp"
                    elif "gif" in ct:
                        ext = "gif"
                return data, ext
        except Exception as e:
            log.debug(f"Error downloading image {url[:80]} (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
    return None


async def _postar_noticia(channel, noticia: dict, history: dict, metrics: dict) -> bool:
    """Post a news item to the channel. Returns True if posted successfully."""
    # Safety lock: never post without image
    img_url = noticia.get("imagem")
    if not img_url:
        log.error(f"Attempt to post without image, aborting: {noticia.get('titulo', '')[:60]}")
        return False

    # Download image for attachment (avoids hotlink protection / URLs Discord won't load)
    img_data = await _baixar_imagem(img_url)
    if not img_data:
        log.warning(f"Failed to download image, aborting post: {noticia.get('titulo', '')[:60]}")
        return False

    img_bytes, img_ext = img_data
    img_id = hashlib.md5(img_bytes[:1024]).hexdigest()[:8]
    img_filename = f"noticia_{img_id}.{img_ext}"
    attachment = discord.File(io.BytesIO(img_bytes), filename=img_filename)

    emoji = EMOJIS_CATEGORIA.get(noticia["categoria"], "🔌")

    titulo_embed = f"{'🚨 ' if noticia['nota'] >= NOTA_URGENTE else ''}{noticia['titulo']}"
    resumo_embed = noticia["resumo"]
    # Discord limits: title 256 chars, description 4096 chars
    if len(titulo_embed) > 256:
        titulo_embed = titulo_embed[:253] + "..."
    if len(resumo_embed) > 4096:
        resumo_embed = resumo_embed[:4093] + "..."
    embed = discord.Embed(
        title=titulo_embed,
        url=noticia["link"],
        description=resumo_embed,
        color=CORES_CATEGORIA.get(noticia["categoria"], COR_PADRAO),
    )
    embed.set_author(
        name=f"Via {noticia['site']} • {noticia['categoria']} {emoji}",
        icon_url="https://cdn-icons-png.flaticon.com/512/2965/2965363.png",
    )
    embed.set_image(url=f"attachment://{img_filename}")
    embed.add_field(
        name="",
        value=f"👉 **[Clique aqui para ler a matéria completa]({noticia['link']})**",
        inline=False,
    )

    texto_rodape = "Notícia resumida por IA"
    if noticia["is_eng"]:
        texto_rodape += " • Fonte em inglês"
    embed.set_footer(text=texto_rodape)

    global _daily_mention_news, _daily_mention_news_date
    # Mention role only for urgent news (score >= 90), max 3 per day
    hoje_br = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
    if hoje_br != _daily_mention_news_date:
        _daily_mention_news_date = hoje_br
        _daily_mention_news = 0
    try:
        mention = None
        if noticia["nota"] >= NOTA_URGENTE and ID_CARGO_PARA_MARCAR and _daily_mention_news < 3:
            guild = getattr(channel, "guild", None)
            if guild and guild.get_role(ID_CARGO_PARA_MARCAR):
                mention = f"<@&{ID_CARGO_PARA_MARCAR}>"
        msg = await channel.send(
            content=mention,
            embed=embed,
            file=attachment,
        )
        try:
            thread_name = f"💬 {noticia['categoria']}: {noticia['titulo'][:80]}"
            if len(thread_name) > 100:
                thread_name = thread_name[:97] + "..."
            await msg.create_thread(
                name=thread_name,
                auto_archive_duration=1440,
            )
        except Exception as e:
            log.warning(f"Error creating thread: {e}")

        historico_set(history, noticia["link_norm"], noticia["dedupe"], "posted")
        metric_inc(metrics, "posts_hoje")
        if mention:
            _daily_mention_news += 1
        log.info(f"  📨 Posted: {noticia['titulo'][:60]}")
        return True
    except Exception as e:
        log.error(f"  Error posting: {e}")
        return False

# =========================
# MAIN PIPELINE
# =========================
# Global state for /status
_last_cycle_time: str = "Nunca"
_last_cycle_stats: dict = {}
# Daily counter for news role mentions (max 3 per day)
_daily_mention_news: int = 0
_daily_mention_news_date: str = ""


@tasks.loop(time=_NEWS_SCHEDULE)
async def verificar_feeds():
    try:
        await _verificar_feeds_inner()
    except Exception as e:
        log.exception(f"Fatal error in news cycle: {e}")

async def _verificar_feeds_inner():
    global _ai_calls_this_cycle, _vision_calls_this_cycle, http_session, _last_cycle_time, _last_cycle_stats
    global _simhash_pruned_this_cycle, _title_pruned_this_cycle, _entity_pruned_this_cycle
    await discord_client.wait_until_ready()

    agora = datetime.now(FUSO_HORARIO_BR)

    # Reset prune flags for this cycle
    _simhash_pruned_this_cycle = False
    _title_pruned_this_cycle = False
    _entity_pruned_this_cycle = False

    if not http_session or http_session.closed:
        connector = aiohttp.TCPConnector(limit=15, limit_per_host=3)
        http_session = aiohttp.ClientSession(connector=connector)

    channel = discord_client.get_channel(CANAL_NOTICIAS_ID)
    if not channel:
        try:
            channel = await discord_client.fetch_channel(CANAL_NOTICIAS_ID)
        except Exception as e:
            log.error(f"News channel not found: {e}")
            return
    if not channel:
        return

    _ai_calls_this_cycle = 0
    _vision_calls_this_cycle = 0
    history = load_history()
    metrics = load_metrics()

    # ===== PHASE 0: Post from previous cycles' queue (active hours only) =====
    queue = load_queue()
    posts_feitos = 0
    em_horario_ativo = HORA_INICIO <= agora.hour < HORA_FIM
    if queue and em_horario_ativo:
        log.info(f"═══ PHASE 0: Posting {len(queue)} from queue ═══")
        queue_restante = queue.copy()
        for item in queue:
            if posts_feitos >= MAX_POSTS_POR_CICLO:
                break
            img = item.get("imagem")
            if not img:
                log.warning(f"  ✗ Queue item without image, discarding: {item.get('titulo', '?')[:60]}")
                queue_restante.remove(item)
                save_queue(queue_restante)
                continue
            
            # Revalidate queue image (URLs may have expired)
            if not await validar_imagem(img):
                log.warning(f"  ✗ Invalid image in queue, discarding: {item.get('titulo', '?')[:60]}")
                queue_restante.remove(item)
                save_queue(queue_restante)
                continue

            # Dedup: check if similar article was already posted (may have been posted
            # in previous cycle or by another queue item in this same cycle)
            titulo_item = item.get("titulo", "")
            if title_is_dup(history, titulo_item):
                log.info(f"  ✗ Queue dedup (title): {titulo_item[:60]}")
                queue_restante.remove(item)
                save_queue(queue_restante)
                continue
            sh_item = _simhash64(f"{titulo_item} {item.get('resumo', '')}")
            if simhash_is_dup(history, sh_item):
                log.info(f"  ✗ Queue dedup (simhash): {titulo_item[:60]}")
                queue_restante.remove(item)
                save_queue(queue_restante)
                continue
            if topic_is_dup(history, titulo_item):
                log.info(f"  ✗ Queue dedup (topic): {titulo_item[:60]}")
                queue_restante.remove(item)
                save_queue(queue_restante)
                continue

            if await _postar_noticia(channel, item, history, metrics):
                posts_feitos += 1
                title_add(history, titulo_item)
                simhash_add(history, sh_item)
                topic_add(history, titulo_item)
                save_history(history)
                save_metrics(metrics)
                queue_restante.remove(item)
                save_queue(queue_restante)
                if posts_feitos < MAX_POSTS_POR_CICLO:
                    await asyncio.sleep(POST_SPACING_SEC)
            else:
                pass  # Remains in queue
        
        if posts_feitos >= MAX_POSTS_POR_CICLO:
            _last_cycle_time = agora.strftime("%H:%M:%S")
            _last_cycle_stats = {"posts": posts_feitos, "fonte": "fila"}
            log.info(f"Post limit reached via queue. Collection deferred to next cycle.")
            return

    # ===== PHASE 1: Parallel collection + pre-filter (no AI) =====
    log.info("═══ PHASE 1: Collection + pre-filter ═══")

    # Fetch all feeds in parallel
    async def _fetch_feed(nome_site: str, url_feed: str):
        if _feed_em_cooldown(nome_site):
            return nome_site, None
        try:
            feed = await asyncio.wait_for(
                asyncio.to_thread(
                    feedparser.parse, url_feed,
                    agent="TiffanyBot/2.0 (+https://discord.gg)"
                ),
                timeout=15,
            )
            return nome_site, feed
        except Exception as e:
            log.warning(f"Feed timeout/error: {nome_site} — {e}")
            _set_feed_cooldown(nome_site)
            return nome_site, None

    resultados_feeds = await asyncio.gather(
        *[_fetch_feed(n, u) for n, u in FONTES_RSS.items()],
        return_exceptions=True,
    )
    # Filter unexpected gather exceptions
    resultados_feeds = [
        r for r in resultados_feeds
        if not isinstance(r, BaseException)
    ]

    # Filter candidates (no image validation yet)
    pre_candidatos = []
    total_examinados = 0
    total_prefiltrados = 0
    total_dedup = 0
    total_antigas = 0
    contagem_por_fonte: dict[str, int] = {}
    # In-cycle dedup sets (do not pollute persistent history)
    _cycle_titles: set[str] = set()
    _cycle_simhashes: set[int] = set()
    _cycle_topic_groups: list[frozenset[str]] = []  # entity overlap dedup in-cycle

    for nome_site, feed in resultados_feeds:
        if not feed or not feed.entries:
            continue

        is_eng = nome_site in FONTES_INGLES
        aceitos_fonte = 0

        for entry in feed.entries[:SCAN_POR_FEED]:
            if aceitos_fonte >= ENTRADAS_POR_FEED:
                break

            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue

            total_examinados += 1

            # Check age FIRST (reject old items before any processing)
            dt = entry_datetime_utc(entry)
            if not noticia_eh_recente(dt):
                total_antigas += 1
                continue

            link_norm = normalizar_url(link)

            # Dedup by URL and hash
            dedupe = make_dedupe_hash(title, int(dt.timestamp()) if dt else int(time.time()))
            if historico_check(history, link_norm, dedupe):
                total_dedup += 1
                continue

            # Dedup by normalized title (cross-site: same story on different sites)
            _tfp = _title_fingerprint(title)
            if title_is_dup(history, title) or _tfp in _cycle_titles:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_titulo"})
                total_dedup += 1
                continue

            # SimHash dedup (similar content even with different titles)
            texto_raw = limpar_html(str(entry.get("summary") or entry.get("description") or title))
            sh = _simhash64(f"{title} {texto_raw[:600]}")
            if simhash_is_dup(history, sh) or sh in _cycle_simhashes:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_simhash"})
                total_dedup += 1
                continue

            # Topic dedup (entity overlap — 2+ shared entities = duplicate)
            _topic_keys = _extract_topic_keys(title)
            _cycle_topic_dup = any(
                len(_topic_keys & past) >= _ENTITY_OVERLAP_MIN
                for past in _cycle_topic_groups
            ) if len(_topic_keys) >= _ENTITY_OVERLAP_MIN else False
            if _topic_keys and (topic_is_dup(history, title) or _cycle_topic_dup):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_topico"})
                total_dedup += 1
                log.info(f"  ✗ Repeated topic: [{nome_site}] {title[:60]}")
                continue

            # KEYWORD PRE-FILTER (zero cost — before AI)
            if not prefiltro_keywords(title, texto_raw):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "prefiltro_keywords"})
                total_prefiltrados += 1
                log.info(f"  ✗ Pre-filter rejected: [{nome_site}] {title[:60]}")
                continue
            
            # PRE-FILTER: title too short/vague (before AI to save calls)
            palavras_titulo = [p for p in title.split() if p]
            if len(palavras_titulo) < 5:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "titulo_curto_prefiltro"})
                total_prefiltrados += 1
                log.info(f"  ✗ Short title pre-filter ({len(palavras_titulo)} words): [{nome_site}] {title[:60]}")
                continue
            
            # PRE-FILTER: title too vague (too generic)
            titulo_lower = title.lower()
            titulos_vagos = ["meta processada", "meta processa", "openai lança", "google lança"]
            if any(vago in titulo_lower for vago in titulos_vagos):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "titulo_vago"})
                total_prefiltrados += 1
                log.info(f"  ✗ Vague title: [{nome_site}] {title[:60]}")
                continue

            # Per-source candidate limit (diversity)
            if contagem_por_fonte.get(nome_site, 0) >= MAX_CANDIDATOS_POR_FONTE:
                continue

            pre_candidatos.append({
                "entry": entry,
                "nome_site": nome_site,
                "link": link,
                "link_norm": link_norm,
                "title": title,
                "texto_raw": texto_raw,
                "is_eng": is_eng,
                "dedupe": dedupe,
                "simhash": sh,
                "feed_url": FONTES_RSS.get(nome_site, ""),
            })
            # Cross-site in-cycle dedup: in-memory set (does not pollute persistent history)
            _cycle_titles.add(_title_fingerprint(title))
            _cycle_simhashes.add(sh)
            if len(_topic_keys) >= 2:
                _cycle_topic_groups.append(_topic_keys)
            aceitos_fonte += 1
            contagem_por_fonte[nome_site] = contagem_por_fonte.get(nome_site, 0) + 1

    # ===== Batch image validation (parallel with semaphore) =====
    total_sem_imagem = 0
    total_img_ia_rejeitada = 0
    candidatos = []

    if pre_candidatos:
        _img_semaphore = asyncio.Semaphore(5)

        async def _validar_img(cand):
            async with _img_semaphore:
                img = await extrair_imagem_completa(cand["entry"], cand["feed_url"])
                return cand, img

        resultados_img = await asyncio.gather(
            *[_validar_img(c) for c in pre_candidatos],
            return_exceptions=True,
        )
        for result in resultados_img:
            if isinstance(result, Exception):
                log.warning("Image validation error: %s", result)
                continue
            cand, img = result
            if not img:
                historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "sem_imagem"})
                total_sem_imagem += 1
                continue
            # AI validation: verify image matches title (with budget)
            titulo_cand = cand.get("title", "")
            if _vision_calls_this_cycle < MAX_VISION_CALLS_POR_CICLO:
                _vision_calls_this_cycle += 1
                if not await validar_imagem_ia(img, titulo_cand):
                    log.info(f"  ✗ Irrelevant image (AI): [{cand.get('nome_site', '?')}] {titulo_cand[:60]}")
                    historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "imagem_irrelevante_ia"})
                    total_img_ia_rejeitada += 1
                    continue
            cand["img"] = img
            candidatos.append(cand)

    log.info(
        f"Phase 1 complete: {total_examinados} scanned, "
        f"{total_antigas} old, {total_dedup} dedup, {total_prefiltrados} pre-filtered, "
        f"{total_sem_imagem} no image, {total_img_ia_rejeitada} irrelevant image (AI) "
        f"→ {len(candidatos)} AI candidates"
    )

    if not candidatos:
        save_history(history)
        return

    # ===== PHASE 2: AI analysis (budget-limited) =====
    log.info(f"═══ PHASE 2: AI analysis (budget: {MAX_IA_CALLS_POR_CICLO}) ═══")
    aprovados = []

    for cand in candidatos:
        if _ai_calls_this_cycle >= MAX_IA_CALLS_POR_CICLO:
            log.info(f"AI budget exhausted ({MAX_IA_CALLS_POR_CICLO} calls).")
            break

        # Extra dedup: check if topic was already approved this cycle
        titulo_lower = cand["title"].lower()
        assunto_keywords = set()
        for palavra in [
            # Big techs & people
            "meta", "openai", "google", "microsoft", "apple", "amazon", "facebook",
            "musk", "altman", "zuckerberg", "spacex", "tesla",
            # IA
            "chatgpt", "gemini", "copilot", "claude", "llama", "grok",
            # Hardware
            "nvidia", "amd", "intel", "samsung", "lg", "sony", "qualcomm", "tsmc",
            "huawei", "corsair", "asus", "logitech",
            # Gaming
            "valve", "steam", "xbox", "playstation", "nintendo", "epic games",
            "call of duty", "activision", "rocket league", "fortnite", "gta",
            "the sims", "project rene",
            # Software & OS
            "windows", "android", "iphone", "pixel", "chrome", "firefox",
            # Space & science
            "jwst", "james webb", "nasa", "shenzhou", "tiangong", "artemis",
            "spacex", "starship", "starlink",
            # Security
            "ransomware", "phishing", "malware", "cve-",
            # Brazil & telecom
            "anatel", "5g", "starlink",
            # Vehicles & specific hardware
            "ddr5", "nand", "ssd", "gpu", "cpu",
        ]:
            if palavra in titulo_lower:
                assunto_keywords.add(palavra)
        
        if assunto_keywords:
            ja_tem_assunto = False
            for aprov in aprovados:
                aprov_titulo = aprov["titulo"].lower()
                for kw in assunto_keywords:
                    if kw in aprov_titulo:
                        ja_tem_assunto = True
                        break
                if ja_tem_assunto:
                    break
            if ja_tem_assunto:
                historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"assunto_repetido_{list(assunto_keywords)[0]}"})
                log.info(f"  ✗ Repeated topic ({list(assunto_keywords)[0]}): [{cand['nome_site']}] {cand['title'][:60]}")
                continue

        _ai_calls_this_cycle += 1
        metric_inc(metrics, "ia_calls_hoje")
        res = await gerar_analise_ia(cand["texto_raw"], cand["title"], cand["nome_site"])

        if not isinstance(res, dict) or res.get("pular"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "ia_rejeitou"})
            metric_inc(metrics, "ia_rejeitadas_hoje")
            log.info(f"  ✗ AI rejected: [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        # Validate required fields in AI response
        if not res.get("titulo") or not res.get("resumo"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "ia_campos_faltando"})
            log.warning(f"  ✗ AI returned without titulo/resumo: [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        try:
            nota = int(res.get("nota", 0))
        except (ValueError, TypeError):
            nota = 0
        categoria = res.get("categoria", "Outros")

        # Score threshold
        min_nota = NOTA_MIN_GAMES if categoria == "Games" else NOTA_MIN_APROVACAO
        if nota < min_nota:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"nota_baixa_{nota}"})
            metric_inc(metrics, "ia_rejeitadas_hoje")
            log.info(f"  ✗ Low score ({nota}): [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        # Post-AI SimHash (generated title + summary)
        sh_post = _simhash64(f"{res.get('titulo', '')} {res.get('resumo', '')}")
        if simhash_is_dup(history, sh_post):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "dup_simhash_pos"})
            continue

        simhash_add(history, sh_post)
        simhash_add(history, cand["simhash"])
        # Register original AND translated title in index
        title_add(history, cand["title"])
        title_add(history, res.get("titulo", ""))
        # Register topic/subject (suppress same story from other sources for hours)
        topic_add(history, cand["title"])
        topic_add(history, res.get("titulo", ""))

        # LOCK: no image = never approve
        if not cand.get("img"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "sem_imagem_fase2"})
            log.info(f"  ✗ No image (Phase 2): [{cand['nome_site']}] {cand['title'][:60]}")
            continue
        
        # LOCK: title must have at least 5 real words
        titulo_final = res.get("titulo", "").strip()
        # Remove emojis and punctuation to count real words
        titulo_limpo = re.sub(r'[^\w\s]', ' ', titulo_final)
        palavras_titulo = [p for p in titulo_limpo.split() if len(p) > 2]  # words with more than 2 letters
        if len(palavras_titulo) < 5:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"titulo_curto_{len(palavras_titulo)}palavras"})
            log.info(f"  ✗ Title too short ({len(palavras_titulo)} words): {titulo_final[:60]}")
            continue
        
        # LOCK: title too vague (fewer than 40 chars after normalization)
        if len(titulo_final) < 40:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "titulo_vago_curto"})
            log.info(f"  ✗ Title too vague/short: {titulo_final[:60]}")
            continue
        
        # EXTRA LOCK: reject titles with only 2-3 words even after processing
        if len(titulo_final.split()) < 6:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"titulo_palavras_insuf_{len(titulo_final.split())}"})
            log.info(f"  ✗ Title with too few words: {titulo_final[:60]}")
            continue

        metric_inc(metrics, "ia_aprovadas_hoje")
        aprovados.append({
            "titulo": res.get("titulo", cand["title"]),  # already normalized in gerar_analise_ia()
            "resumo": res.get("resumo", ""),
            "nota": nota,
            "categoria": categoria,
            "link": cand["link"],
            "link_norm": cand["link_norm"],
            "dedupe": cand["dedupe"],
            "site": cand["nome_site"],
            "imagem": cand["img"],
            "is_eng": cand["is_eng"],
        })
        historico_set(history, cand["link_norm"], cand["dedupe"], "queued")
        log.info(f"  ✓ Approved (score {nota}): [{cand['nome_site']}] {res.get('titulo', '')[:60]}")

    log.info(f"Phase 2 complete: {_ai_calls_this_cycle} AI calls → {len(aprovados)} approved")
    save_history(history)

    if not aprovados:
        save_metrics(metrics)
        return

    # ===== PHASE 3: Post best items + queue the rest =====
    log.info("═══ PHASE 3: Posting best news items ═══")

    # Sort by score (highest first)
    aprovados.sort(key=lambda x: x["nota"], reverse=True)

    # Filter items without image
    com_imagem = [a for a in aprovados if a.get("imagem")]
    if not com_imagem:
        log.warning("No approved news has a valid image. Nothing will be posted.")
        save_history(history)
        save_metrics(metrics)
        return

    # Post up to limit (active hours only), queue the rest
    posts_restantes = MAX_POSTS_POR_CICLO - posts_feitos
    para_postar = com_imagem[:posts_restantes] if em_horario_ativo else []
    para_fila = com_imagem[posts_restantes:] if em_horario_ativo else com_imagem

    posts_fase3 = 0
    
    # Queue remainder for next cycle BEFORE posting (crash safety)
    if para_fila:
        queue_atual = load_queue()
        # Validate required fields before enqueueing
        _campos_obrigatorios = ("titulo", "imagem", "link", "nota")
        para_fila = [n for n in para_fila if all(n.get(c) for c in _campos_obrigatorios)]
        # Dedup: do not enqueue if similar item already in queue
        _queue_titles = {_title_fingerprint(q.get("titulo", "")) for q in queue_atual if q.get("titulo")}
        para_fila_dedup = []
        for item_fila in para_fila:
            fp = _title_fingerprint(item_fila.get("titulo", ""))
            if fp not in _queue_titles:
                para_fila_dedup.append(item_fila)
                _queue_titles.add(fp)
            else:
                log.info(f"  ✗ Queue dedup (already enqueued): {item_fila.get('titulo', '?')[:60]}")
        queue_atual.extend(para_fila_dedup)
        # Limit queue to 10 items (avoid infinite accumulation)
        queue_atual = sorted(queue_atual, key=lambda x: x.get("nota", 0), reverse=True)[:10]
        save_queue(queue_atual)
        log.info(f"  📋 {len(para_fila)} news items queued for next cycle (queue total: {len(queue_atual)})")

    for i, noticia in enumerate(para_postar):
        # Revalidate image at post time (URLs may have expired)
        img = noticia.get("imagem")
        if not img or not await validar_imagem(img):
            log.warning(f"  ✗ Invalid image when posting, discarding: {noticia.get('titulo', '?')[:60]}")
            historico_set(history, noticia["link_norm"], noticia["dedupe"], "skipped", {"reason": "sem_imagem_post"})
            save_history(history)
            continue
        log.info(f"  🏆 Posting (score {noticia['nota']}): [{noticia['site']}] {noticia['titulo'][:60]}")
        if await _postar_noticia(channel, noticia, history, metrics):
            posts_fase3 += 1
            save_metrics(metrics)
        if i < len(para_postar) - 1:
            await asyncio.sleep(POST_SPACING_SEC)

    save_history(history)
    save_metrics(metrics)
    _last_cycle_time = agora.strftime("%H:%M:%S")
    _last_cycle_stats = {
        "examinados": total_examinados,
        "candidatos_ia": len(candidatos),
        "aprovados": len(aprovados),
        "posts": posts_feitos + posts_fase3,
        "fila": len(load_queue()),
    }
    log.info("Cycle complete.")


_CMD_NAMES = (
    "nowplaying", "playlist", "summary", "random", "resume", "pause", "clear", "skip",
    "loop", "play", "chat", "seek", "nonstop", "queue", "language", "mod-panel", "modpanel",
    "shuffle", "replay", "autoplay", "lyrics", "clip", "games", "game", "giveaway", "roleplay",
    "embed",
    "np", "pa", "re", "cl", "pl", "su", "ff", "sh", "rpl", "ap", "ly", "cp", "l",
    "lang", "mod", "gw", "emb", "rp", "roleplay",
    "247",
    "s", "c", "p", "r", "q", "g",
)

@discord_client.event
async def on_message(message: discord.Message):
    """Normalize commands without space (e.g. t!phttps://... → t!p https://...)."""
    try:
        if message.author.bot:
            return
        content = message.content
        if not content:
            return
        lower = content.lower()
        if lower.startswith("t!"):
            after_prefix = content[2:]
            matched = False
            # Try to match known commands (longest first for np/pa/re/cl/pl/su)
            for cmd in sorted(_CMD_NAMES, key=len, reverse=True):
                if after_prefix.lower().startswith(cmd):
                    if len(after_prefix) == len(cmd) or after_prefix[len(cmd)] == " ":
                        # Command already formatted correctly (exact or with space)
                        break
                    # Insert space between command and argument
                    message.content = f"t!{cmd} {after_prefix[len(cmd):]}"
                    matched = True
                    break
            # Normalize prefix to lowercase (T! → t!)
            if not matched and content[:2] != "t!":
                message.content = f"t!{content[2:]}"
        await discord_client.process_commands(message)
    except Exception:
        log.exception("Error in on_message")


@discord_client.event
async def on_guild_join(guild: discord.Guild):
    """Welcome message when a new server adds Tiffany — highlights value for admins."""
    if not _voice_available or not tiffany_voice:
        return
    try:
        em = tiffany_voice.build_welcome_embed(guild, discord_client)
        invite = tiffany_voice.bot_invite_url(discord_client)
        view = tiffany_voice.invite_link_view(invite)
        channel = guild.system_channel
        if not channel or not channel.permissions_for(guild.me).send_messages:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        if channel:
            await channel.send(embed=em, view=view)
            log.info("Welcome message sent guild=%s (%s)", guild.name, guild.id)
    except discord.Forbidden:
        log.warning("No permission to send welcome in guild=%s", guild.id)
    except Exception:
        log.exception("Failed to send welcome guild=%s", guild.id)


@discord_client.event
async def on_ready():
    global _voice_available
    log.info(f"🤖 Tiffany Online: {discord_client.user}")
    if _voice_available and tiffany_voice:
        try:
            tiffany_voice.register_voice(discord_client)
            log.info("Voice commands registered (t! + slash).")
        except Exception:
            log.exception("register_voice failed — voice/prefix/slash commands disabled.")
            _voice_available = False
    else:
        log.warning("Voice module unavailable — t! commands and /help will not work.")
    if _voice_available and tiffany_voice:
        await tiffany_voice.start_presence_rotation(discord_client)
    else:
        log.warning("Voice module unavailable — presence rotation skipped.")
    # Load offers Cog before syncing slash commands
    if not discord_client.get_cog("OffersCog"):
        try:
            await discord_client.load_extension("offers_cog")
            log.info("🛒 Offers Cog loaded successfully.")
        except Exception as e:
            log.error(f"❌ Failed to load Offers Cog: {e}")
    for ext in ("giveaways_cog", "embed_builder_cog"):
        cog_name = {"giveaways_cog": "GiveawaysCog", "embed_builder_cog": "EmbedBuilderCog"}[ext]
        if not discord_client.get_cog(cog_name):
            try:
                await discord_client.load_extension(ext)
                log.info("%s loaded successfully.", ext)
            except Exception as e:
                log.error("Failed to load %s: %s", ext, e)
    # Sync slash commands (Discord builds the profile "Commands" tab from these)
    try:
        # Remove legacy guild-specific duplicates
        for g in discord_client.guilds:
            try:
                discord_client.tree.clear_commands(guild=g)
                await discord_client.tree.sync(guild=g)
            except Exception:
                pass
        synced = await discord_client.tree.sync()
        log.info("Slash commands synced globally (%d commands).", len(synced))
        # Instant sync on home guild (optional — global can take up to ~1h)
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild_obj = discord.Object(id=int(guild_id))
            discord_client.tree.copy_global_to(guild=guild_obj)
            guild_synced = await discord_client.tree.sync(guild=guild_obj)
            log.info("Slash commands synced to GUILD_ID (%d commands).", len(guild_synced))
    except Exception as e:
        log.warning(f"Error syncing slash commands: {e}")
    if _voice_available and tiffany_voice:
        await tiffany_voice.start_warp_monitor(discord_client)
    if not verificar_feeds.is_running():
        verificar_feeds.start()

@discord_client.event
async def on_close():
    global http_session
    if http_session:
        await http_session.close()
        http_session = None
    log.info("🔌 HTTP session closed. Bot shutting down.")


# =========================
# SLASH COMMAND: /status
# =========================
@discord_client.tree.command(name="status", description="Shows if Tiffany is working properly")
async def cmd_status(interaction: discord.Interaction):
    """Simple friendly status: reports normal operation or instability.
    Available to all users. Admins see extra technical details."""
    agora = datetime.now(FUSO_HORARIO_BR)
    em_horario = HORA_INICIO <= agora.hour < HORA_FIM

    # Discord connection health (gateway latency in ms)
    lat = discord_client.latency  # seconds; may be nan right after boot
    lat_ms = int(lat * 1000) if (lat == lat and lat not in (float("inf"), float("-inf"))) else None

    # Temporarily unavailable news sources
    feeds_cooldown = [nome for nome in FONTES_RSS if _feed_em_cooldown(nome)]
    frac_cooldown = len(feeds_cooldown) / (len(FONTES_RSS) or 1)

    conexao_ruim = (lat_ms is None) or (lat_ms > 1000)
    conexao_lenta = (lat_ms is not None) and (400 < lat_ms <= 1000)
    fontes_criticas = em_horario and frac_cooldown >= 0.5
    fontes_lentas = em_horario and len(feeds_cooldown) > 0

    if conexao_ruim or fontes_criticas:
        nivel, titulo, cor = "🔴", "Com instabilidades", 0xED4245
        msg = "Estou instável agora. Tente de novo em alguns minutos. 🙏"
    elif conexao_lenta or fontes_lentas:
        nivel, titulo, cor = "🟡", "Pequenas instabilidades", 0xFEE75C
        msg = "Funcionando, com leve lentidão."
    else:
        nivel, titulo, cor = "🟢", "Funcionando normalmente", 0x57F287
        msg = "Tá tudo certo por aqui! 💖"

    em = discord.Embed(title=f"{nivel} Tiffany — {titulo}", description=msg, color=cor, timestamp=agora)

    if lat_ms is None:
        conexao_txt = "conectando..."
    elif lat_ms <= 200:
        conexao_txt = f"ótima ({lat_ms} ms)"
    elif lat_ms <= 400:
        conexao_txt = f"boa ({lat_ms} ms)"
    elif lat_ms <= 1000:
        conexao_txt = f"lenta ({lat_ms} ms)"
    else:
        conexao_txt = f"instável ({lat_ms} ms)"

    em.add_field(name="📶 Conexão", value=conexao_txt, inline=True)
    if _voice_available and tiffany_voice:
        em.add_field(name="🎵 Música & comandos", value="Disponíveis", inline=True)
        warp_ok = tiffany_voice.check_warp_proxy_ok()
        em.add_field(
            name="🌐 WARP (YouTube)",
            value=(
                "Online (música OK)"
                if warp_ok
                else "Offline — música pode falhar"
            ),
            inline=True,
        )
    else:
        em.add_field(
            name="🎵 Música & comandos",
            value="Indisponíveis — módulo de voz não carregou (reinicie após deploy)",
            inline=True,
        )
    em.add_field(
        name="📰 Notícias",
        value="Ativas (8h–18h)" if em_horario else "Em standby (fora do horário)",
        inline=True,
    )

    # Technical details for admins only (does not clutter regular user view)
    is_admin = bool(
        interaction.guild
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )
    if is_admin:
        metrics = load_metrics()
        queue = load_queue()
        em.add_field(
            name="🔧 Admin · hoje",
            value=(
                f"Posts: {metrics.get('posts_hoje', 0)} · "
                f"IA: {metrics.get('ia_calls_hoje', 0)} · "
                f"✅ {metrics.get('ia_aprovadas_hoje', 0)} / ❌ {metrics.get('ia_rejeitadas_hoje', 0)}"
            ),
            inline=False,
        )
        em.add_field(
            name="🔧 Admin · operação",
            value=(
                f"Fila: {len(queue)} · Último ciclo: {_last_cycle_time}\n"
                f"Feeds em cooldown: {', '.join(feeds_cooldown) if feeds_cooldown else 'Nenhum'}"
            )[:1024],
            inline=False,
        )

    em.set_footer(text="Tiffany 💖")
    await interaction.response.send_message(embed=em, ephemeral=True)


async def _shutdown_cleanup():
    """Guaranteed http_session cleanup in any shutdown scenario."""
    global http_session
    if http_session:
        await http_session.close()
        http_session = None
        log.info("🔌 HTTP session closed on shutdown.")

def _sync_cleanup():
    """Emergency synchronous cleanup via atexit."""
    global http_session
    if http_session and not http_session.closed:
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                loop.create_task(http_session.close())
            else:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(http_session.close())
                loop.close()
        except Exception:
            pass
        log.warning("⚠️ http_session closed via atexit (forced shutdown).")

atexit.register(_sync_cleanup)

if __name__ == "__main__":
    discord_client.run(DISCORD_TOKEN)
