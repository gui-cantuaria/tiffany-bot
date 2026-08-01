"""Payment observability counters — real in-process metrics (no fabricated KPIs)."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = {
    "webhook_received": 0,
    "webhook_duplicate": 0,
    "webhook_invalid_signature": 0,
    "webhook_rejected": 0,
    "webhook_completed": 0,
    "webhook_failed": 0,
    "webhook_idempotency_collision": 0,
    "tier_rejected_unknown": 0,
    "metadata_rejected": 0,
    "outbox_enqueued": 0,
    "outbox_delivered": 0,
    "outbox_failed": 0,
    "outbox_dead_letter": 0,
    "reconciliation_drift": 0,
    "reconciliation_corrected": 0,
    "stale_processing_recovered": 0,
    "webhook_latency_ms_total": 0,
    "webhook_latency_ms_max": 0,
    "webhook_latency_ms_last": 0,
    "outbox_pending_depth": 0,
}


def inc(name: str, delta: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + delta


def observe_webhook_latency_ms(ms: float) -> None:
    ms_i = int(max(0, ms))
    with _lock:
        _counters["webhook_latency_ms_total"] = _counters.get("webhook_latency_ms_total", 0) + ms_i
        _counters["webhook_latency_ms_last"] = ms_i
        prev_max = _counters.get("webhook_latency_ms_max", 0)
        if ms_i > prev_max:
            _counters["webhook_latency_ms_max"] = ms_i


def set_gauge(name: str, value: int) -> None:
    with _lock:
        _counters[name] = value


class webhook_timer:
    """Context manager to measure webhook handler wall time."""

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        observe_webhook_latency_ms((time.perf_counter() - self._start) * 1000)
        return False


def payment_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_counters)
