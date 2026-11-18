"""Batería de un multirrotor (E7a, paso 6): potencia, consumo, tiempo restante y energía a casa.

Potencia en vuelo nivelado según Zeng, Xu y Zhang, «Energy Minimization for Wireless
Communication with Rotary-Wing UAV», arXiv:1804.02238, ec. 6 y tabla I (curva en U según la
velocidad respecto al aire): https://arxiv.org/html/1804.02238v1. Se usa su **forma normalizada**
(`P(V) = P_estacionario · f(V) / f(0)`) con los valores de la tabla I (con W = 100 N: P(0) =
1371 W, P(15 m/s) = 985 W); la potencia en estacionario, la capacidad y la eficiencia son del YAML
(⚠️).
"""

import math

from poc_contracts.scenario import BatteryConfig

from .controller import limit_air_velocity, unit

# Tabla I de Zeng et al.: peso, densidad del aire, radio y área del rotor, velocidad angular,
# solidez, resistencia del fuselaje, factor inducido y coeficiente de perfil.
_W, _RHO, _R, _A, _OMEGA, _S, _D0, _K, _DELTA = (
    100.0,
    1.225,
    0.5,
    0.79,
    400.0,
    0.05,
    0.3,
    0.1,
    0.012,
)
_P0 = _DELTA / 8.0 * _RHO * _S * _A * _OMEGA**3 * _R**3  # perfil de las palas
_PI = (1.0 + _K) * _W**1.5 / math.sqrt(2.0 * _RHO * _A)  # inducida en estacionario
_V0 = math.sqrt(_W / (2.0 * _RHO * _A))  # velocidad inducida en estacionario
_U = _OMEGA * _R  # velocidad de la punta de la pala


def _raw_power(v: float) -> float:
    induced = math.sqrt(max(0.0, math.sqrt(1.0 + v**4 / (4.0 * _V0**4)) - v**2 / (2.0 * _V0**2)))
    return _P0 * (1.0 + 3.0 * v**2 / _U**2) + _PI * induced + 0.5 * _D0 * _RHO * _S * _A * v**3


def power_w(v_air: float, hover_power_w: float) -> float:
    """Potencia mecánica con `v_air` m/s respecto al aire (la mínima, en torno a 20 m/s)."""
    return hover_power_w * _raw_power(v_air) / _raw_power(0.0)


class Battery:
    """Energía consumida, integrando la potencia eléctrica (`P(V_aire) / η`) en el tiempo."""

    def __init__(self, cfg: BatteryConfig) -> None:
        self.cfg = cfg
        self.used_wh = 0.0
        self.power_w = power_w(0.0, cfg.hover_power_w) / cfg.efficiency

    @property
    def remaining_wh(self) -> float:
        return max(0.0, self.cfg.capacity_wh * self.cfg.start_pct / 100.0 - self.used_wh)

    @property
    def soc_pct(self) -> float:
        return 100.0 * self.remaining_wh / self.cfg.capacity_wh

    def step(self, v_air: float, dt_s: float) -> None:
        self.power_w = power_w(v_air, self.cfg.hover_power_w) / self.cfg.efficiency
        self.used_wh += self.power_w * dt_s / 3600.0

    def time_remaining_s(self) -> float:
        return self.remaining_wh * 3600.0 / self.power_w

    def energy_to_home_wh(
        self, pos: tuple[float, float], wind: tuple[float, float], cruise: float, v_max: float
    ) -> float:
        """Energía para volver en línea recta a casa con ese viento (el estimado a bordo o el real):
        a velocidad de crucero sobre el suelo si cabe en la velocidad máxima respecto al aire y, si
        no, a la que se pueda. `inf` si el viento lo impide."""
        dist = math.hypot(*pos)
        if dist < 1.0:
            return 0.0
        ux, uy = unit(-pos[0], -pos[1])
        va = limit_air_velocity((cruise * ux, cruise * uy), wind, v_max)
        ground = (va[0] + wind[0]) * ux + (va[1] + wind[1]) * uy
        if ground < 0.5:
            return math.inf
        seconds = dist / ground
        return (
            power_w(math.hypot(*va), self.cfg.hover_power_w)
            / self.cfg.efficiency
            * seconds
            / 3600.0
        )

    def can_reach_home(
        self, pos: tuple[float, float], wind: tuple[float, float], cruise: float, v_max: float
    ) -> bool:
        need = self.energy_to_home_wh(pos, wind, cruise, v_max)
        return self.remaining_wh >= need * (1.0 + self.cfg.return_reserve)
