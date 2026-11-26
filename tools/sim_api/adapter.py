"""Adaptador de la API del simulador al formato del bus: lo que hará el mediador de cada asset.

Lee los mensajes nativos de los assets (`contracts/api/README.md`), los ordena entre assets con las
marcas de agua de los `heartbeat` y reconstruye los eventos del contrato del bus (`EventDraft`) con
`poc_contracts.topics`. Los de ciclo de vida (`RunStarted`, `RunReset`, `RunFinished`) salen una
sola vez como `Lifecycle`: la API no lleva el nombre del escenario, así que no se reconstruye un
`SimulationStarted` completo.

Solo depende de `poc_contracts`: no importa nada de la plataforma ni del módulo de IA.
"""

from dataclasses import dataclass, field
from typing import Any

from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.topics import asset_for, source_for, topic_for

LIFECYCLE = ("RunStarted", "RunReset", "RunFinished")
ASSETS = ("d1", "radar-1", "meteo-1", "gcs-1")

# Orden de los eventos de un mismo instante en el simulador (§8.5 del contrato): misión, GPS,
# receptor, autopiloto, radar, meteo, enlace, batería.
_T = EventType
TYPE_ORDER: dict[str, int] = {
    **{t.value: 0 for t in (_T.MISSION_PLANNED, _T.MISSION_STARTED, _T.WAYPOINT_REACHED)},
    _T.MISSION_COMPLETED.value: 0,
    _T.POSITION_UPDATED.value: 1,
    _T.GNSS_STATUS.value: 2,
    _T.AUTOPILOT_STATUS.value: 3,
    _T.TRACK_UPDATED.value: 4,
    _T.WIND_REPORTED.value: 5,
    _T.LINK_STATUS.value: 6,
    _T.BATTERY_STATUS.value: 7,
}


@dataclass(frozen=True)
class Lifecycle:
    """Principio, reinicio o fin de una ejecución."""

    kind: str
    run_id: str
    sim_time: float
    data: dict[str, Any]


def to_event(message: dict[str, Any]) -> EventDraft:
    """Un mensaje nativo de un asset como evento del bus (sin `seq` ni `ingestion_time`)."""
    event_type = EventType(message["type"])
    topic = topic_for(event_type)
    _, _, _, domain, routing, *_ = topic.split(".")
    return EventDraft(
        event_id=message["id"],
        topic=topic,
        type=event_type,
        source=source_for(event_type),
        asset=asset_for(domain, routing),
        sim_time=message["sim_time"],
        event_time=message["time_utc"],
        causation_id=None,
        ephemeral=False,
        payload=message["data"],
    )


def parse(message: dict[str, Any]) -> EventDraft | Lifecycle:
    if message["type"] in LIFECYCLE:
        return Lifecycle(message["type"], message["run_id"], message["sim_time"], message["data"])
    return to_event(message)


@dataclass(order=True)
class _Item:
    sim_time: float
    order: int
    seq: int
    value: EventDraft | Lifecycle = field(compare=False)
    run_id: str = field(compare=False, default="")
    key: str = field(compare=False, default="")


class Merger:
    """Mezcla los flujos de varios assets en el orden del simulador, sin perder ni duplicar nada.

    Un mensaje solo sale cuando todos los assets han llegado más allá de su instante: el `sim_time`
    de un `heartbeat` (o de un mensaje) de un asset dice que de ese asset no vendrá nada anterior.
    Las ejecuciones se sueltan una tras otra; cuando todos los assets dicen `RunFinished` se suelta
    el resto de esa ejecución.
    """

    def __init__(self, assets: tuple[str, ...] = ASSETS) -> None:
        self.assets = assets
        self._pending: dict[str, list[_Item]] = {}
        self._runs: list[str] = []
        self._mark: dict[str, tuple[str, float]] = {}  # asset -> (ejecución, instante)
        self._finished: dict[str, set[str]] = {}
        self._seen_lifecycle: set[str] = set()

    def _touch(self, asset: str, run_id: str | None, sim_time: float, *, restart: bool) -> None:
        if run_id is None:
            return
        if run_id not in self._runs:
            self._runs.append(run_id)
        previous = self._mark.get(asset)
        if previous and previous[0] == run_id and not restart:
            sim_time = max(sim_time, previous[1])
        self._mark[asset] = (run_id, sim_time)

    def feed(self, asset: str, event: str, data: dict[str, Any]) -> list[EventDraft | Lifecycle]:
        """Un evento SSE de un asset (`message` o `heartbeat`); devuelve lo que ya puede salir."""
        if event == "heartbeat":
            self._touch(asset, data["run_id"], data["sim_time"], restart=False)
        elif event == "message":
            self._add(asset, data)
        return self._release()

    def _add(self, asset: str, message: dict[str, Any]) -> None:
        run_id, kind = message["run_id"], message["type"]
        self._touch(asset, run_id, message["sim_time"], restart=kind in LIFECYCLE)
        if kind == "RunFinished":
            self._finished.setdefault(run_id, set()).add(asset)
        item = _Item(
            sim_time=message["sim_time"],
            order=(-1 if kind == "RunStarted" else 99) if kind in LIFECYCLE else TYPE_ORDER[kind],
            seq=message["seq"],
            value=parse(message),
            run_id=run_id,
            key=message["id"] if kind in LIFECYCLE else "",
        )
        self._pending.setdefault(run_id, []).append(item)

    def _limit(self, run_id: str) -> float:
        """Hasta qué instante (sin incluirlo) se puede soltar esa ejecución."""
        if len(self._finished.get(run_id, ())) == len(self.assets):
            return float("inf")
        index = self._runs.index(run_id)
        limit = float("inf")
        for asset in self.assets:
            mark = self._mark.get(asset)
            if mark is None:
                return float("-inf")
            if self._runs.index(mark[0]) < index:
                return float("-inf")
            if self._runs.index(mark[0]) == index:
                limit = min(limit, mark[1])
        return limit

    def _release(self, *, everything: bool = False) -> list[EventDraft | Lifecycle]:
        out: list[EventDraft | Lifecycle] = []
        for run_id in list(self._runs):
            limit = float("inf") if everything else self._limit(run_id)
            items = sorted(self._pending.get(run_id, []))
            ready = [i for i in items if i.sim_time < limit or limit == float("inf")]
            self._pending[run_id] = items[len(ready) :]  # `items` está ordenado: es un prefijo
            for item in ready:
                if item.key:  # el mismo mensaje de ciclo de vida llega por cada asset
                    if item.key in self._seen_lifecycle:
                        continue
                    self._seen_lifecycle.add(item.key)
                out.append(item.value)
            if self._pending[run_id]:
                break  # las ejecuciones se sueltan en orden
        return out

    def flush(self) -> list[EventDraft | Lifecycle]:
        """Suelta todo lo que quede (fin de la conexión)."""
        return self._release(everything=True)
