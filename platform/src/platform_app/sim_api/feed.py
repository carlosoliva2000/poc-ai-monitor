"""Registro de mensajes por asset: lo que se ha publicado, con su `seq`, para leer y reanudar.

Se suscribe al bus de la plataforma y traduce cada evento del mundo (`air`, `env`) al formato
propio del asset (`AssetMessage`). Cada asset tiene un registro de solo añadir con `seq`
creciente que **no se reinicia** al cargar otra ejecución; los lectores (histórico y flujo SSE)
leen por índice, así que un cliente lento no pierde mensajes (solo se retrasa).

El bus llama desde el hilo que publica y las rutas leen desde el bucle de asyncio: un cerrojo por
registro protege las dos cosas.
"""

import threading
from collections.abc import Callable

from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.payloads import Inject
from poc_contracts.sim_api import AssetMessage

from ..bus import Bus
from .assets import (
    ASSET_IDS,
    ASSET_OF_TYPE,
    INSTRUCTOR,
    INSTRUCTOR_TYPES,
    LIFECYCLE_OF_TYPE,
    subject_of,
)

RETENTION = 200_000  # mensajes por asset
KEPT_RUNS = 2  # la ejecución en curso y la anterior
MAX_EXAMINED = 50_000  # por página, como tope de trabajo con `types`


class Log:
    """Registro de solo añadir de un asset (o de la parte del instructor)."""

    def __init__(self, cap: int = RETENTION) -> None:
        self.cap = cap
        self._messages: list[AssetMessage] = []
        self._base = 1  # `seq` del primer mensaje que se conserva
        self._next = 1
        self._lock = threading.Lock()

    def add(self, make: Callable[[int], AssetMessage]) -> AssetMessage:
        with self._lock:
            message = make(self._next)
            self._messages.append(message)
            self._next += 1
            extra = len(self._messages) - self.cap
            if extra > 0:
                del self._messages[:extra]
                self._base += extra
            return message

    def drop_run(self, run_id: str) -> None:
        """Quita los mensajes de una ejecución (están al principio: el registro va por orden)."""
        with self._lock:
            n = 0
            while n < len(self._messages) and self._messages[n].run_id == run_id:
                n += 1
            del self._messages[:n]
            self._base += n

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._next - 1

    @property
    def first_available(self) -> int:
        with self._lock:
            return self._base

    def read(self, since: int, limit: int | None = None) -> list[AssetMessage]:
        """Los mensajes con `seq > since` que se conservan (como mucho `limit`)."""
        with self._lock:
            start = max(since + 1, self._base) - self._base
            end = None if limit is None else start + limit
            return self._messages[start:end]


class Feed:
    """Los registros de los cuatro assets y de la parte del instructor, alimentados por el bus."""

    def __init__(self, bus: Bus, retention: int = RETENTION) -> None:
        self.logs: dict[str, Log] = {a: Log(retention) for a in (*ASSET_IDS, INSTRUCTOR)}
        self.run_id: str | None = None
        self.runs: list[str] = []
        self.last: dict[str, dict[str, AssetMessage]] = {a: {} for a in ASSET_IDS}
        self.injects: list[Inject] = []
        self._subscription = bus.subscribe("citadel.>", self.on_event)

    # --- Entrada ------------------------------------------------------------------------------

    def _message(self, asset_id: str, event: Envelope, run_id: str, type_: str, data: dict):
        subject = subject_of(asset_id) if asset_id in ASSET_IDS else INSTRUCTOR

        def make(seq: int) -> AssetMessage:
            return AssetMessage(
                seq=seq,
                run_id=run_id,
                asset_id=asset_id,
                subject=event.asset or subject,
                type=type_,
                id=event.event_id,
                sim_time=event.sim_time,
                time_utc=event.event_time,
                received_utc=event.ingestion_time,
                data=data,
            )

        return self.logs[asset_id].add(make)

    def on_event(self, event: Envelope) -> None:
        kind = event.type
        if kind in LIFECYCLE_OF_TYPE:
            self._lifecycle(event, LIFECYCLE_OF_TYPE[kind])
        elif kind in ASSET_OF_TYPE and self.run_id is not None:
            asset_id = ASSET_OF_TYPE[kind]
            message = self._message(asset_id, event, self.run_id, kind.value, event.payload)
            self.last[asset_id][message.type] = message
        elif kind in INSTRUCTOR_TYPES and self.run_id is not None:
            if kind == EventType.EXERCISE_INJECTS:
                self.injects = [Inject.model_validate(i) for i in event.payload["injects"]]
            self._message(INSTRUCTOR, event, self.run_id, kind.value, event.payload)

    def _lifecycle(self, event: Envelope, name: str) -> None:
        if name == "RunStarted":
            run_id = str(event.payload["run_id"])
            self.runs.append(run_id)
            while len(self.runs) > KEPT_RUNS:
                old = self.runs.pop(0)
                for log in self.logs.values():
                    log.drop_run(old)
            self.run_id = run_id
            self.last = {a: {} for a in ASSET_IDS}
            self.injects = []
            data = {"duration_s": event.payload["duration_s"]}
        else:
            data = {}
        if self.run_id is None:
            return
        for asset_id in (*ASSET_IDS, INSTRUCTOR):
            self._message(asset_id, _with_id(event, self.run_id, name), self.run_id, name, data)

    # --- Lectura ------------------------------------------------------------------------------

    def page(
        self,
        asset_id: str,
        since: int,
        limit: int,
        types: set[str] | None,
        run_id: str | None,
    ) -> tuple[list[AssetMessage], int, bool]:
        """Una página: mensajes, `next` (el último `seq` examinado) y `has_more`."""
        log = self.logs[asset_id]
        run = run_id or self.run_id
        out: list[AssetMessage] = []
        examined = since
        cursor = since
        while True:
            chunk = log.read(cursor, 1000)
            if not chunk:
                return out, examined, False
            for message in chunk:
                examined = message.seq
                if message.run_id == run and (types is None or message.type in types):
                    out.append(message)
                    if len(out) == limit:
                        return out, examined, examined < log.last_seq
                if examined - since >= MAX_EXAMINED:
                    return out, examined, examined < log.last_seq
            cursor = examined


def _with_id(event: Envelope, run_id: str, name: str) -> Envelope:
    """El mismo evento con el id de ciclo de vida de la API (`run-<run_id>-RunStarted`)."""
    return event.model_copy(update={"event_id": f"run-{run_id}-{name}", "asset": None})
