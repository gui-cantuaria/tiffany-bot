"""
Tiffany OS — Domain & Event-Driven Design Layer
==============================================
Provides Immutable Domain Events and a high-performance in-memory Event Bus
for asynchronous, decoupled internal event distribution and CQRS patterns.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Type
import asyncio
import uuid
import logging

log = logging.getLogger("tiffany.core.events")

@dataclass(frozen=True)
class DomainEvent:
    """Base class for all immutable domain events across Tiffany OS."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass(frozen=True)
class AudioPlaybackStarted(DomainEvent):
    guild_id: int = 0
    track_title: str = ""
    duration_ms: int = 0
    requester_id: int = 0
    provider: str = "youtube"

@dataclass(frozen=True)
class AIInferenceCompleted(DomainEvent):
    user_id: int = 0
    guild_id: int = 0
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False

@dataclass(frozen=True)
class GuardrailViolationDetected(DomainEvent):
    user_id: int = 0
    guild_id: int = 0
    reasoning: str = ""
    classification: str = "ILLEGAL_GORE"
    blocked_at_layer: str = "openrouter_guardrail"


EventHandler = Callable[[DomainEvent], Coroutine[Any, Any, None]]

class EventBus:
    """
    Decoupled Event Bus supporting concurrent async listeners with fail-safe isolation.
    Guarantees that a failing handler does not disrupt event propagation or caller threads.
    """
    def __init__(self) -> None:
        self._listeners: Dict[Type[DomainEvent], List[EventHandler]] = {}

    def subscribe(self, event_type: Type[DomainEvent], handler: EventHandler) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        if handler not in self._listeners[event_type]:
            self._listeners[event_type].append(handler)
        log.debug("Subscribed %s to event %s", handler.__name__, event_type.__name__)

    async def publish(self, event: DomainEvent) -> None:
        event_type = type(event)
        handlers = self._listeners.get(event_type, [])
        if not handlers:
            return
        
        # Execute handlers concurrently and defensively
        tasks = [self._execute_handler(handler, event) for handler in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_handler(self, handler: EventHandler, event: DomainEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            log.exception("Error executing handler %s for event %s: %s", 
                          getattr(handler, "__name__", str(handler)), 
                          event.event_id, exc)

# Global singleton event bus instance for domain communication
domain_event_bus = EventBus()
