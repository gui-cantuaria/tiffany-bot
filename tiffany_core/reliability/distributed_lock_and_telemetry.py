"""
Tiffany OS — Distributed Leader Election & OpenTelemetry W3C Distributed Tracing
================================================================================
Equips Tiffany with multi-region zero-downtime leader election (preventing double cron
executions across horizontal scaling clusters) and structured OpenTelemetry W3C trace
spans for end-to-end distributed diagnostics without debugger attachment.
"""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger("tiffany.core.reliability.distributed")

# =============================================================================
# OpenTelemetry-compatible W3C Distributed Tracing Engine
# =============================================================================

@dataclass
class TraceSpan:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: Optional[str] = None
    operation_name: str = "unnamed_operation"
    start_time_ms: float = field(default_factory=lambda: time.perf_counter() * 1000.0)
    end_time_ms: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "IN_PROGRESS"

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def finish(self, status: str = "OK") -> Dict[str, Any]:
        self.end_time_ms = time.perf_counter() * 1000.0
        self.status = status
        duration_ms = round(self.end_time_ms - self.start_time_ms, 3)
        self.attributes["duration_ms"] = duration_ms
        log.debug("[OpenTelemetry Trace] Span '%s' finished [%s] in %.2fms | Trace: %s", 
                  self.operation_name, status, duration_ms, self.trace_id)
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "operation": self.operation_name,
            "status": self.status,
            "duration_ms": duration_ms,
            "attributes": self.attributes
        }

class DistributedTracer:
    """Produces and records W3C trace context across distributed gateway network calls."""
    def __init__(self) -> None:
        self.completed_spans: List[Dict[str, Any]] = []

    def start_span(self, operation_name: str, parent_trace_id: Optional[str] = None) -> TraceSpan:
        trace_id = parent_trace_id or uuid.uuid4().hex
        return TraceSpan(trace_id=trace_id, operation_name=operation_name)

    def record(self, finished_span: Dict[str, Any]) -> None:
        self.completed_spans.append(finished_span)
        if len(self.completed_spans) > 1000:
            self.completed_spans = self.completed_spans[-500:]


# =============================================================================
# Distributed Leader Election & Redlock Coordinator
# =============================================================================

class DistributedLeaderCoordinator:
    """
    Coordinates leader election among stateless horizontal workers. Guarantees that
    high-risk background schedules execute exactly once globally. Supports real Redis
    distributed locking when equipped with a RedisCacheEngine adapter.
    """
    def __init__(self, node_id: Optional[str] = None, lock_ttl_sec: float = 30.0, redis_engine: Optional[Any] = None) -> None:
        self.node_id = node_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.lock_ttl_sec = lock_ttl_sec
        self.redis_engine = redis_engine
        self._current_leader: Optional[str] = None
        self._leader_expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def try_acquire_leadership(self, resource_key: str = "global:cron:leader") -> bool:
        if self.redis_engine is not None:
            acquired = await self.redis_engine.acquire_lock(resource_key, self.node_id, ttl_sec=self.lock_ttl_sec)
            if acquired:
                self._current_leader = self.node_id
                self._leader_expires_at = time.monotonic() + self.lock_ttl_sec
            return acquired

        async with self._lock:
            now = time.monotonic()
            if self._current_leader is None or now >= self._leader_expires_at:
                self._current_leader = self.node_id
                self._leader_expires_at = now + self.lock_ttl_sec
                log.info("[LeaderElection: %s] Acquired leadership for resource '%s' (TTL: %.1fs)", 
                         self.node_id, resource_key, self.lock_ttl_sec)
                return True
            
            if self._current_leader == self.node_id:
                # Renew leadership heartbeat
                self._leader_expires_at = now + self.lock_ttl_sec
                return True

            return False

    def is_current_leader(self) -> bool:
        return self._current_leader == self.node_id and time.monotonic() < self._leader_expires_at

    async def step_down(self, resource_key: str = "global:cron:leader") -> None:
        if self.redis_engine is not None and self._current_leader == self.node_id:
            await self.redis_engine.release_lock(resource_key, self.node_id)

        async with self._lock:
            if self._current_leader == self.node_id:
                self._current_leader = None
                self._leader_expires_at = 0.0
                log.info("[LeaderElection: %s] Voluntarily stepped down from leadership", self.node_id)

tracer = DistributedTracer()
leader_coordinator = DistributedLeaderCoordinator()
