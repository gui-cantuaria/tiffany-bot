# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Tiffany Bot is a multi-purpose Discord bot with three modules:
1. **News Bot** (`notices.py`) — Curates tech news from RSS feeds using AI analysis
2. **Offers Bot** (`offers.py`) — Posts tech deals scraped from Promobit
3. **Voice/Music Bot** (`tiffany_voice.py`) — Music player, voice assistant, and AI chat

Deployed on a Hostinger VPS (Ubuntu 22.04) via `launcher.py` supervisor.

## Running the Bot

```bash
pip install -r requirements.txt
python launcher.py          # Production: runs notices.py + offers.py as subprocesses
python notices.py            # Direct: news + voice/music (tiffany_voice.py is imported)
```

Requires `.env` with: `DISCORD_TOKEN`, `OPENROUTER_API_KEY`, `CANAL_NOTICIAS_ID`, `ID_CARGO_PARA_MARCAR`, `GUILD_ID`. See `.env` for all parameters.

Affiliate env vars (all optional — bot works without them):
`AMAZON_AFFILIATE_TAG`, `MERCADOLIVRE_AFFILIATE_ID`, `AWIN_PUBLISHER_ID`, `MAGALU_LOJA_SLUG`, `TERABYTE_AFFILIATE_ID`, `SHOPINFO_AFFILIATE_ID`, `SHOPINFO_PARAM_NAME`, `ALIEXPRESS_AFFILIATE_ID`

## Architecture

```
launcher.py (supervisor, fcntl lockfile /tmp/tiffany_launcher.lock)
  ├── notices.py (news bot + voice module)
  │     └── imports tiffany_voice.py
  └── offers.py (deals bot, independent process)
```

**launcher.py** — Spawns `notices.py` and `offers.py` as subprocesses, monitors health every 10s, auto-restarts on crash. Uses `fcntl` lockfile to prevent duplicate instances.

**notices.py** — Core bot (~1,700 lines). Handles:
- RSS collection from 15+ feeds every 45 minutes (slots at xx:00 and xx:45)
- AI analysis via OpenRouter (Llama 3.3 70B for text, Llama 4 Maverick for image validation)
- Discord publishing with embeds, threads, and image attachments
- Command normalization (`on_message` handler for spaceless commands like `T$Phttps://...`)
- Imports and registers `tiffany_voice.py` commands

**tiffany_voice.py** — Voice and music module (~2,300 lines). Handles:
- Music playback via yt-dlp download + FFmpeg (download-to-file approach, not streaming)
- Platform resolution: Spotify, Deezer, Apple Music, Amazon Music → YouTube search
- Voice recognition: discord-ext-voice-recv → Opus decode → Google STT / Vosk fallback
- AI chat (`t$c`), URL summarization (`t$su`), TTS responses
- Session persistence across restarts (`voice_state.json`)
- Playlist save/load system (`playlists.json`)

**offers.py** — Deals bot (~750 lines). Handles:
- Promobit scraping (JSON-LD listing + serverOffer detail pages)
- 7 categories: hardware-perifericos, notebooks, notebook-gamer, monitor, processador, placa-mae, pc-gamer
- 9 store whitelist: KaBuM, Terabyte, Magalu, Pichau, Amazon, Mercado Livre, ShopInfo, Shopee, AliExpress
- Filters: 15%+ discount, image required
- Coupon extraction, tag display, store redirect URLs
- Posts to channel 1385327938529919006, mentions role 1386386059390357575

## Key Files

| File | Purpose |
|---|---|
| `notices.py` | News bot + Discord client + voice module loader |
| `tiffany_voice.py` | Music, voice commands, AI chat, playlists |
| `offers.py` | Deals/offers bot (separate process) |
| `launcher.py` | Process supervisor with lockfile |
| `notices_history.json` | Dedup state (URL hashes + SimHash, 7-day cleanup) |
| `offers_history.json` | Processed offers (7-day cleanup) |
| `voice_state.json` | Music session persistence (current song, queue) |
| `playlists.json` | Saved playlists per guild |
| `affiliate_config.py` | Affiliate link builder per store (env-driven) |
| `chat_memory.json` | Persistent conversation context (t$c learning) |
| `cookies.txt` | YouTube cookies for yt-dlp (optional) |
| `vosk-model-small-pt-0.3/` | Vosk STT model (offline fallback) |

## Bot Commands (prefix: `t$`, case-insensitive)

Cada comando tem forma curta e longa (ex.: `t$h` / `t$help`). Lista completa em `t$h` ou `_HELP_TEXT` em `tiffany_voice.py`.

**Chat & IA:** `t$c`/`t$chat`, `t$su`/`t$summary`

**Music:** `t$e`/`t$enter`, `t$leave`/`t$lv`, `t$p`/`t$play`, `t$pa`/`t$pause`, `t$re`/`t$resume`, `t$s`/`t$skip`, `t$l`/`t$loop`, `t$cl`/`t$clear`, `t$r`/`t$random`, `t$ff`/`t$seek`, `t$q`/`t$queue`, `t$np`/`t$nowplaying`

**Playlists:** `t$pl`/`t$playlist`

**Help:** `t$h`/`t$help`

**Voice (in call):**
- "Tiffany, toca [song]" — Add to queue
- "Tiffany, para/pula/sai" — Control playback
- "Tiffany, [question]" — AI question via voice

**Admin:**
- `t$st` — Session stats
- `/status` — Bot status (slash command)

**Important:** Always add new commands to `_HELP_TEXT` / `t$h` in `tiffany_voice.py` AND to `_CMD_NAMES` in `notices.py` (for spaceless command detection).

## News Bot Rules

### Score Thresholds
- General: >= 80 (NOTA_MIN_APROVACAO)
- Games: >= 85 (NOTA_MIN_GAMES)
- Urgent (role ping): >= 90 (NOTA_URGENTE)

### Schedule
- Hours: 8h-18h Sao Paulo time (America/Sao_Paulo, UTC-3)
- Slots: xx:00 and xx:45 (45-minute intervals)
- Pre-heating: 7:45 for RSS collection before 8:00

### Embed Layout (DO NOT CHANGE without authorization)
1. **Author:** `Via {Site} . {Category} {Emoji}`
2. **Title:** Journalistic, non-clickbait. Starts with alert emoji if nota >= 90
3. **Description:** Single dense paragraph (4-6 sentences), formal Portuguese
4. **CTA Field:** `Click here to read full article` link
5. **Image:** Downloaded and attached as `discord.File` (not URL embed)
6. **Footer:** `Noticia resumida por IA` (+ `Fonte em ingles` for EN sources)
7. **Thread:** Auto-created: `Chat {Category}: {Title}`

### AI Models
- **Text analysis:** meta-llama/llama-3.3-70b-instruct (via OpenRouter)
- **Image validation:** meta-llama/llama-4-maverick (vision model, checks image relevance)

### Image Pipeline
- Extract from RSS `<media:content>`, `<enclosure>`, og:image meta tags
- Validate: min 400x200px, no 403 responses, AI vision relevance check
- Download and attach as `discord.File` (never post without image)

## Offers Bot Rules

### Embed Layout
- Title: `Fire emoji {product} — {discount}% OFF`
- Prices: `R$ {original} -> R$ {current} (-{discount}%)`
- Coupon: `Tag emoji Cupom: **{code}**`
- CTA: `Point right emoji **[COMPRAR COM DESCONTO]({url})**` (CAPSLOCK)
- Tags: Extract `name` from tag dicts (e.g., "Frete Gratis", "Parcelado")
- Footer: `Oferta verificada automaticamente`

### Schedule
- Hours: 8h-18h SP, 30min cycle, max 5 posts, 3min spacing

## Music Technical Details

### Platform Resolution
| Platform | Method |
|---|---|
| YouTube | Direct yt-dlp download |
| Spotify | oEmbed API (artist + title) |
| Deezer | oEmbed + /track/{id} API fallback |
| Apple Music | oEmbed + URL parsing fallback |
| Amazon Music | URL path parsing |

### Playback Architecture
- Download audio to temp file via yt-dlp (through WARP SOCKS5 proxy on VPS)
- Play local file with FFmpeg (no proxy needed)
- Seek (`t$ff`): reuse downloaded file with FFmpeg `-ss` parameter
- Session persistence: save current_query + queue to `voice_state.json`

### Voice Recognition Pipeline
```
Discord voice packets → discord-ext-voice-recv → Opus decode
→ PCM buffer (per user, silence-gated) → WAV 48kHz mono
→ FFmpeg resample to 16kHz → Google STT (primary) / Vosk (fallback)
→ _parse_voice_command() → action dispatch
```

### Known Issues
- Opus decoder may throw `OpusError: corrupted stream` — monkey-patched to return silence frames, filtered in sink
- VPS YouTube blocking — resolved via Cloudflare WARP SOCKS5 proxy at 127.0.0.1:40000

## VPS Deploy Workflow

**Não use** `pkill -9 -f "python"` — mata o bot que acabou de iniciar se você rodar o comando duas vezes seguidas (Exit 137).

```bash
# Na VPS — preferir o script:
cd /opt/tiffany-bot && git fetch && bash scripts/vps-restart.sh

# Ou manual (pkill específico do Tiffany):
cd /opt/tiffany-bot && git fetch && git checkout origin/main -- launcher.py notices.py tiffany_voice.py
pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null; pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null
rm -f /tmp/tiffany_launcher.lock; echo '{}' > voice_state.json
sleep 3 && PYTHONUNBUFFERED=1 nohup python3 launcher.py >> bot.log 2>&1 &
```

Never use `git pull` on VPS (has local uncommitted .env changes). Always use `git checkout origin/main -- <specific files>`.

## Code Conventions

- **Language:** All user-facing strings, AI prompts, and logs in Portuguese (BR)
- **Bot prefix:** `t$` (case-insensitive)
- **File naming:** English (offers.py not ofertas.py)
- **No database:** All state in JSON files
- **Rate limiting:** Sequential AI calls, cooldowns between Discord posts
- **Images:** Always download and attach — never post news without image
- **Pings:** Only mention notification role for nota >= 90 (urgent news)
