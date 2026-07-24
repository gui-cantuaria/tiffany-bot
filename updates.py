"""Public changelog for /updates — user-facing content lives in updates.json (PT-BR)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

import discord

from locale_utils import resolve_lang, tr

log = logging.getLogger("tiffany-bot")

_UPDATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "updates.json")
_MAX_ENTRIES = 5
_MAX_ITEMS = 6
_CACHE: dict[str, Any] | None = None


def _load_raw() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not os.path.exists(_UPDATES_FILE):
        log.warning("updates.json not found — /updates will show empty state")
        _CACHE = {"version_label": "", "entries": []}
        return _CACHE
    try:
        with open(_UPDATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("root must be object")
        entries = data.get("entries")
        if not isinstance(entries, list):
            entries = []
        _CACHE = {
            "version_label": str(data.get("version_label") or "").strip(),
            "entries": entries,
        }
    except Exception as e:
        log.error("Failed to load updates.json: %s", e)
        _CACHE = {"version_label": "", "entries": []}
    return _CACHE


def reload_updates_cache() -> None:
    """Clear in-memory cache (tests or hot reload)."""
    global _CACHE
    _CACHE = None


def _fmt_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "?"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw[:10]


def _localized_field(entry: dict[str, Any], key: str, lang: str) -> str:
    """Read title/items from entry — supports plain string or {pt, en, ...} dict."""
    raw = entry.get(key)
    if isinstance(raw, dict):
        return str(raw.get(lang) or raw.get("pt") or raw.get("en") or "").strip()
    return str(raw or "").strip()


def _localized_items(entry: dict[str, Any], lang: str) -> list[str]:
    raw = entry.get("items") or entry.get("highlights") or []
    if isinstance(raw, dict):
        bucket = raw.get(lang) or raw.get("pt") or raw.get("en") or []
        if isinstance(bucket, list):
            return [str(x).strip() for x in bucket if str(x).strip()]
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def build_updates_embed(
    guild: Optional[discord.Guild],
    user_id: Optional[int],
    *,
    pink: int,
) -> discord.Embed:
    lang = resolve_lang(guild, user_id)
    data = _load_raw()
    version = data.get("version_label") or "—"
    entries: list[dict[str, Any]] = [
        e for e in data.get("entries", []) if isinstance(e, dict)
    ][: _MAX_ENTRIES]

    em = discord.Embed(
        title=tr(lang, "updates.title"),
        description=tr(lang, "updates.intro", version=version),
        color=pink,
    )

    if not entries:
        em.add_field(
            name=tr(lang, "updates.empty_title"),
            value=tr(lang, "updates.empty_body"),
            inline=False,
        )
        em.set_footer(text=tr(lang, "updates.footer"))
        return em

    for entry in entries:
        title = _localized_field(entry, "title", lang) or tr(lang, "updates.default_entry_title")
        when = _fmt_date(str(entry.get("date") or ""))
        bullets = _localized_items(entry, lang)[:_MAX_ITEMS]
        body = "\n".join(f"• {line}" for line in bullets) if bullets else "• …"
        em.add_field(
            name=f"📅 {when} · {title}"[:256],
            value=body[:1024],
            inline=False,
        )

    em.set_footer(text=tr(lang, "updates.footer"))
    return em
