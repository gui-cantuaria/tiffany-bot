# CLAUDE.md

## Project Overview

Tiffany Bot — multi-purpose Discord bot with three modules:
1. **News Bot** (`notices.py`) — Curates tech news from RSS feeds using AI analysis
2. **Offers Bot** (`offers_cog.py`) — Posts tech deals scraped from Promobit (loaded as a Cog by `notices.py`)
3. **Voice/Music Bot** (`tiffany_voice.py`) — Music player, voice assistant, AI chat, game picks (`t!g`), audio clips

Deployed on Hostinger VPS (Ubuntu 22.04) via systemd (`tiffany-bot.service`).

## Running

```bash
pip install -r requirements.txt
python launcher.py          # Production: runs notices.py (offers loaded as a Cog)
python notices.py            # Direct: news + offers (offers_cog) + voice/music (tiffany_voice imported)
```

Requires `.env` with: `DISCORD_TOKEN`, `OPENROUTER_API_KEY`, `CANAL_NOTICIAS_ID`, `ID_CARGO_PARA_MARCAR`, `GUILD_ID`. See `.env` for all optional parameters.

## Architecture

```
systemd (tiffany-bot.service)
  └── launcher.py (supervisor, fcntl lockfile)
        └── notices.py (news + imports tiffany_voice.py)
              └── offers_cog.py (deals, loaded as a Discord Cog)
```

## Key Files

| File | Purpose |
|---|---|
| `notices.py` | News bot + Discord client + voice module loader |
| `tiffany_voice.py` | Music, voice commands, AI chat, clip, playlists |
| `offers_cog.py` | Deals/offers bot (Discord Cog loaded by notices.py) |
| `launcher.py` | Process supervisor with lockfile |
| `random_songs.py` | 5000 famous international songs for t!r (Title - Artist) |
| `affiliate_config.py` | Affiliate link builder per store (env-driven) |
| `game_recommendations.py` | `t!g` / `t!game` — AI filter parsing + Steam/Epic validation |

**Detailed technical docs** (read on demand when modifying specific modules):
- `docs/news-technical.md` — News embed layout, AI budget, image pipeline, dedup
- `docs/offers-technical.md` — Offers embed layout, filters, affiliate links, category priority
- `docs/voice-technical.md` — Playback architecture, STT pipeline, Lavalink, known issues
- `docs/games-technical.md` — `t!g` hybrid AI+store pipeline, filters schema, rate limits, `game_history.json`

## Critical Rules

### Must-follow conventions
- **Language:** Source code (comments, docstrings, logs, internal prompts) in **English**. Only user-facing Discord output (embeds, command replies, help text, errors shown to users) in **Portuguese (BR)**. AI prompts may be English with an explicit “output in Brazilian Portuguese” clause where needed.
- **Bot prefix:** `t!` (case-insensitive)
- **AI model:** google/gemini-3.1-flash-lite (via OpenRouter) for ALL AI tasks — no fallback chains
- **Embeds:** All music/voice messages use pink embeds (TIFFANY_PINK = 0xFF69B4) via `_embed()`
- **No database:** All state in JSON files
- **New commands:** Always add to `_COMMAND_REGISTRY` + `_HELP_TEXT`/`/help` in `tiffany_voice.py` AND to `_CMD_NAMES` in `notices.py`

### Content safety
- Content blocklist: refuses music/chat/voice/summary involving dictators, totalitarian regimes, or heavy terms (`_contains_blocked_content` / `_BLOCKED_TERMS`)
- Anti-spam: auto-delete @everyone/@here mentions

### News rules
- Embed layout is locked (see `docs/news-technical.md`) — DO NOT CHANGE without authorization
- Images: always download and attach as `discord.File` — never post news without image
- Pings: only if nota >= 90 AND daily cap not reached (max 3/day). Validate role exists.
- Dedup in-cycle sets must NOT pollute persistent history

### Offers rules
- Active store whitelist: Terabyte, ShopInfo, Amazon, Mercado Livre, Shopee, AliExpress
- Pending whitelist (commented out): KaBuM, Magalu, Pichau
- Role mention cap: first 3 offers per day only
- Filters and embed layout in `docs/offers-technical.md`

## VPS Deploy

### WARP proxy (critical dependency)
Music/yt-dlp requires a Cloudflare WARP SOCKS5 proxy at `127.0.0.1:40000`. On a new
VPS, run `bash scripts/warp-setup.sh` once. A healthcheck timer
(`tiffany-warp-healthcheck.timer`) auto-reconnects it. See `docs/voice-technical.md`.

### Automated (GitHub Actions)
Push to `main` triggers `.github/workflows/deploy.yml` → SSH → `scripts/deploy.sh` → restart.
User workflow: ask in Cursor → agent commits/pushes → VPS updates automatically. See `docs/deploy-automation.md`.

### Manual
```bash
cd /opt/tiffany-bot && git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers_cog.py game_recommendations.py random_songs.py affiliate_config.py
systemctl restart tiffany-bot
journalctl -u tiffany-bot -n 30 --no-pager
```

### Deploy safety
- **NEVER** use `git pull` on VPS (has local uncommitted .env changes). Always `git checkout origin/main -- <files>`.
- **NEVER** use `pkill -9 -f "python"` — kills the bot that just started. Always kill specific processes.
