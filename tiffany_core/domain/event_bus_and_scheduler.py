"""
Tiffany OS — Platform-Agnostic Domain Events, Resource Scheduler & Workflow Engine
==================================================================================
Decouples domain reactivity from Discord-specific payloads via universal events.
Implements a Priority Resource Scheduler to ensure QoS for enterprise tenants and a
resilient Workflow Orchestrator with automated retries and step compensation.
"""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from tiffany_core.domain.events import DomainEvent, domain_event_bus
from tiffany_core.domain.idempotency import IdempotencyIdentity, DurableIdempotencyStore, global_idempotency_store

log = logging.getLogger("tiffany.core.domain.orchestration")

# =============================================================================
# Platform-Agnostic Universal Domain Events
# =============================================================================

class TenantCreated(DomainEvent):
    def __init__(self, tenant_id: int, name: str, platform_origin: str = "discord") -> None:
        super().__init__(payload={"tenant_id": tenant_id, "name": name, "origin": platform_origin})

class SubscriptionRenewed(DomainEvent):
    def __init__(self, tenant_id: int, new_tier: str, amount_usd: float) -> None:
        super().__init__(payload={"tenant_id": tenant_id, "tier": new_tier, "mrr_usd": amount_usd})

class FeatureToggled(DomainEvent):
    def __init__(self, tenant_id: int, feature: str, is_enabled: bool) -> None:
        super().__init__(payload={"tenant_id": tenant_id, "feature": feature, "enabled": is_enabled})

class PaymentSucceeded(DomainEvent):
    def __init__(self, invoice_id: str, tenant_id: int, amount_usd: float) -> None:
        super().__init__(payload={"invoice_id": invoice_id, "tenant_id": tenant_id, "amount": amount_usd})


# =============================================================================
# Multi-Tenant Priority Resource Scheduler
# =============================================================================

@dataclass(order=True)
class ScheduledWorkload:
    priority: int
    created_epoch: float = field(compare=True)
    workload_id: str = field(compare=False, default_factory=lambda: uuid.uuid4().hex[:8])
    tenant_id: int = field(compare=False, default=0)
    tier: str = field(compare=False, default="free")
    task_coroutine_func: Optional[Callable[[], Coroutine[Any, Any, Any]]] = field(compare=False, default=None)

class ResourceScheduler:
    """
    Arbitrates computational resource admission (LLM inference, DB sweeps, Audio processing).
    Enterprise tenants receive high priority (1), Pro (5), Free (10), preventing resource starvation.
    """
    def __init__(self, max_concurrent_workers: int = 10) -> None:
        self.max_concurrent = max_concurrent_workers
        self._queue: asyncio.PriorityQueue[ScheduledWorkload] = asyncio.PriorityQueue()
        self._active_workers: int = 0
        self._lock = asyncio.Lock()

    def _get_priority_for_tier(self, tier: str) -> int:
        tier_lower = tier.lower()
        if tier_lower == "enterprise":
            return 1
        elif tier_lower == "pro":
            return 5
        return 10

    async def submit_and_execute(self, tenant_id: int, tier: str, coro_func: Callable[[], Coroutine[Any, Any, Any]], timeout_sec: float = 10.0) -> Any:
        prio = self._get_priority_for_tier(tier)
        workload = ScheduledWorkload(priority=prio, created_epoch=time.perf_counter(), tenant_id=tenant_id, tier=tier, task_coroutine_func=coro_func)
        await self._queue.put(workload)
        log.debug("[ResourceScheduler] Enqueued workload %s for Tenant %d [Tier: %s | Prio: %d]", 
                  workload.workload_id, tenant_id, tier, prio)

        # Dequeue and execute respecting concurrency bulkhead
        async with self._lock:
            if self._active_workers >= self.max_concurrent:
                log.warning("[ResourceScheduler] Backpressure activated: %d active workers reached capacity!", self._active_workers)
            self._active_workers += 1

        try:
            item = await self._queue.get()
            if item.task_coroutine_func:
                result = await asyncio.wait_for(item.task_coroutine_func(), timeout=timeout_sec)
                self._queue.task_done()
                return result
        finally:
            async with self._lock:
                self._active_workers = max(0, self._active_workers - 1)


# =============================================================================
# Reusable Sequential Workflow Engine
# =============================================================================

@dataclass
class WorkflowStep:
    name: str
    handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]
    retries: int = 2

class WorkflowOrchestrator:
    """
    Executes sequential domain steps (e.g. Onboarding, Billing Retry) with structured
    error handling, state passing, automatic retry backoff, and strict step idempotency.
    """
    def __init__(self, workflow_name: str, idempotency_store: Optional[DurableIdempotencyStore] = None) -> None:
        self.workflow_name = workflow_name
        self._steps: List[WorkflowStep] = []
        self.store = idempotency_store or global_idempotency_store

    def add_step(self, name: str, handler: Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]], retries: int = 2) -> None:
        self._steps.append(WorkflowStep(name=name, handler=handler, retries=retries))

    async def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        state = initial_state.copy()
        log.info("[WorkflowEngine: %s] Starting processing with state: %s", self.workflow_name, state)

        event_id = state.get("event_id")
        idempotency_key = state.get("idempotency_key")
        tenant_id = state.get("tenant_id", 0)
        worker_id = f"worker_{uuid.uuid4().hex[:6]}"

        for step in self._steps:
            step_idempotency_key = None
            if event_id or idempotency_key:
                ident = IdempotencyIdentity(
                    workflow_id=self.workflow_name,
                    step_id=step.name,
                    tenant_id=tenant_id,
                    event_id=event_id,
                    idempotency_key=idempotency_key
                )
                step_idempotency_key = ident.to_key()
                status, cached_output = await self.store.begin_execution(step_idempotency_key, owner=worker_id)
                if status == "COMPLETED" and cached_output is not None:
                    log.info("[WorkflowEngine: %s] Step '%s' already completed! Using idempotent result.", self.workflow_name, step.name)
                    state.update(cached_output)
                    continue

            attempt = 0
            while attempt <= step.retries:
                try:
                    step_output = await step.handler(state)
                    state.update(step_output)
                    if step_idempotency_key:
                        await self.store.complete_execution(step_idempotency_key, owner=worker_id, result=step_output)
                    log.debug("[WorkflowEngine: %s] Step '%s' succeeded on attempt %d", self.workflow_name, step.name, attempt + 1)
                    break
                except Exception as exc:
                    attempt += 1
                    log.warning("[WorkflowEngine: %s] Step '%s' failed attempt %d/%d: %s", 
                                self.workflow_name, step.name, attempt, step.retries + 1, exc)
                    if attempt > step.retries:
                        log.error("[WorkflowEngine: %s] Fatal failure at step '%s'. Aborting workflow.", self.workflow_name, step.name)
                        if step_idempotency_key:
                            await self.store.fail_execution(step_idempotency_key, owner=worker_id, error_detail=str(exc))
                        state["_workflow_status"] = "FAILED"
                        state["_failed_step"] = step.name
                        state["_error_detail"] = str(exc)
                        return state
                    await asyncio.sleep(0.05) * attempt  # Exponential backoff

        state["_workflow_status"] = "COMPLETED"
        log.info("[WorkflowEngine: %s] Successfully completed all %d steps!", self.workflow_name, len(self._steps))
        return state

resource_scheduler = ResourceScheduler()
