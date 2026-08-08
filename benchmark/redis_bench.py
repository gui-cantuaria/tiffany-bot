import argparse
import asyncio
import os
import json
import time
import uuid
from datetime import datetime
try:
    import redis.asyncio as redis
except ImportError:
    pass

from bench_utils import calculate_stats, write_results, measure_time, ResourceMonitor, setup_logger

logger = setup_logger("redis_bench")

async def run_operation(name, client, iterations, concurrency, func):
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
                await func(client)
                latencies.append(time.perf_counter() - start)
            except Exception as e:
                errors += 1
                latencies.append(time.perf_counter() - start)
            
            queue.task_done()
            
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers)
    
    return calculate_stats(name, concurrency, latencies, errors)

async def op_ping(client):
    await client.ping()

async def op_get(client):
    key = f"ent:g:{uuid.uuid4()}"
    await client.get(key)

async def op_setex(client):
    key = f"ent:g:{uuid.uuid4()}"
    await client.setex(key, 300, "1")

async def op_delete(client):
    key = f"ent:g:{uuid.uuid4()}"
    await client.delete(key)

async def op_incr_expire(client):
    key = f"rl:{uuid.uuid4()}"
    pipe = client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    await pipe.execute()

async def op_redlock(client):
    key = f"lock:{uuid.uuid4()}"
    acquired = await client.set(key, "1", nx=True, ex=10)
    if acquired:
        await client.delete(key)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--redis-url', required=True)
    parser.add_argument('--provider', default='local')
    parser.add_argument('--iterations', type=int, default=10000)
    parser.add_argument('--concurrency-levels', type=int, nargs='+', default=[1, 10, 50, 100])
    args = parser.parse_args()

    logger.info("Connecting to Redis...")
    client = redis.from_url(args.redis_url)
    
    # Check connection
    await client.ping()
    
    monitor = ResourceMonitor()
    all_results = []
    
    ops = [
        ("PING", op_ping),
        ("GET (Cache Miss)", op_get),
        ("SETEX", op_setex),
        ("DELETE", op_delete),
        ("INCR+EXPIRE Pipeline", op_incr_expire),
        ("Redlock (SETNX+EXPIRE)", op_redlock)
    ]
    
    for conc in args.concurrency_levels:
        for name, func in ops:
            res = await run_operation(name, client, args.iterations, conc, func)
            all_results.append(res)
            
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark/results/redis_{args.provider}_{timestamp}.json"
    
    metadata = {
        "provider": args.provider,
        "timestamp": timestamp,
        "iterations": args.iterations,
        "concurrency_levels": args.concurrency_levels,
        "resources_after": monitor.get_stats()
    }
    
    write_results(filename, all_results, metadata)
    logger.info(f"Results written to {filename}")
    
    await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
