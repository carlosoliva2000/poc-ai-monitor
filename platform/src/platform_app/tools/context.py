"""Contexto común de las tools de datos: el único punto por el que leen el timeline.

Aquí se imponen las dos garantías de las tools:
- **Corte temporal:** `until` efectivo = mínimo entre lo pedido y el instante actual de la
  simulación; nunca se devuelve un evento con `sim_time` posterior.
- **Sin dominio `sim`:** nunca se devuelven eventos del dominio `sim` (estado del reproductor,
  modo interactivo, fallos inyectados).
Nada de este paquete lee `truth.json` ni `labels.json`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.topics import SIM_DOMAIN, topic_domain

from ..timeline import Timeline


class ToolFailure(Exception):
    """Error de una tool; el mensaje (en español) llega al agente."""


@dataclass(frozen=True)
class ToolContext:
    timeline: Timeline
    now: Callable[[], float]
    """Instante actual de la simulación (`sim_time`)."""

    def cutoff(self, until: float | None = None) -> float:
        """`until` efectivo: el pedido, sin pasar nunca del instante actual."""
        now = self.now()
        return now if until is None else min(until, now)

    def events(
        self,
        *,
        source: str | None = None,
        type: EventType | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int | None = None,
    ) -> tuple[list[Envelope], bool]:
        """Eventos visibles para el agente (con el corte temporal y sin el dominio `sim`).

        Con `limit` devuelve los últimos; el segundo valor dice si se ha recortado.
        """
        found, _ = self.timeline.query(
            source=source, type=type, since=since, until=self.cutoff(until)
        )
        visible = [e for e in found if topic_domain(e.topic) != SIM_DOMAIN]
        if limit is not None and len(visible) > limit:
            return visible[len(visible) - limit :], True
        return visible, False

    def latest(self, type: EventType) -> Envelope | None:
        found, _ = self.events(type=type, limit=1)
        return found[0] if found else None


def format_t(sim_time: float) -> str:
    """`T+mm:ss` (los minutos pueden pasar de 99)."""
    total = int(sim_time)
    return f"T+{total // 60:02d}:{total % 60:02d}"
