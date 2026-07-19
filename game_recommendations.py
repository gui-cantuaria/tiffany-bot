"""Game recommendations: AI filters + store-verified matches (Steam/Epic BRL)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote_plus

from locale_utils import GuildLang, tr

log = logging.getLogger("tiffany-bot")

STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/"
STEAM_DETAILS = "https://store.steampowered.com/api/appdetails"
EPIC_BROWSE = "https://store.epicgames.com/pt-BR/browse"

MAX_RESULTS = 5
STEAM_CANDIDATES = 20
STEAM_DETAIL_CONCURRENCY = 6
EXTRA_MAX_LEN = 80

MULTIPLAYER_HINTS = (
    "multijogador", "multi-player", "multiplayer", "co-op", "coop",
    "online co-op", "pvp", "mmorpg",
)
HORROR_HINTS = ("terror", "horror", "sobrevivência", "survival horror")
STEAM_MULTIPLAYER_CAT_IDS = {1, 9, 38, 39, 27, 36, 37}

_AI_FILTER_SCHEMA = """
{
  "stores": ["steam"] and/or ["epic"],
  "max_price_brl": number or null,
  "min_price_brl": number or null,
  "free_only": boolean,
  "multiplayer": boolean,
  "single_player": boolean,
  "genres": ["terror","rpg",...],
  "tags": ["roguelike",...],
  "developers": ["FromSoftware",...],
  "publishers": ["Valve",...],
  "min_rating": number or null,
  "rating_source": "steam" | "metacritic" | "opencritic" | null,
  "min_steam_reviews": "positive" | "very_positive" | "overwhelmingly_positive" | null,
  "min_release_year": number or null,
  "max_release_year": number or null,
  "language_pt": boolean,
  "exclude": ["battle royale",...],
  "extra": "short niche constraint or null",
  "games": ["Official Game Title 1", ...]
}
"""

_RECOMMEND_SYSTEM = (
    "You recommend real PC games sold on Steam and/or Epic Games Store.\n"
    "Extract filters and suggest candidate game titles from the user message.\n"
    f"Reply with ONLY valid JSON (no markdown). Schema:\n{_AI_FILTER_SCHEMA}\n\n"
    "Filter rules: default stores [\"steam\",\"epic\"]; price/grátis/multiplayer/genre/studio/rating/year/tags/exclude.\n"
    "Keep \"extra\" under 80 chars; omit if redundant with other fields.\n"
    f"Games: 3–{MAX_RESULTS} real titles in \"games\" — names ONLY, no price/URL.\n"
)


@dataclass
class GameFilters:
    stores: list[str] = field(default_factory=lambda: ["steam", "epic"])
    max_price_brl: Optional[float] = None
    min_price_brl: Optional[float] = None
    free_only: bool = False
    multiplayer: bool = False
    single_player: bool = False
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    developers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    min_rating: Optional[float] = None
    rating_source: Optional[str] = None
    min_steam_reviews: Optional[str] = None
    min_release_year: Optional[int] = None
    max_release_year: Optional[int] = None
    language_pt: bool = False
    exclude: list[str] = field(default_factory=list)
    extra: Optional[str] = None


@dataclass
class GameMatch:
    name: str
    store: str
    price_label: str
    url: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _as_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _as_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _str_list(val: Any, *, limit: int = 8) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        val = [val]
    out: list[str] = []
    for item in val:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _sanitize_extra(extra: Optional[str]) -> Optional[str]:
    if not extra:
        return None
    s = re.sub(r"\s+", " ", str(extra).strip())
    if len(s) > EXTRA_MAX_LEN:
        s = s[: EXTRA_MAX_LEN - 1].rstrip() + "…"
    return s or None


def _filters_from_json(data: dict) -> GameFilters:
    stores = [s.lower() for s in _str_list(data.get("stores")) if s.lower() in ("steam", "epic")]
    if not stores:
        stores = ["steam", "epic"]

    steam_reviews = data.get("min_steam_reviews")
    if steam_reviews:
        steam_reviews = str(steam_reviews).strip().lower().replace(" ", "_")
        if steam_reviews not in ("positive", "very_positive", "overwhelmingly_positive"):
            steam_reviews = None

    rating_source = data.get("rating_source")
    if rating_source:
        rating_source = str(rating_source).strip().lower()
        if rating_source not in ("steam", "metacritic", "opencritic"):
            rating_source = None

    return GameFilters(
        stores=stores,
        max_price_brl=_as_float(data.get("max_price_brl")),
        min_price_brl=_as_float(data.get("min_price_brl")),
        free_only=bool(data.get("free_only")),
        multiplayer=bool(data.get("multiplayer")),
        single_player=bool(data.get("single_player")),
        genres=_str_list(data.get("genres")),
        tags=_str_list(data.get("tags")),
        developers=_str_list(data.get("developers")),
        publishers=_str_list(data.get("publishers")),
        min_rating=_as_float(data.get("min_rating")),
        rating_source=rating_source,
        min_steam_reviews=steam_reviews,
        min_release_year=_as_int(data.get("min_release_year")),
        max_release_year=_as_int(data.get("max_release_year")),
        language_pt=bool(data.get("language_pt")),
        exclude=_str_list(data.get("exclude")),
        extra=_sanitize_extra(data.get("extra")),
    )


def _clean_game_name(raw: str) -> str:
    name = str(raw).strip()
    if not name:
        return ""
    name = re.split(r"\s*[-–—|]\s*(?:R\$|Steam|Epic|Grátis|Free|Metacritic)", name, maxsplit=1)[0].strip()
    return re.sub(r"\s*\([^)]*(?:R\$|Steam|Epic)[^)]*\)\s*$", "", name).strip()


def _parse_game_names(data: dict) -> list[str]:
    names: list[str] = []
    for item in data.get("games") or []:
        name = _clean_game_name(str(item))
        if name and name not in names:
            names.append(name)
        if len(names) >= MAX_RESULTS * 2:
            break
    return names


def _regex_parse_filters(text: str) -> GameFilters:
    low = _norm(text)
    stores: list[str] = []
    if re.search(r"\bsteam\b", low):
        stores.append("steam")
    if re.search(r"\bepic\b", low):
        stores.append("epic")
    if not stores:
        stores = ["steam", "epic"]

    max_price = None
    m = re.search(
        r"(?:at[eé]|ate|m[aá]ximo|max|under|below|at[eé]\s+)?\s*"
        r"r?\$?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:reais?|brl|real)?",
        low,
    )
    if m:
        max_price = float(m.group(1).replace(",", "."))

    min_rating = None
    rm = re.search(
        r"(?:nota|avalia[cç][aã]o|rating|metacritic|steam)\s*(?:m[ií]n(?:ima)?\.?|de)?\s*(\d{1,3})",
        low,
    )
    if rm:
        min_rating = float(rm.group(1))

    developers: list[str] = []
    dm = re.search(
        r"(?:est[uú]dio|studio|developer|dev(?:eloper)?\.?)\s+([a-z0-9][a-z0-9\s&.-]{2,40})",
        low,
        re.IGNORECASE,
    )
    if dm:
        developers.append(dm.group(1).strip().title())

    genres: list[str] = []
    for g in ("terror", "horror", "ação", "action", "rpg", "fps", "indie"):
        if g in low:
            genres.append(g)

    return GameFilters(
        stores=stores,
        max_price_brl=max_price,
        free_only=bool(re.search(r"\b(gr[aá]tis|free|de\s+gra[cç]a)\b", low)),
        multiplayer=bool(re.search(r"\b(multiplayer|multijogador|co-?op|coop|online)\b", low)),
        single_player=bool(re.search(r"\b(single[\s-]?player|singleplayer|solo)\b", low)),
        genres=genres,
        developers=developers,
        min_rating=min_rating,
        language_pt=bool(re.search(r"\b(pt[\s-]?br|portugu[eê]s|legendad[oa]|dublad[oa])\b", low)),
    )


def _search_term(filters: GameFilters) -> str:
    # Do NOT include genres or multiplayer in the Steam search term!
    # Steam storesearch uses this for exact name matching.
    parts: list[str] = []
    parts.extend(filters.developers[:2])
    parts.extend(filters.tags[:2])
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        k = _norm(p)
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return " ".join(out[:4]) or "games"


def _price_ok_brl(is_free: bool, price_cents: Optional[int], filters: GameFilters) -> bool:
    if filters.free_only:
        return is_free
    if is_free and filters.max_price_brl is not None:
        return True
    if price_cents is None:
        return filters.max_price_brl is None and not filters.free_only
    price = price_cents / 100.0
    if filters.min_price_brl is not None and price < filters.min_price_brl - 0.01:
        return False
    if filters.max_price_brl is not None and price > filters.max_price_brl + 0.01:
        return False
    return True


def _genre_ok(
    genres: list[str],
    tags: list[str],
    filters: GameFilters,
    *,
    title: str = "",
) -> bool:
    if not filters.genres:
        return True
    hay = _norm(" ".join(genres + tags))
    title_n = _norm(title)
    for g in filters.genres:
        gn = _norm(g)
        if gn in hay or (gn in ("terror", "horror") and any(h in hay for h in HORROR_HINTS)):
            return True
        # Steam often omits Horror/Terror genre tags — match title when user asked horror.
        if gn in ("terror", "horror") and any(h in title_n for h in HORROR_HINTS):
            return True
        if gn in title_n:
            return True
    return False


def _multiplayer_ok(categories: list[dict], tags: list[str], filters: GameFilters) -> bool:
    if not filters.multiplayer:
        return True
    for c in categories:
        if c.get("id") in STEAM_MULTIPLAYER_CAT_IDS:
            return True
        if any(h in _norm(c.get("description", "")) for h in MULTIPLAYER_HINTS):
            return True
    return any(h in _norm(" ".join(tags)) for h in MULTIPLAYER_HINTS)


def _single_player_ok(categories: list[dict], filters: GameFilters) -> bool:
    if not filters.single_player:
        return True
    for c in categories:
        if c.get("id") == 2 or "single" in _norm(c.get("description", "")):
            return True
    return True


def _developer_ok(detail: dict, filters: GameFilters) -> bool:
    if not filters.developers:
        return True
    devs = detail.get("developers") or []
    pubs = detail.get("publishers") or []
    hay = _norm(" ".join(devs + pubs))
    return any(_norm(d) in hay for d in filters.developers)


def _format_brl(cents: int) -> str:
    return f"R$ {cents / 100:.2f}".replace(".", ",")


async def _steam_app_details(session, app_id: int) -> Optional[dict]:
    import aiohttp

    params = {
        "appids": str(app_id),
        "cc": "br",
        "l": "portuguese",
        "filters": "basic,price_overview,categories,genres",
    }
    try:
        async with session.get(
            STEAM_DETAILS, params=params, timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json(content_type=None)
    except Exception:
        return None
    entry = payload.get(str(app_id)) or {}
    if not entry.get("success"):
        return None
    data = entry.get("data") or {}
    if data.get("type") and data.get("type") != "game":
        return None
    return data


def _steam_to_match(detail: dict, app_id: int, filters: GameFilters) -> Optional[GameMatch]:
    is_free = bool(detail.get("is_free"))
    po = detail.get("price_overview") or {}
    cents = 0 if is_free else po.get("final")
    if not _price_ok_brl(is_free, cents, filters):
        return None
    genres = [g.get("description", "") for g in (detail.get("genres") or []) if g.get("description")]
    categories = detail.get("categories") or []
    tags = [c.get("description", "") for c in categories if c.get("description")]
    name = detail.get("name") or f"App {app_id}"
    if not _genre_ok(genres, tags, filters, title=name):
        return None
    if not _multiplayer_ok(categories, tags, filters):
        return None
    if not _single_player_ok(categories, filters):
        return None
    if not _developer_ok(detail, filters):
        return None
    if is_free:
        price_label = "Grátis"
    elif po.get("final_formatted"):
        price_label = po["final_formatted"]
    elif cents is not None:
        price_label = _format_brl(int(cents))
    else:
        price_label = "—"
    return GameMatch(
        name=name,
        store="Steam",
        price_label=price_label,
        url=f"https://store.steampowered.com/app/{app_id}/",
    )


async def _steam_search_name(session, name: str, filters: GameFilters) -> Optional[GameMatch]:
    import aiohttp

    params = {"term": name[:80], "cc": "br", "l": "portuguese", "f": "games", "maxresults": 8}
    try:
        async with session.get(
            STEAM_SEARCH, params=params, timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
    except Exception:
        return None
    target = _norm(name)
    for item in data.get("items") or []:
        if _norm(item.get("name", "")) != target and target not in _norm(item.get("name", "")):
            continue
        app_id = item.get("id")
        if not app_id:
            continue
        detail = await _steam_app_details(session, int(app_id))
        if detail:
            match = _steam_to_match(detail, int(app_id), filters)
            if match:
                return match
    return None


async def search_steam_catalog(session, filters: GameFilters) -> list[GameMatch]:
    import aiohttp

    term = _search_term(filters)
    params = {"term": term, "cc": "br", "l": "portuguese", "f": "games", "maxresults": STEAM_CANDIDATES}
    try:
        async with session.get(
            STEAM_SEARCH, params=params, timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
    except Exception:
        return []

    app_ids = [int(i["id"]) for i in (data.get("items") or []) if i.get("id")]
    sem = asyncio.Semaphore(STEAM_DETAIL_CONCURRENCY)

    async def _fetch(aid: int) -> Optional[GameMatch]:
        async with sem:
            detail = await _steam_app_details(session, aid)
        if not detail:
            return None
        return _steam_to_match(detail, aid, filters)

    results = await asyncio.gather(*[_fetch(aid) for aid in app_ids])
    return [r for r in results if r]


def _epic_price(offer: dict) -> tuple[bool, Optional[int], str]:
    price = offer.get("price") or {}
    total = price.get("totalPrice") or price
    if isinstance(total, dict):
        fmt = total.get("fmtPrice") or {}
        if fmt.get("originalPrice") == "Free":
            return True, 0, "Grátis"
        disc = total.get("discountPrice")
        orig = total.get("originalPrice") or disc
        if disc is not None:
            c = int(disc)
            label = fmt.get("discountPrice") or fmt.get("originalPrice") or _format_brl(c)
            return c == 0, c, str(label)
    return False, None, "—"


def _epic_to_match(node: dict, filters: GameFilters) -> Optional[GameMatch]:
    title = node.get("title") or node.get("name")
    slug = node.get("urlSlug") or node.get("productSlug")
    if not title or not slug:
        return None
    is_free, cents, price_label = _epic_price(node)
    if not _price_ok_brl(is_free, cents, filters):
        return None
    tags_raw = node.get("tags") or node.get("offerTags") or []
    tags = [str(t.get("name") if isinstance(t, dict) else t) for t in tags_raw]
    if not _genre_ok([], tags, filters, title=str(title)):
        return None
    if not _multiplayer_ok([], tags, filters):
        return None
    return GameMatch(
        name=str(title),
        store="Epic",
        price_label=price_label,
        url=f"https://store.epicgames.com/pt-BR/p/{slug}",
    )


async def search_epic_catalog(session, filters: GameFilters) -> list[GameMatch]:
    import aiohttp

    term = _search_term(filters)
    url = f"{EPIC_BROWSE}?q={quote_plus(term)}&sortBy=relevancy&count=80&country=BR"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR,pt;q=0.9"}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=14)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text(errors="replace")
    except Exception:
        return []
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    nodes: list[dict] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("title") and (obj.get("urlSlug") or obj.get("productSlug")):
                nodes.append(obj)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    out: list[GameMatch] = []
    seen: set[str] = set()
    for node in nodes:
        match = _epic_to_match(node, filters)
        if not match:
            continue
        key = _norm(match.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(match)
    return out


async def _verify_ai_names(
    session,
    names: list[str],
    filters: GameFilters,
) -> list[GameMatch]:
    out: list[GameMatch] = []
    seen: set[str] = set()
    if "steam" in filters.stores:
        for name in names:
            match = await _steam_search_name(session, name, filters)
            if match and _norm(match.name) not in seen:
                seen.add(_norm(match.name))
                out.append(match)
            if len(out) >= MAX_RESULTS:
                return out
    return out


def _merge_matches(*groups: list[GameMatch]) -> list[GameMatch]:
    seen: set[str] = set()
    out: list[GameMatch] = []
    for group in groups:
        for m in group:
            key = _norm(m.name)
            if key in seen:
                continue
            seen.add(key)
            out.append(m)
            if len(out) >= MAX_RESULTS:
                return out
    return out


async def _ai_parse(query: str, ai_client) -> tuple[GameFilters, list[str]]:
    resp = await ai_client.chat.completions.create(
        model="google/gemini-3.1-flash-lite",
        messages=[
            {"role": "system", "content": _RECOMMEND_SYSTEM},
            {"role": "user", "content": query[:600]},
        ],
        max_tokens=420,
        temperature=0.25,
        timeout=25.0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    data = json.loads(raw)
    return _filters_from_json(data), _parse_game_names(data)


async def recommend_games(
    query: str,
    ai_client,
) -> tuple[list[GameMatch], GameFilters, Optional[str]]:
    """Return (verified matches, filters, error_message)."""
    try:
        import aiohttp
    except ImportError:
        return [], GameFilters(), "aiohttp_missing"

    if ai_client is None:
        return [], GameFilters(), "api_unavailable"

    try:
        filters, ai_names = await _ai_parse(query, ai_client)
    except Exception as e:
        err_str = str(e).lower()
        if "402" in err_str or "insufficient" in err_str or "quota" in err_str or "balance" in err_str:
            return [], GameFilters(), "api_issue"
        log.debug("Game AI parse failed, regex fallback", exc_info=True)
        filters = _regex_parse_filters(query)
        ai_names = []

    async with aiohttp.ClientSession() as session:
        verified = await _verify_ai_names(session, ai_names, filters) if ai_names else []
        catalog: list[GameMatch] = []
        tasks = []
        if "steam" in filters.stores:
            tasks.append(search_steam_catalog(session, filters))
        if "epic" in filters.stores:
            tasks.append(search_epic_catalog(session, filters))
        if tasks:
            chunks = await asyncio.gather(*tasks)
            for chunk in chunks:
                catalog.extend(chunk)
        matches = _merge_matches(verified, catalog)

    return matches, filters, None


def filters_summary(filters: GameFilters, lang: GuildLang = "pt") -> str:
    """User-facing filter list for the pink embed."""
    lines: list[str] = []
    stores = " · ".join(s.title() for s in filters.stores) or "Steam · Epic"
    lines.append(f"• **{tr(lang, 'game.filter.stores')}:** {stores}")

    if filters.free_only:
        lines.append(f"• **{tr(lang, 'game.filter.price')}:** {tr(lang, 'game.filter.free')}")
    else:
        if filters.min_price_brl is not None and filters.max_price_brl is not None:
            lines.append(
                f"• **{tr(lang, 'game.filter.price')}:** "
                f"R$ {filters.min_price_brl:.2f} – R$ {filters.max_price_brl:.2f}".replace(".", ",")
            )
        elif filters.max_price_brl is not None:
            lines.append(
                f"• **{tr(lang, 'game.filter.price')}:** "
                f"{tr(lang, 'game.filter.up_to')} R$ {filters.max_price_brl:.2f}".replace(".", ",")
            )
        elif filters.min_price_brl is not None:
            lines.append(
                f"• **{tr(lang, 'game.filter.price')}:** "
                f"{tr(lang, 'game.filter.from')} R$ {filters.min_price_brl:.2f}".replace(".", ",")
            )

    if filters.genres:
        lines.append(f"• **{tr(lang, 'game.filter.genre')}:** {', '.join(filters.genres)}")
    if filters.tags:
        lines.append(f"• **{tr(lang, 'game.filter.tags')}:** {', '.join(filters.tags)}")
    if filters.multiplayer:
        lines.append(f"• **{tr(lang, 'game.filter.multiplayer')}:** {tr(lang, 'game.filter.yes')}")
    if filters.single_player:
        lines.append(f"• **{tr(lang, 'game.filter.singleplayer')}:** {tr(lang, 'game.filter.yes')}")
    if filters.developers:
        lines.append(f"• **{tr(lang, 'game.filter.studio')}:** {', '.join(filters.developers)}")
    if filters.publishers:
        lines.append(f"• **{tr(lang, 'game.filter.publisher')}:** {', '.join(filters.publishers)}")
    if filters.min_rating is not None:
        src_key = filters.rating_source or "any"
        src = tr(lang, f"game.filter.rating.{src_key}")
        lines.append(f"• **{tr(lang, 'game.filter.rating')} ({src}):** {filters.min_rating:g}+")
    if filters.min_steam_reviews:
        lines.append(
            f"• **{tr(lang, 'game.filter.steam_reviews')}:** "
            f"{tr(lang, f'game.filter.reviews.{filters.min_steam_reviews}')}"
        )
    if filters.min_release_year is not None or filters.max_release_year is not None:
        y0 = filters.min_release_year or "…"
        y1 = filters.max_release_year or "…"
        if filters.min_release_year and filters.max_release_year:
            lines.append(f"• **{tr(lang, 'game.filter.year')}:** {y0}–{y1}")
        elif filters.min_release_year:
            lines.append(f"• **{tr(lang, 'game.filter.year_from')}:** {y0}")
        else:
            lines.append(f"• **{tr(lang, 'game.filter.year_to')}:** {y1}")
    if filters.language_pt:
        lines.append(f"• **{tr(lang, 'game.filter.language')}:** {tr(lang, 'game.filter.language_pt')}")
    if filters.exclude:
        lines.append(f"• **{tr(lang, 'game.filter.exclude')}:** {', '.join(filters.exclude)}")
    if filters.extra:
        lines.append(f"• **{tr(lang, 'game.filter.extra')}:** {filters.extra}")
    return "\n".join(lines)
