"""Receptor GNSS y estimador a bordo (E7a, pasos 3 y 4).

Cada fuente de ruido nueva usa **su propio generador** con semilla estable (`zlib.crc32`, no
`hash()`, que cambia entre ejecuciones): así no se toca el orden del ruido del `random.Random`
único de siempre. Se saca en cada medida del GPS, esté o no silenciado, y también en los vuelos
sin eventos: con el estimador a bordo la trayectoria depende del ruido.
"""

import math
import random
import zlib
from dataclasses import dataclass

from poc_contracts.scenario import ScenarioConfig

from ..geometry import Point, bearing_deg
from . import sensors


def stable_rng(seed: int, name: str) -> random.Random:
    """Generador propio de una fuente de ruido, con semilla estable a partir de la del escenario."""
    return random.Random(zlib.crc32(f"{seed}:{name}".encode()))


class GaussMarkov:
    """Error con memoria (Gauss-Markov de primer orden) en dos ejes: `x' = φ·x + √(1−φ²)·σ·η`, con
    `φ = exp(−Δt/τ)`. Empieza en un valor de su distribución estacionaria."""

    def __init__(self, rng: random.Random, sigma: float, tau_s: float, dt_s: float) -> None:
        self._rng, self._phi = rng, math.exp(-dt_s / tau_s)
        self._q = sigma * math.sqrt(1.0 - self._phi**2)
        self.x: Point = (rng.gauss(0, sigma), rng.gauss(0, sigma))

    def step(self) -> Point:
        r, p = self._rng, self._phi
        self.x = (p * self.x[0] + self._q * r.gauss(0, 1), p * self.x[1] + self._q * r.gauss(0, 1))
        return self.x


class SlowDrift:
    """Variación lenta y acotada de un escalar (AR(1) recortado a `±bound`): sin saltos."""

    def __init__(self, rng: random.Random, sigma: float, tau_s: float, dt_s: float, bound: float):
        self._rng, self._phi, self._bound = rng, math.exp(-dt_s / tau_s), bound
        self._q = sigma * math.sqrt(1.0 - self._phi**2)
        self.x = max(-bound, min(bound, rng.gauss(0, sigma)))

    def step(self) -> float:
        self.x = max(
            -self._bound,
            min(self._bound, self._phi * self.x + self._q * self._rng.gauss(0, 1)),
        )
        return self.x


# Variación lenta de `sats` y `hdop` en vuelo normal ⚠️ (del orden de ±1 satélite cada pocos
# minutos y un `hdop` suave): sin caídas repentinas, porque no hay nada que las explique.
HDOP_DRIFT_SIGMA, HDOP_DRIFT_TAU_S, HDOP_DRIFT_BOUND = 0.12, 150.0, 0.25
SATS_DRIFT_SIGMA, SATS_DRIFT_TAU_S, SATS_DRIFT_BOUND = 0.8, 240.0, 1.4
CN0_SIGMA_DBHZ, AGC_SIGMA_DB, H_ACC_SIGMA_REL = 0.7, 0.3, 0.1  # ruido de las lecturas ⚠️


@dataclass(frozen=True)
class GnssEpoch:
    """Una medida del receptor: el ruido de posición que se suma (m, este y norte), `sats` y `hdop`
    de ese instante, σ real por eje y lo que dice el receptor de sí mismo."""

    noise: Point
    sats: int
    hdop: float
    sigma_m: float
    h_acc_m: float
    cn0_dbhz: float
    agc_db: float


class GnssModel:
    """Receptor GPS realista : ruido de posición con memoria más un ruido
    blanco pequeño, σ proporcional al `hdop`, y `sats`/`hdop` con variación lenta y acotada."""

    def __init__(self, config: ScenarioConfig) -> None:
        g, seed, dt = config.sensors.gps, config.seed, config.sensors.gps.period_s
        self._gm = GaussMarkov(stable_rng(seed, "gps_gm"), g.gm_sigma_m, g.gm_tau_s, dt)
        self._white = stable_rng(seed, "gps_white")
        self._hdop = SlowDrift(
            stable_rng(seed, "gps_hdop"), HDOP_DRIFT_SIGMA, HDOP_DRIFT_TAU_S, dt, HDOP_DRIFT_BOUND
        )
        self._sats = SlowDrift(
            stable_rng(seed, "gps_sats"), SATS_DRIFT_SIGMA, SATS_DRIFT_TAU_S, dt, SATS_DRIFT_BOUND
        )
        self._receiver = stable_rng(seed, "gnss_receiver")

    def epoch(
        self, config: ScenarioConfig, t: float, d_cn0: float = 0.0, d_agc: float = 0.0
    ) -> GnssEpoch:
        g = config.sensors.gps
        drift = (round(self._sats.step()), self._hdop.step())
        sats, hdop = sensors.gps_quality(config, t, drift)
        ratio = hdop / g.hdop  # σ proporcional al hdop (el nominal es la referencia)
        gm = self._gm.step()
        wx, wy = (self._white.gauss(0, g.white_sigma_m) for _ in range(2))
        noise = ((gm[0] + wx) * ratio, (gm[1] + wy) * ratio)
        sigma = math.hypot(g.gm_sigma_m, g.white_sigma_m) * ratio
        r = self._receiver
        h_acc = max(0.1, math.sqrt(2.0) * sigma * (1.0 + H_ACC_SIGMA_REL * r.gauss(0, 1)))
        cn0 = max(5.0, g.cn0_nominal_dbhz + d_cn0 + r.gauss(0, CN0_SIGMA_DBHZ))
        agc = g.agc_nominal_db + d_agc + r.gauss(0, AGC_SIGMA_DB)
        return GnssEpoch(noise, sats, hdop, sigma, h_acc, cn0, agc)


class Estimator:
    """Estimador a bordo (filtro complementario): predice con la velocidad respecto al aire más el
    viento estimado y se corrige con el GPS: la innovación mueve la posición (`α`) y el viento
    (`k_w`). **Sin GPS solo predice, con el último viento estimado.**"""

    def __init__(self, start: Point, alpha: float, wind_gain: float) -> None:
        self.p, self.wind = start, (0.0, 0.0)
        self._alpha, self._kw = alpha, wind_gain

    def predict(self, air_velocity: Point, dt_s: float) -> None:
        self.p = (
            self.p[0] + (air_velocity[0] + self.wind[0]) * dt_s,
            self.p[1] + (air_velocity[1] + self.wind[1]) * dt_s,
        )

    def correct(self, z: Point) -> float:
        """Corrige con una posición del GPS; devuelve la innovación (m)."""
        nx, ny = z[0] - self.p[0], z[1] - self.p[1]
        self.p = (self.p[0] + self._alpha * nx, self.p[1] + self._alpha * ny)
        self.wind = (self.wind[0] + self._kw * nx, self.wind[1] + self._kw * ny)
        return math.hypot(nx, ny)

    def wind_from_deg(self) -> float:
        """Procedencia del viento estimado (0 = del norte)."""
        return (bearing_deg(*self.wind) + 180.0) % 360.0 if math.hypot(*self.wind) > 1e-9 else 0.0
