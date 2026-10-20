"""Perturbaciones del escenario en cada instante: viento, desfase del GPS y secuestro."""

import math
from dataclasses import dataclass

from poc_contracts.scenario import HijackConfig, SpoofingConfig, WindConfig


@dataclass(frozen=True)
class Wind:
    """Viento en un instante: velocidad media, racha y dirección de **procedencia**."""

    speed_mps: float
    gust_mps: float
    from_deg: float

    def vector(self) -> tuple[float, float]:
        """Velocidad (este, norte) con la que el viento empuja al dron (hacia `from_deg + 180`)."""
        to = math.radians(self.from_deg + 180.0)
        return self.speed_mps * math.sin(to), self.speed_mps * math.cos(to)


def wind_at(t: float, wind: WindConfig) -> Wind:
    """Viento base, o el del episodio activo con rampa de subida y bajada de `ramp_s`.

    La velocidad y la racha se interpolan; la procedencia pasa a la del episodio de golpe.
    """
    speed, gust, from_deg = wind.base.speed_mps, wind.base.gust_mps, wind.base.from_deg
    for e in wind.episodes:
        if e.start_s <= t <= e.end_s:
            k = min(1.0, (t - e.start_s) / e.ramp_s, (e.end_s - t) / e.ramp_s)
            speed += (e.speed_mps - speed) * k
            gust += (e.gust_mps - gust) * k
            from_deg = e.from_deg
    return Wind(speed, gust, from_deg)


def spoof_offset(t: float, spoofing: SpoofingConfig | None) -> tuple[float, float]:
    """Desfase (este, norte) del GPS: crece a `drift_rate_mps` y se anula de golpe en `end_s`."""
    if spoofing is None or not spoofing.start_s <= t < spoofing.end_s:
        return 0.0, 0.0
    k = (t - spoofing.start_s) * spoofing.drift_rate_mps
    a = math.radians(spoofing.direction_deg)
    return k * math.sin(a), k * math.cos(a)


def spoof_offset_rate(t: float, spoofing: SpoofingConfig | None) -> tuple[float, float]:
    """Derivada del desfase (m/s): lo que se suma a la velocidad que dice el GPS."""
    if spoofing is None or not spoofing.start_s <= t < spoofing.end_s:
        return 0.0, 0.0
    a = math.radians(spoofing.direction_deg)
    return spoofing.drift_rate_mps * math.sin(a), spoofing.drift_rate_mps * math.cos(a)


def is_hijacked(t: float, hijack: HijackConfig | None) -> bool:
    """`True` en `[start_s, end_s)`; sin `end_s`, hasta el final."""
    if hijack is None:
        return False
    return hijack.start_s <= t < (hijack.end_s if hijack.end_s is not None else math.inf)
