"""Cola del LLM: una sola plaza por proceso, con prioridad, sustitución y caducidad.

- Menor número = más prioridad (0 apertura e hipótesis … 4 informe).
- Un trabajo con `key` sustituye al pendiente con la misma `key` (la última revisión de un
  incidente) y cancela al que está en curso con esa `key`.
- Un trabajo que no ha empezado en `expire_s` segundos de reloj de pared se descarta.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

PRIORITY_OPEN, PRIORITY_RECOVERY, PRIORITY_CHAT, PRIORITY_CLOSE, PRIORITY_REPORT = range(5)


@dataclass
class Job:
    priority: int
    run: Callable[[], Awaitable[None]]
    key: str | None = None
    expire_s: float | None = None
    on_drop: Callable[[str], None] | None = None
    queued_at: float = field(default_factory=time.monotonic)
    seq: int = 0


class LlmQueue:
    def __init__(self) -> None:
        self._pending: list[Job] = []
        self._wake = asyncio.Event()
        self._seq = 0
        self._current: Job | None = None
        self._task: asyncio.Task[None] | None = None
        self._worker: asyncio.Task[None] | None = None
        self.dropped: list[tuple[str | None, str]] = []  # (key, motivo): para las pruebas

    def submit(self, job: Job) -> None:
        self._seq += 1
        job.seq = self._seq
        job.queued_at = time.monotonic()
        if job.key is not None:
            for old in [j for j in self._pending if j.key == job.key]:
                self._pending.remove(old)
                self._drop(old, "superseded")
            if self._current is not None and self._current.key == job.key and self._task:
                self._task.cancel()  # la de curso queda vieja: vLLM aborta al cerrarse la petición
        self._pending.append(job)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.ensure_future(self._loop())
        self._wake.set()

    def _drop(self, job: Job, reason: str) -> None:
        self.dropped.append((job.key, reason))
        log.info("dropped %s: %s", job.key, reason)
        if job.on_drop:
            job.on_drop(reason)

    def reset(self) -> None:
        """Nueva ejecución: se descarta lo pendiente y lo que está en curso."""
        for job in self._pending:
            self._drop(job, "reset")
        self._pending.clear()
        if self._task is not None:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            while not self._pending:
                self._wake.clear()
                await self._wake.wait()
            self._pending.sort(key=lambda j: (j.priority, j.seq))
            job = self._pending.pop(0)
            if job.expire_s is not None and time.monotonic() - job.queued_at > job.expire_s:
                self._drop(job, "expired")
                continue
            self._current = job
            self._task = asyncio.ensure_future(job.run())
            try:
                await self._task
            except asyncio.CancelledError:
                if self._task.cancelled():
                    self._drop(job, "cancelled")
                else:
                    raise
            except Exception:
                log.exception("assistant job failed")
            finally:
                self._current = self._task = None

    async def idle(self) -> None:
        """Espera a que no quede nada pendiente ni en curso (pruebas y herramientas)."""
        while self._pending or self._current is not None:
            await asyncio.sleep(0.01)
