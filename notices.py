import discord
from discord.ext import tasks, commands
import feedparser
import os
import re
import json
import time
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import html as html_lib
import hashlib
import atexit
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin

import aiohttp
from dotenv import load_dotenv
from openai import AsyncOpenAI

import tiffany_voice

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
NOTA_MIN_APROVACAO = 75
NOTA_MIN_GAMES = 82
NOTA_URGENTE = 90

# --- Anti-dup ---
SIMHASH_TTL_HORAS = 120
SIMHASH_HAMMING_MAX = 4
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

# =========================
# DISCORD + IA CLIENT
# =========================
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

intents = discord.Intents.default()
# Only enable voice intents if voice is enabled
if os.getenv("VOICE_ENABLED", "1").strip() == "1":
    intents.voice_states = True
intents.message_content = True
discord_client = commands.Bot(command_prefix="$", intents=intents)
tiffany_voice.register_voice(discord_client)
ai_client = (
    AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    if OPENROUTER_API_KEY
    else None
)
http_session: aiohttp.ClientSession | None = None

# --- Feed cooldown state ---
_feed_cooldown_until: dict[str, float] = {}

def _set_feed_cooldown(nome_site: str) -> None:
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
CORES_CATEGORIA = {
    "Hardware": 0xE03E3E,
    "Inteligência Artificial": 0x00FFFF,
    "Games": 0x9146FF,
    "Cibersegurança": 0x00FF00,
    "Sistemas Operacionais": 0x00A4EF,
    "Smartphones": 0xFFA500,
    "Big Techs": 0x000080,
    "Ciência & Espaço": 0x808080,
    "Software & Apps": 0x5865F2,
    "Cloud & DevOps": 0x3498DB,
    "Programação & Dev": 0x2ECC71,
    "Internet & Redes": 0x1ABC9C,
    "Mídia & Streaming": 0xE91E63,
    "Curiosidade Tech": 0xF39C12,
    "Outros": 0x95A5A6,
}
COR_PADRAO = 0xFFD700

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
    "review", "análise de produto", "guia de compra", "buying guide",
    "comparativo", "melhor custo-benefício", "vale a pena comprar",
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
    # Preservar índices internos
    if "_simhash_idx" in h:
        novo["_simhash_idx"] = h["_simhash_idx"]
    if "_title_idx" in h:
        novo["_title_idx"] = h["_title_idx"]
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
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(novo, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_FILE)

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
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    os.replace(tmp, METRICS_FILE)

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
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUEUE_FILE)

def _hist_payload(status: str, extra: dict | None = None) -> dict:
    payload = {"status": status, "ts": int(time.time())}
    if extra:
        payload.update(extra)
    return payload

def historico_check(h: dict, link_norm: str, dedupe_hash: str | None) -> bool:
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

def historico_set(h: dict, link_norm: str, dedupe_hash: str | None, status: str, extra: dict | None = None) -> None:
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

def simhash_is_dup(h: dict, sh: int) -> bool:
    if sh == 0:
        return False
    idx = _simhash_prune(_get_simhash_index(h))
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
    idx = _simhash_prune(_get_simhash_index(h))
    idx[f"{sh:016x}"] = int(time.time())
    h["_simhash_idx"] = idx

# =========================
# ÍNDICE DE TÍTULOS (cross-site dedup)
# =========================
def _get_title_index(h: dict) -> dict[str, int]:
    idx = h.get("_title_idx")
    return idx if isinstance(idx, dict) else {}

def _title_idx_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (TITLE_IDX_TTL_HORAS * 3600)
    return {k: ts for k, ts in idx.items() if ts >= cutoff}

def title_is_dup(h: dict, titulo: str) -> bool:
    """Checa se um título normalizado já foi processado (qualquer site)."""
    fp = _title_fingerprint(titulo)
    idx = _title_idx_prune(_get_title_index(h))
    return fp in idx

def title_add(h: dict, titulo: str) -> None:
    """Registra título no índice para dedup futuro."""
    fp = _title_fingerprint(titulo)
    idx = _title_idx_prune(_get_title_index(h))
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

def _norm_img_url(img: str, base: str | None = None) -> str | None:
    if not img:
        return None
    u = img.strip()
    if u.startswith("//"):
        u = "https:" + u
    if base and u.startswith("/"):
        try:
            u = urljoin(base, u)
        except Exception:
            pass
    return u

def extrair_imagem_rss(entry, feed_url: str) -> str | None:
    """Extrai URL de imagem do entry RSS (sem HTTP)."""
    img = None
    try:
        if "media_content" in entry:
            img = _norm_img_url(entry.media_content[0]["url"], feed_url)
        if not img and "media_thumbnail" in entry:
            img = _norm_img_url(entry.media_thumbnail[0]["url"], feed_url)
        if not img and "enclosures" in entry:
            for e in entry.enclosures:
                if "image" in (e.get("type") or "") or IMG_EXT_RE.search(e.get("href") or ""):
                    img = _norm_img_url(e.get("href"), feed_url)
                    break
        if not img:
            content = ""
            if "content" in entry:
                content = entry.content[0].get("value", "")
            summary = entry.get("summary", "")
            m = IMG_SRC_RE.search(content) or IMG_SRC_RE.search(summary)
            if m:
                img = _norm_img_url(m.group(1), feed_url)
    except Exception as e:
        log.debug(f"Erro extraindo imagem RSS: {e}")
    return img

async def fetch_og_image(url: str, retries: int = 2) -> str | None:
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
                if r.status != 200:
                    return None
                html = await r.text()
                m = OG_IMG_RE.search(html) or OG_IMG_RE_ALT.search(html)
                if m:
                    return _norm_img_url(m.group(1), url)
                return None
        except Exception as e:
            log.debug(f"og:image tentativa {attempt+1}/{retries} falhou para {url}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
    return None

async def validar_imagem(url: str) -> bool:
    """HEAD request para verificar se URL é imagem válida (>5KB)."""
    if not url:
        return False
    if not http_session:
        # Sem sessão HTTP: aceita apenas por extensão (menos seguro)
        return bool(IMG_EXT_RE.search(url))
    try:
        async with http_session.head(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=aiohttp.ClientTimeout(total=5),
            allow_redirects=True,
        ) as r:
            if r.status >= 400 and r.status not in (401, 403, 429):
                return False
            ct = r.headers.get("Content-Type", "").lower()
            cl = r.headers.get("Content-Length")
            # Rejeitar imagens < 3KB (ícones/placeholders)
            if cl and int(cl) < 3000:
                return False
            return "image/" in ct
    except Exception as e:
        log.debug(f"Erro validando imagem {url}: {e}")
    return False

async def extrair_imagem_completa(entry, feed_url: str) -> str | None:
    """Pipeline completo: RSS → validação HTTP → fallback og:image."""
    img = extrair_imagem_rss(entry, feed_url)
    if img and await validar_imagem(img):
        return img
    # Fallback: og:image da página
    link = entry.get("link")
    if link:
        og = await fetch_og_image(link)
        if og and await validar_imagem(og):
            return og
    return None

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
    """Padroniza títulos para formato jornalístico direto (sentence case)."""
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
    
    # Nomes próprios que devem ser capitalizados (marcas/produtos)
    proper_names = (
        "Xbox", "Windows", "PlayStation", "Playstation", "Nintendo", "Switch",
        "iPhone", "iPad", "MacBook", "Macbook", "Android", "iOS",
        "Google", "Microsoft", "Apple", "Amazon", "Meta", "Tesla",
        "Facebook", "Instagram", "WhatsApp", "Twitter", "LinkedIn",
        "Discord", "Spotify", "Netflix", "YouTube", "Zoom",
        "Intel", "AMD", "Nvidia", "Samsung", "LG", "Sony",
        "Reddit", "TikTok", "Snapchat", "Pinterest",
    )
    for name in proper_names:
        t = re.sub(rf"\b{name.lower()}\b", name, t, flags=re.IGNORECASE)
    
    # Limita tamanho para ~1,5 linhas (90 caracteres)
    if len(t) > 90:
        cut = t[:90]
        last_space = cut.rfind(" ")
        if last_space >= 50:
            cut = cut[:last_space]
        t = cut.rstrip(" ,;:-") + "..."
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
    Processa o resumo para garantir formato correto e usar TODO o limite do Discord (4096 chars).
    Remove construções semânticas estranhas e garante fluxo contexto->fato->impacto.
    """
    bruto = re.sub(r"\s+", " ", (texto or "").strip())
    if not bruto:
        return ""

    partes = [p.strip() for p in re.split(r"[.!?]+", bruto) if p.strip()]
    if not partes:
        return ""

    conectores = {
        1: "Nesse cenário,",
        2: "Na prática,",
        3: "Além disso,",
        4: "Com isso,",
        5: "Adicionalmente,",
        6: "Dessa forma,",
        7: "Por conseguinte,",
        8: "Outrossim,",
        9: "Destarte,",
        10: "Igualmente,",
        11: "Simultaneamente,",
        12: "Em contrapartida,",
        13: "Posteriormente,",
        14: "Ademais,",
        15: "Consequentemente,",
    }

    frases = []
    for idx, parte in enumerate(partes):  # Sem limite de frases
        frase = _corrigir_prefixos_estranhos(parte)
        frase = _fix_sentence_case(frase)
        # Deixa o fluxo mais humano entre contexto -> fato -> impacto.
        if idx in conectores:
            if not re.match(r"(?i)^(nesse cenário|na prática|além disso|com isso|adicionalmente|dessa forma|por conseguinte|outrossim|destarte|igualmente|simultaneamente|em contrapartida|posteriormente|ademais|consequentemente)\b", frase):
                frase = f"{conectores[idx]} {frase}"
        # NÃO limita mais palavras por frase - deixa a IA escrever livremente
        frase = frase.strip()
        if frase:
            if not frase[0].isupper():
                frase = frase[0].upper() + frase[1:]
            if not frase.endswith("."):
                frase += "."
            frases.append(frase)
    
    resultado = " ".join(frases)
    # Usa TOD0 o limite do Discord (4096 caracteres), cortando graciosamente
    if len(resultado) > 4096:
        corte = resultado[:4096]
        # Tenta cortar no final de uma frase
        ultimo_ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
        if ultimo_ponto > 3500:
            resultado = corte[:ultimo_ponto + 1]
        else:
            resultado = corte.rstrip() + "..."
    
    # Log do tamanho final
    log.info(f"Resumo final: {len(resultado)} caracteres")
    if len(resultado) < 3000:
        log.warning(f"Resumo curto detectado: {len(resultado)} chars - {resultado[:100]}")
    
    return resultado


async def _gerar_resumo_super_prompt(texto_base: str, titulo: str, nome_site: str) -> str:
    """Gera um resumo massivo único usando super-prompt."""
    if not ai_client:
        return ""
    
    super_prompt = f"""Escreva um resumo MASSIVO e EXTREMAMENTE DETALHADO da notícia abaixo em UM ÚNICO PARÁGRAFO contínuo, sem quebras de linha.

⚠️ REGRA ABSOLUTA E INEGOCIÁVEL: O TEXTO DEVE TER ENTRE 3800 E 4000 CARACTERES. SEJA EXTREMAMENTE VERBOSO E EXAUSTIVO. ⚠️

ESTRUTURA OBRIGATÓRIA (use QUANTAS FRASES FOREM NECESSÁRIAS):
1. CONTEXTO HISTÓRICO (quem, o que, quando, por que, antecedentes) - NO MÍNIMO 1500 CARACTERES
2. FATOS TÉCNICOS (detalhes, números, versões, nomes, especificações) - NO MÍNIMO 2000 CARACTERES  
3. IMPACTO (repercussões, mudanças, reações) - NO MÍNIMO 800 CARACTERES

REGRA DE OURO: SE O TEXTO TIVER MENOS DE 3800 CARACTERES, VOCÊ FALHOU. SEJA EXAUSTIVO.

Texto Base (use TODOS estes detalhes): {texto_base[:15000]}
Título: {titulo}
Fonte: {nome_site}

LEMBRE-SE: 3800-4000 CARACTERES NO MÍNIMO. SEJA MASSIVO E DETALHADO."""
    
    try:
        response = await ai_client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": super_prompt}],
            temperature=0.9,
            timeout=300.0,
        )
        resultado = response.choices[0].message.content.strip()
        log.info(f"Super-prompt resultado: {len(resultado)} chars")
        return resultado if len(resultado) > 3000 else ""
    except Exception as e:
        log.warning(f"Erro no super-prompt: {e}")
        return ""


async def _gerar_resumo_em_partes(texto_base: str, titulo: str, nome_site: str) -> str:
    """Gera um resumo massivo dividindo em contexto, fato e impacto."""
    if not ai_client:
        return ""
    
    partes = []
    prompts = [
        (f"""Escreva APENAS o CONTEXTO da notícia abaixo. 
        ⚠️⚠️ REGRA ABSOLUTA: DEVE TER NO MÍNIMO 1500 CARACTERES. SEJA EXTREMAMENTE EXAUSTIVO no contexto histórico, quem, quando, por que, antecedentes.
        Texto: {texto_base[:10000]}
        Título: {titulo}
        Fonte: {nome_site}
        
        Lembre-se: O texto DEVE ter NO MÍNIMO 1500 caracteres. Seja massivo e detalhado no contexto.
        
        EXEMPLO DE TAMANHO: "Em um desenvolvimento que remonta aos esforços iniciais de 2019 quando a empresa anunciou seus primeiros planos para expansão global, a corporação multinacional de tecnologia anunciou hoje uma nova iniciativa que promete transformar radicalmente o mercado de inteligência artificial em escala global, envolvendo investimentos bilionários e parcerias estratégicas com governos e instituições de pesquisa..." (continua por mais 1400 caracteres).""",
         "contexto"),
        
        (f"""Escreva APENAS os FATOS concretos da notícia abaixo.
        ⚠️⚠️ REGRA ABSOLUTA: DEVE TER NO MÍNIMO 2200 CARACTERES. Seja EXTREMAMENTE exaustivo nos detalhes técnicos, números, versões, nomes, especificações.
        Texto: {texto_base[:10000]}
        Título: {titulo}
        Fonte: {nome_site}
        
        Lembre-se: O texto DEVE ter NO MÍNIMO 2200 caracteres. Seja massivo e denso.
        
        EXEMPLO DE TAMANHO: "A empresa divulgou hoje que o novo processador possui 128 núcleos de última geração, com arquitetura Zen 5 personalizada, 256 threads de execução simultânea e capacidade de processar 1.2 trilhões de operações por segundo, representando um avanço de 340% em relação à geração anterior, com consumo de energia reduzido em 45% através de nova técnica de voltagem dinâmica..." (continua por mais 2100 caracteres).""",
         "fatos"),
        
        (f"""Escreva APENAS o IMPACTO da notícia abaixo.
        ⚠️⚠️ REGRA ABSOLUTA: DEVE TER NO MÍNIMO 1000 CARACTERES. Analise repercussões imediatas e de longo prazo, mudanças para usuários/mercado, reações.
        Texto: {texto_base[:10000]}
        Título: {titulo}
        Fonte: {nome_site}
        
        Lembre-se: O texto DEVE ter NO MÍNIMO 1000 caracteres. Seja exaustivo no impacto.
        
        EXEMPLO DE TAMANHO: "Especialistas afirmam que esta mudança representa um marco histórico para a indústria, com previsões de crescimento de 250% no setor nos próximos 24 meses, enquanto analistas de mercado apontam que empresas concorrentes perderão 15% de participação até 2027, forçando uma reestruturação global que afetará diretamente 450 mil trabalhadores..." (continua por mais 900 caracteres).""",
         "impacto"),
    ]
    
    for prompt, nome_parte in prompts:
        try:
            response = await ai_client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                timeout=120.0,
            )
            parte = response.choices[0].message.content.strip()
            log.info(f"Parte {nome_parte}: {len(parte)} chars")
            partes.append(parte)
        except Exception as e:
            log.warning(f"Erro ao gerar parte {nome_parte}: {e}")
    
    resultado = " ".join(partes)
    log.info(f"Resumo combinado (partes): {len(resultado)} chars")
    return resultado if len(resultado) > 2000 else ""


async def _expandir_resumo(resumo_curto: str, texto_base: str, titulo: str, nome_site: str) -> str:
    """Expande um resumo curto para torná-lo massivo e detalhado."""
    if not ai_client:
        return resumo_curto
    
    prompt_expansao = f"""O resumo abaixo está muito curto (menos de 3000 caracteres).
    Expanda-o drasticamente para ter ENTRE 3800 E 4000 CARACTERES, adicionando TODOS os detalhes técnicos, históricos e de impacto que faltam.
    Mantenha o formato de UM ÚNICO PARÁGRAFO contínuo, sem quebras de linha.
    Adicione MAIS frases, MAIS detalhes técnicos, MAIS números, MAIS citações, MAIS contexto histórico.
    SEJA EXAUSTIVO. O resultado deve ser uma matéria completa em parágrafo único.
    
    Título: {titulo}
    Resumo Atual (Curto): {resumo_curto}
    Texto Base para Expandir: {texto_base[:10000]}
    
    Lembre-se: O resultado DEVE ter entre 3800 e 4000 caracteres. Seja massivo e detalhado."""

    try:
        response = await ai_client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct",
            messages=[
                {"role": "system", "content": "Responda APENAS com o texto expandido, sem JSON, sem markdown."},
                {"role": "user", "content": prompt_expansao},
            ],
            temperature=0.9,
            timeout=300.0,
        )
        expandido = response.choices[0].message.content.strip()
        if len(expandido) > len(resumo_curto):
            log.info(f"Resumo expandido: {len(resumo_curto)} -> {len(expandido)} chars")
            return expandido
    except Exception as e:
        log.warning(f"Falha ao expandir resumo: {e}")
    
    return resumo_curto


    return " ".join(frases)

_last_ai_call = 0.0
_ai_calls_this_cycle = 0

async def gerar_analise_ia(texto_base: str, titulo_original: str, nome_site: str) -> dict | None:
    global _last_ai_call
    if not ai_client:
        return None

    # Cooldown entre chamadas
    now = time.monotonic()
    wait = (_last_ai_call + IA_COOLDOWN_SEC) - now
    if wait > 0:
        await asyncio.sleep(wait)
    _last_ai_call = time.monotonic()

    # Estratégia: Super-prompt único para resumo massivo
    resumo_massivo = await _gerar_resumo_super_prompt(texto_base, titulo_original, nome_site)
    if resumo_massivo and len(resumo_massivo) > 3000:
        log.info(f"Resumo super-prompt gerado: {len(resumo_massivo)} chars")
        nota_estimada = 80
        categoria_estimada = "Big Techs"
        return {"pular": False, "titulo": titulo_original, "nota": nota_estimada, "categoria": categoria_estimada, "resumo": resumo_massivo}
    
    # Fallback
    prompt = f"""Você é um editor-chefe de tecnologia de um portal premium. Analise a notícia abaixo e retorne APENAS um JSON válido, sem texto fora do JSON.

⚠️ REGRA ABSOLUTA: O CAMPO "resumo" DEVE TER ENTRE 3800 E 4000 CARACTERES. ⚠️

RESPONDA EM UM DOS DOIS FORMATOS:
1. SE REJEITAR: {{"pular": true, "reason": "motivo curto da rejeição"}}
2. SE APROVAR: {{"pular": false, "titulo": "...", "nota": 85, "categoria": "...", "resumo": "..."}}

═══ REGRAS DE BLOQUEIO IMEDIATO (pular=true) ═══
- Promoção, oferta, cupom, desconto, preço, cashback, afiliado, guia de compra, "vale a pena comprar".
- Review, análise de produto, comparativo, unboxing, "melhor custo-benefício".
- Fofoca, treta, política não-tech, celebridade, esporte, horóscopo, entretenimento genérico.
- Ciência genérica sem relação com tech (biologia, paleontologia, arqueologia, astronomia pura).
- Conteúdo vago, clickbait sem substância, rumor sem fonte, notícia repetitiva.
- Smartphones intermediários/entrada: Galaxy A/M, Moto G/E, Redmi Note, POCO básico, "chegou ao Brasil" sem inovação.
- Games: skins, cosméticos, patch notes menores, eventos semanais, item shop.

═══ CATEGORIAS (use exatamente uma destas) ═══
Hardware | Inteligência Artificial | Games | Cibersegurança | Sistemas Operacionais | Smartphones | Big Techs | Ciência & Espaço | Software & Apps | Cloud & DevOps | Programação & Dev | Internet & Redes | Mídia & Streaming | Curiosidade Tech | Outros

═══ ESCALA DE NOTAS (seja rigoroso e consistente) ═══
- 95-100: CATÁSTROFE ou MARCO MUNDIAL. Queda global de serviço, hack massivo, lançamento de nova geração (iPhone, Windows, GPT novo).
- 85-94: ALTA RELEVÂNCIA. Grandes novidades confirmadas, vulnerabilidade crítica (CVE alto), aquisição bilionária, demissão em massa.
- 75-84: RELEVANTE. Interessante para entusiastas de tech, atualização significativa, nova feature de grande plataforma.
- <75: IRRELEVANTE — marque pular=true. Notícia menor, atualização incremental, conteúdo genérico.

═══ TÍTULO ═══
- Claro, jornalístico, autoexplicativo. Quem lê o título entende o fato sem precisar clicar.
- Traduza para PT-BR. Sem clickbait, sem "Você não vai acreditar", sem títulos genéricos curtos.
- Use sentence case natural em português: somente a primeira palavra e nomes próprios/siglas em maiúscula.
- Limite de até 90 caracteres (máximo 1,5 linhas), direto ao ponto e sem exagero de adjetivos.
- Mantenha nomes próprios corretos: Xbox, Windows, PlayStation, iPhone, etc.

═══ RESUMO (campo mais importante) ═══
⚠️ REGRA ABSOLUTA: NÃO SE PREOCUPE COM LIMITES. ESCREVA O RESUMO MAIS LONGO E COMPLETO POSSÍVEL, COBRINDO TODO O CONTEÚDO DA NOTÍCIA. ⚠️
- UM ÚNICO PARÁGRAFO contínuo, sem quebras de linha, sem bullet points, sem listas.
- NÃO HÁ LIMITE DE FRASES. Use QUANTAS FRASES FOREM NECESSÁRIAS para cobrir CADA detalhe relevante da notícia.
- Estrutura narrativa (use quantas frases precisar para cada seção):
  CONTEXTO (quem, o que, quando, POR QUE, HISTÓRICO — situe o leitor com TODOS os detalhes, contexto histórico, antecedentes).
  FATO (o que aconteceu de concreto, com TODOS os detalhes técnicos, nomes, versões, números, especificações, citações diretas, declarações).
  IMPACTO (por que isso importa, o que muda para o usuário/mercado, repercussões imediatas e de longo prazo, reações de especialistas, análises).
- Cada frase deve ter o máximo de palavras possível para ser densa, informativa e recheada de detalhes técnicos (40-80 palavras por frase).
- Inclua contexto concreto (ator, ação, tempo, versões, números, especificações, porcentagens, datas, CITAÇÕES, NOMES COMPLETOS) detalhado em CADA frase.
- Escreva de forma objetiva e direta, mas com ABSOLUTAMENTE TODO o conteúdo relevante e útil que a notícia oferece. SEJA EXAUSTIVO.
- Use conectores naturais para ligar contexto, fato e impacto.
- O resumo deve ser uma MATÉRIA COMPLETA em parágrafo único. NÃO CORTE INFORMAÇÕES.
- FORMATAÇÃO OBRIGATÓRIA: use português padrão — APENAS a primeira palavra de cada frase começa com maiúscula. NUNCA use Title Case.
- Gramática impecável em PT-BR. O texto deve ser EXTREMAMENTE denso e substancial — nunca genérico ou superficial.
- NÃO POUPE DETALHES: inclua TODOS os nomes de tecnologias, versões, números, porcentagens, datas, nomes de empresas/produtos, CITAÇÕES de fontes, NOMES DE PESSOAS.
- Mantenha nomes próprios corretos: Xbox, Windows, PlayStation, iPhone, etc.
- Não use construções semânticas inválidas como "a empresa governo federal".
- REGRA DE OURO: ESCREVA O MÁXIMO POSSÍVEL. O resumo deve ser massivo, denso e completo. Seja exaustivo na cobertura da notícia.

═══ FILTROS ESPECIAIS POR CATEGORIA ═══
SMARTPHONES: Aceitar APENAS flagships (iPhone, Galaxy S/Z, Pixel Pro, Xiaomi Ultra) ou inovação real (tela dobrável, nova bateria, IA integrada). Rejeitar intermediários e "refresh" sem novidade.
GAMES: Aceitar APENAS AAA, grandes eventos (TGA, E3, Direct, Gamescom), aquisições, ou demissões em massa. Rejeitar skins, cosméticos, patch notes, eventos semanais.
CIBERSEGURANÇA: Priorizar CVE crítico, ransomware, vazamento de dados, zero-day, exploit ativo. Nota ≥85 para esses.

Fonte: {nome_site}
Título Original: {titulo_original}
Texto Base COMPLETO (use CADA detalhe desta notícia para escrever o resumo MASSIVO): {texto_base[:15000]}
"""

    for attempt in range(3):
        try:
            response = await ai_client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=[
                    {"role": "system", "content": "Responda APENAS com JSON válido, sem markdown, sem texto fora do JSON. REGRA CRÍTICA: O CAMPO 'resumo' DEVE TER O MÁXIMO DE CARACTERES POSSÍVEL, IDEALMENTE PRÓXIMO DE 4000 CARACTERES. Seja exaustivo e massivo na escrita."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                timeout=300.0,
            )
            resp = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", resp, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data.get("resumo"), str):
                    resumo_bruto = data["resumo"]
                    # Se resumo curto, tenta expandir
                    if len(resumo_bruto) < 3000 and attempt == 2:  # Na última tentativa
                        log.warning(f"Resumo curto ({len(resumo_bruto)} chars), tentando expandir...")
                        resumo_expandido = await _expandir_resumo(resumo_bruto, texto_base, titulo_original, nome_site)
                        if resumo_expandido and len(resumo_expandido) > len(resumo_bruto):
                            resumo_bruto = resumo_expandido
                    data["resumo"] = _normalizar_resumo_final(resumo_bruto)
                if isinstance(data.get("titulo"), str):
                    data["titulo"] = _normalize_news_title(data["titulo"])
                return data
        except Exception as e:
            log.warning(f"IA tentativa {attempt+1}/3 falhou: {e}")
            await asyncio.sleep(2)
    return None

# =========================
# ENTRY UTILS
# =========================
def entry_datetime_utc(entry) -> datetime | None:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(st), tz=timezone.utc)
    except Exception:
        return None

def noticia_eh_recente(entry_dt: datetime | None) -> bool:
    """Retorna True apenas se a notícia tem data e é recente. Sem data = rejeitar."""
    if not entry_dt:
        return False
    return entry_dt >= datetime.now(timezone.utc) - timedelta(hours=MAX_IDADE_HORAS)

# =========================
# POSTAR NOTÍCIA (extraído para reuso)
# =========================
async def _postar_noticia(channel, noticia: dict, history: dict, metrics: dict) -> bool:
    """Posta uma notícia no canal. Retorna True se postou com sucesso."""
    # Trava de segurança: nunca postar sem imagem
    img = noticia.get("imagem")
    if not img:
        log.error(f"Tentativa de postar sem imagem, abortando: {noticia.get('titulo', '')[:60]}")
        return False

    emoji = EMOJIS_CATEGORIA.get(noticia["categoria"], "🔌")

    embed = discord.Embed(
        title=f"{'🚨 ' if noticia['nota'] >= NOTA_URGENTE else ''}{noticia['titulo']}",
        url=noticia["link"],
        description=noticia["resumo"],
        color=CORES_CATEGORIA.get(noticia["categoria"], COR_PADRAO),
    )
    embed.set_author(
        name=f"Via {noticia['site']} • {noticia['categoria']} {emoji}",
        icon_url="https://cdn-icons-png.flaticon.com/512/2965/2965363.png",
    )
    embed.set_image(url=noticia["imagem"])
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
        msg = await channel.send(content=f"<@&{ID_CARGO_PARA_MARCAR}>", embed=embed)
        try:
            await msg.create_thread(
                name=f"💬 {noticia['categoria']}: {noticia['titulo'][:80]}",
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
_last_run_slot: tuple[int, int, int] | None = None

def _janela_ativa_ou_pre_aquecimento(agora: datetime) -> bool:
    """Permite coleta no horário comercial e no pré-aquecimento antes das 8h."""
    if HORA_INICIO <= agora.hour < HORA_FIM:
        return True
    return agora.hour == (HORA_INICIO - 1) and agora.minute >= MINUTO_PRE_AQUECIMENTO


def _deve_rodar_slot(agora: datetime) -> bool:
    """Roda somente em slots fixos (xx:00 e xx:30) e apenas uma vez por slot."""
    global _last_run_slot
    if agora.minute not in (0, 30):
        return False
    slot = (agora.year * 10000 + agora.month * 100 + agora.day, agora.hour, agora.minute)
    if _last_run_slot == slot:
        return False
    _last_run_slot = slot
    return True


@tasks.loop(minutes=1)
async def verificar_feeds():
    global _ai_calls_this_cycle, http_session, _last_cycle_time, _last_cycle_stats
    await discord_client.wait_until_ready()

    agora = datetime.now(FUSO_HORARIO_BR)
    if not _deve_rodar_slot(agora):
        return

    if not _janela_ativa_ou_pre_aquecimento(agora):
        log.info(f"Standby: {agora.strftime('%H:%M')} fora da janela de coleta (pré 07:45 + 08h-18h).")
        return

    if not http_session:
        http_session = aiohttp.ClientSession()

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
            # Revalidar imagem da fila (URLs podem ter morrido)
            if not await validar_imagem(img):
                log.warning(f"  ✗ Imagem inválida na fila, descartando: {item.get('titulo', '?')[:60]}")
                continue
            if await _postar_noticia(channel, item, history, metrics):
                posts_feitos += 1
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
        *[_fetch_feed(n, u) for n, u in FONTES_RSS.items()]
    )

    # Filtrar candidatos (sem validação de imagem ainda)
    pre_candidatos = []
    total_examinados = 0
    total_prefiltrados = 0
    total_dedup = 0
    total_antigas = 0
    contagem_por_fonte: dict[str, int] = {}

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
            if title_is_dup(history, title):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_titulo"})
                total_dedup += 1
                continue

            # SimHash dedup (conteúdo similar mesmo com títulos diferentes)
            texto_raw = limpar_html(str(entry.get("summary") or entry.get("description") or title))
            sh = _simhash64(f"{title} {texto_raw[:600]}")
            if simhash_is_dup(history, sh):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "dup_simhash"})
                total_dedup += 1
                continue

            # PRÉ-FILTRO POR KEYWORDS (custo zero — antes da IA)
            if not prefiltro_keywords(title, texto_raw):
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "prefiltro_keywords"})
                total_prefiltrados += 1
                log.info(f"  ✗ Prefiltro rejeitou: [{nome_site}] {title[:60]}")
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
            aceitos_fonte += 1
            contagem_por_fonte[nome_site] = contagem_por_fonte.get(nome_site, 0) + 1

    # ===== Validação de imagem em batch (paralelo com semáforo) =====
    total_sem_imagem = 0
    candidatos = []

    if pre_candidatos:
        _img_semaphore = asyncio.Semaphore(5)

        async def _validar_img(cand):
            async with _img_semaphore:
                img = await extrair_imagem_completa(cand["entry"], cand["feed_url"])
                return cand, img

        resultados_img = await asyncio.gather(
            *[_validar_img(c) for c in pre_candidatos]
        )

        for cand, img in resultados_img:
            if not img:
                historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "sem_imagem"})
                total_sem_imagem += 1
                continue
            cand["img"] = img
            candidatos.append(cand)

    log.info(
        f"Fase 1 concluída: {total_examinados} examinados, "
        f"{total_antigas} antigas, {total_dedup} dedup, {total_prefiltrados} prefiltrados, "
        f"{total_sem_imagem} sem imagem → {len(candidatos)} candidatos para IA"
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

        _ai_calls_this_cycle += 1
        metric_inc(metrics, "ia_calls_hoje")
        res = await gerar_analise_ia(cand["texto_raw"], cand["title"], cand["nome_site"])

        if not isinstance(res, dict) or res.get("pular"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "ia_rejeitou"})
            metric_inc(metrics, "ia_rejeitadas_hoje")
            log.info(f"  ✗ IA rejeitou: [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        nota = res.get("nota", 0)
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

        metric_inc(metrics, "ia_aprovadas_hoje")
        aprovados.append({
            "titulo": _normalize_news_title(res.get("titulo", cand["title"])),
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

    for i, noticia in enumerate(para_postar):
        # Revalidar imagem no momento do post (URLs podem ter morrido)
        img = noticia.get("imagem")
        if not img or not await validar_imagem(img):
            log.warning(f"  ✗ Imagem inválida ao postar, descartando: {noticia.get('titulo', '?')[:60]}")
            historico_set(history, noticia["link_norm"], noticia["dedupe"], "skipped", {"reason": "sem_imagem_post"})
            continue
        log.info(f"  🏆 Postando (nota {noticia['nota']}): [{noticia['site']}] {noticia['titulo'][:60]}")
        await _postar_noticia(channel, noticia, history, metrics)
        if i < len(para_postar) - 1:
            await asyncio.sleep(POST_SPACING_SEC)

    # Enfileirar restantes para próximo ciclo
    if para_fila:
        queue_atual = load_queue()
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
        "posts": posts_feitos + len(para_postar),
        "fila": len(load_queue()),
    }
    log.info("Ciclo concluído.")


@discord_client.event
async def on_ready():
    log.info(f"🤖 Tiffany Online: {discord_client.user}")
    # Sync slash commands
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            discord_client.tree.copy_global_to(guild=guild)
            await discord_client.tree.sync(guild=guild)
        else:
            await discord_client.tree.sync()
        log.info("Slash commands sincronizados.")
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
async def cmd_status(interaction: discord.Interaction):
    agora = datetime.now(FUSO_HORARIO_BR)
    metrics = load_metrics()
    queue = load_queue()

    # Feeds em cooldown
    feeds_cooldown = [nome for nome in FONTES_RSS if _feed_em_cooldown(nome)]

    em = discord.Embed(
        title="📊 Status — Tiffany Bot",
        color=0x00FFFF,
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
    if http_session and not http_session.closed:
        log.warning("⚠️ http_session não foi fechada gracefully (atexit).")

atexit.register(_sync_cleanup)

discord_client.run(DISCORD_TOKEN)
