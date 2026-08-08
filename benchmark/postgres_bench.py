import argparse
import asyncio
import os
import json
import time
import uuid
import hashlib
from datetime import datetime
try:
    import asyncpg
except ImportError:
    pass # Will be handled by dependencies

from bench_utils import calculate_stats, write_results, measure_time, ResourceMonitor, setup_logger

logger = setup_logger("postgres_bench")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id VARCHAR(255) PRIMARY KEY,
    tier VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS guild_features (
    guild_id VARCHAR(255) PRIMARY KEY,
    features JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_cosmetics (
    user_id VARCHAR(255) PRIMARY KEY,
    equipped JSONB,
    inventory JSONB
);
CREATE TABLE IF NOT EXISTS ai_usage_daily (
    user_id VARCHAR(255),
    date DATE,
    tokens INT DEFAULT 0,
    PRIMARY KEY (user_id, date)
);
CREATE TABLE IF NOT EXISTS giveaways (
    id SERIAL PRIMARY KEY,
    guild_id VARCHAR(255),
    prize VARCHAR(255),
    end_time TIMESTAMP
);
CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INT,
    user_id VARCHAR(255),
    PRIMARY KEY (giveaway_id, user_id)
);
CREATE TABLE IF NOT EXISTS embed_templates (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    template_data JSONB
);
CREATE TABLE IF NOT EXISTS stripe_events (
    id VARCHAR(255) PRIMARY KEY,
    type VARCHAR(255),
    payload_hash VARCHAR(255) UNIQUE,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS payment_outbox (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(255),
    payload JSONB,
    processed BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS payment_audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    action VARCHAR(255),
    amount INT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
        # Clear some tables for clean slate
        await conn.execute("TRUNCATE subscriptions, stripe_events, payment_outbox, payment_audit_log RESTART IDENTITY CASCADE;")

async def run_operation(name, pool, iterations, concurrency, func):
    logger.info(f"Running {name} (concurrency={concurrency}, iterations={iterations})")
    
    queue = asyncio.Queue()
    for _ in range(iterations):
        queue.put_nowait(1)
        
    latencies = []
    errors = 0
    
    async def worker():
        nonlocal errors
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
            start = time.perf_counter()
            try:
                await func(pool)
                latencies.append(time.perf_counter() - start)
            except Exception as e:
                errors += 1
                latencies.append(time.perf_counter() - start)
            
            queue.task_done()
            
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers)
    
    return calculate_stats(name, concurrency, latencies, errors)

async def op_simple_select(pool):
    user_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT tier FROM subscriptions WHERE user_id = $1", user_id)

async def op_insert(pool):
    user_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO subscriptions (user_id, tier) VALUES ($1, $2)", user_id, "premium")

async def op_update(pool):
    user_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO subscriptions (user_id, tier) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING", user_id, "free")
        await conn.execute("UPDATE subscriptions SET tier = $1, updated_at = NOW() WHERE user_id = $2", "premium", user_id)

async def op_transaction(pool):
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("INSERT INTO subscriptions (user_id, tier) VALUES ($1, $2)", user_id, "premium")
            await conn.execute("INSERT INTO stripe_events (id, type) VALUES ($1, $2)", event_id, "checkout.session.completed")
            await conn.execute("INSERT INTO payment_outbox (event_type, payload) VALUES ($1, $2)", "sub_granted", '{"user": "test"}')

async def op_skip_locked(pool):
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT id FROM payment_outbox WHERE processed = FALSE FOR UPDATE SKIP LOCKED LIMIT 1")
            if row:
                await conn.execute("UPDATE payment_outbox SET processed = TRUE WHERE id = $1", row['id'])

async def op_payment_ledger(pool):
    user_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO payment_audit_log (user_id, action, amount) VALUES ($1, $2, $3)", user_id, "charge", 1000)

async def op_event_insertion(pool):
    event_id = str(uuid.uuid4())
    payload = f"test_payload_{event_id}"
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    async with pool.acquire() as conn:
        try:
            await conn.execute("INSERT INTO stripe_events (id, type, payload_hash) VALUES ($1, $2, $3)", event_id, "event", payload_hash)
        except asyncpg.exceptions.UniqueViolationError:
            pass

async def op_pool_acquisition(pool):
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")

async def op_rollback(pool):
    user_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                await conn.execute("INSERT INTO subscriptions (user_id, tier) VALUES ($1, $2)", user_id, "premium")
                raise Exception("Rollback")
        except Exception:
            pass

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--provider', default='local')
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--concurrency-levels', type=int, nargs='+', default=[1, 5, 10, 25, 50, 100])
    args = parser.parse_args()

    logger.info(f"Connecting to database...")
    pool = await asyncpg.create_pool(args.database_url, min_size=5, max_size=max(args.concurrency_levels) + 10)
    
    await init_db(pool)
    
    monitor = ResourceMonitor()
    all_results = []
    
    ops = [
        ("Simple SELECT", op_simple_select),
        ("INSERT", op_insert),
        ("UPDATE", op_update),
        ("Transaction", op_transaction),
        ("SKIP LOCKED", op_skip_locked),
        ("Payment ledger", op_payment_ledger),
        ("Event insertion", op_event_insertion),
        ("Pool acquisition", op_pool_acquisition),
        ("Rollback", op_rollback)
    ]
    
    for conc in args.concurrency_levels:
        for name, func in ops:
            res = await run_operation(name, pool, args.iterations, conc, func)
            all_results.append(res)
            
    # Schema migration simulation
    logger.info("Running schema migration simulation")
    start = time.perf_counter()
    await init_db(pool)
    migration_time = time.perf_counter() - start
    all_results.append(calculate_stats("Migration", 1, [migration_time]))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark/results/postgres_{args.provider}_{timestamp}.json"
    
    metadata = {
        "provider": args.provider,
        "timestamp": timestamp,
        "iterations": args.iterations,
        "concurrency_levels": args.concurrency_levels,
        "resources_after": monitor.get_stats()
    }
    
    write_results(filename, all_results, metadata)
    logger.info(f"Results written to {filename}")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
