import discord
from discord.ext import tasks
import feedparser
import os
import json
import asyncio
import re
from dotenv import load_dotenv
from openai import AsyncOpenAI  

# --- CONFIGURAÇÕES INICIAIS ---
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY') 

# --- CONFIGURAÇÃO DE IDs FIXOS ---
CANAL_NOTICIAS_ID = 1420835598733938849
CARGO_MENTION_ID = 1460323314357501952 
ID_CARGO_PARA_MARCAR = 1460323314357501952

# --- CORES POR CATEGORIA ---
CORES_CATEGORIA = {
    "Hardware": 0xE03E3E,   
    "IA": 0x00FFFF,         
    "Games": 0x9146FF,      
    "Segurança": 0x00FF00,  
    "Mobile": 0xFFA500,     
    "Business": 0x000080,   
    "Science": 0x808080     
}
COR_PADRAO = 0xFFD700       
COR_URGENTE = 0xFF0000      

# --- FONTES (AMPLIADAS COM SITES DE ALTO NÍVEL) ---
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
    "KrebsOnSecurity": "https://krebsonsecurity.com/feed/",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Google Security Blog": "https://security.googleblog.com/feeds/posts/default?alt=rss",
    "The Register": "https://www.theregister.com/headlines.atom",
    "9to5Mac": "https://9to5mac.com/feed/",
    "9to5Google": "https://9to5google.com/feed/",
    "ZDNet": "https://www.zdnet.com/news/rss.xml"
}

FONTES_INGLES = [
    "The Verge", "TechCrunch", "Ars Technica", "Wired", "Engadget", 
    "KrebsOnSecurity", "BleepingComputer", "Google Security Blog", 
    "The Register", "9to5Mac", "9to5Google", "ZDNet"
]

# --- CATEGORIAS E EMOJIS (VISUAL DISCORD) ---
EMOJIS_CATEGORIA = {
    "Hardware": "🖥️", "Smartphones": "📱", "Inteligência Artificial": "🤖",
    "Games": "🎮", "Cibersegurança": "🛡️", "Software & Apps": "💾",
    "Big Techs": "💼", "Ciência & Espaço": "🚀", "Curiosidade Tech": "💡",
    "Sistemas Operacionais": "🪟", "Internet & Redes": "🌐", 
    "Cloud & DevOps": "☁️", "Programação & Dev": "🧑‍💻", 
    "Mídia & Streaming": "📺", "Outros": "🔌"
}

HISTORY_FILE = "notices_history.json"

intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

if OPENROUTER_API_KEY:
    ai_client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )
else:
    ai_client = None

# --- FUNÇÕES AUXILIARES ---
def load_history():
    if not os.path.exists(HISTORY_FILE): return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except json.JSONDecodeError: return {}

def save_history(history_dict):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_dict, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao salvar histórico: {e}")

def extrair_imagem(entry):
    try:
        if 'media_content' in entry and len(entry.media_content) > 0: 
            return entry.media_content[0]['url']
        if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0: 
            return entry.media_thumbnail[0]['url']
        if 'links' in entry:
            for link in entry.links:
                if 'image' in link.get('type', ''): return link.href
        
        content = getattr(entry, 'content', [{}])[0].get('value', '')
        summary = getattr(entry, 'summary', '')
        
        match = re.search(r'<img[^>]+src="([^">]+\.(?:jpg|jpeg|png|webp)[^">]*)"', content, re.IGNORECASE) or \
                re.search(r'<img[^>]+src="([^">]+\.(?:jpg|jpeg|png|webp)[^">]*)"', summary, re.IGNORECASE)
        if match: 
            return match.group(1)
    except: 
        pass
    return None

# --- FUNÇÃO DE IA ---
async def gerar_analise_ia(texto_base, titulo_original, nome_site):
    if not ai_client or not texto_base: return None
    
    print(f"🤖 IA analisando: {nome_site}...")
    
    prompt = f"""Sua missão é filtrar o irrelevante e reescrever a notícia em um formato específico, retornando APENAS JSON.

REGRAS OBRIGATÓRIAS:
1. TRADUÇÃO: Se a fonte for estrangeira, traduza tudo para Português do Brasil.
2. TÍTULOS EXPLICATIVOS: Crie um título claro que conte o fato principal, sem clickbait. (Ex: "Microsoft testa melhorias de segurança em arquivos batch do Windows 11").
3. O CORPO DO TEXTO (ESTILO DESCHAMPS MISTO):
   - Escreva UM ÚNICO PARÁGRAFO contínuo, longo e denso.
   - COMECE O TEXTO NORMALMENTE COM LETRA MAIÚSCULA.
   - Explique a notícia para que leigos e experientes entendam o impacto da informação.
   - A ÚLTIMA FRASE DEVE SER RIGOROSAMENTE ESTA: "As informações são do site {nome_site}."
4. CATEGORIA: Use uma da lista: Hardware, Smartphones, Inteligência Artificial, Games, Cibersegurança, Software & Apps, Big Techs, Ciência & Espaço, Internet & Redes, Cloud & DevOps, Programação & Dev, Mídia & Streaming, Curiosidade Tech, Sistemas Operacionais, Outros.
5. NOTA: Dê uma nota de 0 a 100. Somente notícias com nota >= 75 serão aprovadas.
6. PULAR: Se for oferta/cupom, review ou celular de entrada sem inovação, marque "pular": true.

FORMATO DO JSON:
{{
  "pular": false,
  "titulo": "Título Explicativo Aqui",
  "nota": 85,
  "categoria": "Sistemas Operacionais",
  "resumo": "A empresa está lançando novas builds de pré-visualização do Windows 11 Insider que visam melhorar a segurança durante a execução de scripts. Essas melhorias são cruciais para manter a segurança do sistema contra ataques maliciosos, além de contribuírem para uma experiência mais rápida. As informações são do site {nome_site}."
}}

Fonte: {nome_site}
Título Original: {titulo_original}
Texto: {texto_base[:1500]}
"""

    try:
        response = await ai_client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct", 
            messages=[
                # Regra de sistema ABSOLUTA para forçar o output JSON
                {"role": "system", "content": "Você é uma API de processamento de dados. Você responde EXCLUSIVAMENTE em formato JSON. Não adicione nenhuma saudação, aviso ou texto fora das chaves {...}."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
        )
        resp_text = response.choices[0].message.content.strip()
        
        # Garra Extratora de JSON: Puxa só o que está entre as chaves {}
        match = re.search(r'\{.*\}', resp_text, re.DOTALL)
        if match:
            resp_text = match.group(0)
        else:
            print(f"❌ Erro: IA não retornou um JSON identificável.")
            return None
            
        dados = json.loads(resp_text)
        
        if dados.get("pular", False) or int(dados.get("nota", 0)) < 75:
            return "SKIP"
            
        return {
            "titulo": dados.get("titulo", titulo_original).strip(),
            "nota": int(dados.get("nota", 75)),
            "categoria": dados.get("categoria", "Outros").strip(),
            "resumo": dados.get("resumo", "").strip()
        }

    # Catching específico para ver o erro se acontecer de novo
    except json.JSONDecodeError:
        print(f"❌ Erro ao decodificar JSON. Resposta crua da IA foi: {resp_text[:150]}...")
        return None
    except Exception as e:
        print(f"❌ Erro na IA (OpenRouter): {e}")
        return None

# --- LOOP PRINCIPAL ---
@tasks.loop(minutes=30)
async def verificar_feeds():
    await discord_client.wait_until_ready()
    
    channel = discord_client.get_channel(CANAL_NOTICIAS_ID)
    if not channel: 
        print(f"Erro: Canal {CANAL_NOTICIAS_ID} não encontrado.")
        return
    
    await discord_client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Tech News"))

    history = load_history()
    print("\n--- 📡 Buscando Notícias ---")
    
    fila = [] 

    for nome_site, url_feed in FONTES_RSS.items():
        await asyncio.sleep(2) 
        try:
            feed = await asyncio.to_thread(feedparser.parse, url_feed, agent="Mozilla/5.0")
            if not feed.entries: continue

            for entry in feed.entries[:3]:
                link = entry.link
                
                if link in history.values() or link in history:
                    continue
                
                url_imagem = extrair_imagem(entry)
                if not url_imagem:
                    history[link] = "sem_imagem"
                    save_history(history)
                    continue

                texto = getattr(entry, 'summary', getattr(entry, 'description', entry.title))
                
                res = await gerar_analise_ia(texto, entry.title, nome_site)

                if res == "SKIP":
                    history[link] = "rejeitada_pela_ia"
                    save_history(history)
                elif isinstance(res, dict):
                    print(f"✅ Aprovada: {res['titulo']} ({res['nota']})")
                    
                    is_eng = nome_site in FONTES_INGLES
                    
                    fila.append({
                        "site": nome_site,
                        "link": link,
                        "titulo": res['titulo'],
                        "resumo": res['resumo'],
                        "nota": res['nota'],
                        "categoria": res['categoria'],
                        "imagem": url_imagem,
                        "is_eng": is_eng
                    })
                    
                    history[link] = "na_fila"
                    save_history(history) 
                    break 
                
        except Exception as e:
            print(f"Erro no site {nome_site}: {e}")

    if fila:
        fila.sort(key=lambda x: x['nota'], reverse=True)
        campea = fila[0]
        
        print(f"🚀 Postando a Vencedora: {campea['titulo']}")

        urgente = campea['nota'] >= 90
        importante = campea['nota'] >= 85 and not urgente
        
        badge = "🚨 " if urgente else ("🔥 " if importante else "")
        titulo_final = f"{badge}{campea['titulo']}"
        
        cor_final = 0xFF0000 if urgente else (0xFFA500 if importante else 0x00FFFF)
        
        emoji_cat = EMOJIS_CATEGORIA.get(campea['categoria'], "🔌")

        embed = discord.Embed(
            title=titulo_final,
            url=campea['link'],
            description=campea['resumo'],
            color=cor_final
        )
        
        embed.set_author(name=f"Via {campea['site']} • {campea['categoria']} {emoji_cat}", icon_url="https://cdn-icons-png.flaticon.com/512/2965/2965363.png")
        embed.add_field(name="", value=f"👉 **[Clique aqui para ler a matéria completa]({campea['link']})**", inline=False)
        embed.set_image(url=campea['imagem'])
        
        footer_text = "Notícia resumida por IA"
        if campea['is_eng']:
            footer_text += " • Fonte em inglês"
        embed.set_footer(text=footer_text)
        
        msg_content = f"<@&{ID_CARGO_PARA_MARCAR}>" if ID_CARGO_PARA_MARCAR else ""
        
        msg = await channel.send(content=msg_content, embed=embed)
        
        try:
            nome_topico = f"💬 {campea['categoria']}: {campea['titulo']}"
            await msg.create_thread(name=nome_topico[:95], auto_archive_duration=1440)
        except:
            pass
        
    else:
        print("💤 Nenhuma notícia relevante nova neste ciclo.")

@discord_client.event
async def on_ready():
    print(f'🤖 Bot Online: {discord_client.user}')
    if not verificar_feeds.is_running():
        verificar_feeds.start()

if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)