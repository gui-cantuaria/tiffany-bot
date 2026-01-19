import discord
from discord.ext import tasks
import feedparser
import os
import json
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse, quote
from dotenv import load_dotenv
from groq import Groq

# --- CONFIGURAÇÕES INICIAIS ---
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- CONFIGURAÇÃO DE VENDAS ---
CANAL_OFERTAS_ID = 1385327938529919006
CARGO_OFERTAS_ID = 1386386059390357575

# --- SEUS IDs DE AFILIADO ---
TAG_AMAZON = "tuffine039-20"
LOMADEE_SOURCE_ID = "2324685"
AWIN_ID = "2729212"  # <--- Quando a Awin aprovar, coloque seu ID aqui

# --- MAPA DA AWIN (Kabum, Pichau, Terabyte, ShopInfo) ---
# Enquanto a Awin não aprova, deixe "00000". O bot postará o link normal.
LOJAS_AWIN = {
    "kabum.com.br": "17729",  # ID Padrão Kabum
    "pichau.com.br": "00000",  # Pichau (Verifique na Awin se eles entraram)
    "terabyteshop.com.br": "00000",  # Terabyte (Geralmente Awin ou Afiliados Próprios)
    "shopinfo.com.br": "00000",  # ShopInfo
    "aliexpress.com": "18879",  # Ali (Opcional, mas bom ter para peças da China)
}

# --- LOJAS LOMADEE (Focado na Magalu e Marcas) ---
# Girafa REMOVIDO
LOJAS_LOMADEE = [
    "magazineluiza.com.br",
    "fastshop.com.br",
    "lenovo.com",
    "acer.com",
    "dell.com",
]

# --- FONTES DE OFERTAS (Para achar promoções dessas lojas) ---
FONTES_RSS = {
    "Gatry": "https://gatry.com/feed",
    "Boletando": "https://boletando.com/feed/",
    "Hardmob Promoções": "https://www.hardmob.com.br/external.php?type=RSS2&forumids=407",
    "Pelando (Hot)": "https://www.pelando.com.br/rss/hot",
}

HISTORY_FILE = "offers_history.json"

# Configuração do Discord
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None

# --- FUNÇÕES AUXILIARES ---


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_history(history_dict):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history_dict, f, indent=4)
    except:
        pass


def extrair_imagem(entry):
    try:
        if "media_content" in entry:
            return entry.media_content[0]["url"]
        if "media_thumbnail" in entry:
            return entry.media_thumbnail[0]["url"]

        content = getattr(entry, "content", [{}])[0].get("value", "")
        summary = getattr(entry, "summary", "")
        match = re.search(r'<img[^>]+src="([^">]+)"', content) or re.search(
            r'<img[^>]+src="([^">]+)"', summary
        )
        if match:
            return match.group(1)
    except:
        pass
    return None


# --- CAÇADOR DE LINKS (TRI-HÍBRIDO) ---
def caçar_link_real(url_noticia):
    print(f"   🕵️  Investigando link: {url_noticia}...")

    # Lista de prioridade
    alvos = ["amazon.com", "amzn.to"] + list(LOJAS_AWIN.keys()) + LOJAS_LOMADEE

    for loja in alvos:
        if loja in url_noticia:
            return url_noticia

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url_noticia, headers=headers, timeout=10)
        if response.status_code != 200:
            return url_noticia

        soup = BeautifulSoup(response.text, "html.parser")
        all_links = soup.find_all("a", href=True)

        for link in all_links:
            href = link["href"]
            for loja in alvos:
                if loja in href:
                    return href

    except Exception as e:
        pass
    return url_noticia


# --- MONETIZAÇÃO INTELIGENTE ---
def monetizar_link(link_original):
    # 1. AMAZON (Rei do Hardware)
    if "amazon.com" in link_original or "amzn.to" in link_original:
        if "amzn.to" in link_original:
            return link_original
        try:
            parsed = urlparse(link_original)
            query = parse_qs(parsed.query)
            if "tag" in query:
                del query["tag"]
            query["tag"] = [TAG_AMAZON]
            novo_query = urlencode(query, doseq=True)
            return urlunparse(parsed._replace(query=novo_query))
        except:
            return link_original

    # 2. AWIN (Kabum, Pichau, Terabyte, ShopInfo)
    for dominio, merchant_id in LOJAS_AWIN.items():
        if dominio in link_original:
            try:
                # Se não tiver ID (00000), retorna original
                if merchant_id == "00000" or AWIN_ID == "SEU_ID_DA_AWIN_AQUI":
                    return link_original

                link_codificado = quote(link_original)
                link_awin = f"https://www.awin1.com/cread.php?awinmid={merchant_id}&awinaffid={AWIN_ID}&ued={link_codificado}"
                print(f"   💰 Link Awin Gerado: {dominio}")
                return link_awin
            except:
                return link_original

    # 3. LOMADEE (Magalu, FastShop)
    eh_lomadee = False
    for loja in LOJAS_LOMADEE:
        if loja in link_original:
            eh_lomadee = True
            break

    if eh_lomadee:
        try:
            link_codificado = quote(link_original)
            link_afiliado = f"https://redirect.lomadee.com/v2/{LOMADEE_SOURCE_ID}?url={link_codificado}"
            print(f"   💰 Link Lomadee Gerado")
            return link_afiliado
        except:
            return link_original

    return link_original


# --- CÉREBRO "HARDWARE ONLY" ---
def gerar_copy_vendas(texto_base, titulo_original, nome_site):
    if not groq_client or not texto_base:
        return None

    prompt = f"""
    Você é um curador de ofertas focado EXCLUSIVAMENTE em HARDWARE e INFORMÁTICA.
    
    PASSO 1: FILTRO RIGOROSO (Estilo TecnoArt)
    - ACEITAR: Placas de Vídeo, Processadores (Ryzen/Intel), RAM, SSD/NVMe, Fontes, Gabinetes, Monitores, Mouses, Teclados Mecânicos, Headsets, Cadeiras Gamer, Notebooks, Consoles, PCs Montados.
    - REJEITAR (Responda PULAR): Roupas, Tênis, Perfumes, Geladeiras, Fogão, AirFryer, Sabão, Milhas, Jogos de tabuleiro, Brinquedos, Celulares básicos (aceitar apenas Gamer/Topo de linha).

    PASSO 2: EXTRAÇÃO
    Extraia o PREÇO. Se não tiver, "Preço no Link".
    
    PASSO 3: FORMATO (3 linhas):
    Linha 1: [Nome do Produto Curto + Emoji 🔥]
    Linha 2: [Preço R$ X.XXX,XX ou "Preço Promocional 📉"]
    Linha 3: [Nome da Loja Exata (ex: Kabum, Terabyte, Pichau)]

    Título: {titulo_original}
    Texto: {texto_base[:2500]}
    """

    try:
        chat = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_tokens=200,
        )
        resp = chat.choices[0].message.content.strip()

        if "PULAR" in resp.upper():
            return "SKIP_NOT_DEAL"

        linhas = [l for l in resp.split("\n") if l.strip()]
        if len(linhas) >= 3:
            return {
                "titulo": linhas[0].replace("Linha 1:", "").strip(),
                "preco": linhas[1].replace("Linha 2:", "").strip(),
                "loja": (
                    linhas[3].replace("Linha 3:", "").strip()
                    if len(linhas) > 3
                    else linhas[2].replace("Linha 3:", "").strip()
                ),
            }
        else:
            return None
    except Exception as e:
        print(f"Erro Groq: {e}")
        return None


# --- LOOP PRINCIPAL ---
@tasks.loop(minutes=30)
async def buscar_ofertas():
    await discord_client.wait_until_ready()
    channel = discord_client.get_channel(CANAL_OFERTAS_ID)
    if not channel:
        return

    history = load_history()
    print("\n--- 🛒 Caçando Hardware (Big Techs) ---")

    for nome_site, url_feed in FONTES_RSS.items():
        print(f"🔎 {nome_site}...")
        try:
            feed = feedparser.parse(url_feed, agent="Mozilla/5.0")
            if not feed.entries:
                continue

            for entry in feed.entries[:3]:
                link_rss = entry.link
                if link_rss in history.values():
                    continue

                texto = getattr(
                    entry, "summary", getattr(entry, "description", entry.title)
                )
                res = gerar_copy_vendas(texto, entry.title, nome_site)

                if res == "SKIP_NOT_DEAL" or res is None:
                    history[nome_site + entry.title] = link_rss
                    save_history(history)
                    continue

                print(f"   🔥 HARDWARE DETECTADO: {res['titulo']}")

                link_real = caçar_link_real(link_rss)
                link_final = monetizar_link(link_real)
                url_imagem = extrair_imagem(entry)

                # --- VISUAL TECNOART ---
                embed = discord.Embed(
                    title=f"{res['titulo']}",
                    url=link_final,
                    color=0xFF4500,  # Laranja Avermelhado (Gamer)
                )

                descricao = f"""
🏢 **Loja:** {res['loja']}
💸 **{res['preco']}**

👇 **GARANTA O SEU AGORA**
[🔗 IR PARA A OFERTA]({link_final})
                """
                embed.description = descricao
                if url_imagem:
                    embed.set_image(url=url_imagem)
                embed.set_footer(text=f"Garimpado por Tuffine Bot • Via {nome_site}")

                msg_content = f"<@&{CARGO_OFERTAS_ID}>" if CARGO_OFERTAS_ID else ""

                try:
                    msg = await channel.send(content=msg_content, embed=embed)
                    await msg.create_thread(
                        name=f"💬 {res['titulo'][:50]}", auto_archive_duration=1440
                    )
                    print(f"   ✅ Postado!")
                except Exception as e:
                    print(f"   ❌ Erro Discord: {e}")

                history[nome_site + entry.title] = link_rss
                save_history(history)
                await asyncio.sleep(5)

        except Exception as e:
            print(f"❌ Erro feed {nome_site}: {e}")

    print("--- Ciclo concluído. Dormindo... ---")


@discord_client.event
async def on_ready():
    print(f"🤖 Bot Gamer Online: {discord_client.user}")
    if not buscar_ofertas.is_running():
        buscar_ofertas.start()


if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)
