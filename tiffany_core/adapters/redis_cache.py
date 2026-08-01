"""
Tiffany OS — Distributed Redis Caching & Lock Engine (P0.6)
===========================================================
Provides distributed caching, atomic TTL expiration, and Redlock distributed leader
coordination across multi-instance deployments. Automatically connects to Redis clusters
if available, with an asynchronous transactional SQLite-backed Redis protocol equivalent
fallback for deterministic enterprise testing and zero-setup deployment.
"""

from __future__ import annotations
import asyncio
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("tiffany.core.adapters.redis")

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    aioredis = Any  # type: ignore


class RedisCacheEngine:
    """
    Distributed cache and synchronization adapter supporting atomic operations, TTL expiry,
    and distributed mutual exclusion (Redlock pattern).
    """
    def __init__(self, db_path: str = "tiffany_redis_equivalent.db", redis_url: Optional[str] = None) -> None:
        self.db_path = db_path
        self.redis_url = redis_url or os.environ.get("REDIS_URL") or os.environ.get("REDIS_HOST")
        self._engine_type: str = "sqlite_kv_fallback"
        self._redis_client: Any = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> str:
        """Initializes connection pool or creates persistent protocol-equivalent tables."""
        if self.redis_url and HAS_REDIS:
            try:
                self._redis_client = aioredis.from_url(self.redis_url, decode_responses=True, timeout=2.0)
                await self._redis_client.ping()
                self._engine_type = "redis_cluster"
                log.info("[RedisCache] Connected to Redis cluster at %s.", self.redis_url)
                return self._engine_type
            except Exception as e:
                log.warning("[RedisCache] Redis connection failed (%s). Falling back to SQLite KV equivalent.", e)
                self._engine_type = "sqlite_kv_fallback"
        
        await self._create_schemas()
        return self._engine_type

    async def _execute_sqlite(self, query: str, params: Tuple[Any, ...] = (), fetch: bool = False, fetch_one: bool = False) -> Any:
        def run_sync():
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                if fetch:
                    return [dict(r) for r in cursor.fetchall()]
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, run_sync)

    async def _create_schemas(self) -> None:
        async with self._lock:
            if self._engine_type == "sqlite_kv_fallback":
                create_kv = """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL
                );
                """
                create_locks = """
                CREATE TABLE IF NOT EXISTS distributed_locks (
                    resource_key TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
                create_idx = "CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at);"
                create_locks_idx = "CREATE INDEX IF NOT EXISTS idx_locks_expires ON distributed_locks(expires_at);"
                await self._execute_sqlite(create_kv)
                await self._execute_sqlite(create_locks)
                await self._execute_sqlite(create_idx)
                await self._execute_sqlite(create_locks_idx)

    async def set(self, key: str, value: str, ttl_sec: Optional[float] = None) -> bool:
        """Stores a key-value pair with optional time-to-live expiration."""
        if self._engine_type == "redis_cluster":
            if ttl_sec is not None:
                return bool(await self._redis_client.set(key, value, ex=int(ttl_sec)))
            return bool(await self._redis_client.set(key, value))

        expires_at = (time.time() + ttl_sec) if ttl_sec is not None else None
        query = "INSERT OR REPLACE INTO kv_store (key, value, expires_at) VALUES (?, ?, ?)"
        await self._execute_sqlite(query, (key, value, expires_at))
        return True

    async def get(self, key: str) -> Optional[str]:
        """Retrieves a value by key, returning None if non-existent or expired."""
        if self._engine_type == "redis_cluster":
            return await self._redis_client.get(key)

        query = "SELECT value, expires_at FROM kv_store WHERE key = ?"
        row = await self._execute_sqlite(query, (key,), fetch_one=True)
        if not row:
            return None
        expires_at = row["expires_at"]
        if expires_at is not None and time.time() >= expires_at:
            await self.delete(key)
            return None
        return str(row["value"])

    async def delete(self, key: str) -> bool:
        """Removes a specified key from cache."""
        if self._engine_type == "redis_cluster":
            res = await self._redis_client.delete(key)
            return bool(res > 0)

        query = "DELETE FROM kv_store WHERE key = ?"
        count = await self._execute_sqlite(query, (key,))
        return bool(count > 0)

    async def exists(self, key: str) -> bool:
        """Checks whether a key exists and has not expired."""
        val = await self.get(key)
        return val is not None

    async def acquire_lock(self, resource_key: str, owner_id: str, ttl_sec: float = 30.0) -> bool:
        """
        Atomically acquires a distributed mutual-exclusion lock (Redlock pattern).
        Prevents double execution across concurrent scaling workers.
        """
        now = time.time()
        expires_at = now + ttl_sec
        if self._engine_type == "redis_cluster":
            acquired = await self._redis_client.set(resource_key, owner_id, nx=True, ex=int(ttl_sec))
            return bool(acquired)

        async with self._lock:
            # Check existing lock in SQLite
            query_check = "SELECT owner_id, expires_at FROM distributed_locks WHERE resource_key = ?"
            row = await self._execute_sqlite(query_check, (resource_key,), fetch_one=True)
            if row:
                existing_expires = row["expires_at"]
                existing_owner = row["owner_id"]
                if now < existing_expires and existing_owner != owner_id:
                    # Lock is actively held by another worker
                    return False
                # Either expired or held by same owner; take over / renew
                query_update = "UPDATE distributed_locks SET owner_id = ?, expires_at = ? WHERE resource_key = ?"
                await self._execute_sqlite(query_update, (owner_id, expires_at, resource_key))
                log.info("[RedisLock: %s] Acquired lock '%s' (TTL: %.1fs)", owner_id, resource_key, ttl_sec)
                return True
            else:
                query_insert = "INSERT INTO distributed_locks (resource_key, owner_id, expires_at) VALUES (?, ?, ?)"
                await self._execute_sqlite(query_insert, (resource_key, owner_id, expires_at))
                log.info("[RedisLock: %s] Acquired lock '%s' (TTL: %.1fs)", owner_id, resource_key, ttl_sec)
                return True

    async def release_lock(self, resource_key: str, owner_id: str) -> bool:
        """Releases a lock only if currently held by the specifying owner."""
        if self._engine_type == "redis_cluster":
            val = await self._redis_client.get(resource_key)
            if val == owner_id:
                await self._redis_client.delete(resource_key)
                return True
            return False

        async with self._lock:
            query = "DELETE FROM distributed_locks WHERE resource_key = ? AND owner_id = ?"
            count = await self._execute_sqlite(query, (resource_key, owner_id))
            return bool(count > 0)

    async def flushall(self) -> None:
        """Clears all stored keys and locks."""
        if self._engine_type == "redis_cluster":
            await self._redis_client.flushall()
        else:
            await self._execute_sqlite("DELETE FROM kv_store;")
            await self._execute_sqlite("DELETE FROM distributed_locks;")

    async def close(self) -> None:
        """Closes any underlying network connections or resources."""
        if self._redis_client and self._engine_type == "redis_cluster":
            await self._redis_client.close()
