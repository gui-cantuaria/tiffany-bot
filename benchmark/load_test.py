import argparse
import asyncio
import os
import json
import time
import uuid
from datetime import datetime
from bench_utils import calculate_stats, write_results, ResourceMonitor, setup_logger

logger = setup_logger("load_test")

async def mixed_workload(pg_pool, redis_client):
    try:
        # Simulate a typical request flow:
        # 1. Check rate limit in Redis
        # 2. Check entitlement cache
        # 3. DB read/write
        if redis_client:
            await redis_client.ping()
        
        if pg_pool:
            async with pg_pool.acquire() as conn:
                await conn.execute("SELECT 1")
                
        await asyncio.sleep(0.01) # Simulate CPU/App work
        return True
    except Exception as e:
        return False

async def run_level(level, concurrency, duration, pg_pool, redis_client):
    logger.info(f"Starting Level {level}: {concurrency} concurrent operations")
    
    end_time = time.time() + duration
    latencies = []
    errors = 0
    ops_completed = 0
    
    async def worker():
        nonlocal errors, ops_completed
        while time.time() < end_time:
            start = time.perf_counter()
            success = await mixed_workload(pg_pool, redis_client)
            latencies.append(time.perf_counter() - start)
            if success:
                ops_completed += 1
            else:
                errors += 1
                
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    
    # Event loop lag monitoring during test
    lags = []
    async def monitor_lag():
        while time.time() < end_time:
            start = time.perf_counter()
            await asyncio.sleep(0.1)
            lags.append(time.perf_counter() - start - 0.1)
            
    lag_task = asyncio.create_task(monitor_lag())
    
    await asyncio.gather(*workers)
    lag_task.cancel()
    
    stats = calculate_stats(f"Level {level}", concurrency, latencies, errors)
    
    # Add custom metrics
    stats.custom_metrics = {
        "ops_per_second": ops_completed / duration if duration > 0 else 0,
        "event_loop_lag_p99": max(lags) if lags else 0,
        "total_errors": errors
    }
    
    return stats

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url', required=False)
    parser.add_argument('--redis-url', required=False)
    parser.add_argument('--provider', default='local')
    parser.add_argument('--duration', type=int, default=10, help="Duration per level in seconds")
    args = parser.parse_args()

    pg_pool = None
    redis_client = None
    
    if args.database_url:
        try:
            import asyncpg
            pg_pool = await asyncpg.create_pool(args.database_url, min_size=5, max_size=2000)
        except ImportError:
            pass
            
    if args.redis_url:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(args.redis_url)
        except ImportError:
            pass

    monitor = ResourceMonitor()
    all_results = []
    
    levels = [
        (1, 100),
        (2, 500),
        (3, 1000),
        (4, 2000)
    ]
    
    for level, concurrency in levels:
        res = await run_level(level, concurrency, args.duration, pg_pool, redis_client)
        all_results.append(res)
        logger.info(f"Level {level} completed: {res.custom_metrics.get('ops_per_second', 0):.2f} ops/sec")
        await asyncio.sleep(2) # Cool down
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark/results/load_{args.provider}_{timestamp}.json"
    
    metadata = {
        "provider": args.provider,
        "timestamp": timestamp,
        "duration_per_level": args.duration,
        "resources_after": monitor.get_stats()
    }
    
    write_results(filename, all_results, metadata)
    logger.info(f"Results written to {filename}")
    
    if pg_pool:
        await pg_pool.close()
    if redis_client:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
