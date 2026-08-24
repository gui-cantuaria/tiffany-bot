"""
Tiffany OS — Concurrency Control & Cache Stampede Protection (Single-Flight)
=============================================================================
Implements Single-Flight promise de-duplication to prevent Thundering Herd attacks
and database pool starvation during massive Discord Gateway reconnection storms.
When N concurrent tasks request the same cache key simultaneously, only ONE task
executes the expensive database/API fetch; the other N-1 tasks await the shared result.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, TypeVar

log = logging.getLogger("tiffany.core.concurrency")

T = TypeVar("T")

class SingleFlightGroup:
    """
    Suppresses duplicate concurrent executions for identical lookup keys.
    Essential for protecting PostgreSQL and OpenRouter during shard reconnect storms.
    """
    def __init__(self) -> None:
        self._calls: Dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def execute(self, key: str, func: Callable[[], Coroutine[Any, Any, T]]) -> T:
        async with self._lock:
            if key in self._calls:
                log.debug("[SingleFlight] Coalescing duplicate execution for key: %s", key)
                future = self._calls[key]
                is_leader = False
            else:
                future = asyncio.Future()
                self._calls[key] = future
                is_leader = True

        if is_leader:
            try:
                result = await func()
                future.set_result(result)
                return result
            except Exception as exc:
                future.set_exception(exc)
                log.warning("[SingleFlight] Execution failed for key %s: %s", key, exc)
                raise
            finally:
                async with self._lock:
                    self._calls.pop(key, None)
                    
        # Fallback if leader status changed
        return await future


class TokenBucketRateLimiter:
    """
    High-precision async token bucket rate limiter to throttle API usage per guild/user,
    protecting downstream LLM quotas from DoS amplification and script abuse.
    """
    def __init__(self, rate_per_sec: float, capacity: int) -> None:
        self.rate = rate_per_sec
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens_needed: float = 1.0) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            
            # Replenish tokens based on elapsed time
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            
            if self.tokens >= tokens_needed:
                self.tokens -= tokens_needed
                return True
            log.warning("[RateLimiter] Bucket exhausted (available: %.2f, required: %.2f)", self.tokens, tokens_needed)
            return False

# Global single-flight coordinator for high-traffic read paths
stampede_protector = SingleFlightGroup()
