# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Tiffany Bot is a multi-purpose Discord bot with three modules:
1. **News Bot** (`notices.py`) — Curates tech news from RSS feeds using AI analysis
2. **Offers Bot** (`offers.py`) — Posts tech deals scraped from Promobit
3. **Voice/Music Bot** (`tiffany_voice.py`) — Music player, voice assistant, AI chat, music quiz, ambient sounds, audio clips

Deployed on a Hostinger VPS (Ubuntu 22.04) via systemd service (`tiffany-bot.service`).

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
systemd (tiffany-bot.service, KillMode=control-group)
  └── launcher.py (supervisor, fcntl lockfile /tmp/tiffany_launcher.lock)
        ├── notices.py (news bot + voice module)
        │     └── imports tiffany_voice.py
        │           └── imports random_songs.py (1000 songs for t$r / t$quiz)
        └── offers.py (deals bot, independent process)
```

**launcher.py** — Spawns `notices.py` and `offers.py` as subprocesses, monitors health every 10s, auto-restarts on crash. Uses `fcntl` lockfile to prevent duplicate instances. Circuit breaker: max 15 total restarts.

**notices.py** — Core bot (~1,700 lines). Handles:
- RSS collection from 15+ feeds every 45 minutes (slots at xx:00 and xx:45)
- AI analysis via OpenRouter (Llama 3.3 70B for text, Llama 4 Maverick for image validation)
- Discord publishing with embeds, threads, and image attachments
- Command normalization (`on_message` handler for spaceless commands like `T$Phttps://...`)
- Imports and registers `tiffany_voice.py` commands
- Log noise suppression for discord.ext.voice_recv and gateway warnings
- Embed safety: title truncated to 256, description to 4096, thread name to 100 chars
- Role mention validation before pinging

**tiffany_voice.py** — Voice and music module (~3,500+ lines). Handles:
- Music playback via yt-dlp download + FFmpeg (download-to-file approach, not streaming)
- Platform resolution: Spotify, Deezer, Apple Music, Amazon Music, YouTube Music -> YouTube search
- Voice recognition: discord-ext-voice-recv -> Opus decode -> Groq Whisper / Google STT / Vosk fallback
- AI chat (`t$c`), URL summarization (`t$su`), TTS responses
- Session persistence across restarts (`voice_state.json`)
- Playlist save/load system (`playlists.json`)
- Music Quiz (`t$quiz`) — plays song snippets, players guess in chat
- Ambient Sounds (`t$ambient`) — rain, lofi, cafe, forest, fire, ocean, thunder (loop via music worker)
- Audio Clip (`t$clip`) — saves last 30s of voice channel audio as WAV file
- Auto-disconnect on 5min idle (no interaction) or empty channel
- Bot moved/kicked detection via `on_voice_state_update`
- Voice command speaker channel membership validation
- Random music from 1000 international hits (`random_songs.py`)
- Anti-spam: auto-delete @everyone/@here with sarcastic response
- Inline dice rolls: `[d20+5 ataque]` detected in any message

**offers.py** — Deals bot (~750 lines). Handles:
- Promobit scraping (JSON-LD listing + serverOffer detail pages)
- 7 categories: hardware-perifericos, notebooks, notebook-gamer, monitor, processador, placa-mae, pc-gamer
- 9 store whitelist: KaBuM, Terabyte, Magalu, Pichau, Amazon, Mercado Livre, ShopInfo, Shopee, AliExpress
- Filters: 15-100% discount range, image required, stars >= 4.2, sales >= 20
- Coupon extraction, tag display, store redirect URLs
- Affiliate link injection via `affiliate_config.py`
- Posts to channel 1385327938529919006, mentions role 1386386059390357575
- Role mention validation before pinging

## Key Files

| File | Purpose |
|---|---|
| `notices.py` | News bot + Discord client + voice module loader |
| `tiffany_voice.py` | Music, voice commands, AI chat, quiz, ambient, clip, playlists |
| `offers.py` | Deals/offers bot (separate process) |
| `launcher.py` | Process supervisor with lockfile |
| `random_songs.py` | 1000 international songs for t$r and t$quiz |
| `affiliate_config.py` | Affiliate link builder per store (env-driven) |
| `notices_history.json` | Dedup state (URL hashes + SimHash, 7-day cleanup) |
| `offers_history.json` | Processed offers (7-day cleanup) |
| `voice_state.json` | Music session persistence (current song, queue) |
| `playlists.json` | Saved playlists per guild |
| `chat_memory.json` | Persistent conversation context (t$c, 24h TTL) |
| `cookies.txt` | YouTube cookies for yt-dlp (optional) |
| `vosk-model-small-pt-0.3/` | Vosk STT model (offline fallback) |
| `scripts/deploy.sh` | VPS deploy script (git fetch + checkout + restart) |
| `scripts/tiffany-bot.service` | systemd unit file for VPS |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD (push to main -> deploy) |

## Bot Commands (prefix: `t$`, case-insensitive)

Lista completa em `/help` (slash command, ephemeral) ou `_HELP_TEXT` em `tiffany_voice.py`.

**Chat & IA:** `t$c`/`t$chat`, `t$su`/`t$summary`

**Music:** `t$e`/`t$enter`, `t$leave`/`t$lv`, `t$p`/`t$play`, `t$pa`/`t$pause`, `t$re`/`t$resume`, `t$s`/`t$skip`, `t$l`/`t$loop`, `t$sh`/`t$shuffle`, `t$rp`/`t$replay`, `t$cl`/`t$clear`, `t$r`/`t$random`, `t$ff`/`t$seek`, `t$q`/`t$queue`, `t$np`/`t$nowplaying`, `t$hi`/`t$history`, `t$ap`/`t$autoplay`, `t$247`/`t$nonstop`, `t$ly`/`t$lyrics`

**Quiz:** `t$quiz [rodadas]`, `t$quizstop`/`t$qs`

**Ambient:** `t$ambient <tipo>` / `t$amb`, `t$ambient stop`

**Clip:** `t$clip`

**Playlists:** `t$pl`/`t$playlist`

**RPG & Dados:** `t$d`/`t$roll`, inline `[d20+5]`

**Voice (in call):**
- "Tiffany, toca [song]" — Add to queue
- "Tiffany, para/pula/loop/sai" — Control playback
- "Tiffany, [question]" — AI question via voice

**Slash Commands (ephemeral):**
- `/help` — Full command list (only you see)
- `/np`, `/queue`, `/stats` — Session info
- `/status` — Bot status

**Admin:** `t$st`/`t$stats`

**Important:** Always add new commands to `_HELP_TEXT` in `tiffany_voice.py` AND to `_CMD_NAMES` in `notices.py` (for spaceless command detection).

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
2. **Title:** Journalistic, non-clickbait. Starts with alert emoji if nota >= 90. Max 256 chars.
3. **Description:** Single dense paragraph (4-6 sentences), formal Portuguese. Max 4096 chars.
4. **CTA Field:** `Click here to read full article` link
5. **Image:** Downloaded and attached as `discord.File` (not URL embed)
6. **Footer:** `Noticia resumida por IA` (+ `Fonte em ingles` for EN sources)
7. **Thread:** Auto-created: `Chat {Category}: {Title}` (max 100 chars)

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

### Filters
- Discount: 15-100% (rejects negatives and absurd values > 100%)
- Image required
- Stars >= 4.2, sales >= 20
- Store must be in whitelist

## Music Technical Details

### Platform Resolution
| Platform | Method |
|---|---|
| YouTube / YouTube Music | Direct yt-dlp download |
| Spotify | oEmbed API -> `__NEXT_DATA__` JSON / legacy regex fallback |
| Deezer | oEmbed + /track/{id} API fallback |
| Apple Music | oEmbed + URL parsing fallback |
| Amazon Music | URL path parsing |

### Playback Architecture
- Download audio to temp file via yt-dlp (through WARP SOCKS5 proxy on VPS)
- Play local file with FFmpeg (no proxy needed)
- Seek (`t$ff`): reuse downloaded file with FFmpeg `-ss` parameter
- Session persistence: save current_query + queue to `voice_state.json`
- Queue limit: 10 songs max
- Playlist extraction: `extract_flat="in_playlist"`, `ignoreerrors: True`

### Voice Recognition Pipeline
```
Discord voice packets -> discord-ext-voice-recv -> Opus decode
-> PCM buffer (per user, silence-gated, 2MB cap) -> WAV 48kHz mono
-> Groq Whisper (48kHz, primary) / Google STT (16kHz, fallback) / Vosk (16kHz, offline)
-> _parse_voice_command() -> speaker channel membership check -> action dispatch
```

### AI Chat (`t$c`)
- AI semaphore: 3 concurrent calls max + global rate limit (15/min)
- Per-user sliding window: 5 turns in-memory, 3 turns persisted in `chat_memory.json`, 24h TTL
- Cooldown: 5s per user
- Supports image attachments (vision model)
- Whitespace-only input rejected

### Music Quiz (`t$quiz`)
- Uses 1000 songs from `random_songs.py`
- Downloads song via yt-dlp, seeks to 1/3 position, plays 20s snippet
- Answer detection via `on_message` listener — fuzzy word matching (40% threshold)
- Per-guild scores, medals for top 3, max 20 rounds
- Pauses current music, resumes after quiz ends
- `t$quizstop` / `t$qs` to cancel mid-game

### Ambient Sounds (`t$ambient`)
- 7 sound types: rain/chuva, lofi, cafe/cafe, forest/floresta, fire/lareira, ocean/mar, thunder/trovao
- Uses music worker with loop enabled — searches YouTube for long ambient tracks
- `t$ambient stop` to stop
- Sets `session.ambient_active` flag

### Audio Clip (`t$clip`)
- Circular PCM buffer (last 30s, 48kHz 16-bit, ~2.88MB max)
- All voice-recv audio from all users stored in `session.clip_buffer`
- Exports as WAV file sent via `discord.File`
- Requires voice-recv to be active (bot must be listening)
- Cooldown: 10s per user

### Idle & Cleanup
- Auto-disconnect after 5min idle (no commands or voice interaction)
- Empty channel watchdog: checks every 60s, disconnects if bot is alone
- `_after()` callback protected against `loop.is_closed()`
- `_notify` truncates content to 4000 chars
- Stale temp files (`tiffany_*`) cleaned on startup (>30min old)

### Random Music (`t$r`)
- 1000 international songs in `random_songs.py`
- Categories: Most Streamed, Pop, Rap/Hip-Hop, Rock, EDM, Indie/Alt, 80s-90s, R&B, Latin, K-Pop, Afrobeats, Country, Classic Anthems
- Avoids repeating last played random song

### Known Issues
- Opus decoder may throw `OpusError: corrupted stream` — monkey-patched to return silence frames, filtered in sink
- VPS YouTube blocking — resolved via Cloudflare WARP SOCKS5 proxy at 127.0.0.1:40000

## VPS Deploy Workflow

### Automated (GitHub Actions)
Push to `main` branch (paths: `*.py`, `scripts/**`) triggers `.github/workflows/deploy.yml`:
1. SSH into VPS via `appleboy/ssh-action`
2. Runs `scripts/deploy.sh`: git fetch -> checkout files -> systemctl restart tiffany-bot

Requires GitHub secrets: `VPS_HOST`, `VPS_SSH_KEY`

### Manual (systemd)
```bash
# Preferir systemd:
cd /opt/tiffany-bot && git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers.py random_songs.py affiliate_config.py
systemctl restart tiffany-bot
journalctl -u tiffany-bot -n 30 --no-pager   # verificar logs
```

### Manual (legacy, sem systemd)
```bash
cd /opt/tiffany-bot && git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers.py random_songs.py
pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null; pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null
rm -f /tmp/tiffany_launcher.lock; echo '{}' > voice_state.json
sleep 3 && PYTHONUNBUFFERED=1 nohup python3 launcher.py >> bot.log 2>&1 &
```

**NEVER** use `git pull` on VPS (has local uncommitted .env changes). Always use `git checkout origin/main -- <specific files>`.

**NEVER** use `pkill -9 -f "python"` — kills the bot that just started if run twice (Exit 137). Always kill specific processes.

## Code Conventions

- **Language:** All user-facing strings, AI prompts, and logs in Portuguese (BR)
- **Bot prefix:** `t$` (case-insensitive)
- **Help:** Only via `/help` slash command (ephemeral, embed rosa). No `t$h`/`t$help` text command.
- **File naming:** English (offers.py not ofertas.py)
- **No database:** All state in JSON files
- **Rate limiting:** Sequential AI calls, cooldowns between Discord posts
- **Images:** Always download and attach — never post news without image
- **Pings:** Only mention notification role for nota >= 90 (urgent news). Always validate role exists before mentioning.
- **Embeds:** All music/voice messages use pink embeds (TIFFANY_PINK = 0xFF69B4) via `_embed()` helper
- **Input validation:** Truncate user inputs (query 500 chars, playlist name 50 chars), strip whitespace, validate before processing
- **Error handling:** `on_message` wrapped in try/except, `_after()` checks `loop.is_closed()`, `_notify` truncates to 4000 chars
