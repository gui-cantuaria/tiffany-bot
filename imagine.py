"""Text-to-image via OpenRouter Images API (cheap model for /imagine)."""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

import aiohttp

log = logging.getLogger("tiffany-bot")

OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL = "black-forest-labs/flux.2-klein-4b"
DEFAULT_ASPECT = "1:1"
MAX_PROMPT_LEN = 500
REQUEST_TIMEOUT_SEC = 120.0


def imagine_model() -> str:
    return (os.getenv("IMAGINE_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def imagine_aspect_ratio() -> str:
    return (os.getenv("IMAGINE_ASPECT_RATIO") or DEFAULT_ASPECT).strip() or DEFAULT_ASPECT


def sanitize_prompt(raw: str) -> str:
    """Trim and cap user prompt."""
    return " ".join((raw or "").split())[:MAX_PROMPT_LEN]


async def generate_image_bytes(prompt: str) -> tuple[Optional[bytes], Optional[str]]:
    """
    Generate one PNG/JPEG from a text prompt.
    Returns (image_bytes, error_key) — error_key is an i18n key under imagine.err.*
    """
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return None, "err.api_key"

    payload = {
        "model": imagine_model(),
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": imagine_aspect_ratio(),
        "output_format": "png",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gui-cantuaria/tiffany-bot",
        "X-Title": "Tiffany Bot",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OPENROUTER_IMAGES_URL, json=payload, headers=headers) as resp:
                if resp.status == 402:
                    return None, "imagine.err.no_credits"
                if resp.status == 429:
                    return None, "imagine.err.rate_limit"
                if resp.status >= 400:
                    body = await resp.text()
                    log.warning("Imagine API HTTP %s: %s", resp.status, body[:300])
                    return None, "imagine.err.failed"

                data = await resp.json()
    except aiohttp.ClientError as exc:
        log.warning("Imagine API network error: %s", exc)
        return None, "imagine.err.failed"
    except Exception:
        log.exception("Imagine API unexpected error")
        return None, "imagine.err.failed"

    items = data.get("data") or []
    if not items:
        log.warning("Imagine API empty data: %s", str(data)[:300])
        return None, "imagine.err.failed"

    item = items[0] if isinstance(items[0], dict) else {}
    b64 = item.get("b64_json")
    if b64:
        try:
            return base64.b64decode(b64), None
        except Exception:
            log.exception("Imagine b64 decode failed")
            return None, "imagine.err.failed"

    url = item.get("url")
    if url:
        try:
            timeout = aiohttp.ClientTimeout(total=60.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(str(url)) as img_resp:
                    if img_resp.status == 200:
                        return await img_resp.read(), None
        except Exception:
            log.exception("Imagine URL fetch failed")
            return None, "imagine.err.failed"

    return None, "imagine.err.failed"
