# Tiffany Bot

Open-source Discord bot for music, AI chat, dice, tech news, and deal alerts. Prefix **`t!`** (case-insensitive) and slash commands.

## Features

- **Music** — queue, shuffle, loop, autoplay, playlists, lyrics, volume (`/play`, `/queue`, and related commands)
- **AI chat** — `/chat`, roleplay mode, link summaries, game suggestions
- **Dice** — inline rolls and macros in text channels
- **News** — RSS-based tech news with optional role pings (configurable)
- **Offers** — curated deal posts to a dedicated channel (optional module)
- **i18n** — per-user language via `/language` (**16 languages**)

Voice wake-word commands and some playback paths are optional and depend on your environment (see `.env.example`).

## Supported languages

English, Hindi, Spanish, Arabic, French, Portuguese (Brazil), Russian, German, Japanese, Korean, Vietnamese, Turkish, Italian, Ukrainian, Dutch, Swedish.

## Requirements

- Python **3.11+**
- A [Discord application](https://discord.com/developers/applications) and bot token
- Dependencies in `requirements.txt`
- Optional: PostgreSQL, Redis, Lavalink, OpenRouter API key (AI/STT features)

Enable the intents your deployment uses in the Discord Developer Portal (typically **Message Content** and **Server Members** if you use prefix commands and voice features).

## Quick start

```bash
git clone https://github.com/gui-cantuaria/tiffany-bot.git
cd tiffany-bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your values — never commit .env
python launcher.py
```

Alternative entry point: `python notices.py` (news + offers cog + voice module).

## Configuration

Copy `.env.example` to `.env` and set at least:

| Variable | Purpose |
|----------|---------|
| `DISCORD_TOKEN` | Bot token |
| `OPENROUTER_API_KEY` | AI features (chat, news analysis, optional STT) |
| `GUILD_ID` | Primary guild (slash sync / dev) |
| `CANAL_NOTICIAS_ID` | News channel |
| `ID_CARGO_PARA_MARCAR` | Role for high-score news pings |
| `BOT_OWNER_ID` | Owner user ID |

Many modules are optional (offers channel, Lavalink, voice STT, affiliates, database). See `.env.example` for the full list.

## Project layout

| Path | Role |
|------|------|
| `launcher.py` | Process supervisor |
| `notices.py` | Discord client, news loop, module loader |
| `tiffany_voice.py` | Music, voice, chat, dice, slash commands |
| `offers_cog.py` | Deals cog (loaded by `notices.py`) |
| `locale_utils.py` | i18n and shared UI strings |
| `locales/` | Per-language JSON catalogs |
| `docs/` | Module-specific technical notes |

## Documentation

- `docs/voice-technical.md` — playback, STT, Lavalink
- `docs/news-technical.md` — news pipeline
- `docs/offers-technical.md` — offers module
- `docs/games-technical.md` — game recommendations

## Self-hosting notes

- You are responsible for how the bot is used on your servers and for complying with the [Discord Developer Policy](https://discord.com/developers/docs/policies-and-agreements/developer-policy) and [Community Guidelines](https://discord.com/guidelines).
- AI and media features rely on third-party services; usage, cost, and acceptable use are governed by those providers’ terms.
- Music playback may be restricted by platform or regional rules; configure only what you need.
- Do not commit secrets (`.env`, tokens, runtime JSON state files).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are welcome — no secrets or personal deployment config in the repo.
