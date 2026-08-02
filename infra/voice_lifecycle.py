"""Runtime lifecycle helpers — bounded cancellation and owned background tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Optional, TypeVar

log = logging.getLogger("tiffany-bot.lifecycle")

TASK_CANCEL_TIMEOUT_SEC = 5.0

T = TypeVar("T")


async def cancel_task_bounded(
    task: Optional[asyncio.Task],
    *,
    label: str,
    timeout: float = TASK_CANCEL_TIMEOUT_SEC,
) -> None:
    """Cancel a task and await completion with a bounded timeout."""
    if task is None or task.done():
        return
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.CancelledError:
        pass
    except asyncio.TimeoutError:
        log.warning("Task %s did not finish within %.1fs during cleanup", label, timeout)
    except Exception:
        log.debug("Task %s raised while awaiting cancellation", label, exc_info=True)


def spawn_ephemeral(coro: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task:
    """Fire-and-forget task with logged failure (avoids 'exception was never retrieved')."""
    task = asyncio.create_task(coro, name=name)

    def _done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.warning("Ephemeral task %s failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_done)
    return task


class OwnedBackgroundTask:
    """Single-owner background task with idempotent start/stop."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._task: Optional[asyncio.Task] = None

    @property
    def task(self) -> Optional[asyncio.Task]:
        return self._task

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, coro_factory: Callable[[], Coroutine]) -> asyncio.Task:
        if self._task and not self._task.done():
            log.debug("Owned task %s already running — reusing", self.name)
            return self._task
        self._task = asyncio.create_task(coro_factory(), name=self.name)
        self._task.add_done_callback(self._on_done)
        log.debug("Owned task %s started", self.name)
        return self._task

    async def stop(self, *, timeout: float = TASK_CANCEL_TIMEOUT_SEC) -> None:
        task = self._task
        if task is None or task.done():
            self._task = None
            return
        await cancel_task_bounded(task, label=self.name, timeout=timeout)
        self._task = None
        log.debug("Owned task %s stopped", self.name)

    def _on_done(self, finished: asyncio.Task) -> None:
        if self._task is finished:
            self._task = None
        if finished.cancelled():
            return
        exc = finished.exception()
        if exc is not None:
            log.error("Owned task %s terminated with error", self.name, exc_info=exc)
