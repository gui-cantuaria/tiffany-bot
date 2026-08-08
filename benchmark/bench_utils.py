import json
import logging
import math
import os
import psutil
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass
class BenchmarkResult:
    operation: str
    concurrency: int
    iterations: int
    p50: float
    p95: float
    p99: float
    min: float
    max: float
    mean: float
    stddev: float
    errors: int
    custom_metrics: Dict[str, Any] = None

def get_percentile(data: List[float], percentile: float) -> float:
    if not data: return 0.0
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data_sorted[int(k)]
    d0 = data_sorted[int(f)] * (c - k)
    d1 = data_sorted[int(c)] * (k - f)
    return d0 + d1

def calculate_stats(operation: str, concurrency: int, latencies: List[float], errors: int = 0) -> BenchmarkResult:
    if not latencies:
        return BenchmarkResult(operation, concurrency, 0, 0, 0, 0, 0, 0, 0, 0, errors)
    
    n = len(latencies)
    mean = sum(latencies) / n
    variance = sum((x - mean) ** 2 for x in latencies) / n
    stddev = math.sqrt(variance)
    
    return BenchmarkResult(
        operation=operation,
        concurrency=concurrency,
        iterations=n,
        p50=get_percentile(latencies, 0.50),
        p95=get_percentile(latencies, 0.95),
        p99=get_percentile(latencies, 0.99),
        min=min(latencies),
        max=max(latencies),
        mean=mean,
        stddev=stddev,
        errors=errors
    )

def write_results(filename: str, results: List[BenchmarkResult], metadata: Dict[str, Any] = None):
    output = {
        "metadata": metadata or {},
        "results": [asdict(r) for r in results]
    }
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)

@contextmanager
def measure_time():
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start

class ResourceMonitor:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        
    def get_stats(self) -> Dict[str, float]:
        try:
            return {
                "cpu_percent": self.process.cpu_percent(),
                "memory_rss_mb": self.process.memory_info().rss / (1024 * 1024),
                "num_fds": self.process.num_handles() if os.name == 'nt' else self.process.num_fds(),
                "num_threads": self.process.num_threads()
            }
        except Exception:
            return {}

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
