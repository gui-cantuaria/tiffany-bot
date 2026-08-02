"""Runtime lifecycle helpers — bounded cancellation and owned background tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, Set, TypeVar

log = logging.getLogger("tiffany-bot.lifecycle")

TASK_CANCEL_TIMEOUT_SEC = 5.0

T = TypeVar("T")

# Strong references for short-lived fire-and-forget tasks until completion.
_EPHEMERAL_TASKS: Set[asyncio.Task] = set()


async def cancel_task_bounded(
    task: Optional[asyncio.Task],
    *,
    label: str,
    timeout: float = TASK_CANCEL_TIMEOUT_SEC,
) -> bool:
    """Cancel a task and await completion with a bounded timeout.

    Returns True if the task finished (done/cancelled); False if still running.
    """
    if task is None or task.done():
        return True
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        log.warning("Task %s did not finish within %.1fs during cleanup", label, timeout)
        return False
    except asyncio.CancelledError:
        pass
    except Exception:
        log.debug("Task %s raised while awaiting cancellation", label, exc_info=True)
    return task.done()


def spawn_ephemeral(coro: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task:
    """Fire-and-forget task with logged failure (avoids 'exception was never retrieved')."""
    task = asyncio.create_task(coro, name=name)
    _EPHEMERAL_TASKS.add(task)

    def _done(t: asyncio.Task) -> None:
        _EPHEMERAL_TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.warning("Ephemeral task %s failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_done)
    return task


def ephemeral_task_count() -> int:
    """Development helper — count tracked ephemeral tasks still alive."""
    _EPHEMERAL_TASKS.difference_update(t for t in _EPHEMERAL_TASKS if t.done())
    return len(_EPHEMERAL_TASKS)


def register_session_task(
    task: asyncio.Task,
    *,
    session: Any,
    attr: str,
    guild_id: int,
    label: str,
) -> asyncio.Task:
    """Attach observability to a session-owned long-running task."""

    def _done(t: asyncio.Task) -> None:
        if getattr(session, attr, None) is t:
            setattr(session, attr, None)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.error(
                "Session task %s guild=%s failed",
                label,
                guild_id,
                exc_info=exc,
            )

    task.add_done_callback(_done)
    return task


class OwnedBackgroundTask:
    """Single-owner background task with idempotent start/stop."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._task: Optional[asyncio.Task] = None
        self._stop_timed_out: bool = False

    @property
    def task(self) -> Optional[asyncio.Task]:
        return self._task

    @property
    def stop_timed_out(self) -> bool:
        return self._stop_timed_out

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, coro_factory: Callable[[], Coroutine]) -> asyncio.Task:
        if self.is_running():
            log.debug("Owned task %s already running — reusing", self.name)
            return self._task  # type: ignore[return-value]
        if self._task is not None and not self._task.done():
            log.critical(
                "Owned task %s still alive after cancel timeout — refusing duplicate start",
                self.name,
            )
            return self._task
        self._stop_timed_out = False
        self._task = asyncio.create_task(coro_factory(), name=self.name)
        self._task.add_done_callback(self._on_done)
        log.debug("Owned task %s started", self.name)
        return self._task

    async def stop(self, *, timeout: float = TASK_CANCEL_TIMEOUT_SEC) -> None:
        task = self._task
        if task is None or task.done():
            self._task = None
            self._stop_timed_out = False
            return
        finished = await cancel_task_bounded(task, label=self.name, timeout=timeout)
        if finished:
            self._task = None
            self._stop_timed_out = False
            log.debug("Owned task %s stopped", self.name)
        else:
            self._stop_timed_out = True
            log.critical(
                "Owned task %s cancel timed out — task still running (ref retained)",
                self.name,
            )

    def _on_done(self, finished: asyncio.Task) -> None:
        if self._task is finished:
            self._task = None
            self._stop_timed_out = False
        if finished.cancelled():
            return
        exc = finished.exception()
        if exc is not None:
            log.error("Owned task %s terminated with error", self.name, exc_info=exc)
