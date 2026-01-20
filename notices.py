import os
import re
import json
import time
import asyncio
import logging
import html as html_lib
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin

import discord
from discord import app_commands
from discord.ext import tasks
import feedparser
import aiohttp
from dotenv import load_dotenv
from groq import Groq

# =========================
# CONFIGURAÇÕES
# =========================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CANAL_NOTICIAS_ID = int(os.getenv("CANAL_NOTICIAS_ID", "0"))
ID_CARGO_PARA_MARCAR = int(os.getenv("ID_CARGO_PARA_MARCAR", "0"))

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
STATUS_EPHEMERAL = os.getenv("STATUS_EPHEMERAL", "1").strip() == "1"

ARQUIVO_HISTORICO = os.getenv("ARQUIVO_HISTORICO", "notices_history.json")
ARQUIVO_CACHE_FEEDS = os.getenv("ARQUIVO_CACHE_FEEDS", "feed_cache.json")

# IA
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "550")) 
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.3"))

# --- INTERVALO DE 30 MINUTOS ---
POST_INTERVAL_MIN = int(os.getenv("POST_INTERVAL_MIN", "30"))
URGENTE_MIN_INTERVAL_SEC = int(os.getenv("URGENTE_MIN_INTERVAL_SEC", "30"))

ENTRADAS_POR_FEED = int(os.getenv("ENTRADAS_POR_FEED", "2"))
SCAN_POR_FEED = int(os.getenv("SCAN_POR_FEED", "6"))

MAX_CONCORRENCIA_FEEDS = int(os.getenv("MAX_CONCORRENCIA_FEEDS", "2"))
MAX_CONCORRENCIA_IA = int(os.getenv("MAX_CONCORRENCIA_IA", "1"))

MAX_QUEUE_POR_CICLO = int(os.getenv("MAX_QUEUE_POR_CICLO", "12"))
MAX_IDADE_HORAS = int(os.getenv("MAX_IDADE_HORAS", "24"))

IA_MIN_INTERVAL_SEC = float(os.getenv("IA_MIN_INTERVAL_SEC", "20"))
MAX_IA_CALLS_PER_CICLO = int(os.getenv("MAX_IA_CALLS_PER_CICLO", "6"))

MIN_TEXTO_CHARS = int(os.getenv("MIN_TEXTO_CHARS", "160"))
MOSTRAR_ORIGINAL_EN = os.getenv("MOSTRAR_ORIGINAL_EN", "1").strip() == "1"

# --- NOTAS DE CORTE (REDUZIDAS PARA POSTAR MAIS) ---
NOTA_MIN_APROVACAO = int(os.getenv("NOTA_MIN_APROVACAO", "60")) # Baixou de 75 para 60
NOTA_IMPORTANTE = int(os.getenv("NOTA_IMPORTANTE", "80"))       # Baixou de 88 para 80
NOTA_URGENTE = int(os.getenv("NOTA_URGENTE", "90"))             # Baixou de 93 para 90
NOTA_MIN_GAMES = int(os.getenv("NOTA_MIN_GAMES", "82"))

MAX_POR_FONTE_POR_CICLO = int(os.getenv("MAX_POR_FONTE_POR_CICLO", "1"))

# Timeouts e Cooldowns
FEED_TASK_TIMEOUT_SEC = int(os.getenv("FEED_TASK_TIMEOUT_SEC", "25"))
FEED_HTTP_TIMEOUT_SEC = int(os.getenv("FEED_HTTP_TIMEOUT_SEC", "15"))
FEED_FAIL_COOLDOWN_MIN = int(os.getenv("FEED_FAIL_COOLDOWN_MIN", "30"))
FEED_COOLDOWN_LOG_EVERY_SEC = int(os.getenv("FEED_COOLDOWN_LOG_EVERY_SEC", "300"))

# Anti-dup
SIMHASH_TTL_HORAS = int(os.getenv("SIMHASH_TTL_HORAS", "36"))
SIMHASH_HAMMING_MAX = int(os.getenv("SIMHASH_HAMMING_MAX", "3"))

LOG_LEVEL = (os.getenv("LOG_LEVEL", "WARNING") or "WARNING").upper()

WHITELIST_TERMS = [
    t.strip().lower()
    for t in (os.getenv("WHITELIST_TERMS", "") or "").split(",")
    if t.strip()
]

def _parse_csv_env(name: str) -> set[str]:
    raw = (os.getenv(name, "") or "").strip()
    if not raw: return set()
    return {x.strip() for x in raw.split(",") if x.strip()}

CATEGORIAS_BLOQUEADAS = _parse_csv_env("CATEGORIAS_BLOQUEADAS")
FONTES_DESATIVADAS_USER = _parse_csv_env("FONTES_DESATIVADAS")

# --- HORÁRIO COMERCIAL (FUSO BRASIL UTC-3) ---
JANELA_INICIO = 10  # 10:00 da manhã
JANELA_FIM = 18     # 18:00 da tarde
FUSO_HORARIO_BR = timezone(timedelta(hours=-3))

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("tuffine-bot")
logging.getLogger("httpx").setLevel(logging.WARNING)

# =========================
# DISCORD CLIENT
# =========================
intents = discord.Intents.default()
intents.guilds = True
discord_client = discord.Client(intents=intents)
tree = app_commands.CommandTree(discord_client)

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

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
    # EN
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Wired": "https://www.wired.com/feed/rss",
    "Engadget": "https://www.engadget.com/rss.xml",
    "KrebsOnSecurity": "https://krebsonsecurity.com/feed/",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Google Security Blog": "https://security.googleblog.com/feeds/posts/default?alt=rss",
    "The Register": "https://www.theregister.com/headlines.atom",
    # Instáveis/Desativadas por padrão
    "NotebookCheck (BR)": "https://www.notebookcheck.info/RSS-Feed-Noticias.152573.0.xml",
    "NerdBunker": "https://jovemnerd.com.br/feed/",
    "Manual do Usuário": "https://manualdousuario.net/feed/",
    "CISA Alerts": "https://www.cisa.gov/cisa-uscert-ncas-alerts.xml",
    "CISA Advisories": "https://www.cisa.gov/cisa-uscert-ncas-advisories.xml",
    "MSRC": "https://msrc.microsoft.com/blog/feed/",
}

DEFAULT_DISABLE = {
    "NotebookCheck (BR)", "NerdBunker", "CISA Alerts", 
    "CISA Advisories", "MSRC", "Manual do Usuário",
}
FONTES_DESATIVADAS = set(FONTES_DESATIVADAS_USER) | DEFAULT_DISABLE

FONTES_INGLES = {
    "The Verge", "TechCrunch", "Ars Technica", "Wired", "Engadget",
    "KrebsOnSecurity", "BleepingComputer", "Google Security Blog", 
    "The Register", "CISA Alerts", "CISA Advisories", "MSRC",
}

FONTES_SEMPRE_URGENTE = {"CISA Alerts", "CISA Advisories"}
FONTES_SEMPRE_IMPORTANTE = {"MSRC", "Google Security Blog"}

# =========================
# CATEGORIAS
# =========================
EMOJIS_CATEGORIA = {
    "Hardware": "🖥️", "Smartphones": "📱", "Inteligência Artificial": "🤖",
    "Games": "🎮", "Cibersegurança": "🛡️", "Software & Apps": "💾",
    "Big Techs": "💼", "Ciência & Espaço": "🚀", "Curiosidade Tech": "💡",
    "Sistemas Operacionais": "🪟", "Internet & Redes": "🌐", 
    "Cloud & DevOps": "☁️", "Programação & Dev": "🧑‍💻", 
    "Mídia & Streaming": "📺", "Outros": "🔌",
}
CATEGORIAS_VALIDAS = list(EMOJIS_CATEGORIA.keys())

# =========================
# FILTROS (REGEX) - URGÊNCIA REFORÇADA
# =========================
URGENTE_RE = re.compile(
    r"\b("
    r"cve-\d{4}-\d+|kev|rce|remote code execution|execu[cç][aã]o remota|"
    r"0-?day|zero-?day|dia zero|actively exploited|exploited in the wild|"
    r"explora[cç][aã]o ativa|out-?of-?band|oob|patch emergencial|"
    r"atualiza[cç][aã]o emergencial|security update|atualiza[cç][aã]o de seguran[cç]a|"
    r"critical vulnerability|vulnerabilidade cr[ií]tica|cvss\s*(9|10|9\.\d|10\.0)|"
    r"severidade cr[ií]tica|ransomware|breach|data breach|vazamento|dados expostos|"
    r"outage|downtime|incident|fora do ar|indisponibilidade|kubernetes|k8s|"
    r"aws outage|azure outage|gcp outage|cloudflare|akamai|" 
    r"microsoft|windows|apple|macos|ios|"
    r"google|android|linux|nvidia|amd|intel"
    r")\b", re.IGNORECASE,
)

GAMES_RUIDO_RE = re.compile(
    r"\b(patch|hotfix|update|atualiza[cç][aã]o|patch notes|notas do patch|"
    r"season|temporada|battle pass|passe de batalha|skin|cosm[eé]tico|"
    r"item shop|loja de itens|evento semanal|weekly|rotation|rota[cç][aã]o|"
    r"meta|build|guia|tips?|dicas?|review|an[aá]lise|comparativo|benchmark)\b", 
    re.IGNORECASE,
)

GAMES_RELEVANTE_RE = re.compile(
    r"\b(the game awards|tga|nintendo direct|state of play|xbox showcase|"
    r"summer game fest|sgf|acquisit|aquisi[cç][aã]o|layoff|demiss|shutdown|"
    r"fechamento|delist|pre[cç]o|price increase|game pass|ps plus|"
    r"playstation plus|steam|valve|epic games|announce|anunci|trailer|"
    r"launch|release date|data de lan[cç]amento|adiad|delay|cancel|ps5|xbox|"
    r"nintendo|switch|pc|rockstar|gta|activision|call of duty|battlefield|"
    r"ubisoft|capcom|blizzard|bethesda)\b", re.IGNORECASE,
)

def games_eh_relevante(titulo: str, texto: str, nota: int, urgente: bool) -> bool:
    blob = f"{titulo}\n{texto}".strip()
    if urgente: return True
    if nota < NOTA_MIN_GAMES: return False
    if not GAMES_RELEVANTE_RE.search(blob): return False
    if GAMES_RUIDO_RE.search(blob): return False
    return True

# =========================
# STATE
# =========================
queue_noticias: asyncio.PriorityQueue = asyncio.PriorityQueue()
http_session: aiohttp.ClientSession | None = None

next_post_time: datetime = datetime.now(timezone.utc)
next_urgent_time: datetime = datetime.now(timezone.utc)

sem_ia = asyncio.Semaphore(MAX_CONCORRENCIA_IA)
_last_ai_call = 0.0
_ai_time_lock = asyncio.Lock()
_ai_calls_this_cycle = 0
_ai_cycle_lock = asyncio.Lock()
_cache_feeds_lock = asyncio.Lock()

_feed_cooldown_until: dict[str, float] = {}
_feed_cooldown_reason: dict[str, str] = {}
_feed_cooldown_lastlog: dict[str, float] = {}

def _now_ts() -> float: return time.time()

def _set_feed_cooldown(nome_site: str, reason: str, long: bool = False) -> None:
    mins = FEED_FAIL_COOLDOWN_MIN * (2 if long else 1)
    until = _now_ts() + (mins * 60)
    _feed_cooldown_until[nome_site] = until
    _feed_cooldown_reason[nome_site] = reason
    _feed_cooldown_lastlog.pop(nome_site, None)

def _feed_em_cooldown(nome_site: str) -> bool:
    return _now_ts() < _feed_cooldown_until.get(nome_site, 0)

def _log_cooldown_se_preciso(nome_site: str) -> None:
    last = _feed_cooldown_lastlog.get(nome_site, 0)
    if (_now_ts() - last) >= FEED_COOLDOWN_LOG_EVERY_SEC:
        until = int(_feed_cooldown_until.get(nome_site, 0))
        reason = _feed_cooldown_reason.get(nome_site, "erro")
        mins_left = max(0, int((until - _now_ts()) // 60))
        log.warning("⏭️ %s em cooldown (%s). Voltando em ~%d min", nome_site, reason, mins_left)
        _feed_cooldown_lastlog[nome_site] = _now_ts()

async def throttle_ia():
    global _last_ai_call
    async with _ai_time_lock:
        now = time.monotonic()
        wait = (_last_ai_call + IA_MIN_INTERVAL_SEC) - now
        if wait > 0: await asyncio.sleep(wait)
        _last_ai_call = time.monotonic()

async def consumir_budget_ia() -> bool:
    global _ai_calls_this_cycle
    async with _ai_cycle_lock:
        if _ai_calls_this_cycle >= MAX_IA_CALLS_PER_CICLO: return False
        _ai_calls_this_cycle += 1
        return True

# =========================
# PERSISTÊNCIA E DEDUPE
# =========================
def _load_json_file(path: str) -> dict:
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f) or {}
    except: return {}

def _atomic_write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def ler_historico() -> dict:
    return _load_json_file(ARQUIVO_HISTORICO) if isinstance(_load_json_file(ARQUIVO_HISTORICO), dict) else {}

def salvar_historico(h: dict) -> None:
    _atomic_write_json(ARQUIVO_HISTORICO, h)

def limpar_historico_antigo(h: dict, dias: int = 7) -> dict:
    """Remove entradas velhas da RAM/JSON"""
    cutoff = int(time.time()) - (dias * 86400)
    novo_h = {}
    if "_simhash_idx" in h: novo_h["_simhash_idx"] = h["_simhash_idx"]
    for k, v in h.items():
        if k == "_simhash_idx": continue
        if isinstance(v, dict) and "ts" in v:
            if v["ts"] > cutoff: novo_h[k] = v
        else: novo_h[k] = v
    return novo_h

def _hist_payload(status: str, extra: dict | None = None) -> dict:
    payload = {"status": status, "ts": int(time.time())}
    if extra: payload.update(extra)
    return payload

def _hist_key_link(link_norm: str) -> str: return f"L:{link_norm}"
def _hist_key_hash(dedupe_hash: str) -> str: return f"H:{dedupe_hash}"

def _hist_get_status(h: dict, key: str) -> str | None:
    item = h.get(key)
    if isinstance(item, dict): return item.get("status")
    if isinstance(item, str): return "posted"
    return None

def historico_status(h: dict, link_norm: str, dedupe_hash: str | None) -> str | None:
    keys = [link_norm, _hist_key_link(link_norm)]
    if dedupe_hash: keys.append(_hist_key_hash(dedupe_hash))
    for k in keys:
        st = _hist_get_status(h, k)
        if st: return st
    return None

def historico_set_duplo(h: dict, link_norm: str, dedupe_hash: str | None, status: str, extra: dict | None = None) -> None:
    payload = _hist_payload(status, extra)
    h[_hist_key_link(link_norm)] = payload
    if dedupe_hash: h[_hist_key_hash(dedupe_hash)] = payload

def title_norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def make_dedupe_hash_global(titulo: str, published_ts: int) -> str:
    bucket = int(published_ts // 3600)
    raw = f"GLOBAL|{bucket}|{title_norm(titulo)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

# SIMHASH
SIMHASH_WORD_RE = re.compile(r"[a-z0-9À-ÿ]{3,}", re.IGNORECASE)
def _simhash64(text: str) -> int:
    text = (text or "").lower()
    toks = SIMHASH_WORD_RE.findall(text)
    if not toks: return 0
    v = [0] * 64
    for tok in toks[:200]:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        x = h & ((1 << 64) - 1)
        for i in range(64):
            bit = (x >> i) & 1
            v[i] += 1 if bit else -1
    out = 0
    for i in range(64):
        if v[i] > 0: out |= 1 << i
    return out

def _hamming(a: int, b: int) -> int: return (a ^ b).bit_count()

def _hist_get_simhash_index(h: dict) -> dict[str, int]:
    idx = h.get("_simhash_idx")
    return idx if isinstance(idx, dict) else {}

def _hist_set_simhash_index(h: dict, idx: dict[str, int]) -> None:
    h["_simhash_idx"] = idx

def _simhash_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (SIMHASH_TTL_HORAS * 3600)
    return {k: ts for k, ts in idx.items() if ts >= cutoff}

def simhash_is_dup(h: dict, sh: int) -> bool:
    if sh == 0: return False
    idx = _simhash_prune(_hist_get_simhash_index(h))
    for hexv in idx.keys():
        try:
            if _hamming(sh, int(hexv, 16)) <= SIMHASH_HAMMING_MAX: return True
        except: continue
    return False

def simhash_add(h: dict, sh: int) -> None:
    if sh == 0: return
    idx = _simhash_prune(_hist_get_simhash_index(h))
    idx[f"{sh:016x}"] = int(time.time())
    _hist_set_simhash_index(h, idx)

# CACHE DE FEED
def ler_cache_feeds() -> dict:
    return _load_json_file(ARQUIVO_CACHE_FEEDS) if isinstance(_load_json_file(ARQUIVO_CACHE_FEEDS), dict) else {}

def salvar_cache_feeds(c: dict) -> None:
    _atomic_write_json(ARQUIVO_CACHE_FEEDS, c)

def _cache_key_feed(nome_site: str, url_feed: str) -> str:
    return f"{nome_site}::{url_feed}"

RSS_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def _base_rss_headers() -> dict:
    return {
        "User-Agent": RSS_UA,
        "Accept": "application/rss+xml,application/atom+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "Cache-Control": "no-cache", "Pragma": "no-cache",
    }

async def fetch_feed_cached(nome_site: str, url_feed: str) -> feedparser.FeedParserDict | None:
    global http_session
    if not http_session: return await asyncio.to_thread(feedparser.parse, url_feed, agent=RSS_UA)
    key = _cache_key_feed(nome_site, url_feed)
    
    async with _cache_feeds_lock:
        cache = ler_cache_feeds()
        cached = cache.get(key, {}) if isinstance(cache.get(key, {}), dict) else {}
        etag = cached.get("etag")
        last_mod = cached.get("last_modified")

    headers = _base_rss_headers()
    if etag: headers["If-None-Match"] = etag
    if last_mod: headers["If-Modified-Since"] = last_mod

    try:
        async with http_session.get(url_feed, headers=headers, allow_redirects=True, timeout=FEED_HTTP_TIMEOUT_SEC) as r:
            if r.status == 304: return None
            if r.status >= 400:
                long_cd = r.status in (401, 403, 404, 429) or r.status >= 500
                _set_feed_cooldown(nome_site, f"http_{r.status}", long=long_cd)
                return await asyncio.to_thread(feedparser.parse, url_feed, agent=RSS_UA)
            
            content = await r.read()
            new_etag = r.headers.get("ETag")
            new_last_mod = r.headers.get("Last-Modified")
            if new_etag or new_last_mod:
                async with _cache_feeds_lock:
                    cache = ler_cache_feeds()
                    payload = cache.get(key, {}) if isinstance(cache.get(key, {}), dict) else {}
                    if new_etag: payload["etag"] = new_etag
                    if new_last_mod: payload["last_modified"] = new_last_mod
                    payload["ts"] = int(time.time())
                    cache[key] = payload
                    salvar_cache_feeds(cache)
            return await asyncio.to_thread(feedparser.parse, content)
    except (asyncio.TimeoutError, aiohttp.ClientError):
        _set_feed_cooldown(nome_site, "net_error", long=True)
        return await asyncio.to_thread(feedparser.parse, url_feed, agent=RSS_UA)
    except:
        _set_feed_cooldown(nome_site, "unk_error", long=True)
        return await asyncio.to_thread(feedparser.parse, url_feed, agent=RSS_UA)

# UTILS URL/HTML
TRACKING_KEYS_PREFIX = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "source"}

def normalizar_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        q = parse_qsl(parts.query, keep_blank_values=True)
        q2 = []
        for k, v in q:
            lk = k.lower()
            if lk.startswith(TRACKING_KEYS_PREFIX) or lk in TRACKING_KEYS: continue
            q2.append((k, v))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q2, doseq=True), ""))
    except: return url

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style).*?>.*?</\1>")
PALAVRAS_BAN_PY = re.compile(r"\b(oferta|desconto|cupom|preço|compre|barato|menor valor|black friday|achados|promoção|promocao|review|análise|analise|comparativo)\b", re.IGNORECASE)

def limpar_html(texto: str) -> str:
    texto = html_lib.unescape(texto or "")
    texto = SCRIPT_STYLE_RE.sub(" ", texto)
    texto = TAG_RE.sub(" ", texto)
    return re.sub(r"\s+", " ", texto).strip()

def prefiltrar_texto(titulo: str, texto: str) -> bool:
    blob = f"{titulo}\n{texto}".strip()
    if not blob: return False
    if URGENTE_RE.search(blob): return True
    if len(blob) < MIN_TEXTO_CHARS: return False
    if PALAVRAS_BAN_PY.search(blob): return False
    if WHITELIST_TERMS:
        low = blob.lower()
        if not any(term in low for term in WHITELIST_TERMS): return False
    return True

def formatar_resumo_3_blocos_uma_linha(resumo: str) -> str:
    s = html_lib.unescape(resumo or "").strip()
    if not s: return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    
    if "||" in s: parts = [p.strip() for p in s.split("||") if p.strip()]
    else: parts = [p.strip() for p in re.split(r"\n\s*\n+", s) if p.strip()]
    
    if len(parts) < 3:
        s1 = re.sub(r"\s+", " ", s).strip()
        sentences = re.split(r"(?<=[.!?])\s+", s1)
        sentences = [x.strip() for x in sentences if x.strip()]
        if len(sentences) >= 3:
            n = len(sentences)
            a = max(1, n // 3)
            b = max(1, (n - a) // 2)
            parts = [" ".join(sentences[:a]), " ".join(sentences[a : a + b]), " ".join(sentences[a + b :])]
        else: parts = [s1]
        
    parts = parts[:3]
    fixed = []
    for p in parts:
        p = re.sub(r"\s*\n+\s*", " ", p).strip()
        p = re.sub(r"[?]+$", "", p).strip()
        if p and not re.search(r"[.!…]$", p): p += "."
        fixed.append(p)
    return " • ".join(fixed).strip()

def entry_datetime_utc(entry) -> datetime | None:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st: return None
    try: return datetime.fromtimestamp(time.mktime(st), tz=timezone.utc)
    except: return None

def noticia_eh_recente(entry_dt: datetime | None) -> bool:
    if not entry_dt: return True
    return entry_dt >= datetime.now(timezone.utc) - timedelta(hours=MAX_IDADE_HORAS)

# EXTRAÇÃO IMAGEM
IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif)(?:\?|#|$)", re.IGNORECASE)
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

def _norm_img_url(img: str, base: str | None = None) -> str | None:
    if not img: return None
    u = img.strip()
    if u.startswith("//"): u = "https:" + u
    if base and u.startswith("/"):
        try: u = urljoin(base, u)
        except: pass
    return u

def extrair_imagem(entry, feed_url: str) -> str | None:
    try:
        if 'media_content' in entry: return _norm_img_url(entry.media_content[0]['url'], feed_url)
        if 'media_thumbnail' in entry: return _norm_img_url(entry.media_thumbnail[0]['url'], feed_url)
        
        if 'enclosures' in entry:
            for e in entry.enclosures:
                if 'image' in (e.get('type') or '') or IMG_EXT_RE.search(e.get('href') or ''):
                    return _norm_img_url(e.get('href'), feed_url)
                    
        content = ""
        if 'content' in entry: content = entry.content[0].get('value', '')
        summary = entry.get('summary', '')
        m = IMG_SRC_RE.search(content) or IMG_SRC_RE.search(summary)
        if m: return _norm_img_url(m.group(1), feed_url)
    except: pass
    return None

async def url_eh_imagem(url: str) -> bool:
    if not url: return False
    looks_like = bool(IMG_EXT_RE.search(url))
    if not http_session: return looks_like
    try:
        async with http_session.head(url, headers={"User-Agent": RSS_UA}, timeout=10) as r:
            if r.status < 400 and "image/" in r.headers.get("Content-Type", "").lower(): return True
            if r.status in (401, 403, 429): return looks_like
    except: pass
    return looks_like

# GROQ IA
JSON_EXTRACT_RE = re.compile(r"\{.*\}", re.DOTALL)
def gerar_resumo_ia_sync(texto_base: str, titulo_original: str, nome_site: str, fonte_ingles: bool) -> dict | str | None:
    if not groq_client: return None
    if not texto_base.strip(): return None

    # PROMPT ATUALIZADO: Pedindo 3 blocos COMPLETOS e RICOS
    prompt = f"""
Você é um Editor Chefe de tecnologia MUITO seletivo.
Regras:
- Se for promoção/oferta/cupom/review/análise/fofoca/política sem tech -> skip=true
- Nota 0..100. Se nota < {NOTA_MIN_APROVACAO} -> skip=true
- Categoria em: {CATEGORIAS_VALIDAS}
- Games: Só aceitar AAA, Grandes Eventos, Aquisições, Mudanças de Serviço. Patch/Skin = skip.
- "resumo": Escreva 3 blocos COMPLETOS, RICOS EM DETALHES e INFORMATIVOS em PT-BR.
  Separe os blocos com " || ". Não pule linha.
  Explique bem o contexto e as consequências. Não economize detalhes.
- Responda APENAS JSON.

Formato: {{"skip":false,"categoria":"Hardware","nota":80,"titulo":"...","resumo":"..."}}
Fonte: {nome_site} {"(EN)" if fonte_ingles else ""}
Título: {titulo_original}
Texto: {texto_base[:1400]}
""".strip()

    for _ in range(5):
        try:
            chat = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=GROQ_MODEL, temperature=GROQ_TEMPERATURE, max_tokens=GROQ_MAX_TOKENS,
            )
            resp = chat.choices[0].message.content.strip()
            try: data = json.loads(resp)
            except: 
                m = JSON_EXTRACT_RE.search(resp)
                if not m: return None
                data = json.loads(m.group(0))
            
            if data.get("skip") is True: return "SKIP"
            if int(data.get("nota", 0)) < NOTA_MIN_APROVACAO: return "SKIP"
            
            cat = data.get("categoria", "Outros").strip()
            if cat not in EMOJIS_CATEGORIA: cat = "Outros"
            
            return {"categoria": cat, "nota": int(data.get("nota", 0)), 
                    "titulo": data.get("titulo", "").strip(), "resumo": data.get("resumo", "").strip()}
        except Exception as e:
            if "rate limit" in str(e).lower(): time.sleep(60); continue
            return None
    return None

# DISCORD
def limitar_texto(s: str, max_len: int) -> str:
    s = (s or "").strip()
    return s[:max_len-1] + "…" if len(s) > max_len else s

async def postar_noticia(item: dict) -> bool:
    channel = discord_client.get_channel(CANAL_NOTICIAS_ID)
    if not channel: 
        try: channel = await discord_client.fetch_channel(CANAL_NOTICIAS_ID)
        except: return False
    
    if not channel or not item.get("imagem"): return False

    cat = item.get("categoria", "Outros")
    emoji = EMOJIS_CATEGORIA.get(cat, "🔌")
    resumo = limitar_texto(formatar_resumo_3_blocos_uma_linha(item.get("resumo", "")), 3900)
    
    urgente, importante = bool(item.get("urgente")), bool(item.get("importante"))
    badge = "🚨" if urgente else ("🔥" if importante else "")
    titulo = limitar_texto(f"{badge} {item.get('titulo')}".strip(), 250)
    
    cor = discord.Color.red() if urgente else (discord.Color.orange() if importante else discord.Color.from_rgb(0, 255, 255))
    
    embed = discord.Embed(title=titulo, url=item.get("link"), description=resumo, color=cor)
    embed.set_author(name=f"Via {item.get('site')} • {cat} {emoji}", icon_url="https://cdn-icons-png.flaticon.com/512/2965/2965363.png")
    embed.set_image(url=item.get("imagem"))
    embed.add_field(name="", value=f"👉 **[Clique aqui para ler a matéria completa]({item.get('link')})**", inline=False)
    
    footer = "Resumido por IA"
    if MOSTRAR_ORIGINAL_EN and item.get("fonte_ingles"): footer += " • Fonte em inglês"
    embed.set_footer(text=footer)
    
    try:
        msg = await channel.send(content=f"<@&{ID_CARGO_PARA_MARCAR}>" if ID_CARGO_PARA_MARCAR else "", embed=embed)
        try: await msg.create_thread(name=limitar_texto(f"💬 {cat}: {item.get('titulo')}", 90), auto_archive_duration=1440)
        except: pass
        return True
    except: return False

# =========================
# PIPELINE
# =========================
async def processar_fonte(nome_site: str, url_feed: str, historico: dict, sem_feeds: asyncio.Semaphore) -> list:
    if nome_site in FONTES_DESATIVADAS or _feed_em_cooldown(nome_site): return []
    aprovadas = []
    
    async with sem_feeds:
        try:
            feed = await asyncio.wait_for(fetch_feed_cached(nome_site, url_feed), timeout=FEED_TASK_TIMEOUT_SEC)
            if not feed or not feed.entries: return []
            
            is_eng = nome_site in FONTES_INGLES
            for entry in feed.entries[:SCAN_POR_FEED]:
                if len(aprovadas) >= ENTRADAS_POR_FEED: break
                
                link, title = entry.get("link"), entry.get("title")
                if not link or not title: continue
                
                link_norm = normalizar_url(link)
                dt = entry_datetime_utc(entry)
                if not noticia_eh_recente(dt): continue
                
                dedupe = make_dedupe_hash_global(title, int(dt.timestamp()) if dt else int(time.time()))
                if historico_status(historico, link_norm, dedupe): continue
                
                texto = limpar_html(str(entry.get("summary") or entry.get("description") or title))
                if nome_site not in FONTES_SEMPRE_URGENTE and not prefiltrar_texto(title, texto):
                    historico_set_duplo(historico, link_norm, dedupe, "skipped", {"reason": "prefiltro"})
                    continue
                
                sh_pre = _simhash64(f"{title} {texto[:600]}")
                if simhash_is_dup(historico, sh_pre):
                    historico_set_duplo(historico, link_norm, dedupe, "skipped", {"reason": "dup_simhash"})
                    continue
                
                img = extrair_imagem(entry, url_feed)
                if not img or not await url_eh_imagem(img):
                    historico_set_duplo(historico, link_norm, dedupe, "skipped", {"reason": "sem_imagem"})
                    continue
                
                if not await consumir_budget_ia(): continue
                
                async with sem_ia:
                    await throttle_ia()
                    res = await asyncio.to_thread(gerar_resumo_ia_sync, texto, title, nome_site, is_eng)
                
                if res == "SKIP" or not res:
                    historico_set_duplo(historico, link_norm, dedupe, "skipped", {"reason": "ia"})
                    continue
                
                if res["categoria"] in CATEGORIAS_BLOQUEADAS: continue
                
                urgente = (nome_site in FONTES_SEMPRE_URGENTE or res["nota"] >= NOTA_URGENTE or URGENTE_RE.search(f"{res['titulo']} {texto}"))
                importante = (nome_site in FONTES_SEMPRE_IMPORTANTE or res["nota"] >= NOTA_IMPORTANTE)
                
                if res["categoria"] == "Games" and not games_eh_relevante(res["titulo"], texto, res["nota"], urgente): continue
                
                sh_post = _simhash64(f"{res['titulo']} {res['resumo']}")
                if simhash_is_dup(historico, sh_post): continue
                
                item = {
                    "site": nome_site, "link": link, "link_norm": link_norm, "dedupe_hash": dedupe,
                    "imagem": img, "categoria": res["categoria"], "titulo": res["titulo"],
                    "resumo": res["resumo"], "nota": res["nota"], "urgente": urgente,
                    "importante": importante, "fonte_ingles": is_eng, "simhash": sh_post,
                    "_priority": 0 if urgente else 1
                }
                aprovadas.append(item)
                historico_set_duplo(historico, link_norm, dedupe, "queued")
                simhash_add(historico, sh_post)
        except: _set_feed_cooldown(nome_site, "erro", long=True)
    return aprovadas

# =========================
# TASKS
# =========================
@tasks.loop(hours=1)
async def coletar_noticias():
    global _ai_calls_this_cycle
    await discord_client.wait_until_ready()
    _ai_calls_this_cycle = 0
    historico = ler_historico()
    sem = asyncio.Semaphore(MAX_CONCORRENCIA_FEEDS)
    
    tasks_list = [processar_fonte(n, u, historico, sem) for n, u in FONTES_RSS.items()]
    results = await asyncio.gather(*tasks_list)
    
    enqueued, counts = 0, {}
    for lista in results:
        for item in lista:
            if enqueued >= MAX_QUEUE_POR_CICLO: break
            
            # Limite por fonte (apenas para não urgentes)
            if not item["urgente"]:
                c = counts.get(item["site"], 0)
                if c >= MAX_POR_FONTE_POR_CICLO: continue
                counts[item["site"]] = c + 1
            
            await queue_noticias.put((item["_priority"], -item["nota"], time.time(), item))
            enqueued += 1
            
    historico = limpar_historico_antigo(historico)
    salvar_historico(historico)
    log.warning(f"✅ Coleta: {enqueued} novos itens. Fila total: {queue_noticias.qsize()}")

@tasks.loop(seconds=30)
async def postar_da_fila():
    global next_post_time, next_urgent_time
    await discord_client.wait_until_ready()
    if queue_noticias.empty(): return
    
    got = await queue_noticias.get()
    prio, _, _, item = got
    
    # --- LÓGICA DE HORÁRIO COMERCIAL ---
    urgente = bool(item.get("urgente"))
    
    # Pega hora atual no Brasil (UTC-3)
    agora_br = datetime.now(FUSO_HORARIO_BR)
    hora = agora_br.hour
    
    # Se NÃO for urgente E estiver fora do horário (antes das 10 ou depois das 18)
    if not urgente and (hora < JANELA_INICIO or hora >= JANELA_FIM):
        # Devolve pra fila e espera
        await queue_noticias.put(got)
        return # Sai da função, tenta de novo em 30s (loop)

    # --- LÓGICA DE INTERVALO ---
    now_utc = datetime.now(timezone.utc)
    target_time = next_urgent_time if urgente else next_post_time
    
    if now_utc < target_time:
        await queue_noticias.put(got)
        return

    # Posta
    historico = ler_historico()
    if await postar_noticia(item):
        historico_set_duplo(historico, item["link_norm"], item["dedupe_hash"], "posted")
        salvar_historico(historico)
        
        delay = timedelta(seconds=URGENTE_MIN_INTERVAL_SEC) if urgente else timedelta(minutes=POST_INTERVAL_MIN)
        if urgente: next_urgent_time = now_utc + delay
        else: next_post_time = now_utc + delay
        
        log.warning(f"📨 Postado: {item['titulo']}")
    else:
        await queue_noticias.put(got)
    queue_noticias.task_done()

@tree.command(name="status")
async def status_cmd(interaction: discord.Interaction):
    q = queue_noticias.qsize()
    await interaction.response.send_message(f"Fila: {q} | IA Usada: {_ai_calls_this_cycle}/{MAX_IA_CALLS_PER_CICLO}", ephemeral=STATUS_EPHEMERAL)

@discord_client.event
async def on_ready():
    global http_session
    if not http_session: http_session = aiohttp.ClientSession()
    if not coletar_noticias.is_running(): coletar_noticias.start()
    if not postar_da_fila.is_running(): postar_da_fila.start()
    try: await tree.sync()
    except: pass
    log.warning(f"🤖 Bot Online: {discord_client.user}")

if __name__ == "__main__":
    discord_client.run(DISCORD_TOKEN)