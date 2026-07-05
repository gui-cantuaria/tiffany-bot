# Game Recommendations Technical Reference

Detailed reference for `t!g` / `t!game` and `game_recommendations.py`. Read this before changing filter parsing, store validation, embed layout, or rate limits.

## Command surface

| Alias | Handler | Module |
|---|---|---|
| `t!g`, `t!game`, `t!games` | `cmd_game` | `tiffany_voice.py` |
| Voice: *"Tiffany, recomenda jogos …"* | `_parse_voice_command` → `game` action | `tiffany_voice.py` |

Guild-only. Registered in `_COMMAND_REGISTRY`, normalized in `notices.py` `_CMD_NAMES` (`g`, `game`, `games`).

User-facing output is **Portuguese (BR)** by default; `/help` and `/about` strings for `t!g` are localized via `locale_utils.py` (`pt` / `en` / `es`). Command replies and embed body use `tr(resolve_guild_lang(guild), …)` where implemented.

## Hybrid pipeline (AI + store validation)

The command uses a **hybrid** flow: AI interprets natural language and proposes titles; **store APIs** confirm that each title exists and matches hard filters (price in BRL, store, free-only, etc.). Hallucinated or mismatched games are dropped before the embed is sent.

```
User query (text or voice)
  │
  ├─ Content block (_contains_blocked_content / _should_block_content on query + names)
  ├─ Per-command rate limit (_check_cmd_rate_limit, key "g")
  ├─ Per-user AI cooldown (_check_cooldown — separate window from t!c when configured)
  ├─ Global/server AI budget (_ai_rate_limit_peek / _ai_rate_limit_consume)
  │
  ▼
recommend_games(query, openrouter_client)          [game_recommendations.py]
  │
  ├─ 1. Primary: single OpenRouter call (google/gemini-3.1-flash-lite)
  │      System: _RECOMMEND_SYSTEM + _AI_FILTER_SCHEMA
  │      Returns JSON → GameFilters + games[] (official titles only, 3–5 names)
  │
  └─ 2. Fallback on JSON/parse failure:
         _regex_parse_filters(query) → suggest_game_names() (second AI call)
  │
  ▼
validate_suggested_games(names, filters)             [game_recommendations.py]
  │
  ├─ _verify_ai_names: for each AI title → _steam_search_name → appdetails (cc=br)
  ├─ search_steam_catalog: storesearch term from filters → parallel appdetails
  ├─ search_epic_catalog: Epic browse __NEXT_DATA__ (pt-BR / country=BR)
  ├─ _price_ok_brl / _genre_ok / _multiplayer_ok filter each candidate
  └─ _merge_matches(verified, catalog) — dedupe by normalized title, cap MAX_RESULTS
  │
  ▼
GameMatch list → embed (name, store, price_label, optional url)
  │
  ▼
_build_game_recommendations_embed(matches, filters)  [tiffany_voice.py]
  └─ Pink embed (_embed / TIFFANY_PINK), filters_summary() + numbered list
  │
  ▼
Persist last request per user → game_history.json
```

**Why hybrid:** Pure AI can invent games or wrong prices. Store lookup is the source of truth for existence and BRL price; AI handles messy natural-language filters (studio, tags, “sem battle royale”, etc.).

**Return type:** `recommend_games()` → `(list[GameMatch], GameFilters, error_key | None)`. Each `GameMatch` has `name`, `store`, `price_label`, `url`.

**Catalog fallback:** If AI names fail verification, `search_steam_catalog` / `search_epic_catalog` still run from filter-derived search terms (`_search_term`).

**AI model:** `google/gemini-3.1-flash-lite` via OpenRouter only — no fallback model chain (project rule).

## Store APIs

| Store | Endpoints | Region |
|---|---|---|
| Steam | `storesearch` + `appdetails` | `cc=br`, `l=portuguese` |
| Epic | `store.epicgames.com/pt-BR/browse` + `__NEXT_DATA__` | `country=BR` |

Steam detail fetch uses `STEAM_DETAIL_CONCURRENCY` (6) semaphore. Epic walks JSON tree for product nodes with slug + price.

## Filter schema (`GameFilters` / AI JSON)

Parsed by `_filters_from_json()` after AI response; regex fallback via `_regex_parse_filters()` (stores, price, rating, developer, core genres, free/multiplayer/single-player, PT — **not** release year or Steam review tier; those need AI JSON).

| Field | Type | Notes |
|---|---|---|
| `stores` | `["steam"]`, `["epic"]`, or both | Default both if omitted. Invalid values stripped. |
| `max_price_brl` | float \| null | e.g. "até 10 reais" |
| `min_price_brl` | float \| null | e.g. "a partir de 20" |
| `free_only` | bool | "grátis", "free" |
| `multiplayer` | bool | multiplayer, co-op, online |
| `single_player` | bool | solo, single-player |
| `genres` | string[] | terror, rpg, fps, … (max 8) |
| `tags` | string[] | roguelike, souls-like, pixel art, … |
| `developers` | string[] | studio names |
| `publishers` | string[] | publisher names |
| `min_rating` | float \| null | Metacritic/Steam/OpenCritic threshold |
| `rating_source` | `steam` \| `metacritic` \| `opencritic` \| null | |
| `min_steam_reviews` | `positive` \| `very_positive` \| `overwhelmingly_positive` \| null | |
| `min_release_year` | int \| null | |
| `max_release_year` | int \| null | |
| `language_pt` | bool | PT-BR audio/subtitles |
| `exclude` | string[] | negative constraints |
| `extra` | string \| null | niche constraints; shown in embed only if short |
| `games` | string[] | AI output: official titles only, no price/URL |

Embed filter block is built by `filters_summary()` (PT-BR bullet list). Keep embed layout stable unless explicitly authorized.

## Rate limits

All limits are in-memory (no JSON persistence). Applied in `cmd_game` before any OpenRouter call.

| Layer | Constant | Value | Scope |
|---|---|---|---|
| Per-command spam | `_CMD_RL_DEFAULT` | **1.5 s** | Per user, command key `"g"` (not in `_CMD_COOLDOWN_MAP`) |
| AI command cooldown | `_CMD_COOLDOWN_SEC` | **8 s** | Minimum gap between AI commands per user |
| AI abuse window | `_USER_RL_WINDOW` / `_USER_RL_MAX` | **60 s / 3 calls** | Then `_USER_RL_BLOCK_SEC` = **40 s** block |
| Global AI | `_GLOBAL_RL_WINDOW` / `_GLOBAL_RL_MAX` | **60 s / 15** | All AI features |
| Server AI | `_SERVER_RL_MAX` | **5 / 60 s** | Per guild |

`t!g` consumes **one** server+global AI slot on the successful path (`_ai_rate_limit_consume`). Store validation HTTP calls do not count toward the AI budget.

Voice game requests use the same limits when dispatched from the voice loop.

## `game_history.json`

Runtime state beside the bot root (same directory as `chat_memory.json`). **Not committed** — preserve on VPS deploy/migration.

```json
{
  "123456789012345678": {
    "query": "terror multiplayer até 10 reais steam",
    "filters": { "stores": ["steam"], "max_price_brl": 10.0, "multiplayer": true, "genres": ["terror"] },
    "games": ["Game A", "Game B"],
    "ts": 1717612800.0
  }
}
```

- Key: Discord user id (string).
- Updated after each successful recommendation (validated list non-empty).
- Used for optional “repeat last search” / debugging; trim old entries periodically if file grows (e.g. keep last N users or 30-day TTL in code).
- **Backup:** include in VPS migration (`scp *.json`) — see `docs/deploy-automation.md` → Runtime JSON state.

## Voice phrase

Wake word + game intent in `_parse_voice_command()`:

| Pattern (after wake) | Action | Argument |
|---|---|---|
| `recomenda jogos …`, `recomenda um jogo …`, `sugere jogos …` | `game` | remainder of utterance (filters) |
| EN: `recommend games …`, `suggest a game …` | `game` | same |

Dispatched like text `t!g`: same rate limits, hybrid pipeline, embed posted to `session.text_channel_id`. Music may pause briefly while processing (same as voice questions).

STT env vars: `STT_OPENROUTER_MODEL`, `STT_CHAT_MODEL`, optional `DEBUG_STT=1` — see `docs/voice-technical.md`.

## Internationalization (i18n)

| Surface | Mechanism |
|---|---|
| `/help`, `/about` | `locale_utils._STRINGS` — `help.chat.body` includes `t!g` in pt/en/es |
| Command usage / errors / embed | `tr(lang, "game.*")` keys in `locale_utils.py` |
| AI prompts | English (`_RECOMMEND_SYSTEM`); output game **names** stay official (usually EN) |
| `filters_summary()` | PT-BR only (filter labels); guild lang does not translate genre tokens from user query |

Guild language: `resolve_guild_lang(guild)` from `discord.Locale` / `preferred_locale` prefix (`pt`, `en`, `es`).

## Content safety

- Query and each suggested name: `_contains_blocked_content` (fast) + `_should_block_content` (AI moderation) before embed.
- Blocked queries get `_pick_blocked_reply()`; blocked names removed from list.

## Embed layout (do not change without authorization)

1. **Description:** `🎮 **Recomendações**` → **Filtros** (`filters_summary`) → **Jogos** (numbered bold titles).
2. **Color:** `TIFFANY_PINK` via `_embed()`.
3. **Footer:** remind user to verify price/availability on the store (localized).

Optional markdown links on titles (Steam/Epic URLs) must stay compact — no price/description blocks in embed.

## Files

| File | Role |
|---|---|
| `game_recommendations.py` | Filters, AI prompts, regex fallback, store validation |
| `tiffany_voice.py` | `cmd_game`, embed builder, voice dispatch, rate limits |
| `locale_utils.py` | Help/about + `game.*` strings |
| `notices.py` | `t!game` command normalization |
| `game_history.json` | Per-user last recommendation (runtime) |

## Testing

- `test_game_recommendations.py` — unit tests for `_regex_parse_filters` (no network, no `.env`).
- Run locally: `py -3 test_game_recommendations.py`
- CI: `.github/workflows/test.yml`
