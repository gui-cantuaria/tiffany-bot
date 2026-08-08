import argparse
import asyncio
import os
import json
import time
import uuid
import signal
from datetime import datetime
from bench_utils import ResourceMonitor, setup_logger

logger = setup_logger("soak_test")

should_stop = False

def handle_sigterm(*args):
    global should_stop
    logger.info("Received SIGTERM, stopping soak test...")
    should_stop = True

signal.signal(signal.SIGINT, handle_sigterm)
signal.signal(signal.SIGTERM, handle_sigterm)

async def simulate_work(pg_pool, redis_client):
    start = time.perf_counter()
    try:
        if redis_client:
            await redis_client.ping()
        if pg_pool:
            async with pg_pool.acquire() as conn:
                await conn.execute("SELECT 1")
        await asyncio.sleep(0.01)
        return time.perf_counter() - start, False
    except Exception as e:
        return time.perf_counter() - start, True

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url', required=False)
    parser.add_argument('--redis-url', required=False)
    parser.add_argument('--provider', default='local')
    parser.add_argument('--duration', type=int, default=3600, help="Duration in seconds (default 1h)")
    args = parser.parse_args()

    pg_pool = None
    redis_client = None
    
    if args.database_url:
        try:
            import asyncpg
            pg_pool = await asyncpg.create_pool(args.database_url, min_size=5, max_size=50)
        except ImportError:
            pass
            
    if args.redis_url:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(args.redis_url)
        except ImportError:
            pass

    monitor = ResourceMonitor()
    time_series = []
    
    logger.info(f"Starting Soak Test for {args.duration} seconds...")
    end_time = time.time() + args.duration
    
    baseline_stats = monitor.get_stats()
    logger.info(f"Baseline stats: {baseline_stats}")

    latencies = []
    errors = 0
    
    # Background worker
    async def worker():
        nonlocal latencies, errors
        while not should_stop and time.time() < end_time:
            lat, err = await simulate_work(pg_pool, redis_client)
            latencies.append(lat)
            if err: errors += 1
            await asyncio.sleep(0.05) # Throttle

    worker_task = asyncio.create_task(worker())
    
    # Sampling loop
    while not should_stop and time.time() < end_time:
        await asyncio.sleep(10)
        
        current_stats = monitor.get_stats()
        
        avg_latency = sum(latencies[-100:]) / len(latencies[-100:]) if latencies else 0
        
        sample = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": current_stats.get("cpu_percent", 0),
            "memory_rss_mb": current_stats.get("memory_rss_mb", 0),
            "num_fds": current_stats.get("num_fds", 0),
            "avg_latency": avg_latency,
            "errors": errors
        }
        time_series.append(sample)
        logger.info(f"Sample: mem={sample['memory_rss_mb']:.2f}MB, fds={sample['num_fds']}, lat={sample['avg_latency']:.4f}s")
        
        # Anomaly detection
        if baseline_stats.get("memory_rss_mb") and sample["memory_rss_mb"] > baseline_stats["memory_rss_mb"] * 1.1:
            logger.warning(f"Memory anomaly detected: {sample['memory_rss_mb']}MB > 10% over baseline")
            
        if baseline_stats.get("num_fds") and sample["num_fds"] > baseline_stats["num_fds"] * 1.2:
            logger.warning(f"FD anomaly detected: {sample['num_fds']} > 20% over baseline")

    worker_task.cancel()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark/results/soak_{args.provider}_{timestamp}.json"
    
    output = {
        "metadata": {
            "provider": args.provider,
            "duration": args.duration,
            "baseline": baseline_stats
        },
        "time_series": time_series
    }
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
        
    logger.info(f"Results written to {filename}")
    
    if pg_pool:
        await pg_pool.close()
    if redis_client:
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
