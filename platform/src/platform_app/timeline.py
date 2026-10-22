"""Timeline: historial en memoria de los eventos no efímeros de una ejecución.

Guarda los sobres en orden de publicación (`seq`) y mantiene índices por `source` y por `type`.
Es lo único que consultan las tools de datos y `GET /api/timeline`. Se vuelca a
`runs/<escenario>/<run_id>/timeline.jsonl` (una línea por `Envelope`). El volcado es incremental:
después de `dump`, cada evento nuevo (la última respuesta del monitor, el informe, los chats) se
añade al final del fichero, hasta que el timeline se vacía.
"""

from pathlib import Path

from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope


class Timeline:
    def __init__(self) -> None:
        self._events: list[Envelope] = []
        self._by_source: dict[str, list[Envelope]] = {}
        self._by_type: dict[EventType, list[Envelope]] = {}
        self._by_id: dict[str, Envelope] = {}
        self._sink: Path | None = None  # fichero al que se añaden los eventos nuevos tras `dump`

    def __len__(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()
        self._by_source.clear()
        self._by_type.clear()
        self._by_id.clear()
        self._sink = None

    def add(self, event: Envelope) -> None:
        self._events.append(event)
        self._by_source.setdefault(event.source, []).append(event)
        self._by_type.setdefault(event.type, []).append(event)
        self._by_id[event.event_id] = event
        if self._sink is not None:
            with self._sink.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")

    def get(self, event_id: str) -> Envelope | None:
        return self._by_id.get(event_id)

    def all(self) -> list[Envelope]:
        """Copia de todos los eventos, en orden de publicación."""
        return list(self._events)

    def query(
        self,
        *,
        source: str | None = None,
        type: EventType | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int | None = None,
    ) -> tuple[list[Envelope], bool]:
        """Eventos que cumplen los filtros, ordenados por `sim_time` (y `seq` a igualdad).

        `since` y `until` son inclusivos y se aplican a `sim_time`. Con `limit` se devuelven
        los **últimos** `limit`. El segundo valor indica si había más y se han recortado.
        """
        if source is not None and type is not None:
            by_source, by_type = self._by_source.get(source, []), self._by_type.get(type, [])
            candidates = by_source if len(by_source) <= len(by_type) else by_type
        elif source is not None:
            candidates = self._by_source.get(source, [])
        elif type is not None:
            candidates = self._by_type.get(type, [])
        else:
            candidates = self._events
        found = [
            e
            for e in candidates
            if (source is None or e.source == source)
            and (type is None or e.type == type)
            and (since is None or e.sim_time >= since)
            and (until is None or e.sim_time <= until)
        ]
        found.sort(key=lambda e: (e.sim_time, e.seq))
        truncated = limit is not None and len(found) > limit
        if truncated:
            found = found[len(found) - limit :] if limit > 0 else []
        return found, truncated

    def dump(self, path: Path) -> Path:
        """Escribe `timeline.jsonl` (crea las carpetas que falten) y, a partir de aquí, añade a él
        cada evento nuevo."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(e.model_dump_json() + "\n" for e in self._events)
        path.write_text(lines, encoding="utf-8")
        self._sink = path
        return path
