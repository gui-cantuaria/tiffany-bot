# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Tiffany Bot is a multi-purpose Discord bot with three modules:
1. **News Bot** (`notices.py`) — Curates tech news from RSS feeds using AI analysis
2. **Offers Bot** (`offers.py`) — Posts tech deals scraped from Promobit
3. **Voice/Music Bot** (`tiffany_voice.py`) — Music player, voice assistant, AI chat, audio clips

Deployed on a Hostinger VPS (Ubuntu 22.04) via systemd service (`tiffany-bot.service`).

## Running the Bot

```bash
pip install -r requirements.txt
python launcher.py          # Production: runs notices.py + offers.py as subprocesses
python notices.py            # Direct: news + voice/music (tiffany_voice.py is imported)
```

Requires `.env` with: `DISCORD_TOKEN`, `OPENROUTER_API_KEY`, `CANAL_NOTICIAS_ID`, `ID_CARGO_PARA_MARCAR`, `GUILD_ID`. See `.env` for all parameters.

Optional env vars:
- Voice/TTS: `VOICE_ENABLED` (default "1"), `TTS_ENABLED` (default "1"), `FFMPEG_PATH`, `OPUS_LIB_PATH`, `VOICE_CONNECT_TIMEOUT_SEC` (default 25), `DEBUG_STT`
- Voice reconnect: `VOICE_AUTO_REJOIN` (default "0" — bot NOT rejoins after restart, avoids entering alone)
- STT: `STT_GEMINI_FALLBACK` (default "1" — enables Whisper+Gemini fallback chain), `STT_OPENROUTER_MODEL` (default `openai/whisper-large-v3`), `STT_CHAT_MODEL` (default `google/gemini-3.1-flash-lite`)
- Offers: `CANAL_OFERTAS_ID` (default 1512902840908124281), `ID_CARGO_OFERTAS` (legado, 0=off), `ID_CARGO_OFERTAS_ULTRA` (default 1386386059390357575), `DESCONTO_ULTRA_OFERTA` (default 60%)
- Lavalink: `LAVALINK_ENABLED` (default "0"), `LAVALINK_HOST` (default localhost), `LAVALINK_PORT` (default 2333), `LAVALINK_PASSWORD` (default tiffany_lavalink_2026)
- Affiliate: `AMAZON_AFFILIATE_TAG`, `MERCADOLIVRE_AFFILIATE_ID`, `AWIN_PUBLISHER_ID`, `MAGALU_LOJA_SLUG`, `TERABYTE_AFFILIATE_ID`, `SHOPINFO_AFFILIATE_ID`, `SHOPINFO_PARAM_NAME`, `ALIEXPRESS_AFFILIATE_ID`, `SHOPEE_AFFILIATE_ID`, `LOMADEE_SOURCE_ID`, `LOMADEE_APP_TOKEN`

## Architecture

```
systemd (tiffany-bot.service, KillMode=control-group)
  └── launcher.py (supervisor, fcntl lockfile /tmp/tiffany_launcher.lock)
        ├── notices.py (news bot + voice module)
        │     └── imports tiffany_voice.py
        │           └── imports random_songs.py (~5050 songs for t!r)
        └── offers.py (deals bot, independent process)
```

**launcher.py** — Spawns `notices.py` and `offers.py` as subprocesses, monitors health every 10s, auto-restarts on crash. Uses `fcntl` lockfile to prevent duplicate instances. Circuit breaker: max 15 total restarts.

**notices.py** — Core bot (~2,150 lines). Handles:
- RSS collection from 31 feeds (8 BR + 23 EN) every 45 minutes (elapsed-time based)
- AI analysis via OpenRouter (Gemini 3.1 Flash Lite for text and image validation)
- Budget-limited AI: max 3 text analysis + max 2 vision calls per cycle
- Discord publishing with embeds, threads, and image attachments
- Command normalization (`on_message` handler for spaceless commands like `T!Phttps://...`)
- Imports and registers `tiffany_voice.py` commands
- Log noise suppression for discord.ext.voice_recv and gateway warnings
- Embed safety: title truncated to 256, description to 4096, thread name to 100 chars
- Role mention validation before pinging
- Image integrity validation: Content-Length check, EOF markers (JPEG FFD9, PNG IEND)
- Dedup: in-cycle sets (not polluting persistent history) + SimHash + title fingerprint

**tiffany_voice.py** — Voice and music module (~4,100 lines). Handles:
- Music playback via yt-dlp download + FFmpeg (download-to-file approach, not streaming)
- Platform resolution: Spotify, Deezer, Apple Music, Amazon Music, YouTube Music -> YouTube search
- Voice recognition: discord-ext-voice-recv -> Opus decode -> Google STT / Vosk fallback
- AI chat (`t!c`), URL summarization (`t!su`), TTS responses
- Session persistence across restarts (`voice_state.json`)
- Playlist save/load system (`playlists.json`)
- Audio Clip (`t!clip`) — saves last 30s of voice channel audio as WAV file (stereo 48kHz buffer)
- Auto-disconnect on 5min idle (no interaction) or empty channel (with guard against duplicate handlers)
- Bot moved/kicked detection via `on_voice_state_update`
- Voice command speaker channel membership validation
- Random music from ~5050 international hits (`random_songs.py`)
- Anti-spam: auto-delete @everyone/@here with sarcastic response
- Inline dice rolls: `[d20+5 ataque]` detected in any message
- Queue limit: 50 songs max
- Content blocklist: refuses any music/chat/voice/summary request involving dictators, totalitarian regimes, or heavy terms (`_contains_blocked_content` / `_BLOCKED_TERMS`)

**offers.py** — Deals bot (~960 lines). Handles:
- Promobit scraping (JSON-LD listing + serverOffer detail pages)
- 15 categories: hardware-perifericos, notebooks, notebook-gamer, monitor, processador, placa-mae, pc-gamer, roteador-e-repetidor (rede/adaptadores), teclado, mouse, headset, webcam, ssd, memoria-ram, mesa-digitalizadora
- **Active store whitelist** (affiliate configured): Terabyte/TerabyteShop, ShopInfo, Amazon, Mercado Livre, Shopee
- Full whitelist (when all affiliates active): + KaBuM, Magalu, Pichau, AliExpress (commented out)
- Filters: 15-100% discount, image required, stars >= 4.3, sales >= 50, at least one quality metric
- `DESCONTO_SEM_METRICA = 25%` — accepts offers without stars/sales data if discount >= 25%
- Coupon extraction, tag display, store redirect URLs
- Affiliate link injection via `affiliate_config.py`
- Posts to channel 1512902840908124281, mentions role via `ID_CARGO_OFERTAS_ULTRA`
- **Role mention cap: first 3 offers per day only** (counter resets at midnight BR)
- Role mention validation before pinging
- First cycle runs immediately on startup (no 30min delay)

## Key Files

| File | Purpose |
|---|---|
| `notices.py` | News bot + Discord client + voice module loader (~2,150 lines) |
| `tiffany_voice.py` | Music, voice commands, AI chat, clip, playlists (~4,100 lines) |
| `offers.py` | Deals/offers bot (separate process, ~940 lines) |
| `launcher.py` | Process supervisor with lockfile |
| `random_songs.py` | ~5050 international songs for t!r |
| `affiliate_config.py` | Affiliate link builder per store (env-driven) |
| `notices_history.json` | Dedup state (URL hashes + SimHash, 7-day cleanup) |
| `notices_metrics.json` | News cycle metrics (posts, AI calls, etc.) |
| `notices_queue.json` | Queued news for next cycle |
| `offers_history.json` | Processed offers (7-day cleanup) |
| `voice_state.json` | Music session persistence (current song, queue) |
| `playlists.json` | Saved playlists per guild |
| `chat_memory.json` | Persistent conversation context (t!c, 24h TTL) |
| `cookies.txt` | YouTube cookies for yt-dlp (optional) |
| `vosk-model-small-pt-0.3/` | Vosk STT model (offline fallback) |
| `scripts/deploy.sh` | VPS deploy script (git fetch + checkout + restart) |
| `scripts/tiffany-bot.service` | systemd unit file for VPS |
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD (push to main -> deploy) |

## Bot Commands (prefix: `t!`, case-insensitive)

Lista completa em `/help` (slash command, ephemeral) ou `_HELP_TEXT` em `tiffany_voice.py`.

**Chat & IA:** `t!c`/`t!chat`, `t!su`/`t!summary`

**Music:** `t!e`/`t!enter`, `t!leave`/`t!lv`, `t!p`/`t!play`, `t!pa`/`t!pause`, `t!re`/`t!resume`, `t!s`/`t!skip`, `t!l`/`t!loop`, `t!sh`/`t!shuffle`, `t!rp`/`t!replay`, `t!cl`/`t!clear`, `t!r`/`t!random`, `t!ff`/`t!seek`, `t!q`/`t!queue`, `t!np`/`t!nowplaying`, `t!hi`/`t!history`, `t!ap`/`t!autoplay`, `t!247`/`t!nonstop`, `t!ly`/`t!lyrics`

**Clip:** `t!clip`

**Playlists:** `t!pl`/`t!playlist`

**RPG & Dados:** `t!d`/`t!roll`, inline `[d20+5]`

**Voice (in call):**
- "Tiffany, toca [song]" — Add to queue
- "Tiffany, para/pula/loop/sai" — Control playback
- "Tiffany, [question]" — AI question via voice

**Slash Commands (ephemeral):**
- `/help` — Full command list (only you see)
- `/queue` — Current music queue
- `/status` — Bot status (admin-only: `default_permissions(administrator=True)`)

**Important:** Always add new commands to `_COMMAND_REGISTRY` + `_HELP_TEXT`/`/help` in `tiffany_voice.py` AND to `_CMD_NAMES` in `notices.py` (for spaceless command detection).

## News Bot Rules

### Score Thresholds
- General: >= 80 (NOTA_MIN_APROVACAO)
- Games: >= 85 (NOTA_MIN_GAMES)
- Urgent (role ping): >= 90 (NOTA_URGENTE) — **max 3 pings per day** (`_daily_mention_news` counter, resets at midnight BR)

### Schedule
- Hours: 8h-18h Sao Paulo time (UTC-3, `FUSO_HORARIO_BR`)
- Interval: every 45 minutes (elapsed-time based, `INTERVALO_NOTICIAS_MIN=45`)
- Pre-heating: entire 7h hour (`MINUTO_PRE_AQUECIMENTO=0`) — RSS collected before 8h window opens

### AI Budget per Cycle
- **Text analysis** (`gerar_analise_ia`): max 3 calls (MAX_IA_CALLS_POR_CICLO)
- **Vision validation** (`validar_imagem_ia`): max 2 calls (MAX_VISION_CALLS_POR_CICLO)
- After vision budget exhausted, images are accepted without AI validation (integrity checks still apply)
- Cooldown between AI calls: 15s (IA_COOLDOWN_SEC)
- Max 1 post per cycle (MAX_POSTS_POR_CICLO), surplus queued for next cycle
- Max 2 candidates per RSS source (MAX_CANDIDATOS_POR_FONTE)
- News older than 12h discarded (MAX_IDADE_HORAS)

### Embed Layout (DO NOT CHANGE without authorization)
1. **Author:** `Via {Site} . {Category} {Emoji}`
2. **Title:** Journalistic, non-clickbait. 6-11 words, concise (never more than 3 lines on screen). Starts with alert emoji if nota >= 90. Max 256 chars.
3. **Description:** Single dense paragraph (4-6 sentences), formal Portuguese. Max 4096 chars.
4. **CTA Field:** `Click here to read full article` link
5. **Image:** Downloaded and attached as `discord.File` (not URL embed)
6. **Footer:** `Noticia resumida por IA` (+ `Fonte em ingles` for EN sources)
7. **Thread:** Auto-created: `Chat {Category}: {Title}` (max 100 chars)

### AI Model
- **Unified model:** google/gemini-3.1-flash-lite (via OpenRouter)
- Used for: text analysis, image validation (vision), chat (`t!c`), URL summary (`t!su`), voice questions
- No fallback chain — same model for all attempts (3 retries with backoff)
- **Cost control:** Previous model (gemini-3.5-flash) was 6x more expensive and burned ~$5/day. Current model costs ~$0.25/M input, $1.50/M output tokens.

### Image Pipeline
- Extract from RSS `<media:content>`, `<enclosure>`, og:image meta tags
- Validate: min 400x200px, no 403 responses, AI vision relevance check (budget-limited)
- Download with `r.read()` (full response, not truncated)
- Integrity: Content-Length vs bytes received, JPEG EOF (FFD9), PNG IEND chunk
- Timeout: 30s, 3 retries
- Attach as `discord.File` (never post without image)

### Dedup System
- URL hash + SimHash (Hamming distance <= 6) + title fingerprint
- In-cycle: `_cycle_titles` and `_cycle_simhashes` sets (in-memory only, do NOT pollute persistent history)
- Persistent: `_simhash_idx` and `_title_idx` in `notices_history.json` (pruned once per cycle)
- Title/simhash only added to persistent history AFTER IA approval (Fase 2)

## Offers Bot Rules

### Embed Layout
- Author: `Via {store} • Oferta {cat_emoji}` (category emoji from `CATEGORIAS_EMOJI`)
- Title: `🔥 {product} — {discount}% OFF`
- Description line 1: `~~R$ original~~ → **R$ current** (-X%)`
- Description line 2: `Você economiza R$ X` (no emoji)
- Details block (when available): `🏷️ Cupom: \`code\``, `💳 installments`, `⏰ Expira: date`, `⭐ N/5 (N avaliações)`, tags (plain text, no emoji)
- CTA in description: `## [COMPRAR COM X% OFF](url)` (heading link, no emoji)
- Button: `🛒 COMPRAR COM X% OFF` (Discord link button, always gray)
- Footer: `Preço sujeito a alterações`
- Role mention content (first 3/day): `<@&cargo_id>`
- Thread: `🛒 {store}: {title[:70]}`

### Schedule
- Hours: 8h-18h SP, 30min cycle (`SCAN_INTERVAL_MIN=30`), max 5 posts per cycle, 3min spacing
- First cycle runs immediately on bot startup (no delay)

### Category Variety / Prioritization
- **Enrichment ordering**: `pre_candidates` sorted by `_CATEGORY_PRIORITY` first (then whitelist-known store), so priority parts (CPU/GPU/RAM = priority 1) get the limited enrichment budget (`[:26]`) before monitors/motherboards
- **Diversification** (`_select_diverse`): final post selection is a round-robin across categories, **max 2 per category per cycle**, so a single category (e.g. monitor) can't dominate and priority parts surface. Applied after priority+score sort, before `_interleave_by_store`
- Accessories ("Suporte e Acessórios": monitor arms/stands) demoted to priority 4 (was 2) to avoid crowding out real parts

### Filters
- Discount: 15-100% (rejects negatives and absurd values > 100%)
- Image required
- **Relevance filter** (`_is_irrelevant` / `_IRRELEVANT_KEYWORDS`): rejects non-IT products that Promobit sometimes lists inside PC categories (appliances/kitchen/toys: pipoqueira, liquidificador, fritadeira, etc.). Fixes cases like "Pipoqueira Disney Mickey Mouse" landing in `/mouse/`.
- **Stars >= 4.3, sales >= 50**
- Store must be in active whitelist (Terabyte, ShopInfo, Amazon, Mercado Livre, Shopee)
- Must have at least one quality metric (stars OR sales) — or discount >= 25% if no data at all (`DESCONTO_SEM_METRICA`)
- **Rede/adaptadores** (`_is_rede`: categoria `roteador-e-repetidor` ou título com palavra-chave de adaptador): filtros próprios e mais rígidos — stars >= 4.5 AND sales >= 100 AND discount >= 40%, sem fallback "sem métrica" (exige dados reais do Promobit)

### Role Mentions (Offers)
- **Cap: first 3 offers per day** get `<@&ID_CARGO_OFERTAS_ULTRA>` mention
- Daily counter: `_mention_count_ofertas` / `_mention_date_ofertas` (in-memory, resets at midnight BR)
- Cargo ID: `ID_CARGO_OFERTAS_ULTRA` env var (default 1386386059390357575)
- Old ultra-offer logic (ping only on disc >= 60%) replaced by daily cap

### Affiliate Links (affiliate_config.py)
| Store | Method | Env var |
|---|---|---|
| Amazon | `?tag=` param | `AMAZON_AFFILIATE_TAG` |
| Mercado Livre | `?matt_word=` param | `MERCADOLIVRE_AFFILIATE_ID` |
| KaBuM | Awin deeplink | `AWIN_PUBLISHER_ID` |
| Terabyte | Lomadee deeplink > Awin > param | `LOMADEE_SOURCE_ID` / `AWIN_PUBLISHER_ID` |
| Pichau | Awin deeplink | `AWIN_PUBLISHER_ID` |
| ShopInfo | Lomadee deeplink > param | `LOMADEE_SOURCE_ID` / `SHOPINFO_AFFILIATE_ID` |
| Shopee | `s.shopee.com.br/an_redir?origin_link=...&affiliate_id=` | `SHOPEE_AFFILIATE_ID` |
| AliExpress | `?aff_fcid=` param | `ALIEXPRESS_AFFILIATE_ID` |

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
- Seek (`t!ff`): reuse downloaded file with FFmpeg `-ss` parameter, safety timeout on worker wait loop
- Session persistence: save current_query + queue to `voice_state.json`
- Queue limit: 50 songs max
- Playlist extraction: `extract_flat="in_playlist"`, `ignoreerrors: True`
- Shuffle: zip display+query together before shuffling (keeps them synchronized)

### Voice Recognition Pipeline
```
Discord voice packets -> discord-ext-voice-recv -> Opus decode
-> PCM buffer (per user, silence-gated, min 1s / max 10s rolling)
-> normalize_audio() -> vad_filter() (drops silence frames)
-> WAV 48kHz -> FFmpeg -> WAV 16kHz
-> _transcribe_wav_bytes() -> _pick_best_stt_transcript()
-> _parse_voice_command() -> speaker channel membership check -> action dispatch
```

**STT priority chain** (all run, best transcript selected):
1. **Whisper via OpenRouter** (`openai/whisper-large-v3`, env `STT_OPENROUTER_MODEL`) — primary
2. **Gemini chat STT** (`google/gemini-3.1-flash-lite`, env `STT_CHAT_MODEL`) — runs if Whisper fails or no wake word detected
3. **Google STT** (`speech_recognition.recognize_google`, free, pt-BR)
4. **Vosk** (offline, `vosk-model-small-pt-0.3/`)

`_pick_best_stt_transcript()`: prefers transcripts containing wake word "Tiffany" (fuzzy-normalized), then longest.
`_is_stt_bleed()`: filters YouTube/video "subscribe" phrases that leak via mic.
`STT_TAIL_SEC=6`: if audio > 6s, sends only last 6s to STT.
Enabled by `STT_GEMINI_FALLBACK=1` (default). Disable with `STT_GEMINI_FALLBACK=0` for Google+Vosk only.

### AI Chat (`t!c`)
- Model: google/gemini-3.1-flash-lite (via OpenRouter)
- AI semaphore: 3 concurrent calls max + global rate limit (15/min)
- Per-user sliding window: 5 turns in-memory, 3 turns persisted in `chat_memory.json`, 24h TTL
- Cooldown: 5s per user
- Supports image attachments (same model handles vision natively)
- Whitespace-only input rejected

### Audio Clip (`t!clip`)
- Circular PCM buffer (last 30s, stereo 48kHz 16-bit, ~5.76MB max)
- All voice-recv audio from all users stored in `session.clip_buffer`
- Exports as WAV file sent via `discord.File`
- Requires voice-recv to be active (bot must be listening)
- Cooldown: 10s per user

### Idle & Cleanup
- Auto-disconnect after 5min idle (no commands or voice interaction)
- Skips disconnect if 24/7 mode enabled
- Empty channel watchdog: checks every 60s, disconnects if bot is alone
- `on_voice_state_update` handler: guard against duplicate 60s sleeps (`_empty_channel_pending`)
- `_after()` callback protected against `loop.is_closed()`
- `_notify` truncates content to 4000 chars
- Stale temp files (`tiffany_*`) cleaned on startup (>30min old)

### Random Music (`t!r`)
- ~5050 international songs in `random_songs.py` (expand via `scripts/merge_all_song_sources.py`)
- Categories: Most Streamed, Pop, Rap/Hip-Hop, Rock, EDM, Indie/Alt, 80s-90s, R&B, Latin, K-Pop, Afrobeats, Country, Classic Anthems
- Avoids repeating last played random song

### Lavalink / wavelink
- Code fully integrated (`wavelink>=3.4.0`, `import wavelink` with graceful fallback if not installed)
- **Disabled by default** (`LAVALINK_ENABLED=0`) — VPS uses yt-dlp mode to keep `VoiceRecvClient` (voice listening)
- When enabled: connects to `LAVALINK_HOST:LAVALINK_PORT` with `LAVALINK_PASSWORD` on `on_ready`
- Docker infra ready: `Dockerfile`, `docker-compose.yml`, `lavalink/application.yml` (password: `tiffany_lavalink_2026`)
- `VOICE_AUTO_REJOIN=0` (default) — bot does NOT auto-rejoin voice after restart to avoid entering channels alone

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
- **Bot prefix:** `t!` (case-insensitive)
- **Help:** Only via `/help` slash command (ephemeral, embed rosa). No `t!h`/`t!help` text command.
- **File naming:** English (offers.py not ofertas.py)
- **No database:** All state in JSON files
- **AI model:** Single unified model (Gemini 3.1 Flash Lite) for all AI tasks — no fallback chains
- **AI cost control:** Budget limits per cycle (3 text + 2 vision), ~13 cycles/day (every 45 min). Model history: gemini-2.5-flash-preview (discontinued) -> gemini-3.5-flash (too expensive, $5/day) -> gemini-3.1-flash-lite (current, cheap)
- **Rate limiting:** Sequential AI calls, cooldowns between Discord posts
- **Images:** Always download and attach — never post news without image. Validate integrity (Content-Length, EOF markers).
- **Pings (news):** Mention role only if nota >= 90 AND daily cap not reached (max 3/day). Always validate role exists.
- **Pings (offers):** Mention role for first 3 offers of the day only. No ultra-offer distinction anymore.
- **Embeds:** All music/voice messages use pink embeds (TIFFANY_PINK = 0xFF69B4) via `_embed()` helper
- **Input validation:** Truncate user inputs (query 500 chars, playlist name 50 chars), strip whitespace, validate before processing
- **Error handling:** `on_message` wrapped in try/except, `_after()` checks `loop.is_closed()`, `_notify` truncates to 4000 chars
- **JSON persistence:** `save_metrics()` and `save_queue()` use try/except with .tmp cleanup on failure
