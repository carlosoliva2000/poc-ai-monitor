"""Perturbaciones del escenario en cada instante: viento, desfase del GPS y secuestro."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from poc_contracts.commands import WindCommandParams
from poc_contracts.scenario import HijackConfig, SpoofingConfig, WindConfig


@dataclass(frozen=True)
class Wind:
    """Viento en un instante: velocidad media y dirección de **procedencia**."""

    speed_mps: float
    from_deg: float

    def vector(self) -> tuple[float, float]:
        """Velocidad (este, norte) con la que el viento empuja al dron (hacia `from_deg + 180`)."""
        to = math.radians(self.from_deg + 180.0)
        return self.speed_mps * math.sin(to), self.speed_mps * math.cos(to)


@dataclass
class CommandWind:
    """Viento puesto por el instructor: un episodio más, aplicado **después** de los del escenario.

    Sustituye al viento que haya (la velocidad sube con la rampa desde el viento de ese
    instante; la procedencia cambia de golpe, como en un episodio). Termina solo a los `duration_s`
    (con la rampa de bajada) o antes: `cancel` baja con su rampa desde el nivel que tenga y
    `replace_by` (otro `set_wind`) lo congela mientras sube el nuevo, para que la transición sea
    continua.
    """

    start_s: float
    params: WindCommandParams
    end_s: float = math.inf
    cut_at: float | None = None
    release_after: float = 0.0  # con `replace_by`: lo que dura el relevo; 0 = cancelación con rampa

    def __post_init__(self) -> None:
        if self.params.duration_s is not None:
            self.end_s = self.start_s + self.params.duration_s

    def _level(self, t: float) -> float:
        r = self.params.ramp_s
        return max(0.0, min(1.0, (t - self.start_s) / r, (self.end_s - t) / r))

    def level(self, t: float) -> float | None:
        """Peso del comando en `t` (0 a 1), o `None` si no está en curso."""
        if t < self.start_s or t > self.end_s:
            return None
        if self.cut_at is None or t <= self.cut_at:
            return self._level(t)
        held = self._level(self.cut_at)
        if self.release_after > 0.0:  # relevo: se mantiene hasta que el nuevo llega a su nivel
            return held if t < self.cut_at + self.release_after else None
        left = 1.0 - (t - self.cut_at) / self.params.ramp_s  # cancelación: baja con su rampa
        return held * left if left > 0.0 else None


def wind_at(t: float, wind: WindConfig, commands: Sequence[CommandWind] = ()) -> Wind:
    """Viento base, o el del episodio activo con rampa de subida y bajada de `ramp_s`, y por
    encima el del instructor si lo hay.

    La velocidad se interpola; la procedencia pasa a la del episodio de golpe.
    """
    speed, from_deg = wind.base.speed_mps, wind.base.from_deg
    for e in wind.episodes:
        if e.start_s <= t <= e.end_s:
            k = min(1.0, (t - e.start_s) / e.ramp_s, (e.end_s - t) / e.ramp_s)
            speed += (e.speed_mps - speed) * k
            from_deg = e.from_deg
    for c in commands:
        k = c.level(t)
        if k is not None:
            speed += (c.params.speed_mps - speed) * k
            from_deg = c.params.from_deg
    return Wind(speed, from_deg)


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
