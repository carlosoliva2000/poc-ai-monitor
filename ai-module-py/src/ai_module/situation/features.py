"""Características por segundo del monitor de situación, solo con lo observable (eventos del dron,
del radar, de la estación y de nuestro enlace; nunca la verdad).

Se agrupan los eventos del mundo (dominios `air` y `env`) por segundo entero de `sim_time`; al
llegar un evento de un segundo posterior se cierra el anterior y sale **una fila por segundo**
(los segundos sin eventos repiten el último estado, con las edades creciendo). La misma clase
calcula las características en directo y sobre `events.jsonl` (y las del entrenamiento): ninguna
depende de la salida de las tablas ni del instante absoluto.

Cada característica es un número o `None` (sin dato). Los valores de una fuente solo valen mientras
su último mensaje es reciente (`FRESH_PERIODS` periodos); las edades (`age_*`) dicen cuánto hace
del último.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
Point = tuple[float, float]

# Un valor de una fuente vale mientras su último mensaje tiene menos de 1,5 periodos de esa fuente
# (el periodo sale de la configuración de los activos: `assets.yaml`).
FRESH_PERIODS = 1.5
SOURCES = ("gps", "gnss", "autopilot", "radar", "link", "meteo", "battery")
TELEMETRY = ("gps", "gnss", "autopilot", "battery")  # lo que solo llega si llega el paquete
EVENT_SOURCE = {  # tipo de evento → fuente
    "PositionUpdated": "gps", "GnssStatus": "gnss", "AutopilotStatus": "autopilot",
    "TrackUpdated": "radar", "LinkStatus": "link", "WindReported": "meteo",
    "BatteryStatus": "battery",
}  # fmt: skip
RADAR_WINDOW = 2  # media de las últimas 2 trazas **reales** del radar (cada 2 s): 4 s de memoria
CUSUM_ALLOWANCE_M = 12.0  # holgura del CUSUM GPS–radar: el ruido normal de la discrepancia
CUSUM_MAX_M = 5000.0
CUSUM_ALLOWANCE_SIGMA = 2.0  # holgura del CUSUM en múltiplos del error esperado (σ combinada)
CUSUM_MAX_SIGMA = 500.0
BASE_S = 60.0  # línea base de C/N0 y AGC: la mediana de los primeros 60 s con receptor
SLOW_S = 360.0  # referencia lenta: la mediana de los últimos 300 s, sin el último minuto
SLOW_SKIP_S = 60.0
SLOW_MIN_S = 90.0
LINK_BASE_SAMPLES = 6  # línea base del enlace: los 6 primeros mensajes
MIN_SIGMA_REL = 0.25  # el error esperado del GPS no baja de esta fracción del nominal
HISTORY_S = 31  # segundos que se recuerdan de cada serie para tendencias y máximos
AGE_CAP_S = 1000.0
MIN_SPEED_FOR_COURSE_MPS = 1.0
SETTLED_MPS = (
    1.0  # por debajo de esta velocidad sobre el suelo, el dron ya está parado en su punto de espera
)

FEATURES = (
    # edades (s desde el último mensaje de cada fuente) y hueco de la telemetría
    "age_gps", "age_gnss", "age_autopilot", "age_radar", "age_link", "age_meteo", "age_battery",
    "tele_gap_s",
    # receptor GPS
    "gps_fix_3d", "gps_sats", "gps_hdop", "gps_hacc_m",
    "cn0_dbhz", "agc_db", "cn0_vs_base_db", "agc_vs_base_db", "cn0_vs_slow_db", "agc_vs_slow_db",
    # distancia a la referencia del modo, tendencias y retraso del tramo
    "gps_dev_m", "radar_dev_m", "gps_dev_slope", "radar_dev_slope", "gps_dev_max30",
    "radar_dev_max30", "gps_delay_s", "radar_delay_s", "gps_delay_rate", "radar_delay_rate",
    # discrepancia GPS–radar
    "gps_radar_m", "gps_radar_avg_m", "gps_radar_cusum_m",
    # autopiloto, viento y estación
    "mode_hold", "mode_return", "mode_land", "airspeed_mps", "ground_speed_mps", "speed_gap_mps",
    "heading_course_deg", "wind_est_mps", "wind_est_mean5", "innovation_m", "innovation_max10",
    "station_wind_mps", "wind_est_minus_station", "wind_dir_diff_deg",
    # enlace
    "link_loss_pct", "link_rssi_dbm", "link_latency_ms",
    # radar
    "radar_speed_mps", "radar_range_ratio",
    # batería
    "battery_pct", "battery_power_w", "battery_time_s", "home_dist_m", "home_time_ratio",
    "pct_per_km",
)  # fmt: skip

# Relativas (E7b, paso 2b): sin unidades del dron ni del sensor concretos. Se calculan con la
# configuración de los activos (`assets.yaml`), que solo entra a través de estos cocientes.
RELATIVE = (
    # antigüedad en periodos de cada fuente
    "age_gps_p", "age_gnss_p", "age_autopilot_p", "age_radar_p", "age_link_p", "age_meteo_p",
    "age_battery_p", "tele_gap_p",
    # viento y velocidades respecto al dron
    "wind_est_over_limit", "wind_est_over_airspeed", "wind_est_mean5_over_limit",
    "station_wind_over_limit", "station_wind_over_airspeed", "wind_diff_over_limit",
    "airspeed_over_max", "airspeed_over_cruise", "ground_speed_over_cruise",
    "speed_gap_over_max", "radar_speed_over_cruise",
    # desviaciones en múltiplos del error esperado de cada sensor
    "gps_dev_sigma", "radar_dev_sigma", "gps_dev_sigma_max30", "radar_dev_sigma_max30",
    "gps_dev_slope_cruise", "radar_dev_slope_cruise", "gps_radar_sigma", "gps_radar_avg_sigma",
    "gps_radar_cusum_sigma", "innovation_sigma", "innovation_max10_sigma",
    # receptor frente a su referencia nominal
    "cn0_vs_nominal_db", "agc_vs_nominal_db",
    # enlace frente a su línea base
    "link_latency_vs_base", "link_rssi_vs_base_db",
)  # fmt: skip
# Error esperado de cada posición, en metros (1 eje): lo usa la tabla determinista de la situación
# del dron para dar un margen a los umbrales de 25 y 15 m.
ERRORS = ("gps_sigma_m", "radar_sigma_m")
FEATURES = FEATURES + RELATIVE + ERRORS


@dataclass(frozen=True)
class Assets:
    """Lo que el monitor conoce de antemano de sus activos (configuración, no eventos): el radar,
    el dron, los periodos de las fuentes y el receptor. Solo entra en las características a través
    de cocientes (la distancia al radar entre su alcance, el viento entre el límite del dron…),
    nunca como valores sueltos."""

    radar_x: float = 0.0
    radar_y: float = 0.0
    radar_max_range_m: float = 6000.0
    radar_sigma0_m: float = 5.0
    radar_sigma_per_km_m: float = 2.0
    max_airspeed_mps: float = 17.0
    wind_limit_mps: float = 12.0
    cruise_mps: float = 15.0
    gps_period_s: float = 1.0  # también el de `GnssStatus` y `AutopilotStatus`
    radar_period_s: float = 2.0
    link_period_s: float = 5.0
    meteo_period_s: float = 10.0
    battery_period_s: float = 10.0
    gps_sigma_m: float = 1.53  # σ nominal de la posición del receptor
    cn0_nominal_dbhz: float = 45.0
    agc_nominal_db: float = 0.0

    def period(self, source: str) -> float:
        """Periodo (s) de una fuente; el receptor y el autopiloto van con el GPS."""
        return (
            self.gps_period_s
            if source in ("gnss", "autopilot")
            else getattr(self, f"{source}_period_s")
        )


def load_assets(path: Path = HERE / "assets.yaml") -> Assets:
    """Lee `assets.yaml`; lo que falte (ficheros anteriores al paso 2b) queda por defecto."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    radar, drone = raw["radar"], raw.get("drone", {})
    periods, gnss = raw.get("periods_s", {}), raw.get("gnss", {})
    d = Assets()
    return Assets(
        float(radar["x"]), float(radar["y"]), float(radar["max_range_m"]),
        radar_sigma0_m=float(radar.get("sigma0_m", d.radar_sigma0_m)),
        radar_sigma_per_km_m=float(radar.get("sigma_per_km_m", d.radar_sigma_per_km_m)),
        max_airspeed_mps=float(drone.get("max_airspeed_mps", d.max_airspeed_mps)),
        wind_limit_mps=float(drone.get("wind_limit_mps", d.wind_limit_mps)),
        cruise_mps=float(drone.get("cruise_mps", d.cruise_mps)),
        gps_period_s=float(periods.get("gps", d.gps_period_s)),
        radar_period_s=float(periods.get("radar", d.radar_period_s)),
        link_period_s=float(periods.get("link", d.link_period_s)),
        meteo_period_s=float(periods.get("meteo", d.meteo_period_s)),
        battery_period_s=float(periods.get("battery", d.battery_period_s)),
        gps_sigma_m=float(raw.get("gps", {}).get("sigma_m", d.gps_sigma_m)),
        cn0_nominal_dbhz=float(gnss.get("cn0_nominal_dbhz", d.cn0_nominal_dbhz)),
        agc_nominal_db=float(gnss.get("agc_nominal_db", d.agc_nominal_db)),
    )  # fmt: skip


def segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distancia del punto `p` al segmento `a`–`b`."""
    return math.dist(p, project(p, a, b)[0])


def project(p: Point, a: Point, b: Point) -> tuple[Point, float]:
    """El punto del segmento `a`–`b` más cercano a `p` y su fracción (0 en `a`, 1 en `b`)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    u = 0.0 if length2 == 0 else ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    u = max(0.0, min(1.0, u))
    return (a[0] + u * dx, a[1] + u * dy), u


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _angle_gap(a: float, b: float) -> float:
    """Diferencia entre dos rumbos en grados, entre 0 y 180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


@dataclass
class FeatureRow:
    """Lo que ve el monitor en un segundo: `values` por nombre de `FEATURES` (`None` = sin dato)."""

    t: float
    leg: int
    values: dict[str, float | None]
    evidence_ids: dict[str, str] = field(default_factory=dict)  # por fuente, el último evento

    # Nombres que usa el monitor con las tablas escritas a mano.
    @property
    def tele_gap_s(self) -> float:
        return round(self.values["tele_gap_s"] or 0.0, 1)

    @property
    def gps_route_dev_m(self) -> float | None:
        return self.values["gps_dev_m"]

    @property
    def radar_route_dev_m(self) -> float | None:
        return self.values["radar_dev_m"]

    @property
    def link_loss_pct(self) -> float | None:
        return self.values["link_loss_pct"]

    @property
    def cn0_dbhz(self) -> float | None:
        return self.values["cn0_dbhz"]

    @property
    def agc_db(self) -> float | None:
        return self.values["agc_db"]

    @property
    def wind_est_mps(self) -> float | None:
        return self.values["wind_est_mps"]


class FeatureExtractor:
    """Convierte el flujo de eventos del mundo en una fila por segundo."""

    def __init__(self, assets: Assets | None = None) -> None:
        self.assets = assets or load_assets()
        a = self.assets
        self._fresh_s = {src: FRESH_PERIODS * a.period(src) for src in SOURCES}
        self._radar_expires = 3.0 * a.period("radar")  # una traza vale 3 periodos del radar
        gnss_period = a.period("gnss")
        self._base_n = max(10, round(BASE_S / gnss_period))  # muestras de la línea base
        self._slow_n = round(SLOW_S / gnss_period)
        self._slow_skip = round(SLOW_SKIP_S / gnss_period)
        self._slow_min = round(SLOW_MIN_S / gnss_period)
        self.route: list[Point] = []
        self.etas: list[float] = []
        self.cruise_mps = 0.0
        self.reset()

    @property
    def waypoints(self) -> list[Point]:
        return self.route

    def reset(self) -> None:
        self.leg = 1
        self._second: int | None = None
        self._first_t: float | None = None
        self._last_t: dict[str, float] = {}
        self._last: dict[str, dict[str, Any]] = {}
        self._ids: dict[str, str] = {}
        # referencia del modo: `None` = tramo de la misión; si no, el segmento de la vuelta o
        # el punto de espera, fijado al entrar en ese modo
        self._mode: str | None = None
        self._anchor: tuple[Point, Point] | None = None
        self._known: Point | None = None  # última posición conocida de cualquier fuente
        self._prev_est: Point | None = None  # estima del mensaje anterior del autopiloto
        self._prev_est_t = 0.0
        self._settling = False  # esperando a que el dron se pare en su punto de espera
        # (t, distancia, distancia en múltiplos del error esperado)
        self._radar_dev: deque[tuple[float, float, float]] = deque(maxlen=RADAR_WINDOW)
        self._gps_radar: deque[tuple[float, float, float]] = deque(maxlen=RADAR_WINDOW)
        self._cusum = 0.0
        self._cusum_sigma = 0.0
        self._link_base: list[tuple[float, float]] = []  # (rssi, latencia) de los primeros avisos
        self._base_cn0: list[float] = []
        self._base_agc: list[float] = []
        self._cn0: deque[float] = deque(maxlen=self._slow_n)
        self._agc: deque[float] = deque(maxlen=self._slow_n)
        self._cum_dist = 0.0  # metros recorridos según la velocidad sobre el suelo del autopiloto
        self._hist: dict[str, deque[float | None]] = {}
        self._energy: deque[tuple[float, float | None]] = deque(maxlen=61)

    def set_plan(self, waypoints: list[dict[str, Any]], cruise_mps: float = 0.0) -> None:
        self.route = [(float(w["x"]), float(w["y"])) for w in waypoints]
        self.etas = [float(w.get("eta_s", 0.0)) for w in waypoints]
        self.cruise_mps = cruise_mps

    # --- Entrada de eventos ----------------------------------------------------------------

    def push(self, event: dict[str, Any]) -> list[FeatureRow]:
        """Añade un evento (`type`, `source`, `sim_time`, `event_id`, `payload`). Devuelve las filas
        de los segundos que este evento cierra (normalmente una)."""
        second = math.floor(event["sim_time"])
        rows: list[FeatureRow] = []
        if self._second is None:
            self._first_t = float(event["sim_time"])
        else:
            for closed in range(self._second, second):
                row = self._close(closed)
                if row is not None:
                    rows.append(row)
        self._second = max(second, self._second or second)
        self._apply(event)
        return rows

    def flush(self) -> list[FeatureRow]:
        """Cierra el segundo en curso (fin de la ejecución)."""
        row = self._close(self._second) if self._second is not None else None
        self._second = None
        return [row] if row is not None else []

    def _apply(self, event: dict[str, Any]) -> None:
        kind, payload, t = event["type"], event["payload"], float(event["sim_time"])
        if kind == "MissionPlanned":
            self.set_plan(payload["waypoints"], float(payload.get("cruise_speed_mps", 0.0)))
            self.leg = 1
            self._mode, self._anchor = None, None
        elif kind == "WaypointReached" and self.route:
            self.leg = min(int(payload["index"]) + 1, len(self.route) - 1)
        source = EVENT_SOURCE.get(kind)
        if source is None:
            return
        self._last_t[source], self._last[source] = t, payload
        self._ids[source] = event["event_id"]
        if kind == "PositionUpdated" and payload.get("x") is not None:
            self._known = (payload["x"], payload["y"])
        elif kind == "AutopilotStatus":
            self._on_autopilot(payload, t)
        elif kind == "TrackUpdated":
            self._on_track(payload, t)
        elif kind == "GnssStatus":
            self._on_gnss(payload)
        elif (
            kind == "LinkStatus"
            and payload.get("rssi_dbm") is not None
            and len(self._link_base) < LINK_BASE_SAMPLES
        ):
            self._link_base.append((payload["rssi_dbm"], payload["latency_ms"]))

    def _on_autopilot(self, p: dict[str, Any], t: float) -> None:
        est = (p["est_x"], p["est_y"])
        self._known = est
        self._cum_dist += p["ground_speed_mps"] * self.assets.gps_period_s  # un mensaje por periodo
        previous, previous_t = self._prev_est, self._prev_est_t
        self._prev_est, self._prev_est_t = est, t
        mode = p["mode"]
        if mode == self._mode:
            if self._settling and p["ground_speed_mps"] < SETTLED_MPS:
                # el dron va al punto de espera y se queda allí: donde se para es ese punto (el
                # mensaje del modo nuevo llega hasta un periodo tarde y con un dron rápido o un GPS
                # lento la estima de ese instante está lejos de él)
                self._anchor, self._settling = (est, est), False
            return
        self._mode = mode
        # El modo cambió en algún instante entre el mensaje anterior y este: el punto de partida de
        # la referencia es el punto medio de las dos estimas (con un dron rápido, una u otra solas
        # se equivocan hasta lo que recorre en un periodo). Sin mensaje anterior reciente, esta.
        recent = previous is not None and t - previous_t <= FRESH_PERIODS * self.assets.gps_period_s
        start = ((est[0] + previous[0]) / 2, (est[1] + previous[1]) / 2) if recent else est
        if mode == "failsafe_return" and self.route:
            self._anchor = (start, self.route[-1])  # de donde está hacia la base
        elif mode in ("failsafe_hold", "failsafe_land"):
            self._anchor = (start, start)  # el punto de espera, de momento
        else:
            self._anchor = None
        self._settling = mode in ("failsafe_hold", "failsafe_land")

    def _gps_sigma(self, gnss: dict[str, Any] | None) -> float:
        """Error esperado de la posición del GPS: el que dice el receptor (`h_acc`/√2; no cambia con
        el engaño) o, sin receptor, el nominal."""
        nominal = self.assets.gps_sigma_m
        if gnss is None:
            return nominal
        return max(MIN_SIGMA_REL * nominal, gnss["h_acc_m"] / math.sqrt(2.0))

    def _radar_sigma(self, pos: Point) -> float:
        """Error esperado de una traza del radar a esa distancia: σ0 más σ por km."""
        a = self.assets
        d_km = math.dist(pos, (a.radar_x, a.radar_y)) / 1000.0
        return a.radar_sigma0_m + a.radar_sigma_per_km_m * d_km

    def _on_track(self, p: dict[str, Any], t: float) -> None:
        pos = (p["x"], p["y"])
        self._known = pos
        sigma_radar = self._radar_sigma(pos)
        a, b = self._reference()
        dev = segment_distance(pos, a, b)
        self._radar_dev.append((t, dev, dev / sigma_radar))
        gps = self._fresh("gps", t)
        if gps and gps.get("x") is not None:
            d = math.dist((gps["x"], gps["y"]), pos)
            z = d / math.hypot(self._gps_sigma(self._fresh("gnss", t)), sigma_radar)
            self._gps_radar.append((t, d, z))
            self._cusum = min(CUSUM_MAX_M, max(0.0, self._cusum + d - CUSUM_ALLOWANCE_M))
            self._cusum_sigma = min(
                CUSUM_MAX_SIGMA, max(0.0, self._cusum_sigma + z - CUSUM_ALLOWANCE_SIGMA)
            )

    def _on_gnss(self, p: dict[str, Any]) -> None:
        if len(self._base_cn0) < self._base_n:
            self._base_cn0.append(p["cn0_dbhz"])
            self._base_agc.append(p["agc_db"])
        self._cn0.append(p["cn0_dbhz"])
        self._agc.append(p["agc_db"])

    # --- Ayudas ----------------------------------------------------------------------------

    def _age(self, source: str, t: float) -> float:
        last = self._last_t.get(source, self._first_t if self._first_t is not None else t)
        return min(AGE_CAP_S, max(0.0, t - last))

    def _fresh(self, source: str, t: float) -> dict[str, Any] | None:
        """El último payload de la fuente si es reciente (sin mensaje, `None`)."""
        if source in self._last and self._age(source, t) < self._fresh_s[source]:
            return self._last[source]
        return None

    def _reference(self) -> tuple[Point, Point]:
        """La referencia del modo: el tramo de la misión, el tramo a casa o el punto de espera."""
        if self._anchor is not None:
            return self._anchor
        return self.route[self.leg - 1], self.route[self.leg]

    def _delay(self, pos: Point | None, t: float) -> float | None:
        """Segundos de retraso en el tramo: `t` menos el instante previsto para ese avance."""
        if pos is None or self._anchor is not None or len(self.etas) <= self.leg:
            return None
        _, u = project(pos, self.route[self.leg - 1], self.route[self.leg])
        eta0, eta1 = self.etas[self.leg - 1], self.etas[self.leg]
        return t - (eta0 + u * (eta1 - eta0))

    def _series(self, name: str, value: float | None) -> deque[float | None]:
        hist = self._hist.setdefault(name, deque(maxlen=HISTORY_S))
        hist.append(value)
        return hist

    @staticmethod
    def _slope(hist: deque[float | None], seconds: int = 10) -> float | None:
        if len(hist) <= seconds or hist[-1] is None or hist[-1 - seconds] is None:
            return None
        return (hist[-1] - hist[-1 - seconds]) / seconds  # type: ignore[operator]

    @staticmethod
    def _recent(hist: deque[float | None], seconds: int, how: str) -> float | None:
        values = [v for v in list(hist)[-seconds:] if v is not None]
        if not values:
            return None
        return max(values) if how == "max" else sum(values) / len(values)

    # --- Una fila --------------------------------------------------------------------------

    def _close(self, second: int | None) -> FeatureRow | None:
        if len(self.route) < 2 or second is None:
            return None
        t = float(second)
        v: dict[str, float | None] = dict.fromkeys(FEATURES)
        ages = {s: self._age(s, t) for s in SOURCES}
        for s in SOURCES:
            v[f"age_{s}"] = ages[s]
        v["tele_gap_s"] = min(ages[s] for s in TELEMETRY)
        gps, gnss, ap = self._fresh("gps", t), self._fresh("gnss", t), self._fresh("autopilot", t)
        bat, link, met = self._fresh("battery", t), self._fresh("link", t), self._fresh("meteo", t)
        a, b = self._reference()
        gps_pos: Point | None = (gps["x"], gps["y"]) if gps and gps.get("x") is not None else None

        if gps:
            v["gps_fix_3d"] = 1.0 if gps["fix"] == "3d" else 0.0
            v["gps_sats"], v["gps_hdop"] = float(gps["sats"]), gps["hdop"]
        if gnss:
            v["gps_hacc_m"], v["cn0_dbhz"], v["agc_db"] = (
                gnss["h_acc_m"],
                gnss["cn0_dbhz"],
                gnss["agc_db"],
            )
            self._receiver_references(v)
        if ap:
            self._autopilot_features(v, ap)
        if met:
            v["station_wind_mps"] = met["speed_mps"]
            if v["wind_est_mps"] is not None:
                v["wind_est_minus_station"] = v["wind_est_mps"] - met["speed_mps"]
        if ap and met:
            v["wind_dir_diff_deg"] = _angle_gap(ap["wind_est_from_deg"], met["from_deg"])
        if link:
            v["link_loss_pct"], v["link_rssi_dbm"] = link.get("packet_loss_pct"), link["rssi_dbm"]
            v["link_latency_ms"] = link["latency_ms"]

        # Distancias a la referencia del modo, retrasos y tendencias.
        radar_pos = self._fresh_radar_position(t)
        if gps_pos:
            v["gps_dev_m"] = segment_distance(gps_pos, a, b)
        radar_tracks = [(d, z) for tt, d, z in self._radar_dev if t - tt <= self._radar_expires]
        radar_z = None
        if radar_tracks:
            v["radar_dev_m"] = sum(d for d, _ in radar_tracks) / len(radar_tracks)
            radar_z = sum(z for _, z in radar_tracks) / len(radar_tracks)
        gps_dev = self._series("gps_dev", v["gps_dev_m"])
        radar_dev = self._series("radar_dev", v["radar_dev_m"])
        v["gps_dev_slope"], v["radar_dev_slope"] = self._slope(gps_dev), self._slope(radar_dev)
        v["gps_dev_max30"] = self._recent(gps_dev, 30, "max")
        v["radar_dev_max30"] = self._recent(radar_dev, 30, "max")
        v["gps_delay_s"], v["radar_delay_s"] = self._delay(gps_pos, t), self._delay(radar_pos, t)
        v["gps_delay_rate"] = self._slope(self._series("gps_delay", v["gps_delay_s"]))
        v["radar_delay_rate"] = self._slope(self._series("radar_delay", v["radar_delay_s"]))

        # Discrepancia GPS–radar.
        pairs = [(d, z) for tt, d, z in self._gps_radar if t - tt <= self._radar_expires]
        if gps_pos and radar_pos:
            v["gps_radar_m"] = math.dist(gps_pos, radar_pos)
        if pairs:
            v["gps_radar_avg_m"] = sum(d for d, _ in pairs) / len(pairs)
        if ages["gps"] < 10.0 and ages["radar"] < 10.0:
            v["gps_radar_cusum_m"] = self._cusum
        self._relative(v, ap, gnss, met, link, radar_z, pairs, len(radar_tracks), t)

        # Radar: velocidad y a qué fracción de su alcance está el dron (donde se le supone).
        if radar_pos and (track := self._fresh("radar", t)):
            v["radar_speed_mps"] = track["speed_mps"]
        where = gps_pos or (ap and (ap["est_x"], ap["est_y"])) or self._known
        if where:
            v["radar_range_ratio"] = (
                math.dist(where, (self.assets.radar_x, self.assets.radar_y))
                / self.assets.radar_max_range_m
            )

        self._battery_features(v, bat, ap, gps_pos)
        return FeatureRow(t, self.leg, v, self._evidence(t))

    def _relative(
        self,
        v: dict[str, float | None],
        ap: dict[str, Any] | None,
        gnss: dict[str, Any] | None,
        met: dict[str, Any] | None,
        link: dict[str, Any] | None,
        radar_z: float | None,
        pairs: list[tuple[float, float]],
        radar_n: int,
        t: float,
    ) -> None:
        """Las características relativas: cocientes con la configuración de los activos."""
        a = self.assets
        ratio = lambda x, d: None if x is None else x / d  # noqa: E731
        for src in SOURCES:
            v[f"age_{src}_p"] = v[f"age_{src}"] / a.period(src)
        v["tele_gap_p"] = min(
            v[f"age_{s}_p"] for s in ("gps", "gnss", "autopilot")
        )  # el paquete rápido
        # viento y velocidades respecto al dron
        v["wind_est_over_limit"] = ratio(v["wind_est_mps"], a.wind_limit_mps)
        v["wind_est_over_airspeed"] = ratio(v["wind_est_mps"], a.max_airspeed_mps)
        v["wind_est_mean5_over_limit"] = ratio(v["wind_est_mean5"], a.wind_limit_mps)
        v["station_wind_over_limit"] = ratio(v["station_wind_mps"], a.wind_limit_mps)
        v["station_wind_over_airspeed"] = ratio(v["station_wind_mps"], a.max_airspeed_mps)
        v["wind_diff_over_limit"] = ratio(v["wind_est_minus_station"], a.wind_limit_mps)
        v["airspeed_over_max"] = ratio(v["airspeed_mps"], a.max_airspeed_mps)
        v["airspeed_over_cruise"] = ratio(v["airspeed_mps"], a.cruise_mps)
        v["ground_speed_over_cruise"] = ratio(v["ground_speed_mps"], a.cruise_mps)
        v["speed_gap_over_max"] = ratio(v["speed_gap_mps"], a.max_airspeed_mps)
        v["radar_speed_over_cruise"] = ratio(v["radar_speed_mps"], a.cruise_mps)
        # desviaciones en múltiplos del error esperado de cada sensor
        sigma_gps = self._gps_sigma(gnss)
        v["gps_sigma_m"] = sigma_gps
        last_radar = self._last.get("radar")
        if radar_n and last_radar is not None:  # el error de la media de las trazas de la ventana
            v["radar_sigma_m"] = self._radar_sigma((last_radar["x"], last_radar["y"])) / math.sqrt(
                radar_n
            )
        v["gps_dev_sigma"] = ratio(v["gps_dev_m"], sigma_gps)
        v["radar_dev_sigma"] = radar_z
        v["gps_dev_sigma_max30"] = self._recent(
            self._series("gps_dev_z", v["gps_dev_sigma"]), 30, "max"
        )
        v["radar_dev_sigma_max30"] = self._recent(self._series("radar_dev_z", radar_z), 30, "max")
        v["gps_dev_slope_cruise"] = ratio(v["gps_dev_slope"], a.cruise_mps)
        v["radar_dev_slope_cruise"] = ratio(v["radar_dev_slope"], a.cruise_mps)
        last_track = self._last.get("radar")
        if v["gps_radar_m"] is not None and last_track is not None:
            sigma_radar = self._radar_sigma((last_track["x"], last_track["y"]))
            v["gps_radar_sigma"] = v["gps_radar_m"] / math.hypot(sigma_gps, sigma_radar)
        if pairs:
            v["gps_radar_avg_sigma"] = sum(z for _, z in pairs) / len(pairs)
        if v["age_gps_p"] < 10.0 and v["age_radar_p"] < 5.0:
            v["gps_radar_cusum_sigma"] = self._cusum_sigma
        v["innovation_sigma"] = ratio(v["innovation_m"], sigma_gps)
        v["innovation_max10_sigma"] = ratio(v["innovation_max10"], sigma_gps)
        # receptor frente a su referencia nominal; enlace frente a su línea base
        v["cn0_vs_nominal_db"] = (
            None if v["cn0_dbhz"] is None else v["cn0_dbhz"] - a.cn0_nominal_dbhz
        )
        v["agc_vs_nominal_db"] = None if v["agc_db"] is None else v["agc_db"] - a.agc_nominal_db
        if link and self._link_base:
            rssi0 = _median([r for r, _ in self._link_base])
            lat0 = _median([x for _, x in self._link_base])
            v["link_rssi_vs_base_db"] = (
                link["rssi_dbm"] - rssi0 if link["rssi_dbm"] is not None else None
            )
            if link["latency_ms"] is not None and lat0 > 0:
                v["link_latency_vs_base"] = link["latency_ms"] / lat0

    def _fresh_radar_position(self, t: float) -> Point | None:
        track = self._fresh("radar", t)
        return (track["x"], track["y"]) if track else None

    def _receiver_references(self, v: dict[str, float | None]) -> None:
        """C/N0 y AGC frente a la mediana de los primeros 60 s y frente a la de los 5 min
        anteriores al último minuto (dos referencias que no dependen de nada que decida el
        monitor)."""
        base = len(self._base_cn0)
        v["cn0_vs_base_db"] = v["cn0_dbhz"] - _median(self._base_cn0)  # type: ignore[operator]
        v["agc_vs_base_db"] = v["agc_db"] - _median(self._base_agc)  # type: ignore[operator]
        if len(self._cn0) >= self._slow_min and base:
            old_cn0, old_agc = (
                list(self._cn0)[: -self._slow_skip],
                list(self._agc)[: -self._slow_skip],
            )
            v["cn0_vs_slow_db"] = v["cn0_dbhz"] - _median(old_cn0)  # type: ignore[operator]
            v["agc_vs_slow_db"] = v["agc_db"] - _median(old_agc)  # type: ignore[operator]

    def _autopilot_features(self, v: dict[str, float | None], ap: dict[str, Any]) -> None:
        mode = ap["mode"]
        v["mode_hold"] = 1.0 if mode == "failsafe_hold" else 0.0
        v["mode_return"] = 1.0 if mode == "failsafe_return" else 0.0
        v["mode_land"] = 1.0 if mode == "failsafe_land" else 0.0
        v["airspeed_mps"], v["ground_speed_mps"] = ap["airspeed_mps"], ap["ground_speed_mps"]
        v["speed_gap_mps"] = ap["airspeed_mps"] - ap["ground_speed_mps"]
        if ap["ground_speed_mps"] >= MIN_SPEED_FOR_COURSE_MPS:
            v["heading_course_deg"] = _angle_gap(ap["heading_deg"], ap["course_deg"])
        v["wind_est_mps"] = ap["wind_est_speed_mps"]
        v["wind_est_mean5"] = self._recent(self._series("wind", v["wind_est_mps"]), 5, "mean")
        v["innovation_m"] = ap["innovation_m"]
        v["innovation_max10"] = self._recent(self._series("innov", ap["innovation_m"]), 10, "max")

    def _battery_features(
        self,
        v: dict[str, float | None],
        bat: dict[str, Any] | None,
        ap: dict[str, Any] | None,
        gps_pos: Point | None,
    ) -> None:
        pos = (ap and (ap["est_x"], ap["est_y"])) or gps_pos or self._known
        if pos and self.route:
            v["home_dist_m"] = math.dist(pos, self.route[-1])
        pct = None
        if bat:
            pct, v["battery_pct"] = bat["battery_pct"], bat["battery_pct"]
            v["battery_power_w"], v["battery_time_s"] = (
                bat.get("power_w"),
                bat.get("time_remaining_s"),
            )
            if v["home_dist_m"] is not None and v["battery_time_s"] and self.cruise_mps > 0:
                v["home_time_ratio"] = v["home_dist_m"] / self.cruise_mps / v["battery_time_s"]
        self._energy.append((self._cum_dist, pct))
        old_dist, old_pct = self._energy[0]
        km = (self._cum_dist - old_dist) / 1000.0
        if pct is not None and old_pct is not None and km >= 0.1:
            v["pct_per_km"] = (old_pct - pct) / km

    def _evidence(self, t: float) -> dict[str, str]:
        return {s: i for s, i in self._ids.items() if self._age(s, t) < self._fresh_s[s] * 2}
