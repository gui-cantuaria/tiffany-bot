"""
Tiffany OS — Application-Level Healthcheck Probe
=================================================
Verifies real application subsystems (PostgreSQL, Redis, Lavalink, process health).
Returns 0 if healthy, 1 if unhealthy.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys

def check_socket(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False

async def verify_postgres(url: str) -> bool:
    try:
        import asyncpg
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        if not check_socket(host, port, timeout=3.0):
            return False
        conn = await asyncio.wait_for(asyncpg.connect(url, timeout=5), timeout=5.0)
        await asyncio.wait_for(conn.execute("SELECT 1"), timeout=3.0)
        await conn.close()
        return True
    except Exception as e:
        sys.stderr.write(f"[HealthCheck] PostgreSQL check failed: {e}\n")
        return False

async def verify_redis(url: str) -> bool:
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(url, decode_responses=True, socket_timeout=3.0)
        await asyncio.wait_for(client.ping(), timeout=3.0)
        await client.close()
        return True
    except Exception as e:
        sys.stderr.write(f"[HealthCheck] Redis check failed: {e}\n")
        return False

async def main() -> int:
    unhealthy_reasons = []

    # 1. PostgreSQL Check if configured
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url:
        ok = await verify_postgres(db_url)
        if not ok:
            unhealthy_reasons.append("PostgreSQL connection failed")

    # 2. Redis Check if configured
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        ok = await verify_redis(redis_url)
        if not ok:
            unhealthy_reasons.append("Redis ping failed")

    # 3. Lavalink Node Socket Check if configured
    lavalink_host = os.getenv("LAVALINK_HOST", "127.0.0.1").strip()
    lavalink_port = int(os.getenv("LAVALINK_PORT", "2333"))
    lavalink_password = os.getenv("LAVALINK_PASSWORD", "").strip()
    if lavalink_password or os.getenv("LAVALINK_NODES"):
        if not check_socket(lavalink_host, lavalink_port, timeout=3.0):
            unhealthy_reasons.append(f"Lavalink node unavailable at {lavalink_host}:{lavalink_port}")

    if unhealthy_reasons:
        sys.stderr.write(f"[HealthCheck] STATUS UNHEALTHY: {', '.join(unhealthy_reasons)}\n")
        return 1

    sys.stdout.write("[HealthCheck] STATUS HEALTHY: All configured subsystems operational\n")
    return 0

if __name__ == "__main__":
    try:
        code = asyncio.run(asyncio.wait_for(main(), timeout=12.0))
    except asyncio.TimeoutError:
        sys.stderr.write("[HealthCheck] STATUS UNHEALTHY: Overall probe timeout (12s)\n")
        code = 1
    sys.exit(code)
