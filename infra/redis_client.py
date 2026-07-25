"""Optional Redis — in-memory fallback when REDIS_URL is unset (local dev)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

log = logging.getLogger("tiffany-bot")

_redis: Any = None
_memory: dict[str, tuple[str, float]] = {}
_USE_MEMORY = True


async def init_redis() -> None:
    """Connect Redis if REDIS_URL is set."""
    global _redis, _USE_MEMORY
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        _USE_MEMORY = True
        log.info("REDIS_URL unset — using in-memory cache (not HA-safe)")
        return
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(url, decode_responses=True)
        await _redis.ping()
        _USE_MEMORY = False
        log.info("Redis connected")
    except Exception as e:
        log.warning("Redis unavailable (%s) — in-memory fallback", e)
        _redis = None
        _USE_MEMORY = True


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None


async def cache_get(key: str) -> Optional[str]:
    if _redis is not None:
        try:
            return await _redis.get(key)
        except Exception as e:
            log.debug("Redis GET failed: %s", e)
    entry = _memory.get(key)
    if entry and entry[1] > time.time():
        return entry[0]
    _memory.pop(key, None)
    return None


async def cache_setex(key: str, ttl_sec: int, value: str) -> None:
    if _redis is not None:
        try:
            await _redis.setex(key, ttl_sec, value)
            return
        except Exception as e:
            log.debug("Redis SETEX failed: %s", e)
    _memory[key] = (value, time.time() + ttl_sec)


async def cache_delete(key: str) -> None:
    if _redis is not None:
        try:
            await _redis.delete(key)
        except Exception:
            pass
    _memory.pop(key, None)


async def cache_incr(key: str, *, ttl_sec: int = 60) -> int:
    """Increment counter (flood/rate limit). Returns new value."""
    if _redis is not None:
        try:
            pipe = _redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_sec)
            results = await pipe.execute()
            return int(results[0])
        except Exception as e:
            log.debug("Redis INCR failed: %s", e)
    val = int((await cache_get(key)) or "0") + 1
    await cache_setex(key, ttl_sec, str(val))
    return val
