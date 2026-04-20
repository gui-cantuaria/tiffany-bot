# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tiffany Bot is a Discord news aggregation bot that autonomously collects tech news from 15 RSS feeds (Brazilian and international), filters them using AI analysis (OpenRouter/Llama 3.3 70B), and posts curated articles as rich embeds to a Discord channel. It runs on the Discloud hosting platform.

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run via watchdog supervisor (production entry point)
python launcher.py

# Run bot directly (no auto-restart)
python notices.py
```

The bot requires a `.env` file with `DISCORD_TOKEN`, `OPENROUTER_API_KEY`, `CANAL_NOTICIAS_ID`, `ID_CARGO_PARA_MARCAR`, and `GUILD_ID`. See `.env` for all configuration parameters.

Deployed to Discloud via `discloud.config` with `launcher.py` as the main entry point.

## Architecture

**launcher.py** — Process supervisor/watchdog. Spawns `notices.py` as a subprocess, monitors health every 10 seconds, and auto-restarts on crash.

**notices.py** — Core bot logic (~1,365 lines). Three responsibilities:
1. **RSS Collection**: Fetches from 15 feeds every 30 minutes using `feedparser` + `asyncio.to_thread()`. Only operates during business hours (8–18h São Paulo time).
2. **AI Analysis**: Sends each article to OpenRouter API for translation, summarization, categorization, and relevance scoring (0–100). Sequential calls with 20-second cooldown.
3. **Discord Publishing**: Posts top-scored articles (≥75, ≥82 for games) as embeds with category emoji/color, images, source attribution, and auto-created discussion threads.

**notices_history.json** — File-based dedup state. Tracks processed articles via URL hashes and SimHash fingerprinting (Hamming distance ≤3, 36-hour TTL). Auto-cleans entries older than 7 days.

## Data Flow

```
RSS Feeds → feedparser → Image extraction → AI scoring (OpenRouter)
→ Filter pipeline (dedup, score threshold, skip flags)
→ Discord embed + thread creation → History persistence
```

## Key Design Decisions

- **No database**: All state is in `notices_history.json` (JSON file persistence).
- **Rate limiting everywhere**: `MAX_CONCORRENCIA_IA=1` (sequential AI calls), 20-second cooldown between calls, max 6 AI calls per cycle, 5-minute intervals between Discord posts.
- **SimHash deduplication**: Near-duplicate detection using content hashing with Hamming distance threshold, not just exact URL matching.
- **Pre-filter before AI**: Rejects coupons, deals, rumors, and articles without images before spending AI calls.
- **All content in Portuguese**: AI translates English sources and generates Portuguese summaries. English sources get a "Fonte em inglês" tag.

## Content Categories

8 main categories with emoji and color codes: Hardware, Inteligência Artificial, Games, Cibersegurança, Sistemas Operacionais, Mobile, Big Techs, Ciência & Espaço. Articles scoring 90+ get an emergency indicator (🚨).

## Important Notes

- The `tiffany-bot/` subdirectory is a duplicate/mirror of the root files.
- The bot language is Portuguese (Brazilian). All user-facing strings, AI prompts, and logs are in Portuguese.
- `.env` is gitignored and contains all API keys and tunable parameters (score thresholds, intervals, feed limits, etc.).

# Contexto do Projeto: Tiffany Bot (Discord News Bot)

Você atuará como um Engenheiro de Software Sênior especialista em Python e `discord.py`. O nosso projeto atual é um bot de Discord chamado "Tiffany", focado em fazer a curadoria, sumarização e publicação automatizada de notícias premium usando Inteligência Artificial.

## 🎯 Objetivo Principal e Nicho
O bot deve publicar **ESTRITAMENTE notícias relacionadas ao mundo da tecnologia, programação e desenvolvimento de software**. 
- **Tópicos desejados:** Inteligência Artificial, Engenharia de Software, Cibersegurança, Cloud/DevOps, Big Techs, Hardwares relevantes para devs e Sistemas Operacionais.
- **Tópicos proibidos:** Ciência genérica (ex: biologia, astronomia não espacial/tech, paleontologia), fofocas, entretenimento genérico, ofertas/cupons de lojas, ou reviews de celulares de entrada.

## 🎨 Padrão Visual Obrigatório (Layout do Discord)
A formatação do Embed do Discord já foi validada e está perfeita. Sob nenhuma hipótese o layout abaixo deve ser alterado sem minha autorização expressa:

1. **Author Line:** `Via {Nome do Site} • {Categoria} {Emoji da Categoria}`
2. **Título (Title):** Explicativo, jornalístico, não-clickbait. Começa com 🚨 se a nota de relevância for >= 90. A cor do embed varia conforme a categoria ou urgência.
3. **Corpo do Texto (Description):** OBRIGATORIAMENTE um **único parágrafo** longo, denso e bem construído (4 a 6 frases). Deve começar com letra maiúscula (texto formal). NUNCA usar bullet points, quebras de linha ou resumos de uma linha só. O texto deve explicar o contexto, o fato e o impacto da notícia.
4. **Call to Action (Field):** Um link com o texto exato: `👉 **[Clique aqui para ler a matéria completa]({link})**`
5. **Imagem (Image):** Imagem horizontal (16:9) extraída da notícia original.
6. **Rodapé (Footer):** Deve exibir `Notícia resumida por IA`. Se a fonte original for gringa, deve concatenar dinamicamente para: `Notícia resumida por IA • Fonte em inglês`.
7. **Thread:** O bot deve criar uma thread automaticamente na mensagem publicada com o nome: `💬 {Categoria}: {Título da Notícia}`.

## ⚙️ Stack Tecnológica e Regras de Negócio Atuais
- **Linguagem/Libs:** Python 3, `discord.py`, `feedparser`, `pytz`, pacote `openai` (apontando para a API do OpenRouter usando Llama 3.3).
- **Loop e Horário:** O bot usa `@tasks.loop(minutes=30)` para varrer os RSS feeds. Existe uma trava de fuso horário (`America/Sao_Paulo`) que impede o bot de postar fora do horário comercial (funciona apenas das 08h00 às 17h59).
- **Banco de Dados:** Atualmente usa um arquivo `.json` local (`notices_history.json`) para salvar os links processados e evitar duplicidade. Há uma função de limpeza automática para apagar links com mais de 7 dias.
- **Resiliência:** A chamada de IA possui um bloco de `retry` (3 tentativas) com `timeout` para evitar que instabilidades na API do OpenRouter travem o bot.
- **A IA Summarizadora:** O prompt enviado ao LLM exige que ele retorne um formato JSON estrito contendo: `pular` (boolean para descartar irrelevantes), `titulo` (traduzido e adaptado), `nota` (relevância de 0 a 100), `categoria` e o `resumo` de um parágrafo.

Sempre que eu pedir atualizações, refatorações ou novas features, mantenha essas regras como sua base absoluta de código.