"""Lo que el asistente del alumno guarda del bus en su propio proceso (regla de conexión del §2).

Solo admite los tipos de evento de `ALLOWED_TYPES`: lo demás (dominio `sim`, chat del instructor,
verdad del ejercicio) se descarta aquí aunque llegara, como segunda barrera tras sus suscripciones.
Eventos como diccionarios (`Envelope.model_dump(mode="json")` o una línea de `events.jsonl`).
"""

from collections import defaultdict
from typing import Any

# El mundo que ve el monitor, los incidentes y, para los chats, lo que dice el operador.
WORLD_TYPES = frozenset(
    {
        "MissionPlanned",
        "MissionCompleted",
        "PositionUpdated",
        "TrackUpdated",
        "WindReported",
        "LinkStatus",
        "BatteryStatus",
        "GnssStatus",
        "AutopilotStatus",
    }
)
ALLOWED_TYPES = WORLD_TYPES | {"IncidentUpdated"}
READINGS = ("PositionUpdated", "TrackUpdated", "WindReported", "LinkStatus", "BatteryStatus",
            "GnssStatus", "AutopilotStatus")  # fmt: skip


class Store:
    def __init__(self, cn0_nominal_dbhz: float = 45.0, agc_nominal_db: float = 0.0) -> None:
        """`cn0_nominal_dbhz` y `agc_nominal_db`: el receptor sano, de la configuración de los
        activos (`situation/assets.yaml`; en CITADEL, del inventario)."""
        self.cn0_nominal_dbhz = cn0_nominal_dbhz
        self.agc_nominal_db = agc_nominal_db
        self.reset()

    def reset(self) -> None:
        self.now = 0.0
        self.route: list[tuple[float, float]] = []
        self.last: dict[str, tuple[float, dict[str, Any]]] = {}  # tipo -> (sim_time, payload)
        self.revisions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.event_ids: dict[tuple[str, int], str] = {}  # (incident_id, revision) -> event_id
        self.texts: dict[str, str] = {}  # incidente -> el último texto que el asistente publicó
        self.history: dict[str, list[tuple[str, str]]] = defaultdict(
            list
        )  # chat -> (pregunta, respuesta)
        self.report: str | None = None  # el informe del asistente, para el chat del informe
        self.mission_end: dict[str, Any] | None = None  # `MissionCompleted` (t y motivo)
        self.radar_track: list[
            tuple[float, float, float]
        ] = []  # (t, x, y) del radar, para el informe

    def observe(self, event: dict[str, Any]) -> bool:
        """Guarda el evento si es de los permitidos; devuelve si lo guardó."""
        kind = event["type"]
        if kind not in ALLOWED_TYPES:
            return False
        payload = event["payload"]
        self.now = max(self.now, float(event["sim_time"]))
        if kind == "MissionPlanned":
            self.route = [(w["x"], w["y"]) for w in payload["waypoints"]]
        elif kind == "MissionCompleted":
            self.mission_end = {"t": float(event["sim_time"]), **payload}
        elif kind == "IncidentUpdated":
            self.revisions[payload["incident_id"]].append(payload)
            self.event_ids[(payload["incident_id"], payload["revision"])] = event["event_id"]
        else:
            self.last[kind] = (float(event["sim_time"]), payload)
            if kind == "TrackUpdated":
                self.radar_track.append((float(event["sim_time"]), payload["x"], payload["y"]))
        return True

    def reading(self, kind: str, max_age_s: float) -> dict[str, Any] | None:
        """La última lectura de ese tipo si no tiene más de `max_age_s` segundos."""
        entry = self.last.get(kind)
        if entry is None or self.now - entry[0] > max_age_s:
            return None
        return entry[1]

    def opening(self, incident_id: str) -> dict[str, Any] | None:
        revisions = self.revisions.get(incident_id)
        return revisions[0] if revisions else None

    def snapshot(self) -> "Store":
        """Una copia de lo que se sabe ahora: la pregunta de un chat se contesta con la situación
        del momento en que se hizo, aunque la cola tarde en llegar a ella."""
        copy = Store(self.cn0_nominal_dbhz, self.agc_nominal_db)
        copy.now = self.now
        copy.route = list(self.route)
        copy.last = dict(self.last)
        copy.revisions = defaultdict(list, {k: list(v) for k, v in self.revisions.items()})
        copy.event_ids = dict(self.event_ids)
        copy.texts = dict(self.texts)
        copy.report = self.report
        copy.mission_end = self.mission_end
        copy.radar_track = list(self.radar_track)
        return copy
