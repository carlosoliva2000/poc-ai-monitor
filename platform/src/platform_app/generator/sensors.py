"""Lo que reporta cada fuente: ruido y payload de una medida.

Los periodos y las σ principales vienen del YAML; las constantes de aquí son el ruido de lo
secundario (altitud, velocidad, rumbo, RSSI, latencia, batería).

Contrato v1.0: los campos que salieron (`quality` del radar, `gust_mps` de la estación, `voltage_v`
de la batería) **siguen gastando sus números aleatorios** y se descartan, para que el resto del
ruido salga igual que antes de quitarlos.
Todo el ruido sale de un único `random.Random` (el de la semilla del escenario). Cada función
saca **siempre** los mismos números aleatorios, también cuando la fuente está silenciada o en
pérdida: así un fallo no cambia el ruido de las demás medidas.
"""

import math
import random
from typing import TYPE_CHECKING

from poc_contracts.scenario import ScenarioConfig

from ..geometry import bearing_deg
from .controller import STEP_S, Sample
from .disturbances import Wind

if TYPE_CHECKING:
    from .receiver import GnssEpoch

GPS_ALT_SIGMA_M = 0.5
GPS_SPEED_SIGMA_MPS = 0.2
GPS_HEADING_SIGMA_DEG = 1.0
GNSS_CN0_NOMINAL_DBHZ = (
    45.0  # ⚠️ de partida: C/N0 medio de un receptor sano (se modela en el paso 3)
)
GPS_LOSS_HDOP = 99.9  # con la pérdida, el receptor reporta sin fix, sin satélites y hdop enorme
RADAR_SPEED_SIGMA_MPS = 0.5
RADAR_COURSE_SIGMA_DEG = 3.0
RADAR_QUALITY_RANGE = (0.85, 0.95)  # solo para gastar el número aleatorio de siempre
LINK_RSSI_SIGMA_DB = 1.5
LINK_LATENCY_SIGMA_MS = 5.0
BATTERY_PCT_SIGMA = 0.1
BATTERY_VOLTAGE_SIGMA_V = 0.02


def period_steps(period_s: float) -> int:
    """Pasos de simulación (0,1 s) que dura el periodo; tiene que ser múltiplo de 0,1 s."""
    steps = round(period_s / STEP_S)
    if steps < 1 or abs(steps * STEP_S - period_s) > 1e-9:
        raise ValueError(f"the period {period_s} s is not a multiple of {STEP_S} s")
    return steps


def _toward(nominal: float, target: float | None, k: float) -> float:
    return nominal if target is None else nominal + (target - nominal) * k


def gps_quality(
    config: ScenarioConfig, t: float, drift: tuple[int, float] = (0, 0.0)
) -> tuple[int, float]:
    """`sats` y `hdop` en `t` (sin pérdida): los nominales (más la variación lenta del receptor
    realista, `drift`) o los del episodio de degradación activo, con su rampa. No saca números
    aleatorios: sin episodios y sin `drift`, todo sale igual que antes."""
    g = config.sensors.gps
    sats0, hdop0 = g.sats + drift[0], g.hdop + drift[1]
    for e in g.episodes:
        k = e.level(t)
        if k is not None:
            sats = sats0 if e.sats is None else round(_toward(sats0, e.sats, k))
            hdop = hdop0 if e.hdop is None else round(_toward(hdop0, e.hdop, k), 2)
            return sats, hdop
    return sats0, round(hdop0, 2) if drift[1] else hdop0


def gps_payload(
    config: ScenarioConfig,
    rng: random.Random,
    pos: tuple[float, float],
    vel: tuple[float, float],
    loss: bool,
    t: float,
    receiver: "GnssEpoch",
) -> dict:
    """`PositionUpdated`. `pos` y `vel` son lo que cree el dron: con el engaño, la posición y la
    velocidad falsas; en pérdida, la estima y su velocidad respecto al aire (sin fix). La pérdida
    manda sobre un episodio de degradación."""
    # El ruido de posición viene del receptor; el del generador único se saca igualmente (y se
    # descarta) para no cambiar el de lo demás.
    rng.gauss(0, 1)
    rng.gauss(0, 1)
    sats, hdop = (0, GPS_LOSS_HDOP) if loss else (receiver.sats, receiver.hdop)
    x, y = round(pos[0] + receiver.noise[0], 1), round(pos[1] + receiver.noise[1], 1)
    payload: dict = {
        "x": x,
        "y": y,
        "alt_m": round(config.drone.altitude_m + rng.gauss(0, GPS_ALT_SIGMA_M), 1),
        "speed_mps": round(max(0.0, math.hypot(*vel) + rng.gauss(0, GPS_SPEED_SIGMA_MPS)), 1),
        "course_deg": round((bearing_deg(*vel) + rng.gauss(0, GPS_HEADING_SIGMA_DEG)) % 360, 1),
        "fix": "none" if loss else "3d",
        "sats": sats,
        "hdop": hdop,
    }
    if loss:  # un receptor sin fix no da posición, velocidad ni rumbo
        payload.update(x=None, y=None, alt_m=None, speed_mps=None, course_deg=None)
    return payload


def radar_range_m(config: ScenarioConfig, x: float, y: float) -> float:
    """Distancia del dron al radar."""
    r = config.sensors.radar
    return math.hypot(x - r.x, y - r.y)


def radar_sigma_m(config: ScenarioConfig, x: float, y: float) -> float:
    """σ de la posición del radar: la del YAML más un término creciente con la distancia."""
    r = config.sensors.radar
    return r.sigma_m + r.sigma_per_km_m * radar_range_m(config, x, y) / 1000.0


def radar_payload(config: ScenarioConfig, rng: random.Random, s: Sample) -> dict:
    sigma = radar_sigma_m(config, s.x, s.y)
    payload = {
        "x": round(s.x + rng.gauss(0, sigma), 1),
        "y": round(s.y + rng.gauss(0, sigma), 1),
        "speed_mps": round(max(0.0, s.speed_mps + rng.gauss(0, RADAR_SPEED_SIGMA_MPS)), 1),
        "course_deg": round((s.course_deg + rng.gauss(0, RADAR_COURSE_SIGMA_DEG)) % 360, 1),
    }
    rng.uniform(*RADAR_QUALITY_RANGE)  # `quality` ya no existe: se gasta el número y se descarta
    return payload


def meteo_payload(config: ScenarioConfig, rng: random.Random, w: Wind) -> dict:
    """`WindReported` con el viento real `w` (el del escenario y, si lo hay, el del instructor)."""
    m = config.sensors.meteo
    speed = max(0.0, w.speed_mps + rng.gauss(0, m.sigma_mps))
    rng.gauss(0, m.sigma_mps)  # la racha ya no existe: se gasta el número y se descarta
    return {
        "speed_mps": round(speed, 1),
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


def link_payload_physics(
    config: ScenarioConfig,
    rng: random.Random,
    rssi: float,
    latency: float,
    up: bool,
    loss_pct: float,
) -> dict:
    """`LinkStatus` con física: lo mide nuestra estación. Con el enlace caído no llega señal ni
    latencia (`null`) y se pierde el 100 %. Gasta los mismos números aleatorios de siempre."""
    noisy_rssi = rssi + rng.gauss(0, LINK_RSSI_SIGMA_DB)
    noisy_latency = max(1.0, latency + rng.gauss(0, LINK_LATENCY_SIGMA_MS))
    if not up:
        return {"rssi_dbm": None, "latency_ms": None, "packet_loss_pct": 100.0}
    return {
        "rssi_dbm": round(noisy_rssi, 1),
        "latency_ms": round(noisy_latency, 1),
        "packet_loss_pct": round(loss_pct, 1),
    }


def battery_payload(rng: random.Random, model: tuple[float, float, float]) -> dict:
    """`BatteryStatus`; `model` = (carga %, potencia W, tiempo restante s)."""
    noise = rng.gauss(0, BATTERY_PCT_SIGMA)
    rng.gauss(0, BATTERY_VOLTAGE_SIGMA_V)  # `voltage_v` ya no existe: se gasta y se descarta
    pct = min(100.0, max(0.0, model[0] + noise))
    return {
        "battery_pct": round(pct, 1),
        "power_w": round(model[1], 0),
        "time_remaining_s": round(model[2], 0),
    }
