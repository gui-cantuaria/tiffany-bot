# Rate limits reference

In-memory limits only (reset on bot restart). User-facing messages are localized via `locale_utils.tr()`.

## Command spam (`t!*` prefix)

| Layer | Where | Default | Scope |
|---|---|---|---|
| Global `@bot.check` | `_check_cmd_rate_limit` | **1.0 s** default | Per user, per command name |
| Per-command map | `_CMD_COOLDOWN_MAP` | e.g. `"g": 2.0`, `"c": 3.0` | Overrides default for hot commands |
| Exception | `TiffanyRateLimited` | Shows wait seconds | Raised before handler runs |

## AI budget (chat, summary, games, voice questions)

| Layer | Constants | Default | Notes |
|---|---|---|---|
| Per-user cooldown | `_CMD_COOLDOWN_SEC` | **8 s** | Gap between AI commands per user |
| User abuse window | `_USER_RL_WINDOW` / `_USER_RL_MAX` | **60 s / 3** | Then `_USER_RL_BLOCK_SEC` = **40 s** |
| Global | `_GLOBAL_RL_WINDOW` / `_GLOBAL_RL_MAX` | **60 s / 15** | All AI features |
| Per-server | `_SERVER_RL_MAX` | **5 / 60 s** | Per guild |
| Game bucket | `bucket="game"` | Same server/global slots | `t!g` only |
| DM users | `user_id` bucket | Same rules | When `guild_id=0` |

Peek before work: `_ai_rate_limit_peek()` · consume on success: `_ai_rate_limit_consume()`.

## Game command (`t!g`)

| Layer | Value | Notes |
|---|---|---|
| `_GAME_CMD_COOLDOWN_SEC` | **5 s** | Separate from generic AI cooldown message |
| Command check `"g"` | **2.0 s** in `_CMD_COOLDOWN_MAP` | Anti double-fire (do not duplicate in `cmd_game`) |

See also `docs/games-technical.md`.

## Dice (prefixless)

Uses command key `"d"` with the global check (default 1 s).

## Offers / news

No per-user Discord rate limits in Cog/news loop. Internal pacing:

- Offers: `POST_SPACING_SEC` between posts, `SCAN_INTERVAL_MIN` between cycles
- News: `IA_COOLDOWN_SEC` between OpenRouter calls, `MAX_POSTS_POR_CICLO` per feed cycle
