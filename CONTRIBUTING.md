# Contributing

Thanks for helping improve Tiffany Bot.

## Development setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your tokens — never commit .env
python launcher.py
```

Run tests: `python -m unittest test_smoke -q`

## Project structure

| Module | File |
|--------|------|
| Discord client + news | `notices.py` |
| Music, voice, chat, dice | `tiffany_voice.py` |
| Deals cog | `offers_cog.py` |
| Supervisor | `launcher.py` |
| i18n | `locale_utils.py`, `locales/` |
| Tiffany OS Core (experimental, private-boundary) | `tiffany_core/` — see `tiffany_core/PRIVATE_CORE.md` |

See `docs/*-technical.md` for module-specific notes.  
Strategic boundary: `docs/open-ecosystem-strategy.md`. Security: `SECURITY.md`.

## Conventions

- **Source code** (comments, logs, internal prompts): **English**
- **User-facing Discord text**: use `tr()` / `locales/` (16 languages)
- **Prefix:** `t!` (case-insensitive); register new commands in `tiffany_voice.py` and `notices.py`
- **Embeds:** music/voice UI uses pink (`TIFFANY_PINK`) via `_embed()`
- **AI model:** `google/gemini-3.1-flash-lite` via OpenRouter (project standard)
- **State:** JSON files at runtime; optional PostgreSQL/Redis for HA features

## Content safety

- Respect Discord's [Developer Policy](https://discord.com/developers/docs/policies-and-agreements/developer-policy) and [Community Guidelines](https://discord.com/guidelines)
- Do not weaken `_BLOCKED_TERMS`, moderation pipelines, or anti-spam guards without a clear reason
- Never commit secrets, production IDs, or personal deployment config

## Pull requests

- Keep diffs focused
- Update locale keys when changing user-visible strings
- Avoid committing runtime JSON state files
