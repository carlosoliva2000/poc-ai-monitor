"""Bus de eventos en memoria, con comodines al estilo NATS.

Modelo de entrega (pensado para usarse desde el reproductor y desde el WebSocket sin bloquear
el bucle de asyncio):

- `publish` es **síncrono** y no espera a nadie: pone `seq` e `ingestion_time`, guarda el
  evento en el timeline (si no es efímero) y lo entrega a los suscriptores.
- Los handlers **síncronos** se ejecutan dentro de `publish`. Deben ser rápidos y no bloquear
  (p. ej. `put_nowait` en una cola). Si fallan, se registra el error y se sigue.
- Los handlers **asíncronos** (`async def`) no se pueden esperar desde `publish`: cada uno tiene
  su propia cola y una tarea que la vacía en orden, creada con `asyncio.create_task` en el
  bucle en marcha. Por eso `publish` con suscriptores asíncronos necesita un bucle de asyncio
  activo (si no lo hay, se registra el error y el evento no se entrega a ese handler).
- Si un handler publica a su vez (p. ej. un monitor que responde a una detección), el evento
  nuevo recibe su `seq` al momento pero se entrega **después** de terminar la entrega en curso.
  Así todos los suscriptores ven los eventos en orden de `seq`.
- `reset` vacía el timeline y reinicia `seq`; las suscripciones se conservan.
"""

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.topics import topic_matches, validate_pattern

from .timeline import Timeline

log = logging.getLogger(__name__)

Handler = Callable[[Envelope], None] | Callable[[Envelope], Awaitable[None]]


def wall_time_iso() -> str:
    """Reloj de pared en ISO 8601 UTC con milisegundos (`ingestion_time`)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass(eq=False)
class Subscription:
    pattern: str
    handler: Handler
    is_async: bool
    pending: deque[Envelope] = field(default_factory=deque)
    draining: bool = False


class Bus:
    def __init__(
        self,
        timeline: Timeline | None = None,
        *,
        now_iso: Callable[[], str] = wall_time_iso,
    ) -> None:
        self.timeline = timeline if timeline is not None else Timeline()
        self._now_iso = now_iso
        self._seq = 0
        self._subs: list[Subscription] = []
        self._outbox: deque[Envelope] = deque()
        self._delivering = False

    @property
    def last_seq(self) -> int:
        return self._seq

    def subscribe(self, pattern: str, handler: Handler) -> Subscription:
        """Suscribe `handler` a los topics que casan con `pattern` (`*` y `>` como en NATS)."""
        validate_pattern(pattern)
        sub = Subscription(pattern, handler, inspect.iscoroutinefunction(handler))
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)
            sub.pending.clear()

    def reset(self) -> None:
        """Vacía el timeline y vuelve a `seq = 1`. Las suscripciones se mantienen."""
        self.timeline.clear()
        self._seq = 0

    def publish(self, event: EventDraft | Envelope) -> Envelope:
        """Pone `seq` e `ingestion_time`, guarda en el timeline (salvo efímeros) y entrega."""
        self._seq += 1
        data = event.model_dump(exclude={"seq", "ingestion_time"})
        envelope = Envelope(seq=self._seq, ingestion_time=self._now_iso(), **data)
        if not envelope.ephemeral:
            self.timeline.add(envelope)
        self._outbox.append(envelope)
        if not self._delivering:
            self._deliver()
        return envelope

    def _deliver(self) -> None:
        self._delivering = True
        try:
            while self._outbox:
                envelope = self._outbox.popleft()
                for sub in list(self._subs):
                    if topic_matches(sub.pattern, envelope.topic):
                        self._send(sub, envelope)
        finally:
            self._delivering = False

    def _send(self, sub: Subscription, envelope: Envelope) -> None:
        if not sub.is_async:
            try:
                sub.handler(envelope)
            except Exception:
                log.exception("handler failed for %s on %s", envelope.event_id, sub.pattern)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.error("async handler on %s needs a running event loop", sub.pattern)
            return
        sub.pending.append(envelope)
        if not sub.draining:
            sub.draining = True
            loop.create_task(self._drain(sub))

    async def _drain(self, sub: Subscription) -> None:
        try:
            while sub.pending:
                envelope = sub.pending.popleft()
                try:
                    await sub.handler(envelope)  # type: ignore[misc]
                except Exception:
                    log.exception("async handler failed for %s", envelope.event_id)
        finally:
            sub.draining = False
