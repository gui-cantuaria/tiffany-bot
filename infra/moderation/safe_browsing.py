"""Google Safe Browsing API v4 — URL threat check with Redis cache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

import aiohttp

from infra import redis_client

log = logging.getLogger("tiffany-bot")

_API = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
_CACHE_TTL = 86400  # 24h


def _enabled() -> bool:
    return bool(os.getenv("GOOGLE_SAFE_BROWSING_API_KEY", "").strip())


async def check_urls(urls: list[str]) -> tuple[bool, str]:
    """
    Return (is_threat, reason). Empty list or disabled API → (False, "").
    Uses Redis cache per URL hash.
    """
    if not urls or not _enabled():
        return False, ""

    api_key = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY", "").strip()
    unchecked: list[str] = []
    for url in urls[:10]:
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        ck = f"gsb:{h}"
        cached = await redis_client.cache_get(ck)
        if cached == "1":
            return True, "Link flagged by Safe Browsing (phishing/malware)."
        if cached == "0":
            continue
        unchecked.append(url)

    if not unchecked:
        return False, ""

    body = {
        "client": {"clientId": "tiffany-bot", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": u} for u in unchecked],
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _API,
                params={"key": api_key},
                json=body,
                timeout=aiohttp.ClientTimeout(total=4),
            ) as resp:
                if resp.status != 200:
                    log.debug("Safe Browsing HTTP %s", resp.status)
                    return False, ""
                data = await resp.json()
    except Exception as e:
        log.debug("Safe Browsing request failed: %s", e)
        return False, ""

    matches = data.get("matches") or []
    matched_urls = {m.get("threat", {}).get("url") for m in matches if isinstance(m, dict)}

    for url in unchecked:
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        ck = f"gsb:{h}"
        if url in matched_urls or any(url.startswith(m or "") for m in matched_urls if m):
            await redis_client.cache_setex(ck, _CACHE_TTL, "1")
            return True, "Link perigoso bloqueado (Safe Browsing)."
        await redis_client.cache_setex(ck, _CACHE_TTL, "0")

    return False, ""
