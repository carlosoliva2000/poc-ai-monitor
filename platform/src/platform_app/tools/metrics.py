"""Tool `get_track_metrics`: métricas de trayectoria calculadas a partir de los eventos.

Cálculos (todo sale de `PositionUpdated` del GPS y `TrackUpdated` del radar en la ventana):
- Desviación respecto al plan: distancia de cada posición a la polilínea de waypoints de
  `MissionPlanned` (con la vuelta a la base).
- `trend`: media del primer tercio de las muestras frente a la del último tercio. Es
  `increasing`/`decreasing` si cambia más de un 20 % y más de 2 m; si no, `stable`. Con menos de
  3 muestras es `None`.
- `gps_radar_distance_m`: distancia entre cada medida del radar y el GPS interpolado a su
  instante (no se interpola a través de un hueco de más de 3 s).
- `drift_direction_deg`: rumbo del vector medio que va del punto más cercano de la ruta a la
  posición GPS.
- `course_deg`: rumbo del desplazamiento neto entre la primera y la última posición de la ventana.
- Hechos calculados (para que el modelo no compare números): `wind.notable`, `wind.with_drift`,
  `gps_radar.disagreed` y `gps_max_step_m` (mayor aumento de la desviación del GPS entre dos
  muestras consecutivas: en una recuperación del GPS salta decenas de metros de golpe).
- `wind`: velocidad media y racha máxima de los `WindReported` de la ventana; la dirección es la
  media vectorial ponderada por la velocidad (`from_deg`), `wind_to_deg` = `from_deg` + 180 y
  `drift_vs_wind_deg` la diferencia absoluta (0 a 180) con `drift_direction_deg`.
"""

import math
from bisect import bisect_left
from collections.abc import Sequence

from poc_contracts.enums import EventType, Trend
from poc_contracts.envelope import Envelope
from poc_contracts.tools import (
    GetTrackMetricsArgs,
    GpsRadarFact,
    MetricStat,
    SampleCounts,
    SourcePair,
    TrackMetrics,
    WindStat,
)

from ..geometry import Point, bearing_deg, closest_on_route
from .context import ToolContext, ToolFailure
from .events import mission_planned, next_waypoint

GPS_SOURCE = "d1-gps"
RADAR_SOURCE = "radar-1"
METEO_SOURCE = "meteo-1"
TREND_RATIO = 0.2  # cambio relativo mínimo entre el primer y el último tercio
TREND_MIN_DELTA_M = 2.0  # y cambio absoluto mínimo, para no ver tendencias en el ruido
MAX_INTERP_GAP_S = 3.0
MIN_TREND_SAMPLES = 3
MIN_COURSE_DISTANCE_M = 0.5
WIND_NOTABLE_SPEED_MPS = 5.0  # viento notable: velocidad media ≥ 5 m/s o racha máxima ≥ 8 m/s
WIND_NOTABLE_GUST_MPS = 8.0
WIND_WITH_DRIFT_DEG = 45.0  # la deriva va a favor del viento si difiere como mucho esto
DISAGREED_M = 25.0  # GPS y radar discrepan si la distancia máxima de la ventana llega a esto
MAX_STEP_GAP_S = 1.5  # solo se comparan muestras consecutivas del GPS a esta distancia o menos

Sample = tuple[float, float, float]  # (sim_time, x, y)


def _samples(events: Sequence[Envelope]) -> list[Sample]:
    return [(e.sim_time, float(e.payload["x"]), float(e.payload["y"])) for e in events]


def _trend(values: list[float]) -> Trend | None:
    if len(values) < MIN_TREND_SAMPLES:
        return None
    k = max(1, len(values) // 3)
    first, last = sum(values[:k]) / k, sum(values[-k:]) / k
    delta = last - first
    if abs(delta) < TREND_MIN_DELTA_M or abs(delta) <= TREND_RATIO * abs(first):
        return Trend.STABLE
    return Trend.INCREASING if delta > 0 else Trend.DECREASING


def _stat(values: list[float]) -> MetricStat | None:
    if not values:
        return None
    return MetricStat(
        mean=round(sum(values) / len(values), 1), max=round(max(values), 1), trend=_trend(values)
    )


def _interpolate(series: list[Sample], times: list[float], t: float) -> Point | None:
    """Posición de `series` en el instante `t`, o `None` si no hay muestras cercanas."""
    i = bisect_left(times, t)
    if i < len(series) and series[i][0] == t:
        return series[i][1], series[i][2]
    if i == 0 or i == len(series):
        return None
    (t0, x0, y0), (t1, x1, y1) = series[i - 1], series[i]
    if t1 - t0 > MAX_INTERP_GAP_S:
        return None
    f = (t - t0) / (t1 - t0)
    return x0 + f * (x1 - x0), y0 + f * (y1 - y0)


def _course(samples: list[Sample]) -> float | None:
    if len(samples) < 2:
        return None
    dx, dy = samples[-1][1] - samples[0][1], samples[-1][2] - samples[0][2]
    if math.hypot(dx, dy) < MIN_COURSE_DISTANCE_M:
        return None
    return round(bearing_deg(dx, dy), 1)


def _mean(events: Sequence[Envelope], key: str) -> float | None:
    if not events:
        return None
    return round(sum(float(e.payload[key]) for e in events) / len(events), 1)


def _angle_diff(a: float, b: float) -> float:
    """Diferencia absoluta entre dos rumbos, de 0 a 180."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _wind(events: Sequence[Envelope], drift: float | None) -> WindStat | None:
    """Viento de la ventana, o `None` si no hay informes (o están todos en calma total)."""
    if not events:
        return None
    speeds = [float(e.payload["speed_mps"]) for e in events]
    # vector hacia el que empuja el viento (la procedencia + 180), ponderado por la velocidad
    vx = vy = 0.0
    for e, speed in zip(events, speeds, strict=True):
        to = math.radians(float(e.payload["from_deg"]) + 180.0)
        vx += speed * math.sin(to)
        vy += speed * math.cos(to)
    if math.hypot(vx, vy) < 1e-9:
        return None
    wind_to = bearing_deg(vx, vy)
    mean_speed = round(sum(speeds) / len(speeds), 1)
    max_gust = round(max(float(e.payload["gust_mps"]) for e in events), 1)
    drift_vs_wind = None if drift is None else round(_angle_diff(drift, wind_to), 1)
    return WindStat(
        mean_speed_mps=mean_speed,
        max_gust_mps=max_gust,
        from_deg=round((wind_to + 180.0) % 360.0, 1),
        wind_to_deg=round(wind_to, 1),
        drift_vs_wind_deg=drift_vs_wind,
        notable=mean_speed >= WIND_NOTABLE_SPEED_MPS or max_gust >= WIND_NOTABLE_GUST_MPS,
        with_drift=drift_vs_wind is not None and drift_vs_wind <= WIND_WITH_DRIFT_DEG,
        samples=len(events),
        last_event_id=events[-1].event_id,
    )


def _max_step(times: list[float], deviation: list[float]) -> float | None:
    """Mayor aumento de la desviación entre dos muestras consecutivas del GPS (a ≤ 1,5 s)."""
    if len(deviation) < 2:
        return None
    steps = [
        deviation[i + 1] - deviation[i]
        for i in range(len(deviation) - 1)
        if times[i + 1] - times[i] <= MAX_STEP_GAP_S
    ]
    return round(max(steps + [0.0]), 1)


def get_track_metrics(ctx: ToolContext, args: GetTrackMetricsArgs) -> TrackMetrics:
    if args.since > args.until:
        raise ToolFailure("`since` cannot be greater than `until`")
    plan = mission_planned(ctx)
    route: list[Point] = [(w.x, w.y) for w in plan.waypoints]
    until = ctx.cutoff(args.until)

    gps_events, _ = ctx.events(
        source=GPS_SOURCE, type=EventType.POSITION_UPDATED, since=args.since, until=until
    )
    radar_events, _ = ctx.events(
        source=RADAR_SOURCE, type=EventType.TRACK_UPDATED, since=args.since, until=until
    )
    gps, radar = _samples(gps_events), _samples(radar_events)
    meteo_events, _ = ctx.events(
        source=METEO_SOURCE, type=EventType.WIND_REPORTED, since=args.since, until=until
    )

    gps_dev = [closest_on_route((x, y), route)[1] for _, x, y in gps]
    radar_dev = [closest_on_route((x, y), route)[1] for _, x, y in radar]

    # GPS con tres segundos de margen antes de la ventana, solo para interpolar
    gps_context, _ = ctx.events(
        source=GPS_SOURCE,
        type=EventType.POSITION_UPDATED,
        since=args.since - MAX_INTERP_GAP_S,
        until=until,
    )
    gps_series = _samples(gps_context)
    gps_times = [s[0] for s in gps_series]
    distances = []
    for t, x, y in radar:
        pos = _interpolate(gps_series, gps_times, t)
        if pos is not None:
            distances.append(math.hypot(x - pos[0], y - pos[1]))

    drift: float | None = None
    if gps:
        vectors = [
            (x - c[0], y - c[1]) for _, x, y in gps for c in [closest_on_route((x, y), route)[0]]
        ]
        mx = sum(v[0] for v in vectors) / len(vectors)
        my = sum(v[1] for v in vectors) / len(vectors)
        if math.hypot(mx, my) > 1e-9:
            drift = round(bearing_deg(mx, my), 1)

    next_wp = next_waypoint(ctx, plan, until) if gps else None
    bearing: float | None = None
    if next_wp is not None:
        target = next(w for w in plan.waypoints if w.id == next_wp)
        bearing = round(bearing_deg(target.x - gps[-1][1], target.y - gps[-1][2]), 1)

    def last_seen(source: str, event_type: EventType) -> float | None:
        found, _ = ctx.events(source=source, type=event_type, limit=1)
        return found[0].sim_time if found else None

    first_ids = [e[0].event_id for e in (gps_events, radar_events) if e]
    last_ids = [e[-1].event_id for e in (gps_events, radar_events) if e]
    gps_radar_stat = _stat(distances)
    return TrackMetrics(
        since=args.since,
        until=until,
        gps_deviation_from_plan_m=_stat(gps_dev),
        radar_deviation_from_plan_m=_stat(radar_dev),
        gps_radar_distance_m=gps_radar_stat,
        drift_direction_deg=drift,
        course_deg=SourcePair(gps=_course(gps), radar=_course(radar)),
        bearing_to_next_waypoint_deg=bearing,
        next_waypoint=next_wp,
        mean_speed_mps=SourcePair(
            gps=_mean(gps_events, "speed_mps"), radar=_mean(radar_events, "speed_mps")
        ),
        wind=_wind(meteo_events, drift),
        gps_radar=(
            None
            if gps_radar_stat is None
            else GpsRadarFact(disagreed=gps_radar_stat.max >= DISAGREED_M)
        ),
        gps_max_step_m=_max_step([s[0] for s in gps], gps_dev),
        samples=SampleCounts(gps=len(gps), radar=len(radar)),
        gps_available=bool(gps),
        radar_available=bool(radar),
        last_seen_sim_time=SourcePair(
            gps=last_seen(GPS_SOURCE, EventType.POSITION_UPDATED),
            radar=last_seen(RADAR_SOURCE, EventType.TRACK_UPDATED),
        ),
        first_event_ids=first_ids,
        last_event_ids=last_ids,
    )
