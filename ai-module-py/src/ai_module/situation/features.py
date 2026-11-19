"""Características por segundo del monitor de situación, solo con lo observable (eventos del dron,
del radar, de la estación y de nuestro enlace; nunca la verdad).

Se agrupan los eventos del mundo (dominios `air` y `env`) por segundo entero de `sim_time`; al
llegar un evento de un segundo posterior se cierra el anterior y sale una fila. Solo salen filas
de los segundos que tienen eventos. En directo y sobre `events.jsonl` el resultado es el mismo.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# Telemetría del dron: solo llega si llega su paquete por nuestro enlace.
TELEMETRY_SOURCES = frozenset({"d1-gps", "d1-gnss", "d1-autopilot", "d1-bat"})
FRESH_S = 1.5  # un dato del dron vale si tiene menos de 1,5 s
RADAR_FRESH_S = 2.5  # el radar publica cada 2 s
RADAR_WINDOW = 3  # media de 3 trazas (6 s): una traza suelta a 2,5 km tiene σ ≈ 10 m
REFERENCE_WINDOW = 60  # mediana de 60 s para C/N0 y AGC
WIND_LIMIT_MPS = 12.0  # viento por encima del cual el dron no garantiza la ruta


def segment_distance(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Distancia del punto `p` al segmento `a`–`b`."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    u = 0.0 if length2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    u = max(0.0, min(1.0, u))
    return math.hypot(p[0] - (a[0] + u * dx), p[1] - (a[1] + u * dy))


def _median(values: deque[float]) -> float:
    return sorted(values)[len(values) // 2]


@dataclass
class FeatureRow:
    """Lo que ve el monitor en un segundo. `None` = sin dato."""

    t: float
    leg: int
    tele_gap_s: float
    gps_route_dev_m: float | None = None
    radar_route_dev_m: float | None = None  # media de las últimas trazas
    link_loss_pct: float | None = None
    cn0_dbhz: float | None = None
    agc_db: float | None = None
    wind_est_mps: float | None = None
    evidence_ids: dict[str, str] = field(default_factory=dict)  # por fuente, el último evento


class FeatureExtractor:
    """Convierte el flujo de eventos del mundo en una fila por segundo."""

    def __init__(self) -> None:
        self.waypoints: list[tuple[float, float]] = []
        self.reset()

    def reset(self) -> None:
        self.leg = 1
        self._second: int | None = None
        self._last: dict[str, dict[str, Any]] = {}
        self._last_ids: dict[str, str] = {}
        self._last_tele = 0.0
        self._radar: tuple[float, float, float] | None = None
        self._radar_window: deque[float] = deque(maxlen=RADAR_WINDOW)

    def set_plan(self, waypoints: list[dict[str, Any]]) -> None:
        self.waypoints = [(float(w["x"]), float(w["y"])) for w in waypoints]

    def push(self, event: dict[str, Any]) -> list[FeatureRow]:
        """Añade un evento (`type`, `source`, `sim_time`, `event_id`, `payload`). Devuelve la fila
        del segundo anterior si este evento lo cierra."""
        second = math.floor(event["sim_time"])
        rows: list[FeatureRow] = []
        if self._second is not None and second > self._second:
            row = self._close()
            if row is not None:
                rows.append(row)
        self._second = second
        self._apply(event)
        return rows

    def flush(self) -> list[FeatureRow]:
        """Cierra el segundo en curso (fin de la ejecución)."""
        row = self._close() if self._second is not None else None
        self._second = None
        return [row] if row is not None else []

    def _apply(self, event: dict[str, Any]) -> None:
        kind, payload = event["type"], event["payload"]
        if kind == "MissionPlanned":
            self.set_plan(payload["waypoints"])
        elif kind == "WaypointReached" and self.waypoints:
            self.leg = min(int(payload["index"]) + 1, len(self.waypoints) - 1)
        if event["source"] in TELEMETRY_SOURCES:
            self._last_tele = float(event["sim_time"])
        if kind == "TrackUpdated":
            self._radar = (payload["x"], payload["y"], float(event["sim_time"]))
        self._last[kind] = payload
        self._last_ids[kind] = event["event_id"]

    def _close(self) -> FeatureRow | None:
        if len(self.waypoints) < 2 or self._second is None:
            return None
        t = float(self._second)
        a, b = self.waypoints[self.leg - 1], self.waypoints[self.leg]
        fresh = t - self._last_tele < FRESH_S
        row = FeatureRow(t=t, leg=self.leg, tele_gap_s=round(t - self._last_tele, 1))
        ids = self._last_ids
        gps = self._last.get("PositionUpdated")
        if fresh and gps and gps.get("x") is not None:
            row.gps_route_dev_m = segment_distance((gps["x"], gps["y"]), a, b)
            row.evidence_ids["gps"] = ids["PositionUpdated"]
        if self._radar and t - self._radar[2] < RADAR_FRESH_S:
            self._radar_window.append(segment_distance(self._radar[:2], a, b))
            row.evidence_ids["radar"] = ids["TrackUpdated"]
        if self._radar_window:
            row.radar_route_dev_m = sum(self._radar_window) / len(self._radar_window)
        autopilot = self._last.get("AutopilotStatus")
        if fresh and autopilot:
            row.wind_est_mps = autopilot["wind_est_speed_mps"]
            row.evidence_ids["autopilot"] = ids["AutopilotStatus"]
        gnss = self._last.get("GnssStatus")
        if fresh and gnss:
            row.cn0_dbhz, row.agc_db = gnss["cn0_dbhz"], gnss["agc_db"]
            row.evidence_ids["gnss"] = ids["GnssStatus"]
        link = self._last.get("LinkStatus")
        if link:
            row.link_loss_pct = link.get("packet_loss_pct")
            row.evidence_ids["link"] = ids["LinkStatus"]
        return row


class GnssReference:
    """Referencia de C/N0 y AGC: la mediana de los últimos 60 s, **congelada mientras el GPS no es
    fiable** (una mediana que siguiera actualizándose subiría con el engaño y lo dejaría de ver)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._cn0: deque[float] = deque(maxlen=REFERENCE_WINDOW)
        self._agc: deque[float] = deque(maxlen=REFERENCE_WINDOW)
        self.cn0: float | None = None
        self.agc: float | None = None

    def deltas(self, row: FeatureRow) -> tuple[float | None, float | None]:
        """C/N0 y AGC menos su referencia (la primera lectura es su propia referencia)."""
        if row.cn0_dbhz is None or row.agc_db is None:
            return None, None
        if self.cn0 is None or self.agc is None:
            self.cn0, self.agc = row.cn0_dbhz, row.agc_db
        return row.cn0_dbhz - self.cn0, row.agc_db - self.agc

    def update(self, row: FeatureRow, reliable: bool) -> None:
        if not reliable or row.cn0_dbhz is None or row.agc_db is None:
            return
        self._cn0.append(row.cn0_dbhz)
        self._agc.append(row.agc_db)
        self.cn0, self.agc = _median(self._cn0), _median(self._agc)
