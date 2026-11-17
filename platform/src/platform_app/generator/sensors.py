"""Lo que reporta cada fuente: ruido y payload de una medida.

Los periodos y las σ principales vienen del YAML; las constantes de aquí son el ruido de lo
secundario (altitud, velocidad, rumbo, calidad del radar, RSSI, latencia, batería).
Todo el ruido sale de un único `random.Random` (el de la semilla del escenario). Cada función
saca **siempre** los mismos números aleatorios, también cuando la fuente está silenciada o en
pérdida: así un fallo no cambia el ruido de las demás medidas.
"""

import math
import random

from poc_contracts.scenario import ScenarioConfig

from ..geometry import bearing_deg
from .controller import STEP_S, Sample
from .disturbances import Wind, is_hijacked

GPS_ALT_SIGMA_M = 0.5
GPS_SPEED_SIGMA_MPS = 0.2
GPS_HEADING_SIGMA_DEG = 1.0
GPS_LOSS_HDOP = 99.9  # con la pérdida, el receptor reporta sin fix, sin satélites y hdop enorme
RADAR_SPEED_SIGMA_MPS = 0.5
RADAR_COURSE_SIGMA_DEG = 3.0
RADAR_QUALITY_RANGE = (0.85, 0.95)
LINK_RSSI_SIGMA_DB = 1.5
LINK_LATENCY_SIGMA_MS = 5.0
BATTERY_PCT_SIGMA = 0.1
BATTERY_VOLTAGE_EMPTY_V = 21.0  # 6S: 3,5 V por celda vacía…
BATTERY_VOLTAGE_FULL_V = 25.2  # …y 4,2 V por celda llena
BATTERY_VOLTAGE_SIGMA_V = 0.02


def period_steps(period_s: float) -> int:
    """Pasos de simulación (0,1 s) que dura el periodo; tiene que ser múltiplo de 0,1 s."""
    steps = round(period_s / STEP_S)
    if steps < 1 or abs(steps * STEP_S - period_s) > 1e-9:
        raise ValueError(f"the period {period_s} s is not a multiple of {STEP_S} s")
    return steps


def _toward(nominal: float, target: float | None, k: float) -> float:
    return nominal if target is None else nominal + (target - nominal) * k


def gps_quality(config: ScenarioConfig, t: float) -> tuple[int, float]:
    """`sats` y `hdop` en `t` (sin pérdida): los nominales o los del episodio de degradación
    activo, con su rampa. No saca números aleatorios: sin episodios, todo sale igual que antes."""
    g = config.sensors.gps
    for e in g.episodes:
        k = e.level(t)
        if k is not None:
            sats = g.sats if e.sats is None else round(_toward(g.sats, e.sats, k))
            hdop = g.hdop if e.hdop is None else round(_toward(g.hdop, e.hdop, k), 2)
            return sats, hdop
    return g.sats, g.hdop


def gps_payload(
    config: ScenarioConfig,
    rng: random.Random,
    pos: tuple[float, float],
    vel: tuple[float, float],
    loss: bool,
    t: float,
) -> dict:
    """`PositionUpdated`. `pos` y `vel` son lo que cree el dron: con el engaño, la posición y la
    velocidad falsas; en pérdida, la estima y su velocidad respecto al aire (sin fix). La pérdida
    manda sobre un episodio de degradación."""
    g = config.sensors.gps
    sats, hdop = (0, GPS_LOSS_HDOP) if loss else gps_quality(config, t)
    return {
        "x": round(pos[0] + rng.gauss(0, g.sigma_m), 1),
        "y": round(pos[1] + rng.gauss(0, g.sigma_m), 1),
        "alt_m": round(config.drone.altitude_m + rng.gauss(0, GPS_ALT_SIGMA_M), 1),
        "speed_mps": round(max(0.0, math.hypot(*vel) + rng.gauss(0, GPS_SPEED_SIGMA_MPS)), 1),
        "heading_deg": round((bearing_deg(*vel) + rng.gauss(0, GPS_HEADING_SIGMA_DEG)) % 360, 1),
        "fix": "none" if loss else "3d",
        "sats": sats,
        "hdop": hdop,
    }


def radar_payload(config: ScenarioConfig, rng: random.Random, s: Sample) -> dict:
    r = config.sensors.radar
    return {
        "radar_id": r.id,
        "x": round(s.x + rng.gauss(0, r.sigma_m), 1),
        "y": round(s.y + rng.gauss(0, r.sigma_m), 1),
        "speed_mps": round(max(0.0, s.speed_mps + rng.gauss(0, RADAR_SPEED_SIGMA_MPS)), 1),
        "course_deg": round((s.course_deg + rng.gauss(0, RADAR_COURSE_SIGMA_DEG)) % 360, 1),
        "quality": round(rng.uniform(*RADAR_QUALITY_RANGE), 2),
    }


def meteo_payload(config: ScenarioConfig, rng: random.Random, w: Wind) -> dict:
    """`WindReported` con el viento real `w` (el del escenario y, si lo hay, el del instructor)."""
    m = config.sensors.meteo
    speed = max(0.0, w.speed_mps + rng.gauss(0, m.sigma_mps))
    gust = max(speed, w.gust_mps + rng.gauss(0, m.sigma_mps))
    return {
        "station_id": m.id,
        "speed_mps": round(speed, 1),
        "gust_mps": round(gust, 1),
        "from_deg": round((w.from_deg + rng.gauss(0, m.sigma_deg)) % 360, 1),
    }


def link_quality(config: ScenarioConfig, t: float) -> tuple[float, float]:
    """RSSI y latencia nominales en `t` (sin secuestro), o los del episodio de degradación activo,
    con su rampa. El ruido se suma después, con los mismos números aleatorios de siempre."""
    lk = config.sensors.link
    for e in lk.episodes:
        k = e.level(t)
        if k is not None:
            return _toward(lk.rssi_dbm, e.rssi_dbm, k), _toward(lk.latency_ms, e.latency_ms, k)
    return lk.rssi_dbm, lk.latency_ms


def link_payload(config: ScenarioConfig, rng: random.Random, t: float) -> dict:
    """`LinkStatus`. Durante un secuestro manda el enlace del secuestro (`link_hint`) sobre un
    episodio de degradación."""
    if is_hijacked(t, config.hijack):
        hint = config.hijack.link_hint
        controller, rssi, latency = hint.controller_id, hint.rssi_dbm, hint.latency_ms
    else:
        controller = config.sensors.link.controller_id
        rssi, latency = link_quality(config, t)
    return {
        "controller_id": controller,
        "rssi_dbm": round(rssi + rng.gauss(0, LINK_RSSI_SIGMA_DB), 1),
        "latency_ms": round(max(1.0, latency + rng.gauss(0, LINK_LATENCY_SIGMA_MS)), 1),
    }


def battery_payload(config: ScenarioConfig, rng: random.Random, t: float) -> dict:
    b = config.sensors.battery
    span = BATTERY_VOLTAGE_FULL_V - BATTERY_VOLTAGE_EMPTY_V
    pct = min(
        100.0,
        max(0.0, b.start_pct - b.drain_pct_per_min * t / 60 + rng.gauss(0, BATTERY_PCT_SIGMA)),
    )
    volts = BATTERY_VOLTAGE_EMPTY_V + span * pct / 100 + rng.gauss(0, BATTERY_VOLTAGE_SIGMA_V)
    return {"battery_pct": round(pct, 1), "voltage_v": round(volts, 2)}
