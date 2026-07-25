# Infrastructure roadmap — implementation steps

This document tracks the six pillars from the Tiffany scale-up plan and what exists in the repo today.

## 1. Audio — Lavalink + LavaSrc ✅ foundation

**Done:**
- `lavalink/application.yml` — YouTube plugin + LavaSrc 4.7 (Spotify, Apple, Deezer, Tidal, Yandex)
- `docker-compose.yml` — `lavalink-primary` with WARP via `JAVA_TOOL_OPTIONS` SOCKS5 on **node**
- `infra/audio/lavalink_nodes.py` — `LAVALINK_NODES` JSON cluster
- `tiffany_voice.py` — connects `wavelink.Pool` to all nodes
- Volume embed UX — `locales/*/volume.json` + `build_volume_embed()`

**Next:**
- Set `SPOTIFY_CLIENT_ID/SECRET` in `.env` for LavaSrc Spotify
- Uncomment `lavalink-secondary` on port 2334 + second `LAVALINK_NODES` entry
- Route platform URLs through Lavalink search (reduce yt-dlp on VPS)
- Audius/Bandcamp: enable LavaSrc sources or keep oEmbed → search fallback

## 2. HA 99.999% 📋 documented

**Done:** `docs/ha-architecture.md`

**Next:** PostgreSQL + Redis on managed services; K8s when guilds >2.5k

## 3. i18n ✅ foundation

**Done:**
- 13 languages in `GuildLang` + `/language` select
- `locales/{lang}/*.json` namespaced catalog
- `tr()` checks JSON → `_STRINGS` fallback
- `infra/i18n_loader.lookup_db()` stub for PG overlay

**Next:**
- Migrate `locale_utils._STRINGS` keys to JSON files incrementally
- Import JSON → `i18n_strings` table for CMS-style edits without deploy
- RTL layout note for Arabic embeds (Discord handles rendering)

## 4. Automod ✅ foundation

**Done:**
- `infra/moderation/rules.py` — L1 regex
- `infra/moderation/pipeline.py` — L2 Redis flood
- `infra/moderation/safe_browsing.py` — Google Safe Browsing + Redis cache
- `moderation_auto.py` — wired to pipeline + L3 AI

**Next:**
- Set `GOOGLE_SAFE_BROWSING_API_KEY`
- Attachment NSFW scan (async queue)
- Log to `automod_events` table when `DATABASE_URL` set

## 5. Giveaways / Embed 📋 schema ready

**Done:** `schema/001_initial.sql` tables `giveaways`, `giveaway_entries`, `embed_templates`

**Next:**
- `infra/repositories/giveaways.py` — dual-write JSON + PG migration
- Rio-style embed UI: dropdown for color, modal for fields (extend `embed_builder_cog.py`)
- Persistent views reload from PG on `on_ready`

## 6. Premium ✅ foundation

**Done:**
- `subscriptions`, `guild_features`, `user_cosmetics` tables
- `infra/premium.py` — `get_entitlement()`, Redis 5min cache, `@requires_premium`
- `handle_discord_subscription_event()` for webhooks

**Next:**
- HTTP endpoint for Discord Entitlements webhook (separate aiohttp sidecar or K8s ingress)
- `/premium` slash command + upsell embed
- Wire premium limits: queue size, embed count, AI quota

## Environment checklist

```bash
# Minimum for new infra features
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
LAVALINK_ENABLED=1
LAVALINK_NODES=[{"uri":"http://127.0.0.1:2333","identifier":"primary"}]
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
GOOGLE_SAFE_BROWSING_API_KEY=...
```

## VPS quick start (audio cluster)

```bash
bash scripts/warp-setup.sh
bash scripts/start-lavalink.sh
# .env: LAVALINK_ENABLED=1
systemctl restart tiffany-bot
journalctl -u tiffany-bot -n 30 | grep -i lavalink
```
