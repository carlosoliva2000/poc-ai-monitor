"""Lo que reporta cada fuente: muestreo, ruido y payload.

Los periodos y las σ principales vienen del YAML; las constantes de aquí son el ruido de lo
secundario (altitud, velocidad, rumbo, calidad del radar, RSSI, latencia, batería).
Todo el ruido sale de un único `random.Random` (el de la semilla del escenario).
"""

import math
import random
from collections.abc import Iterator

from poc_contracts.enums import EventType
from poc_contracts.scenario import ScenarioConfig

from ..geometry import bearing_deg
from .controller import STEP_S, Sample
from .disturbances import Wind, is_hijacked, spoof_offset_rate, wind_at

GPS_ALT_SIGMA_M = 0.5
GPS_SPEED_SIGMA_MPS = 0.2
GPS_HEADING_SIGMA_DEG = 1.0
RADAR_SPEED_SIGMA_MPS = 0.5
RADAR_COURSE_SIGMA_DEG = 3.0
RADAR_QUALITY_RANGE = (0.85, 0.95)
LINK_RSSI_SIGMA_DB = 1.5
LINK_LATENCY_SIGMA_MS = 5.0
BATTERY_PCT_SIGMA = 0.1
BATTERY_VOLTAGE_EMPTY_V = 21.0  # 6S: 3,5 V por celda vacía…
BATTERY_VOLTAGE_FULL_V = 25.2  # …y 4,2 V por celda llena
BATTERY_VOLTAGE_SIGMA_V = 0.02

# (tipo, instante, payload) de cada medida; el id lo pone `build`
Reading = tuple[EventType, float, dict]


def ticks(period_s: float, end_s: float) -> Iterator[tuple[int, float]]:
    """(k, t) con t = k·periodo, k ≥ 1, hasta `end_s` incluido."""
    k = 1
    while (t := round(k * period_s, 6)) <= end_s + 1e-9:
        yield k, t
        k += 1


def sample_at(samples: list[Sample], t: float) -> Sample:
    """Muestra de la simulación más cercana a `t` (los periodos son múltiplos de 0,1 s)."""
    return samples[min(round(t / STEP_S), len(samples) - 1)]


def gps_readings(
    config: ScenarioConfig, samples: list[Sample], rng: random.Random, end_s: float
) -> Iterator[Reading]:
    g = config.sensors.gps
    for _, t in ticks(g.period_s, end_s):
        s = sample_at(samples, t)
        gx, gy = s.gps
        # velocidad y rumbo de navegación del dron: los del suelo más la deriva del engaño
        dvx, dvy = spoof_offset_rate(t, config.spoofing)
        vx, vy = s.vx + dvx, s.vy + dvy
        yield (
            EventType.POSITION_UPDATED,
            t,
            {
                "x": round(gx + rng.gauss(0, g.sigma_m), 1),
                "y": round(gy + rng.gauss(0, g.sigma_m), 1),
                "alt_m": round(config.drone.altitude_m + rng.gauss(0, GPS_ALT_SIGMA_M), 1),
                "speed_mps": round(
                    max(0.0, math.hypot(vx, vy) + rng.gauss(0, GPS_SPEED_SIGMA_MPS)), 1
                ),
                "heading_deg": round(
                    (bearing_deg(vx, vy) + rng.gauss(0, GPS_HEADING_SIGMA_DEG)) % 360, 1
                ),
                "fix": "3d",
                "sats": g.sats,
                "hdop": g.hdop,
            },
        )


def radar_readings(
    config: ScenarioConfig, samples: list[Sample], rng: random.Random, end_s: float
) -> Iterator[Reading]:
    r = config.sensors.radar
    for _, t in ticks(r.period_s, end_s):
        s = sample_at(samples, t)
        yield (
            EventType.TRACK_UPDATED,
            t,
            {
                "radar_id": r.id,
                "x": round(s.x + rng.gauss(0, r.sigma_m), 1),
                "y": round(s.y + rng.gauss(0, r.sigma_m), 1),
                "speed_mps": round(max(0.0, s.speed_mps + rng.gauss(0, RADAR_SPEED_SIGMA_MPS)), 1),
                "course_deg": round((s.course_deg + rng.gauss(0, RADAR_COURSE_SIGMA_DEG)) % 360, 1),
                "quality": round(rng.uniform(*RADAR_QUALITY_RANGE), 2),
            },
        )


def meteo_readings(config: ScenarioConfig, rng: random.Random, end_s: float) -> Iterator[Reading]:
    m = config.sensors.meteo
    for _, t in ticks(m.period_s, end_s):
        w: Wind = wind_at(t, config.wind)
        speed = max(0.0, w.speed_mps + rng.gauss(0, m.sigma_mps))
        gust = max(speed, w.gust_mps + rng.gauss(0, m.sigma_mps))
        yield (
            EventType.WIND_REPORTED,
            t,
            {
                "station_id": m.id,
                "speed_mps": round(speed, 1),
                "gust_mps": round(gust, 1),
                "from_deg": round((w.from_deg + rng.gauss(0, m.sigma_deg)) % 360, 1),
            },
        )


def link_readings(config: ScenarioConfig, rng: random.Random, end_s: float) -> Iterator[Reading]:
    lk = config.sensors.link
    for _, t in ticks(lk.period_s, end_s):
        hint = config.hijack.link_hint if is_hijacked(t, config.hijack) else lk
        yield (
            EventType.LINK_STATUS,
            t,
            {
                "controller_id": hint.controller_id,
                "rssi_dbm": round(hint.rssi_dbm + rng.gauss(0, LINK_RSSI_SIGMA_DB), 1),
                "latency_ms": round(
                    max(1.0, hint.latency_ms + rng.gauss(0, LINK_LATENCY_SIGMA_MS)), 1
                ),
            },
        )


def battery_readings(config: ScenarioConfig, rng: random.Random, end_s: float) -> Iterator[Reading]:
    b = config.sensors.battery
    span = BATTERY_VOLTAGE_FULL_V - BATTERY_VOLTAGE_EMPTY_V
    for _, t in ticks(b.period_s, end_s):
        pct = min(
            100.0,
            max(0.0, b.start_pct - b.drain_pct_per_min * t / 60 + rng.gauss(0, BATTERY_PCT_SIGMA)),
        )
        volts = BATTERY_VOLTAGE_EMPTY_V + span * pct / 100 + rng.gauss(0, BATTERY_VOLTAGE_SIGMA_V)
        yield (
            EventType.BATTERY_STATUS,
            t,
            {"battery_pct": round(pct, 1), "voltage_v": round(volts, 2)},
        )
