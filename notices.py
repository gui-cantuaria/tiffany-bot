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
from datetime import datetime, timedelta, timezone
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
    _log_tmp.getLogger("tiffany-bot").warning("tiffany_voice não carregou (%s) — comandos de voz desativados.", _ve)
    tiffany_voice = None
    _voice_available = False

# =========================
# CONFIGURAÇÕES
# =========================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

CANAL_NOTICIAS_ID = int(os.getenv("CANAL_NOTICIAS_ID", "0"))
ID_CARGO_PARA_MARCAR = int(os.getenv("ID_CARGO_PARA_MARCAR", "0"))

HORA_INICIO = 8
HORA_FIM = 18
FUSO_HORARIO_BR = timezone(timedelta(hours=-3))
MINUTO_PRE_AQUECIMENTO = 45

# --- Pipeline ---
SCAN_POR_FEED = 5
ENTRADAS_POR_FEED = 3
MAX_IA_CALLS_POR_CICLO = 8
IA_COOLDOWN_SEC = 15
POST_SPACING_SEC = 120
MAX_POSTS_POR_CICLO = 1

# --- Notas de corte ---
NOTA_MIN_APROVACAO = 80
NOTA_MIN_GAMES = 85
NOTA_URGENTE = 90

# --- Anti-dup ---
SIMHASH_TTL_HORAS = 120
SIMHASH_HAMMING_MAX = 6
TITLE_IDX_TTL_HORAS = 72
MAX_IDADE_HORAS = 12

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

# Silenciar ruído de bibliotecas externas
logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.voice_state").setLevel(logging.WARNING)

# =========================
# DISCORD + IA CLIENT
# =========================
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

intents = discord.Intents.default()
# Only enable voice intents if voice is enabled
if os.getenv("VOICE_ENABLED", "1").strip() == "1":
    intents.voice_states = True
intents.message_content = True
discord_client = commands.Bot(
    command_prefix=commands.when_mentioned_or("t$", "T$"),
    case_insensitive=True,
    intents=intents,
    help_command=None,  # /help (slash command) fornece a ajuda dos comandos
)
if _voice_available and tiffany_voice:
    tiffany_voice.register_voice(discord_client)
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
    # Limpar entradas expiradas se o dict ficou grande
    if len(_feed_cooldown_until) > _FEED_COOLDOWN_MAX_ENTRIES:
        now = time.time()
        expired = [k for k, v in _feed_cooldown_until.items() if now >= v]
        for k in expired:
            del _feed_cooldown_until[k]
    _feed_cooldown_until[nome_site] = time.time() + (FEED_COOLDOWN_MIN * 60)

def _feed_em_cooldown(nome_site: str) -> bool:
    return time.time() < _feed_cooldown_until.get(nome_site, 0)

# =========================
# FONTES RSS
# =========================
FONTES_RSS = {
    # BR
    "Adrenaline": "https://adrenaline.com.br/feed/",
    "TudoCelular": "https://www.tudocelular.com/rss/",
    "Tecnoblog": "https://tecnoblog.net/feed/",
    "Canaltech": "https://canaltech.com.br/rss/",
    "Olhar Digital": "https://olhardigital.com.br/rss/",
    "G1 Tecnologia": "https://g1.globo.com/dynamo/tecnologia/rss2.xml",
    "Giz Brasil": "https://gizmodo.uol.com.br/feed/",
    "Convergência Digital": "https://convergenciadigital.com.br/feed/",
    # EN — Geral
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
    "Axios Tech": "https://api.axios.com/feed/technology",
    "IEEE Spectrum": "https://spectrum.ieee.org/rss",
    # EN — Segurança
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "KrebsOnSecurity": "https://krebsonsecurity.com/feed/",
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Dark Reading": "https://www.darkreading.com/rss.xml",
    "Socket": "https://socket.dev/blog/rss.xml",
    # EN — IA / Dev
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
# CATEGORIAS
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
MAX_CANDIDATOS_POR_FONTE = 2

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
# PRÉ-FILTRO POR KEYWORDS
# =========================
KEYWORDS_TECH = {
    # IA / ML
    "inteligência artificial", "inteligencia artificial", "machine learning",
    "deep learning", "llm", "chatgpt", "openai", "gemini", "copilot",
    "anthropic", "claude", "midjourney", "stable diffusion", "neural",
    "gpt", "transformers", "nlp", "generative ai", "ia generativa",
    # Hardware
    "nvidia", "amd", "intel", "gpu", "cpu", "processador", "placa de vídeo",
    "placa de video", "rtx", "radeon", "ryzen", "chip", "semicondutor",
    "semiconductor", "tsmc", "qualcomm", "snapdragon", "apple silicon",
    # Segurança
    "cibersegurança", "ciberseguranca", "cybersecurity", "ransomware",
    "malware", "phishing", "vulnerabilidade", "vulnerability", "cve",
    "zero-day", "0-day", "exploit", "data breach", "vazamento de dados",
    "hacker", "ddos", "firewall", "encryption", "criptografia",
    # Cloud / DevOps
    "kubernetes", "docker", "aws", "azure", "google cloud", "cloud computing",
    "devops", "ci/cd", "microservices", "serverless", "terraform",
    # Sistemas Operacionais
    "windows 11", "windows 12", "linux", "macos", "android", "ios",
    "ubuntu", "kernel", "atualização de segurança", "security update",
    # Programação
    "python", "javascript", "typescript", "rust", "golang", "github",
    "gitlab", "api", "framework", "open source", "código aberto",
    "developer", "desenvolvedor", "programming", "programação",
    "react", "nextjs", "node.js",
    # Big Techs
    "google", "microsoft", "apple", "meta", "amazon", "tesla", "spacex",
    "samsung", "sony", "nintendo", "valve", "steam",
    # Mobile (flagships)
    "iphone", "galaxy s", "pixel", "ipad",
    # Geral
    "startup", "big tech", "algoritmo", "blockchain", "web3",
    "5g", "6g", "wi-fi", "fibra óptica", "satélite", "starlink",
    "realidade virtual", "realidade aumentada", "vr", "ar", "metaverso",
    "robô", "robot", "automação", "automation", "quantum", "quântico",
}

KEYWORDS_BLOCK = {
    # Ofertas / Compras
    "oferta", "desconto", "cupom", "coupon", "promoção", "promocao",
    "black friday", "prime day", "compre", "barato", "menor preço",
    "menor preco", "cashback", "afiliado", "affiliate",
    # Entretenimento genérico
    "horóscopo", "horoscopo", "futebol", "soccer", "nba", "nfl",
    "novela", "big brother", "reality show", "celebridade", "celebrity",
    "fofoca", "gossip", "tiktok trend", "meme",
    # Ciência genérica (fora de escopo)
    "paleontologia", "arqueologia", "fóssil", "fossil",
    "dinossauro", "dinosaur",
    # Reviews / Guias de compra
    "análise de produto", "guia de compra", "buying guide",
    "melhor custo-benefício", "vale a pena comprar",
    "unboxing",
}

def prefiltro_keywords(titulo: str, texto: str) -> bool:
    """Retorna True se o artigo PASSA no filtro (é potencialmente tech).
    Retorna False se deve ser rejeitado antes da IA."""
    blob = f"{titulo} {texto}".lower()

    # Rejeitar se contém keyword bloqueada
    for kw in KEYWORDS_BLOCK:
        if kw in blob:
            return False
    # Keywords bloqueadas com word boundary (evitar falsos positivos com substrings)
    _BLOCK_WORD_BOUNDARY = ("review", "comparativo")
    for kw in _BLOCK_WORD_BOUNDARY:
        if re.search(rf"\b{kw}\b", blob):
            return False

    # Aceitar se contém keyword tech
    for kw in KEYWORDS_TECH:
        if kw in blob:
            return True

    # Se não contém nenhuma keyword tech, rejeitar
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
# HISTÓRICO (PERSISTÊNCIA)
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
        log.warning(f"Erro ao carregar histórico: {e}")
        return {}

def save_history(h: dict) -> None:
    # Limpar entradas com mais de 7 dias
    cutoff = int(time.time()) - (7 * 86400)
    novo = {}
    # Preservar índices internos (com pruning para não crescerem sem limite)
    if "_simhash_idx" in h:
        novo["_simhash_idx"] = _simhash_prune(h["_simhash_idx"])
    if "_title_idx" in h:
        novo["_title_idx"] = _title_idx_prune(h["_title_idx"])
    for k, v in h.items():
        if k in ("_simhash_idx", "_title_idx"):
            continue
        if isinstance(v, dict) and "ts" in v:
            if v["ts"] > cutoff:
                novo[k] = v
        elif isinstance(v, dict) and "data" in v:
            # Backward-compat com V16 (campo "data" em ISO)
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
        log.exception("Erro ao salvar histórico")
        try:
            os.remove(tmp)
        except OSError:
            pass

# =========================
# MÉTRICAS PERSISTENTES
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
        log.error(f"Erro ao salvar métricas: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass

def metric_inc(m: dict, key: str, amount: int = 1) -> None:
    hoje = datetime.now(FUSO_HORARIO_BR).strftime("%Y-%m-%d")
    if "_date" not in m or m["_date"] != hoje:
        # Novo dia: resetar contadores diários, preservar totais
        m["_date"] = hoje
        for k in ("posts_hoje", "ia_aprovadas_hoje", "ia_rejeitadas_hoje", "ia_calls_hoje"):
            m[k] = 0
    m[key] = m.get(key, 0) + amount
    total_key = key.replace("_hoje", "_total")
    if total_key != key:
        m[total_key] = m.get(total_key, 0) + amount

# =========================
# FILA DE APROVADOS (persistência entre ciclos)
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
        log.error(f"Erro ao salvar fila: {e}")
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
    """Retorna True se já foi processado (dedup por URL ou hash)."""
    # Checar formato V17 (L: / H:)
    if _hist_key_link(link_norm) in h:
        return True
    if dedupe_hash and _hist_key_hash(dedupe_hash) in h:
        return True
    # Backward-compat: checar URL bare (formato V16)
    if link_norm in h:
        return True
    return False

def historico_set(h: dict, link_norm: str, dedupe_hash: Optional[str], status: str, extra: Optional[dict] = None) -> None:
    payload = _hist_payload(status, extra)
    h[_hist_key_link(link_norm)] = payload
    if dedupe_hash:
        h[_hist_key_hash(dedupe_hash)] = payload

def make_dedupe_hash(titulo: str, published_ts: int) -> str:
    # Sem bucket de hora — mesmo título = mesmo hash independente de quando foi publicado
    raw = f"GLOBAL|{_normalizar_titulo(titulo)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

# =========================
# NORMALIZAÇÃO DE TÍTULO
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
    """Normaliza título removendo stopwords, pontuação e espaços extras.
    'Microsoft lança atualização do Windows 11' → 'microsoft lança atualização windows 11'"""
    t = (titulo or "").lower().strip()
    t = _PUNCT_RE.sub(" ", t)
    palavras = [p for p in t.split() if p not in _STOPWORDS and len(p) > 1]
    return " ".join(palavras)

def _title_fingerprint(titulo: str) -> str:
    """Hash curto do título normalizado para dedup cross-site."""
    norm = _normalizar_titulo(titulo)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]

# SimHash index no histórico
def _get_simhash_index(h: dict) -> dict[str, int]:
    idx = h.get("_simhash_idx")
    return idx if isinstance(idx, dict) else {}

MAX_SIMHASH_INDEX = 500

def _simhash_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (SIMHASH_TTL_HORAS * 3600)
    pruned = {k: ts for k, ts in idx.items() if ts >= cutoff}
    # Limitar tamanho: manter apenas os mais recentes
    if len(pruned) > MAX_SIMHASH_INDEX:
        sorted_items = sorted(pruned.items(), key=lambda x: x[1], reverse=True)
        pruned = dict(sorted_items[:MAX_SIMHASH_INDEX])
    return pruned

_simhash_pruned_this_cycle = False

def _ensure_simhash_pruned(h: dict) -> dict[str, int]:
    """Prune o índice apenas uma vez por ciclo."""
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
# ÍNDICE DE TÍTULOS (cross-site dedup)
# =========================
def _get_title_index(h: dict) -> dict[str, int]:
    idx = h.get("_title_idx")
    return idx if isinstance(idx, dict) else {}

MAX_TITLE_INDEX = 500

def _title_idx_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (TITLE_IDX_TTL_HORAS * 3600)
    pruned = {k: ts for k, ts in idx.items() if ts >= cutoff}
    # Limitar tamanho: manter apenas os mais recentes
    if len(pruned) > MAX_TITLE_INDEX:
        sorted_items = sorted(pruned.items(), key=lambda x: x[1], reverse=True)
        pruned = dict(sorted_items[:MAX_TITLE_INDEX])
    return pruned

_title_pruned_this_cycle = False

def _ensure_title_pruned(h: dict) -> dict[str, int]:
    """Prune o índice apenas uma vez por ciclo."""
    global _title_pruned_this_cycle
    idx = _get_title_index(h)
    if not _title_pruned_this_cycle:
        idx = _title_idx_prune(idx)
        h["_title_idx"] = idx
        _title_pruned_this_cycle = True
    return idx

def title_is_dup(h: dict, titulo: str) -> bool:
    """Checa se um título normalizado já foi processado (qualquer site)."""
    fp = _title_fingerprint(titulo)
    idx = _ensure_title_pruned(h)
    return fp in idx

def title_add(h: dict, titulo: str) -> None:
    """Registra título no índice para dedup futuro."""
    fp = _title_fingerprint(titulo)
    idx = _ensure_title_pruned(h)
    idx[fp] = int(time.time())
    h["_title_idx"] = idx

# =========================
# EXTRAÇÃO DE IMAGEM
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
    # Converte HTTP para HTTPS (muitos sites bloqueiam HTTP ou redirecionam)
    if u.startswith("http://"):
        u = "https://" + u[7:]
    if base and u.startswith("/"):
        try:
            u = urljoin(base, u)
        except Exception:
            pass
    return u

def extrair_imagem_rss(entry, feed_url: str) -> Optional[str]:
    """Extrai URL de imagem do entry RSS (sem HTTP)."""
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
        log.debug(f"Erro extraindo imagem RSS: {e}")
    return img

async def fetch_og_image(url: str, retries: int = 2) -> Optional[str]:
    """Busca og:image da página como fallback, com retry."""
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
                    continue  # retry em 5xx
                if r.status != 200:
                    return None
                raw = await r.content.read(1_000_000)  # max 1MB
                html = raw.decode("utf-8", errors="replace")
                m = OG_IMG_RE.search(html) or OG_IMG_RE_ALT.search(html)
                if m:
                    return _norm_img_url(m.group(1), url)
                return None
        except Exception as e:
            log.debug(f"og:image tentativa {attempt+1}/{retries} falhou para {url}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
    return None

MIN_IMG_WIDTH = 400
MIN_IMG_HEIGHT = 200

def _img_dimensions_from_bytes(data: bytes) -> Optional[Tuple[int, int]]:
    """Extrai (width, height) dos headers de PNG, JPEG ou GIF sem lib externa."""
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
            # Pular bytes de padding 0xFF
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
                break  # segmento malformado
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
        # VP8X (extended WebP — formato mais comum moderno)
        if data[12:16] == b"VP8X" and len(data) >= 30:
            w = (data[24] | (data[25] << 8) | (data[26] << 16)) + 1
            h = (data[27] | (data[28] << 8) | (data[29] << 16)) + 1
            return w, h
    return None

async def validar_imagem(url: str) -> bool:
    """Verifica se URL e imagem valida (>5KB, status 200/206, dimensoes minimas)."""
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
            # Verificar tamanho total
            cr = r.headers.get("Content-Range", "")
            if cr and "/" in cr:
                total = cr.rsplit("/", 1)[-1]
                if total.isdigit() and int(total) < 5000:
                    return False
            else:
                cl = r.headers.get("Content-Length", "")
                if cl.isdigit() and int(cl) < 5000:
                    return False
            # Ler bytes iniciais para checar dimensoes
            chunk = await r.content.read(32768)
            dims = _img_dimensions_from_bytes(chunk)
            if dims:
                w, h = dims
                if w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT:
                    log.info(f"Imagem rejeitada por dimensao: {w}x{h} ({url[:80]})")
                    return False
                # Rejeitar aspect ratio extremo (banners, imagens cortadas)
                ratio = w / h if h > 0 else 0
                if ratio > 4.0 or ratio < 0.3:
                    log.info(f"Imagem rejeitada por aspect ratio ({ratio:.2f}): {w}x{h} ({url[:80]})")
                    return False
            return True
    except Exception as e:
        log.debug(f"Erro validando imagem {url}: {e}")
    return False

async def extrair_imagem_completa(entry, feed_url: str) -> Optional[str]:
    """Pipeline completo: RSS → validação HTTP → fallback og:image obrigatório."""
    img = extrair_imagem_rss(entry, feed_url)
    # Se imagem RSS válida, retorna
    if img and await validar_imagem(img):
        log.debug(f"Imagem extraída via RSS: {img[:80]}")
        return img
    
    # Fallback OBRIGATÓRIO: og:image da página (mesmo se RSS retornou algo inválido)
    link = entry.get("link")
    if link:
        log.debug(f"RSS falhou, buscando og:image para: {link[:80]}")
        og = await fetch_og_image(link)
        if og and await validar_imagem(og):
            log.info(f"Imagem recuperada via og:image: {og[:80]}")
            return og
        elif og:
            log.warning(f"og:image encontrado mas inválido: {og[:80]}")
    
    log.warning(f"Nenhuma imagem válida encontrada para: {entry.get('title', '?')[:60]}")
    return None


async def validar_imagem_ia(img_url: str, titulo: str) -> bool:
    """Usa IA de visão para verificar se a imagem combina com o título."""
    if not ai_client or not img_url or not titulo:
        return True  # Se não tem IA, assume válida (não bloqueia)
    try:
        resp = await ai_client.chat.completions.create(
            model="google/gemini-3.1-flash-lite",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um validador de imagens para um bot de notícias de tecnologia. "
                        "Analise se a imagem tem relação com o título da notícia. "
                        "Responda APENAS 'SIM' se a imagem é relevante ao tema da notícia, "
                        "ou 'NAO' se a imagem é completamente irrelevante (ex: anúncio, produto aleatório, "
                        "logo genérico, cortador de grama em notícia de cibersegurança, etc). "
                        "Imagens genéricas de tecnologia (teclados, telas, servidores) são aceitáveis "
                        "para notícias de tech. Responda apenas SIM ou NAO, nada mais."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Título da notícia: {titulo}"},
                        {"type": "image_url", "image_url": {"url": img_url}},
                    ],
                },
            ],
            max_tokens=5,
            temperature=0.0,
            timeout=15.0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        relevante = "SIM" in answer
        if not relevante:
            log.info(f"IA rejeitou imagem por irrelevância: {img_url[:80]} | título: {titulo[:60]}")
        return relevante
    except Exception as e:
        log.debug(f"Erro na validação IA de imagem: {e}")
        return True  # Em caso de erro, não bloqueia

# =========================
# ANÁLISE IA (OpenRouter)
# =========================
def _fix_sentence_case(text: str) -> str:
    """Converte Title Case para sentence case quando detectado."""
    words = text.split()
    if not words:
        return text
    long_words = [w for w in words if len(w) > 3 and not w[0].isdigit()]
    if not long_words:
        return text
    capitalized_ratio = sum(1 for w in long_words if w[0].isupper()) / len(long_words)
    if capitalized_ratio < 0.6:
        return text  # Não é Title Case, não mexe
    # Converte para sentence case: minúsculas, depois capitaliza após pontuação de fim de frase
    result = text.lower()
    result = result[0].upper() + result[1:] if result else result
    for punct in [". ", "! ", "? "]:
        parts = result.split(punct)
        result = punct.join(p[0].upper() + p[1:] if p else p for p in parts)
    return result


def _normalize_news_title(title: str) -> str:
    """Padroniza títulos para formato jornalístico direto (max 90 chars, sentence case)."""
    t = re.sub(r"\s+", " ", (title or "").strip())
    if not t:
        return t
    # Remove emoji/símbolos no começo para evitar duplicar marcador de urgência no embed.
    t = re.sub(r"^[^\wÀ-ÿ]+", "", t).strip()
    # Remove aspas e pontuação soltas no início/fim.
    t = t.strip(" -:;,.!?\"'`")
    # Limpa padrões comuns de clickbait.
    t = re.sub(r"(?i)\b(voc[eê] n[aã]o vai acreditar|imperd[ií]vel|chocante|surpreendente)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = _fix_sentence_case(t)
    
    # Mantém siglas comuns em caixa alta após normalização
    acronyms = ("IA", "EUA", "UE", "UK", "API", "CVE", "CEO", "GPU", "CPU", "AI")
    for ac in acronyms:
        t = re.sub(rf"\b{ac.lower()}\b", ac, t, flags=re.IGNORECASE)
    
    # Nomes próprios que devem ser TRADUZIDOS ou capitalizados
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
        # Nomes de jogos/personagens (traduzir)
        "mr. karate": "Senhor Karatê",
        "mr.karate": "Senhor Karatê",
        "fatal fury": "Fatal Fury",
        "city of the wolves": "Cidade dos Lobos",
        "pragmata": "Pragmata",
        "re requiem": "RE: Requiem",
        "phantom blade zero": "Phantom Blade Zero",
        "gamescom": "Gamescom",
    }
    # Nomes próprios compostos (multi-palavra) — aplicar primeiro
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
    
    # Garante pelo menos 8 palavras (se o original tiver)
    words = t.split()
    min_words = 8
    if len(words) < min_words and len(t) <= 150:
        # Título curto, manter original se não for muito longo
        pass
    else:
        # Limita tamanho para ~2 linhas (150 caracteres) preservando palavras
        max_len = 150
        if len(t) > max_len:
            cut = t[:max_len]
            # Corta no último espaço para não quebrar palavra
            last_space = cut.rfind(" ")
            if last_space >= 80:  # pelo menos 80 chars para caber 8 palavras
                cut = cut[:last_space]
            # Se após corte ficou com menos de 8 palavras, tenta recuperar
            if len(words) >= min_words and len(cut.split()) < min_words:
                # Recua até o 8º espaço
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
            t = t  # mantém original se <= max_len
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

    # Evita construções semânticas ruins como "A empresa governo federal".
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
    Processa o resumo para garantir formato correto e limite de 1000 caracteres.
    Remove construções semânticas estranhas e garante fluxo natural.
    """
    bruto = re.sub(r"\s+", " ", (texto or "").strip())
    if not bruto:
        return ""

    # Garante que termina com pontuação
    if not bruto[-1] in ".!?":
        bruto += "."

    # Limita a 1000 caracteres, cortando graciosamente no último ponto
    if len(bruto) > 1000:
        corte = bruto[:1000]
        ultimo_ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
        if ultimo_ponto > 400:
            bruto = corte[:ultimo_ponto + 1]
        else:
            bruto = corte.rstrip() + "..."
    
    # Corrige formatação de sentence case
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
    log.info(f"Resumo final: {len(resultado)} caracteres")
    
    return resultado if len(resultado) >= 50 else ""



_last_ai_call = 0.0
_ai_calls_this_cycle = 0

async def gerar_analise_ia(texto_base: str, titulo_original: str, nome_site: str) -> Optional[dict]:
    global _last_ai_call
    if not ai_client:
        return None

    # Cooldown entre chamadas
    now = time.monotonic()
    wait = (_last_ai_call + IA_COOLDOWN_SEC) - now
    if wait > 0:
        await asyncio.sleep(wait)
    # Atualizar timestamp ANTES da chamada (protege contra exceções)
    _last_ai_call = time.monotonic()

    prompt = f"""Analise a notícia abaixo e responda APENAS com JSON válido, sem markdown.

REGRAS RÍGIDAS PARA O TÍTULO (NÃO NEGOCIÁVEL):
- O CAMPO "titulo" DEVE TER ENTRE 8 E 15 PALAVRAS OBRIGATORIAMENTE.
- TÍTULO CURTO = REJEIÇÃO AUTOMÁTICA. Mínimo: 8 palavras. Máximo: 15.
- Se o título original tiver menos de 8 palavras, EXPENDA-O adicionando contexto jornalístico.
- Exemplos:
  ✗ "Meta processada" (2 palavras - REJETADO)
  ✗ "OpenAI lança GPT-5" (4 palavras - REJETADO)
  ✓ "Meta enfrenta processo milionário por uso indevido de livros no treinamento de IA" (11 palavras - ACEITO)
  ✓ "Nova versão do ChatGPT reduz alucinações em aplicações médicas e jurídicas" (10 palavras - ACEITO)

RESPONDA EM UM DOS DOIS FORMATOS:
1. SE REJEITAR: {{"pular": true, "reason": "motivo curto"}}
2. SE APROVAR: {{"pular": false, "titulo": "...", "nota": 85, "categoria": "...", "resumo": "..."}}

═══ REGRAS DE BLOQUEIO IMEDIATO (pular=true) ═══
- Promoção, oferta, cupom, desconto, preço, cashback, afiliado, guia de compra, "vale a pena comprar".
- Review, análise de produto, comparativo, unboxing, "melhor custo-benefício".
- Fofoca, treta, política não-tech, celebridade, esporte, horóscopo, entretenimento genérico.
- Ciência genérica sem relação com tech (biologia, paleontologia, arqueologia, astronomia pura).
- Conteúdo vago, clickbait sem substância, rumor sem fonte, notícia repetitiva.
- Smartphones intermediários/entrada: Galaxy A/M, Moto G/E, Redmi Note, POCO básico, "chegou ao Brasil" sem inovação.
- Games: reviews, skins, cosméticos, patch notes menores, eventos semanais, item shop, preços, promoções de jogos.

═══ CATEGORIAS (use exatamente uma destas) ═══
Hardware | Inteligência Artificial | Games | Cibersegurança | Sistemas Operacionais | Smartphones | Big Techs | Ciência & Espaço | Software & Apps | Cloud & DevOps | Programação & Dev | Internet & Redes | Mídia & Streaming | Curiosidade Tech | Outros

═══ ESCALA DE NOTAS (seja rigoroso) ═══
- 95-100: CATÁSTROFE ou MARCO MUNDIAL. Queda global de serviço, hack massivo, lançamento de nova geração (iPhone, Windows, GPT novo).
- 85-94: ALTA RELEVÂNCIA. Grandes novidades confirmadas, vulnerabilidade crítica (CVE alto), aquisição bilionária, demissão em massa.
- 75-84: RELEVANTE. Interessante para entusiastas de tech, atualização significativa, nova feature de grande plataforma.
- <75: IRRELEVANTE — marque pular=true.

═══ TÍTULO ═══
- OBRIGATÓRIO: EXATAMENTE ENTRE 8 E 15 PALAVRAS. NUNCA MENOS QUE 8.
- Claro, jornalístico, autoexplicativo. Quem lê o título entende o fato sem precisar clicar.
- Em PT-BR. Jargões tech comuns podem ser mantidos em inglês: "phishing", "ransomware", "zero-day", "malware", "exploit", "hacker", "Windows", "iPhone", "ChatGPT", "Google", "Android", "API", "Linux", "Wi-Fi", "Bluetooth", etc.
- MAS o título deve ser CLARO e LEGÍVEL para qualquer entusiasta de tech. Proibido:
  ✗ Aportuguesar verbos ingleses: "hijacka", "bypassa", "patcha" — use equivalentes: "sequestra", "burla", "corrige".
  ✗ Acumular jargões sem contexto: "Kit de phishing Tycoon2FA hijacka contas via device-code phishing" — incompreensível.
  ✗ Nomes de ferramentas/malwares obscuros no título: mova para o resumo. Ex: "Tycoon2FA" → resumo.
  ✓ BOM: "Novo golpe de phishing rouba contas do Microsoft 365 usando código de verificação"
  ✓ BOM: "Falha zero-day no Chrome permite execução de código remoto"
  ✓ BOM: "Ransomware ataca hospitais nos EUA e paralisa sistemas por dias"
- Sem clickbait. Sentence case: só primeira palavra e nomes próprios em maiúscula.
- Entre 80 e 150 caracteres. Conta as palavras ANTES de enviar.
- EXEMPLOS DE TÍTULOS BONS:
  ✓ "Meta enfrenta processo milionário por uso indevido de livros no treinamento de IA"
  ✓ "Nova versão do ChatGPT reduz erros em aplicações médicas e jurídicas"
  ✓ "Novo golpe de phishing rouba contas do Microsoft 365 usando código de verificação"
  ✗ "Meta processada" (RUIM: apenas 2 palavras)
  ✗ "Kit de phishing Tycoon2FA hijacka contas via device-code" (RUIM: verbos aportuguesados + jargões obscuros acumulados)

═══ RESUMO ═══
- Um único parágrafo contínuo, 4 a 6 frases. Sem bullet points, sem quebras de linha.
- Estilo Filipe Deschamps: engajante, contextualizado, explica o fato, o porquê e o impacto real.
- Estrutura: CONTEXTO/GANCHO → FATO PRINCIPAL → DETALHE RELEVANTE → IMPACTO ou REAÇÃO.
- Linguagem jornalística mas acessível: não seco, não acadêmico, não telegráfico. Faz o leitor entender por que isso importa.
- NÃO REPITA a mesma ideia com palavras diferentes. Cada frase deve trazer informação NOVA.
- PROIBIDO frases genéricas de enchimento como:
  ✗ "pode ter implicações significativas" / "o que pode ser um grande diferencial"
  ✗ "além disso, essa novidade pode influenciar..." / "isso pode impactar o mercado"
  ✗ "a comunidade aguarda com expectativa" / "destaca a importância de..."
  ✗ Qualquer frase que poderia ser colada em QUALQUER notícia sem mudar nada. Cada frase deve conter FATOS CONCRETOS da notícia.
- PROIBIDO inventar informações ou confundir empresas/produtos. Se a notícia não menciona um dado, NÃO invente.
- Em PT-BR com gramática impecável.
- LIMITE: entre 600 e 1000 caracteres. Não ultrapasse 1000.

═══ FILTROS ESPECIAIS ═══
SMARTPHONES: Aceitar APENAS flagships (iPhone, Galaxy S/Z, Pixel Pro, Xiaomi Ultra) ou inovação real.
GAMES: Aceitar APENAS grandes lançamentos AAA confirmados, grandes eventos (TGA, E3, Nintendo Direct), aquisições de estúdios ou demissões em massa (100+ funcionários). Rejeitar: sindicatos, direitos trabalhistas, greves, negociações coletivas, vazamentos de código-fonte de jogos antigos, mods, hacks de console, cheats, patches de balanceamento, temporadas de battle pass, polêmicas internas de estúdio.
CIBERSEGURANÇA: Priorizar CVE crítico, ransomware, vazamento de dados, zero-day. Nota ≥85.

Fonte: {nome_site}
Título Original: {titulo_original}
Texto da Notícia: {texto_base[:8000]}
"""

    modelo_principal = "google/gemini-3.1-flash-lite"
    modelo_fallback = "google/gemini-3.1-flash-lite"

    for attempt in range(3):
        modelo = modelo_principal if attempt == 0 else modelo_fallback
        log.info(f"IA tentativa {attempt+1}/3 usando modelo: {modelo}")
        try:
            response = await ai_client.chat.completions.create(
                model=modelo,
                messages=[
                    {"role": "system", "content": "Responda APENAS com JSON válido, sem markdown, sem texto fora do JSON. REGRAS CRÍTICAS: 1) Título claro e legível em PT-BR — jargões tech comuns OK, mas nunca aportuguesar verbos ingleses nem acumular termos obscuros. 2) Resumo: parágrafo denso com 4-6 frases, entre 600 e 1000 caracteres. Cada frase deve trazer FATOS CONCRETOS — PROIBIDO frases genéricas de enchimento como 'pode ter implicações significativas' ou 'destaca a importância'. 3) NUNCA invente informações que não estão na notícia."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                timeout=60.0,
            )
            resp = response.choices[0].message.content.strip()
            # Descartar respostas absurdamente grandes (evita hang no parsing)
            if len(resp) > 50_000:
                log.error("Resposta da IA muito grande (%d chars), descartando", len(resp))
                continue
            # Extrair JSON: tenta achar o primeiro objeto JSON válido
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
                        log.warning("Resumo vazio após normalização, rejeitando")
                        return None
                if isinstance(data.get("titulo"), str):
                    data["titulo"] = _normalize_news_title(data["titulo"])
                return data
        except Exception as e:
            log.warning(f"IA tentativa {attempt+1}/3 falhou ({modelo}): {e}")
            if attempt < 2:
                backoff = 2 ** (attempt + 1)
                log.info(f"Aguardando {backoff}s antes da próxima tentativa...")
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
    """Retorna True apenas se a notícia tem data e é recente. Sem data = rejeitar."""
    if not entry_dt:
        return False
    return entry_dt >= datetime.now(timezone.utc) - timedelta(hours=MAX_IDADE_HORAS)

# =========================
# POSTAR NOTÍCIA (extraído para reuso)
# =========================
async def _baixar_imagem(url: str, retries: int = 3) -> Optional[tuple[bytes, str]]:
    """Baixa a imagem e retorna (bytes, extensão). Retry em caso de falha.
    Valida dimensões mínimas e aspect ratio para evitar imagens cortadas/banners."""
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
                    log.debug(f"Imagem HTTP {r.status}: {url[:80]} (tentativa {attempt+1})")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                ct = r.headers.get("Content-Type", "").lower()
                if "image/" not in ct:
                    log.debug(f"Imagem Content-Type inválido ({ct}): {url[:80]}")
                    return None
                # Verificar Content-Length antes de baixar (rejeitar > 10MB)
                cl_header = r.headers.get("Content-Length", "")
                expected_size = int(cl_header) if cl_header.isdigit() else 0
                if expected_size > 10 * 1024 * 1024:
                    log.debug(f"Imagem grande demais ({expected_size} bytes): {url[:80]}")
                    return None
                data = await r.read()  # lê resposta completa (não trunca)
                if len(data) > 10 * 1024 * 1024:
                    log.debug(f"Imagem grande demais ({len(data)} bytes): {url[:80]}")
                    return None
                if len(data) < 5000:
                    log.debug(f"Imagem muito pequena ({len(data)} bytes): {url[:80]}")
                    return None
                # Verificar integridade: Content-Length vs bytes recebidos
                if expected_size and len(data) < expected_size:
                    log.warning(f"Imagem incompleta ({len(data)}/{expected_size} bytes): {url[:80]}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                # Validar dimensões da imagem completa (evita imagens cortadas/corrompidas)
                dims = _img_dimensions_from_bytes(data)
                if dims:
                    w, h = dims
                    if w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT:
                        log.warning(f"Imagem download rejeitada: {w}x{h} < {MIN_IMG_WIDTH}x{MIN_IMG_HEIGHT} ({url[:80]})")
                        return None
                    # Rejeitar aspect ratio extremo (banners finos, imagens muito altas)
                    ratio = w / h if h > 0 else 0
                    if ratio > 4.0 or ratio < 0.3:
                        log.warning(f"Imagem rejeitada por aspect ratio ({ratio:.2f}): {w}x{h} ({url[:80]})")
                        return None
                else:
                    # Se não conseguiu extrair dimensões, rejeitar (imagem possivelmente corrompida)
                    log.warning(f"Imagem rejeitada: impossível extrair dimensões ({url[:80]})")
                    return None
                # Validar magic bytes e integridade do EOF
                if data[:2] == b'\xff\xd8':
                    ext = "jpg"
                    # JPEG deve terminar com FFD9 (End of Image)
                    if data[-2:] != b'\xff\xd9':
                        log.warning(f"JPEG truncado (sem EOF marker): {url[:80]}")
                        if attempt < retries - 1:
                            await asyncio.sleep(2)
                        continue
                elif data[:4] == b'\x89PNG':
                    ext = "png"
                    # PNG deve terminar com IEND chunk
                    if b'IEND' not in data[-20:]:
                        log.warning(f"PNG truncado (sem IEND): {url[:80]}")
                        if attempt < retries - 1:
                            await asyncio.sleep(2)
                        continue
                elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                    ext = "webp"
                elif data[:4] == b'GIF8':
                    ext = "gif"
                else:
                    # Fallback pelo content-type
                    ext = "jpg"
                    if "png" in ct:
                        ext = "png"
                    elif "webp" in ct:
                        ext = "webp"
                    elif "gif" in ct:
                        ext = "gif"
                return data, ext
        except Exception as e:
            log.debug(f"Erro ao baixar imagem {url[:80]} (tentativa {attempt+1}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
    return None


async def _postar_noticia(channel, noticia: dict, history: dict, metrics: dict) -> bool:
    """Posta uma notícia no canal. Retorna True se postou com sucesso."""
    # Trava de segurança: nunca postar sem imagem
    img_url = noticia.get("imagem")
    if not img_url:
        log.error(f"Tentativa de postar sem imagem, abortando: {noticia.get('titulo', '')[:60]}")
        return False

    # Baixar imagem para anexar (evita hotlink protection / URLs que Discord não carrega)
    img_data = await _baixar_imagem(img_url)
    if not img_data:
        log.warning(f"Falha ao baixar imagem, abortando post: {noticia.get('titulo', '')[:60]}")
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

    try:
        # Só menciona o cargo se ele existe e a nota é urgente
        mention = None
        if noticia["nota"] >= NOTA_URGENTE and ID_CARGO_PARA_MARCAR:
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
            log.warning(f"Erro ao criar thread: {e}")

        historico_set(history, noticia["link_norm"], noticia["dedupe"], "posted")
        metric_inc(metrics, "posts_hoje")
        log.info(f"  📨 Postado: {noticia['titulo'][:60]}")
        return True
    except Exception as e:
        log.error(f"  Erro ao postar: {e}")
        return False

# =========================
# PIPELINE PRINCIPAL
# =========================
# Estado global para /status
_last_cycle_time: str = "Nunca"
_last_cycle_stats: dict = {}
_last_run_slot: Optional[Tuple[int, int, int]] = None

def _janela_ativa_ou_pre_aquecimento(agora: datetime) -> bool:
    """Permite coleta no horário comercial e no pré-aquecimento antes das 8h."""
    if HORA_INICIO <= agora.hour < HORA_FIM:
        return True
    return agora.hour == (HORA_INICIO - 1) and agora.minute >= MINUTO_PRE_AQUECIMENTO


def _deve_rodar_slot(agora: datetime) -> bool:
    """Roda somente em slots fixos (xx:00 e xx:45) e apenas uma vez por slot."""
    global _last_run_slot
    if agora.minute not in (0, 45):
        return False
    slot = (agora.year * 10000 + agora.month * 100 + agora.day, agora.hour, agora.minute)
    if _last_run_slot == slot:
        return False
    _last_run_slot = slot
    return True


@tasks.loop(minutes=1)
async def verificar_feeds():
    global _ai_calls_this_cycle, http_session, _last_cycle_time, _last_cycle_stats
    global _simhash_pruned_this_cycle, _title_pruned_this_cycle
    await discord_client.wait_until_ready()

    agora = datetime.now(FUSO_HORARIO_BR)
    if not _deve_rodar_slot(agora):
        return

    if not _janela_ativa_ou_pre_aquecimento(agora):
        log.info(f"Standby: {agora.strftime('%H:%M')} fora da janela de coleta (pré 07:45 + 08h-18h).")
        return

    # Resetar flags de prune para este ciclo
    _simhash_pruned_this_cycle = False
    _title_pruned_this_cycle = False

    if not http_session or http_session.closed:
        connector = aiohttp.TCPConnector(limit=15, limit_per_host=3)
        http_session = aiohttp.ClientSession(connector=connector)

    channel = discord_client.get_channel(CANAL_NOTICIAS_ID)
    if not channel:
        try:
            channel = await discord_client.fetch_channel(CANAL_NOTICIAS_ID)
        except Exception as e:
            log.error(f"Canal de notícias não encontrado: {e}")
            return
    if not channel:
        return

    _ai_calls_this_cycle = 0
    history = load_history()
    metrics = load_metrics()

    # ===== FASE 0: Postar da fila de ciclos anteriores (apenas em horário ativo) =====
    queue = load_queue()
    posts_feitos = 0
    em_horario_ativo = HORA_INICIO <= agora.hour < HORA_FIM
    if queue and em_horario_ativo:
        log.info(f"═══ FASE 0: Postando {len(queue)} da fila ═══")
        nova_queue = []
        for item in queue:
            if posts_feitos >= MAX_POSTS_POR_CICLO:
                nova_queue.append(item)
                continue
            img = item.get("imagem")
            if not img:
                log.warning(f"  ✗ Item da fila sem imagem, descartando: {item.get('titulo', '?')[:60]}")
                continue
            # Dedup: verificar se título já foi postado
            titulo_item = item.get("titulo", "")
            if titulo_item and title_is_dup(history, titulo_item):
                log.info(f"  ✗ Fila: título duplicado, descartando: {titulo_item[:60]}")
                continue
            # Dedup: verificar simhash do conteúdo
            sh_item = _simhash64(f"{titulo_item} {item.get('resumo', '')}")
            if simhash_is_dup(history, sh_item):
                log.info(f"  ✗ Fila: simhash duplicado, descartando: {titulo_item[:60]}")
                continue
            # Revalidar imagem da fila (URLs podem ter morrido)
            if not await validar_imagem(img):
                log.warning(f"  ✗ Imagem inválida na fila, descartando: {item.get('titulo', '?')[:60]}")
                continue
            if await _postar_noticia(channel, item, history, metrics):
                posts_feitos += 1
                title_add(history, titulo_item)
                simhash_add(history, sh_item)
                if posts_feitos < MAX_POSTS_POR_CICLO:
                    await asyncio.sleep(POST_SPACING_SEC)
            else:
                nova_queue.append(item)
        save_queue(nova_queue)
        save_history(history)
        save_metrics(metrics)

        if posts_feitos >= MAX_POSTS_POR_CICLO:
            _last_cycle_time = agora.strftime("%H:%M:%S")
            _last_cycle_stats = {"posts": posts_feitos, "fonte": "fila"}
            log.info(f"Limite de posts atingido via fila. Coleta adiada para próximo ciclo.")
            return

    # ===== FASE 1: Coleta paralela + Pré-filtro (sem IA) =====
    log.info("═══ FASE 1: Coleta + Pré-filtro ═══")

    # Buscar todos os feeds em paralelo
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
            log.warning(f"Feed timeout/erro: {nome_site} — {e}")
            _set_feed_cooldown(nome_site)
            return nome_site, None

    resultados_feeds = await asyncio.gather(
        *[_fetch_feed(n, u) for n, u in FONTES_RSS.items()],
        return_exceptions=True,
    )
    # Filtrar exceções inesperadas do gather
    resultados_feeds = [
        r for r in resultados_feeds
        if not isinstance(r, BaseException)
    ]

    # Filtrar candidatos (sem validação de imagem ainda)
    pre_candidatos = []
    total_examinados = 0
    total_prefiltrados = 0
    total_dedup = 0
    total_antigas = 0
    contagem_por_fonte: dict[str, int] = {}
    # Sets de dedup in-cycle (não poluem o histórico persistente)
    _cycle_titles: set[str] = set()
    _cycle_simhashes: set[int] = set()

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

            # Verificar idade PRIMEIRO (rejeitar velhas antes de qualquer processamento)
            dt = entry_datetime_utc(entry)
            if not noticia_eh_recente(dt):
                total_antigas += 1
                continue

            link_norm = normalizar_url(link)

            # Dedup por URL e hash
            dedupe = make_dedupe_hash(title, int(dt.timestamp()) if dt else int(time.time()))
            if historico_check(history, link_norm, dedupe):
                total_dedup += 1
                continue

            # Dedup por título normalizado (cross-site: mesma notícia em sites diferentes)
            _tfp = _title_fingerprint(title)
            if title_is_dup(history, title) or _tfp in _cycle_titles:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_titulo"})
                total_dedup += 1
                continue

            # SimHash dedup (conteúdo similar mesmo com títulos diferentes)
            texto_raw = limpar_html(str(entry.get("summary") or entry.get("description") or title))
            sh = _simhash64(f"{title} {texto_raw[:600]}")
            if simhash_is_dup(history, sh) or sh in _cycle_simhashes:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_simhash"})
                total_dedup += 1
                continue

            # PRÉ-FILTRO POR KEYWORDS (custo zero — antes da IA)
            if not prefiltro_keywords(title, texto_raw):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "prefiltro_keywords"})
                total_prefiltrados += 1
                log.info(f"  ✗ Prefiltro rejeitou: [{nome_site}] {title[:60]}")
                continue
            
            # PRÉ-FILTRO: Título muito curto/vago (antes da IA para economizar calls)
            palavras_titulo = [p for p in title.split() if p]
            if len(palavras_titulo) < 8:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "titulo_curto_prefiltro"})
                total_prefiltrados += 1
                log.info(f"  ✗ Título curto pré-filtro ({len(palavras_titulo)} palavras): [{nome_site}] {title[:60]}")
                continue
            
            # PRÉ-FILTRO: Título muito vago (genérico demais)
            titulo_lower = title.lower()
            titulos_vagos = ["meta processada", "meta processa", "openai lança", "google lança"]
            if any(vago in titulo_lower for vago in titulos_vagos):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "titulo_vago"})
                total_prefiltrados += 1
                log.info(f"  ✗ Título vago: [{nome_site}] {title[:60]}")
                continue

            # Limite de candidatos por fonte (diversidade)
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
            # Dedup cross-site no mesmo ciclo: usar set em memória (não polui o histórico persistente)
            _cycle_titles.add(_title_fingerprint(title))
            _cycle_simhashes.add(sh)
            aceitos_fonte += 1
            contagem_por_fonte[nome_site] = contagem_por_fonte.get(nome_site, 0) + 1

    # ===== Validação de imagem em batch (paralelo com semáforo) =====
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
                log.warning("Erro na validação de imagem: %s", result)
                continue
            cand, img = result
            if not img:
                historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "sem_imagem"})
                total_sem_imagem += 1
                continue
            # Validação IA: verificar se imagem combina com o título
            titulo_cand = cand.get("title", "")
            if not await validar_imagem_ia(img, titulo_cand):
                log.info(f"  ✗ Imagem irrelevante (IA): [{cand.get('nome_site', '?')}] {titulo_cand[:60]}")
                historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "imagem_irrelevante_ia"})
                total_img_ia_rejeitada += 1
                continue
            cand["img"] = img
            candidatos.append(cand)

    log.info(
        f"Fase 1 concluída: {total_examinados} examinados, "
        f"{total_antigas} antigas, {total_dedup} dedup, {total_prefiltrados} prefiltrados, "
        f"{total_sem_imagem} sem imagem, {total_img_ia_rejeitada} imagem irrelevante (IA) "
        f"→ {len(candidatos)} candidatos para IA"
    )

    if not candidatos:
        save_history(history)
        return

    # ===== FASE 2: Análise IA (budget-limited) =====
    log.info(f"═══ FASE 2: Análise IA (budget: {MAX_IA_CALLS_POR_CICLO}) ═══")
    aprovados = []

    for cand in candidatos:
        if _ai_calls_this_cycle >= MAX_IA_CALLS_POR_CICLO:
            log.info(f"Budget de IA esgotado ({MAX_IA_CALLS_POR_CICLO} chamadas).")
            break

        # Dedup extra: verificar se assunto já foi aprovado neste ciclo
        titulo_lower = cand["title"].lower()
        assunto_keywords = set()
        for palavra in [
            # Big techs & pessoas
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
            # Espaço & ciência
            "jwst", "james webb", "nasa", "shenzhou", "tiangong", "artemis",
            "spacex", "starship", "starlink",
            # Segurança
            "ransomware", "phishing", "malware", "cve-",
            # Brasil & telecom
            "anatel", "5g", "starlink",
            # Veículos & hardware específico
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
                log.info(f"  ✗ Assunto repetido ({list(assunto_keywords)[0]}): [{cand['nome_site']}] {cand['title'][:60]}")
                continue

        _ai_calls_this_cycle += 1
        metric_inc(metrics, "ia_calls_hoje")
        res = await gerar_analise_ia(cand["texto_raw"], cand["title"], cand["nome_site"])

        if not isinstance(res, dict) or res.get("pular"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "ia_rejeitou"})
            metric_inc(metrics, "ia_rejeitadas_hoje")
            log.info(f"  ✗ IA rejeitou: [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        # Validar campos obrigatórios da resposta da IA
        if not res.get("titulo") or not res.get("resumo"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "ia_campos_faltando"})
            log.warning(f"  ✗ IA retornou sem titulo/resumo: [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        try:
            nota = int(res.get("nota", 0))
        except (ValueError, TypeError):
            nota = 0
        categoria = res.get("categoria", "Outros")

        # Threshold de nota
        min_nota = NOTA_MIN_GAMES if categoria == "Games" else NOTA_MIN_APROVACAO
        if nota < min_nota:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"nota_baixa_{nota}"})
            metric_inc(metrics, "ia_rejeitadas_hoje")
            log.info(f"  ✗ Nota baixa ({nota}): [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        # SimHash pós-IA (título + resumo gerados)
        sh_post = _simhash64(f"{res.get('titulo', '')} {res.get('resumo', '')}")
        if simhash_is_dup(history, sh_post):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "dup_simhash_pos"})
            continue

        simhash_add(history, sh_post)
        simhash_add(history, cand["simhash"])
        # Registrar título original E traduzido no índice
        title_add(history, cand["title"])
        title_add(history, res.get("titulo", ""))

        # TRAVA: sem imagem = não aprovar jamais
        if not cand.get("img"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "sem_imagem_fase2"})
            log.info(f"  ✗ Sem imagem (Fase 2): [{cand['nome_site']}] {cand['title'][:60]}")
            continue
        
        # TRAVA: título deve ter pelo menos 8 palavras (contagem real)
        titulo_final = res.get("titulo", "").strip()
        # Remove emojis e pontuação para contar palavras reais
        titulo_limpo = re.sub(r'[^\w\s]', ' ', titulo_final)
        palavras_titulo = [p for p in titulo_limpo.split() if len(p) > 2]  # palavras com mais de 2 letras
        if len(palavras_titulo) < 8:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"titulo_curto_{len(palavras_titulo)}palavras"})
            log.info(f"  ✗ Título muito curto ({len(palavras_titulo)} palavras): {titulo_final[:60]}")
            continue
        
        # TRAVA: título muito vago (menos de 60 caracteres após normalização)
        if len(titulo_final) < 60:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "titulo_vago_curto"})
            log.info(f"  ✗ Título muito vago/curto: {titulo_final[:60]}")
            continue
        
        # TRAVA EXTRA: Rejeitar títulos que são apenas 2-3 palavras mesmo após processamento
        if len(titulo_final.split()) < 8:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"titulo_palavras_insuf_{len(titulo_final.split())}"})
            log.info(f"  ✗ Título com poucas palavras: {titulo_final[:60]}")
            continue

        metric_inc(metrics, "ia_aprovadas_hoje")
        aprovados.append({
            "titulo": res.get("titulo", cand["title"]),  # já normalizado em gerar_analise_ia()
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
        log.info(f"  ✓ Aprovado (nota {nota}): [{cand['nome_site']}] {res.get('titulo', '')[:60]}")

    log.info(f"Fase 2 concluída: {_ai_calls_this_cycle} chamadas IA → {len(aprovados)} aprovados")

    if not aprovados:
        save_history(history)
        save_metrics(metrics)
        return

    # ===== FASE 3: Postar as melhores + enfileirar restantes =====
    log.info("═══ FASE 3: Postando melhores notícias ═══")

    # Ordenar por nota (maior primeiro)
    aprovados.sort(key=lambda x: x["nota"], reverse=True)

    # Filtrar sem imagem
    com_imagem = [a for a in aprovados if a.get("imagem")]
    if not com_imagem:
        log.warning("Nenhuma notícia aprovada possui imagem válida. Nada será postado.")
        save_history(history)
        save_metrics(metrics)
        return

    # Postar até o limite (somente horário ativo), enfileirar o restante
    posts_restantes = MAX_POSTS_POR_CICLO - posts_feitos
    para_postar = com_imagem[:posts_restantes] if em_horario_ativo else []
    para_fila = com_imagem[posts_restantes:] if em_horario_ativo else com_imagem

    posts_fase3 = 0
    for i, noticia in enumerate(para_postar):
        # Revalidar imagem no momento do post (URLs podem ter morrido)
        img = noticia.get("imagem")
        if not img or not await validar_imagem(img):
            log.warning(f"  ✗ Imagem inválida ao postar, descartando: {noticia.get('titulo', '?')[:60]}")
            historico_set(history, noticia["link_norm"], noticia["dedupe"], "skipped", {"reason": "sem_imagem_post"})
            continue
        log.info(f"  🏆 Postando (nota {noticia['nota']}): [{noticia['site']}] {noticia['titulo'][:60]}")
        if await _postar_noticia(channel, noticia, history, metrics):
            posts_fase3 += 1
        if i < len(para_postar) - 1:
            await asyncio.sleep(POST_SPACING_SEC)

    # Enfileirar restantes para próximo ciclo
    if para_fila:
        queue_atual = load_queue()
        # Validar campos obrigatórios antes de enfileirar
        _campos_obrigatorios = ("titulo", "imagem", "link", "nota")
        para_fila = [n for n in para_fila if all(n.get(c) for c in _campos_obrigatorios)]
        queue_atual.extend(para_fila)
        # Limitar fila a 10 itens (evitar acúmulo infinito)
        queue_atual = sorted(queue_atual, key=lambda x: x.get("nota", 0), reverse=True)[:10]
        save_queue(queue_atual)
        log.info(f"  📋 {len(para_fila)} notícias enfileiradas para próximo ciclo (fila total: {len(queue_atual)})")

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
    log.info("Ciclo concluído.")


_CMD_NAMES = (
    "nowplaying", "playlist", "summary", "random", "resume", "pause", "clear", "skip",
    "enter", "entra", "leave", "loop", "play", "chat", "seek", "nonstop", "queue",
    "shuffle", "replay", "history", "autoplay", "lyrics", "roll", "dice", "clip",
    "np", "pa", "re", "cl", "pl", "su", "ff", "sh", "rp", "hi", "ap", "ly", "lv", "cp", "lo",
    "ch", "247", "q",
    "l", "e", "s", "c", "p", "r", "d",
)

@discord_client.event
async def on_message(message: discord.Message):
    """Normaliza comandos sem espaço (ex: t$phttps://... → t$p https://...)."""
    try:
        if message.author.bot:
            return
        content = message.content
        if not content:
            return
        lower = content.lower()
        if lower.startswith("t$"):
            after_prefix = content[2:]
            matched = False
            # Tenta casar com comandos conhecidos (maior primeiro para np/pa/re/cl/pl/st/su)
            for cmd in sorted(_CMD_NAMES, key=len, reverse=True):
                if after_prefix.lower().startswith(cmd):
                    if len(after_prefix) == len(cmd) or after_prefix[len(cmd)] == " ":
                        # Comando já formatado corretamente (exato ou com espaço)
                        break
                    # Insere espaço entre comando e argumento
                    message.content = f"t${cmd} {after_prefix[len(cmd):]}"
                    matched = True
                    break
            # Normaliza prefixo para minúsculo (T$ → t$)
            if not matched and content[:2] != "t$":
                message.content = f"t${content[2:]}"
        await discord_client.process_commands(message)
    except Exception:
        log.exception("Erro no on_message")


@discord_client.event
async def on_ready():
    log.info(f"🤖 Tiffany Online: {discord_client.user}")
    # Sync slash commands: limpar guild-specific antigos + sync global
    try:
        # Remover comandos guild-specific duplicados (legado)
        for g in discord_client.guilds:
            try:
                discord_client.tree.clear_commands(guild=g)
                await discord_client.tree.sync(guild=g)
            except Exception:
                pass
        # Sync global (funciona em todos os servidores)
        await discord_client.tree.sync()
        log.info("Slash commands sincronizados (global, %d guilds limpos).", len(discord_client.guilds))
    except Exception as e:
        log.warning(f"Erro ao sincronizar slash commands: {e}")
    if not verificar_feeds.is_running():
        verificar_feeds.start()

@discord_client.event
async def on_close():
    global http_session
    if http_session:
        await http_session.close()
        http_session = None
    log.info("🔌 Sessão HTTP fechada. Bot desligando.")


# =========================
# SLASH COMMAND: /status
# =========================
@discord_client.tree.command(name="status", description="Exibe o status atual do bot Tiffany")
@discord.app_commands.default_permissions(administrator=True)
async def cmd_status(interaction: discord.Interaction):
    agora = datetime.now(FUSO_HORARIO_BR)
    metrics = load_metrics()
    queue = load_queue()

    # Feeds em cooldown
    feeds_cooldown = [nome for nome in FONTES_RSS if _feed_em_cooldown(nome)]

    em = discord.Embed(
        title="📊 Status — Tiffany Bot",
        color=TIFFANY_PINK,
        timestamp=agora,
    )
    em.add_field(
        name="⏰ Horário (SP)",
        value=agora.strftime("%H:%M:%S"),
        inline=True,
    )
    em.add_field(
        name="🔄 Último ciclo",
        value=_last_cycle_time,
        inline=True,
    )
    em.add_field(
        name="📡 Modo",
        value="Ativo" if HORA_INICIO <= agora.hour < HORA_FIM else "Standby",
        inline=True,
    )
    em.add_field(
        name="📨 Posts hoje",
        value=str(metrics.get("posts_hoje", 0)),
        inline=True,
    )
    em.add_field(
        name="🤖 IA calls hoje",
        value=str(metrics.get("ia_calls_hoje", 0)),
        inline=True,
    )
    em.add_field(
        name="✅ Aprovadas / ❌ Rejeitadas",
        value=f"{metrics.get('ia_aprovadas_hoje', 0)} / {metrics.get('ia_rejeitadas_hoje', 0)}",
        inline=True,
    )
    em.add_field(
        name="📋 Fila",
        value=f"{len(queue)} notícias aguardando",
        inline=True,
    )
    em.add_field(
        name="📰 Feeds em cooldown",
        value=", ".join(feeds_cooldown) if feeds_cooldown else "Nenhum",
        inline=False,
    )

    if _last_cycle_stats:
        stats = _last_cycle_stats
        em.add_field(
            name="📈 Último ciclo",
            value=(
                f"Examinados: {stats.get('examinados', '?')} · "
                f"Para IA: {stats.get('candidatos_ia', '?')} · "
                f"Aprovados: {stats.get('aprovados', '?')} · "
                f"Postados: {stats.get('posts', '?')}"
            ),
            inline=False,
        )

    em.add_field(
        name="📊 Totais",
        value=(
            f"Posts: {metrics.get('posts_total', 0)} · "
            f"IA calls: {metrics.get('ia_calls_total', 0)} · "
            f"Aprovadas: {metrics.get('ia_aprovadas_total', 0)} · "
            f"Rejeitadas: {metrics.get('ia_rejeitadas_total', 0)}"
        ),
        inline=False,
    )

    em.set_footer(text="Tiffany Bot v18")
    await interaction.response.send_message(embed=em, ephemeral=True)


async def _shutdown_cleanup():
    """Cleanup garantido para http_session em qualquer cenário de shutdown."""
    global http_session
    if http_session:
        await http_session.close()
        http_session = None
        log.info("🔌 Sessão HTTP fechada no shutdown.")

def _sync_cleanup():
    """Cleanup síncrono de emergência via atexit."""
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
        log.warning("⚠️ http_session fechada via atexit (shutdown forçado).")

atexit.register(_sync_cleanup)

discord_client.run(DISCORD_TOKEN)
