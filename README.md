# Tiffany Bot

A self-hosted Discord bot for music, AI chat, dice, tech news, and deal alerts. Prefix **`t!`** and slash commands.

## Features

- Music — queue, shuffle, loop, autoplay, playlists, lyrics, volume
- AI chat — conversation, roleplay, link summaries, game picks
- Dice — rolls and macros in chat
- Tech news — curated RSS posts (optional)
- Deals — offer alerts to a channel (optional)
- **16 languages** — per-user via `/language`

## Setup

**Python 3.11+** and a [Discord bot token](https://discord.com/developers/applications) are required.

```bash
git clone https://github.com/gui-cantuaria/tiffany-bot.git
cd tiffany-bot
pip install -r requirements.txt
cp .env.example .env   # add your token and settings
python launcher.py
```

See `.env.example` for optional modules and extra settings.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
