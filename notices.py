import discord
from discord.ext import tasks
import feedparser
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

import aiohttp
from dotenv import load_dotenv
from openai import AsyncOpenAI

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

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("tiffany-bot")

# =========================
# DISCORD + IA CLIENT
# =========================
intents = discord.Intents.default()
discord_client = discord.Client(intents=intents)
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
    # EN — Segurança
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "KrebsOnSecurity": "https://krebsonsecurity.com/feed/",
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Dark Reading": "https://www.darkreading.com/rss.xml",
    # EN — IA / Dev
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "OpenAI Blog": "https://openai.com/blog/rss.xml",
    "GitHub Blog": "https://github.blog/feed/",
}

FONTES_INGLES = {
    "The Verge", "TechCrunch", "Ars Technica", "Wired", "Engadget",
    "BleepingComputer", "9to5Mac", "9to5Google", "ZDNet",
    "The Register", "Tom's Hardware",
    "KrebsOnSecurity", "The Hacker News", "Dark Reading",
    "MIT Technology Review", "OpenAI Blog", "GitHub Blog",
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
    except:
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
    except:
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
            except:
                novo[k] = v
        else:
            novo[k] = v
    tmp = f"{HISTORY_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(novo, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_FILE)

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

def _simhash_prune(idx: dict[str, int]) -> dict[str, int]:
    cutoff = int(time.time()) - (SIMHASH_TTL_HORAS * 3600)
    return {k: ts for k, ts in idx.items() if ts >= cutoff}

def simhash_is_dup(h: dict, sh: int) -> bool:
    if sh == 0:
        return False
    idx = _simhash_prune(_get_simhash_index(h))
    for hexv in idx.keys():
        try:
            if _hamming(sh, int(hexv, 16)) <= SIMHASH_HAMMING_MAX:
                return True
        except:
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
        except:
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
    except:
        pass
    return img

async def fetch_og_image(url: str) -> str | None:
    """Busca og:image da página como fallback."""
    if not http_session:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with http_session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            html = await r.text()
            m = OG_IMG_RE.search(html) or OG_IMG_RE_ALT.search(html)
            if m:
                return _norm_img_url(m.group(1), url)
    except:
        pass
    return None

async def validar_imagem(url: str) -> bool:
    """HEAD request para verificar se URL é imagem válida (>5KB)."""
    if not url:
        return False
    looks_like = bool(IMG_EXT_RE.search(url))
    if not http_session:
        return looks_like
    try:
        async with http_session.head(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as r:
            if r.status >= 400 and r.status not in (401, 403, 429):
                return False
            ct = r.headers.get("Content-Type", "").lower()
            cl = r.headers.get("Content-Length")
            # Rejeitar imagens < 3KB (ícones/placeholders)
            if cl and int(cl) < 3000:
                return False
            if "image/" in ct:
                return True
    except:
        pass
    return looks_like

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

    prompt = f"""Você é um editor-chefe de tecnologia de um portal premium. Analise a notícia abaixo e retorne APENAS um JSON válido, sem texto fora do JSON.

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

═══ RESUMO (campo mais importante) ═══
- UM ÚNICO PARÁGRAFO contínuo, sem quebras de linha, sem bullet points, sem listas.
- EXATAMENTE 5 FRASES, cada uma terminando com ponto final.
- Estrutura narrativa obrigatória:
  Frase 1-2: CONTEXTO (quem, o que, quando — situe o leitor).
  Frase 3-4: FATO (o que aconteceu de concreto, com detalhes técnicos relevantes).
  Frase 5: IMPACTO (por que isso importa, o que muda para o usuário/mercado).
- Comece com letra maiúscula. Gramática impecável em PT-BR.
- O texto deve ser denso e substancial — nunca genérico ou superficial.

═══ FILTROS ESPECIAIS POR CATEGORIA ═══
SMARTPHONES: Aceitar APENAS flagships (iPhone, Galaxy S/Z, Pixel Pro, Xiaomi Ultra) ou inovação real (tela dobrável, nova bateria, IA integrada). Rejeitar intermediários e "refresh" sem novidade.
GAMES: Aceitar APENAS AAA, grandes eventos (TGA, E3, Direct, Gamescom), aquisições, ou demissões em massa. Rejeitar skins, cosméticos, patch notes, eventos semanais.
CIBERSEGURANÇA: Priorizar CVE crítico, ransomware, vazamento de dados, zero-day, exploit ativo. Nota ≥85 para esses.

Fonte: {nome_site}
Título Original: {titulo_original}
Texto Base: {texto_base[:2000]}
"""

    for attempt in range(3):
        try:
            response = await ai_client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=[
                    {"role": "system", "content": "Responda APENAS com JSON válido, sem markdown, sem texto fora do JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                timeout=30.0,
            )
            resp = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", resp, re.DOTALL)
            if match:
                return json.loads(match.group(0))
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
    except:
        return None

def noticia_eh_recente(entry_dt: datetime | None) -> bool:
    """Retorna True apenas se a notícia tem data e é recente. Sem data = rejeitar."""
    if not entry_dt:
        return False
    return entry_dt >= datetime.now(timezone.utc) - timedelta(hours=MAX_IDADE_HORAS)

# =========================
# PIPELINE PRINCIPAL
# =========================
@tasks.loop(minutes=30)
async def verificar_feeds():
    global _ai_calls_this_cycle, http_session
    await discord_client.wait_until_ready()

    agora = datetime.now(FUSO_HORARIO_BR)
    if not (HORA_INICIO <= agora.hour < HORA_FIM):
        log.info(f"Standby: {agora.strftime('%H:%M')} fora do horário comercial (08h-18h).")
        return

    if not http_session:
        http_session = aiohttp.ClientSession()

    channel = discord_client.get_channel(CANAL_NOTICIAS_ID)
    if not channel:
        try:
            channel = await discord_client.fetch_channel(CANAL_NOTICIAS_ID)
        except:
            log.error("Canal de notícias não encontrado.")
            return
    if not channel:
        return

    _ai_calls_this_cycle = 0
    history = load_history()

    # ===== FASE 1: Coleta paralela + Pré-filtro (sem IA) =====
    log.info("═══ FASE 1: Coleta + Pré-filtro ═══")

    # Buscar todos os feeds em paralelo
    async def _fetch_feed(nome_site: str, url_feed: str):
        if _feed_em_cooldown(nome_site):
            return nome_site, None
        try:
            feed = await asyncio.wait_for(
                asyncio.to_thread(feedparser.parse, url_feed),
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

    # Filtrar candidatos
    candidatos = []
    total_examinados = 0
    total_prefiltrados = 0
    total_dedup = 0
    total_sem_imagem = 0
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

            # Validação de imagem via HTTP HEAD
            img = await extrair_imagem_completa(entry, FONTES_RSS.get(nome_site, ""))
            if not img:
                historico_set(history, link_norm, dedupe, "skipped", {"reason": "sem_imagem"})
                total_sem_imagem += 1
                continue

            candidatos.append({
                "entry": entry,
                "nome_site": nome_site,
                "link": link,
                "link_norm": link_norm,
                "title": title,
                "texto_raw": texto_raw,
                "img": img,
                "is_eng": is_eng,
                "dedupe": dedupe,
                "simhash": sh,
            })
            aceitos_fonte += 1
            contagem_por_fonte[nome_site] = contagem_por_fonte.get(nome_site, 0) + 1

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
        res = await gerar_analise_ia(cand["texto_raw"], cand["title"], cand["nome_site"])

        if not isinstance(res, dict) or res.get("pular"):
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": "ia_rejeitou"})
            log.info(f"  ✗ IA rejeitou: [{cand['nome_site']}] {cand['title'][:60]}")
            continue

        nota = res.get("nota", 0)
        categoria = res.get("categoria", "Outros")

        # Threshold de nota
        min_nota = NOTA_MIN_GAMES if categoria == "Games" else NOTA_MIN_APROVACAO
        if nota < min_nota:
            historico_set(history, cand["link_norm"], cand["dedupe"], "skipped", {"reason": f"nota_baixa_{nota}"})
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

        aprovados.append({
            "titulo": res.get("titulo", cand["title"]),
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
        return

    # ===== FASE 3: Postar a melhor notícia do ciclo =====
    log.info("═══ FASE 3: Selecionando a melhor notícia ═══")

    # Ordenar por nota (maior primeiro) e pegar a campeã
    aprovados.sort(key=lambda x: x["nota"], reverse=True)

    # TRAVA FINAL: só postar notícia com imagem válida
    campea = None
    for candidata in aprovados:
        if candidata.get("imagem"):
            campea = candidata
            break
        else:
            log.warning(f"  ✗ Sem imagem na hora de postar, pulando: {candidata['titulo'][:60]}")

    if not campea:
        log.warning("Nenhuma notícia aprovada possui imagem válida. Nada será postado.")
        save_history(history)
        return

    log.info(f"  🏆 Campeã (nota {campea['nota']}): [{campea['site']}] {campea['titulo'][:60]}")

    # Montar embed (layout frozen — idêntico ao V16)
    emoji = EMOJIS_CATEGORIA.get(campea["categoria"], "🔌")

    embed = discord.Embed(
        title=f"{'🚨 ' if campea['nota'] >= NOTA_URGENTE else ''}{campea['titulo']}",
        url=campea["link"],
        description=campea["resumo"],
        color=CORES_CATEGORIA.get(campea["categoria"], COR_PADRAO),
    )
    embed.set_author(
        name=f"Via {campea['site']} • {campea['categoria']} {emoji}",
        icon_url="https://cdn-icons-png.flaticon.com/512/2965/2965363.png",
    )
    embed.set_image(url=campea["imagem"])
    embed.add_field(
        name="",
        value=f"👉 **[Clique aqui para ler a matéria completa]({campea['link']})**",
        inline=False,
    )

    texto_rodape = "Notícia resumida por IA"
    if campea["is_eng"]:
        texto_rodape += " • Fonte em inglês"
    embed.set_footer(text=texto_rodape)

    try:
        msg = await channel.send(content=f"<@&{ID_CARGO_PARA_MARCAR}>", embed=embed)
        try:
            await msg.create_thread(
                name=f"💬 {campea['categoria']}: {campea['titulo'][:80]}",
                auto_archive_duration=1440,
            )
        except:
            pass

        historico_set(history, campea["link_norm"], campea["dedupe"], "posted")
        log.info(f"  📨 Postado: {campea['titulo'][:60]}")
    except Exception as e:
        log.error(f"  Erro ao postar: {e}")

    save_history(history)
    log.info("Ciclo concluído.")


@discord_client.event
async def on_ready():
    log.info(f"🤖 Tiffany Online: {discord_client.user}")
    if not verificar_feeds.is_running():
        verificar_feeds.start()

@discord_client.event
async def on_close():
    global http_session
    if http_session:
        await http_session.close()
        http_session = None
    log.info("🔌 Sessão HTTP fechada. Bot desligando.")


discord_client.run(DISCORD_TOKEN)
