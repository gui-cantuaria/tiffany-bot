import discord
from discord.ext import tasks
import feedparser
import os
import json
import asyncio
import re
import logging
from datetime import datetime, timedelta
import pytz  # Fuso horário brasileiro
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Logs para acompanhar o que acontece na Discloud
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Configurações de IDs e Horários
CANAL_NOTICIAS_ID = 1420835598733938849
ID_CARGO_PARA_MARCAR = 1460323314357501952
HORA_INICIO = 8
HORA_FIM = 18
FUSO_HORARIO = pytz.timezone("America/Sao_Paulo")  # Garante o horário de Goiânia

# Listas de Estilo e Fontes
CORES_CATEGORIA = {
    "Hardware": 0xE03E3E,
    "IA": 0x00FFFF,
    "Games": 0x9146FF,
    "Segurança": 0x00FF00,
    "Mobile": 0xFFA500,
    "Business": 0x000080,
    "Science": 0x808080,
}
COR_PADRAO = 0xFFD700

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

FONTES_RSS = {
    "Adrenaline": "https://adrenaline.com.br/feed/",
    "TudoCelular": "https://www.tudocelular.com/rss/",
    "Tecnoblog": "https://tecnoblog.net/feed/",
    "Canaltech": "https://canaltech.com.br/rss/",
    "Olhar Digital": "https://olhardigital.com.br/rss/",
    "G1 Tecnologia": "https://g1.globo.com/dynamo/tecnologia/rss2.xml",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Wired": "https://www.wired.com/feed/rss",
    "Engadget": "https://www.engadget.com/rss.xml",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "9to5Mac": "https://9to5mac.com/feed/",
    "9to5Google": "https://9to5google.com/feed/",
    "ZDNet": "https://www.zdnet.com/news/rss.xml",
}

FONTES_INGLES = [
    "The Verge",
    "TechCrunch",
    "Ars Technica",
    "Wired",
    "Engadget",
    "BleepingComputer",
    "9to5Mac",
    "9to5Google",
    "ZDNet",
]
HISTORY_FILE = "notices_history.json"

intents = discord.Intents.default()
discord_client = discord.Client(intents=intents)
ai_client = (
    AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    if OPENROUTER_API_KEY
    else None
)


# --- FUNÇÕES DE APOIO ---
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except:
        return {}


def save_history(history_dict):
    # Limpeza: Mantém apenas os últimos 7 dias para não pesar o arquivo
    limite = datetime.now(FUSO_HORARIO) - timedelta(days=7)
    historico_limpo = {
        k: v
        for k, v in history_dict.items()
        if isinstance(v, dict) and datetime.fromisoformat(v["data"]) > limite
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(historico_limpo, f, indent=4, ensure_ascii=False)


def extrair_imagem(entry):
    try:
        if "media_content" in entry and entry.media_content:
            return entry.media_content[0]["url"]
        content = getattr(entry, "content", [{}])[0].get("value", "") + getattr(
            entry, "summary", ""
        )
        match = re.search(
            r'<img[^>]+src="([^">]+\.(?:jpg|jpeg|png|webp)[^">]*)"',
            content,
            re.IGNORECASE,
        )
        return match.group(1) if match else None
    except:
        return None


async def gerar_analise_ia(texto_base, titulo_original, nome_site):
    if not ai_client:
        return None
    prompt = f"""Você é um jornalista estilo Filipe Deschamps. Retorne APENAS um JSON.
    Regras: Parágrafo único, comece com minúscula, termine com 'As informações são do site {nome_site}.'
    {{ "pular": false, "titulo": "...", "nota": 85, "categoria": "...", "resumo": "..." }}
    Fonte: {nome_site} | Título: {titulo_original} | Texto: {texto_base[:1500]}"""

    for _ in range(3):  # 3 tentativas
        try:
            response = await ai_client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=[
                    {"role": "system", "content": "JSON API mode."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                timeout=25.0,
            )
            resp = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", resp, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            await asyncio.sleep(2)
    return None


# --- TAREFA PRINCIPAL ---
@tasks.loop(minutes=30)
async def verificar_feeds():
    await discord_client.wait_until_ready()

    # 🕒 Agora usando fuso horário correto
    agora = datetime.now(FUSO_HORARIO)
    if not (HORA_INICIO <= agora.hour < HORA_FIM):
        logging.info(f"Standby: {agora.strftime('%H:%M')} fora do horário comercial.")
        return

    channel = discord_client.get_channel(CANAL_NOTICIAS_ID)
    if not channel:
        return

    history = load_history()
    fila = []

    for nome_site, url_feed in FONTES_RSS.items():
        try:
            # Timeout de 10s para cada site não travar o bot
            feed = await asyncio.to_thread(feedparser.parse, url_feed)
            if not feed or not feed.entries:
                continue

            entry = feed.entries[0]
            if entry.link in history:
                continue

            img = extrair_imagem(entry)
            if not img:
                history[entry.link] = {
                    "status": "sem_imagem",
                    "data": datetime.now(FUSO_HORARIO).isoformat(),
                }
                continue

            res = await gerar_analise_ia(entry.summary, entry.title, nome_site)
            if (
                isinstance(res, dict)
                and not res.get("pular")
                and res.get("nota", 0) >= 75
            ):
                fila.append(
                    {
                        **res,
                        "link": entry.link,
                        "site": nome_site,
                        "imagem": img,
                        "is_eng": nome_site in FONTES_INGLES,
                    }
                )
                history[entry.link] = {
                    "status": "postado",
                    "data": datetime.now(FUSO_HORARIO).isoformat(),
                }
                save_history(history)
                break
        except Exception as e:
            logging.error(f"Erro em {nome_site}: {e}")

    if fila:
        campea = sorted(fila, key=lambda x: x["nota"], reverse=True)[0]
        embed = discord.Embed(
            title=f"{'🚨 ' if campea['nota'] >= 90 else ''}{campea['titulo']}",
            url=campea["link"],
            description=campea["resumo"],
            color=CORES_CATEGORIA.get(campea["categoria"], COR_PADRAO),
        )
        embed.set_author(
            name=f"Via {campea['site']} • {campea['categoria']} {EMOJIS_CATEGORIA.get(campea['categoria'], '🔌')}"
        )
        embed.set_image(url=campea["imagem"])
        embed.add_field(
            name="",
            value=f"👉 **[Clique aqui para ler a matéria completa]({campea['link']})**",
        )
        embed.set_footer(
            text=f"Resumido por IA {'• Fonte em inglês' if campea['is_eng'] else ''}"
        )

        msg = await channel.send(content=f"<@&{ID_CARGO_PARA_MARCAR}>", embed=embed)
        try:
            await msg.create_thread(
                name=f"💬 {campea['categoria']}: {campea['titulo'][:80]}",
                auto_archive_duration=1440,
            )
        except:
            pass


@discord_client.event
async def on_ready():
    logging.info(f"🤖 Tiffany Online: {discord_client.user}")
    if not verificar_feeds.is_running():
        verificar_feeds.start()


discord_client.run(DISCORD_TOKEN)
