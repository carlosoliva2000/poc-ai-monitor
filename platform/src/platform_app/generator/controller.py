"""Controlador del dron: guiado y muestra de estado (física 2D, paso de 0,1 s).

El bucle de simulación paso a paso está en `simulator.py`.

- Velocidad respecto al aire = `cruise_speed` en la dirección del rumbo (acelera con `max_accel`).
- Velocidad respecto al suelo = velocidad respecto al aire + viento.
- Guiado con punto de mira sobre el tramo: se proyecta la posición que CREE tener el dron (el
  GPS, sin ruido) sobre el tramo pendiente y se apunta a un punto `lookahead_m` por delante. El
  rumbo gira hacia él con el giro limitado a `max_turn_rate`. No compensa el viento de forma
  integral: con viento lateral `w` queda un error `lookahead · tan(asin(w / v))`.
- El waypoint cambia cuando el GPS está a menos de `acceptance_radius_m`.
- Secuestro: el objetivo pasa a `target`; al recuperar el mando vuelve a seguir el tramo pendiente.
- Spoofing: GPS = real + desfase creciente; el controlador usa el GPS, así que el dron se desvía.
- Pérdida de GPS: el dron navega a estima (integra su velocidad respecto al aire, sin conocer el
  viento) y el controlador sigue el plan con esa estimación.
"""

import math
from dataclasses import dataclass

from poc_contracts.scenario import ScenarioConfig

from ..geometry import Point, bearing_deg

STEP_S = 0.1
BASE = "BASE"


@dataclass(frozen=True)
class Sample:
    """Estado tras `n` pasos. La velocidad es respecto al suelo; (0, 0) en el instante inicial."""

    n: int
    x: float
    y: float
    vx: float
    vy: float
    heading_deg: float
    offset: tuple[float, float]  # desfase del GPS (este, norte)

    @property
    def t(self) -> float:
        return round(self.n * STEP_S, 6)

    @property
    def speed_mps(self) -> float:
        return math.hypot(self.vx, self.vy)

    @property
    def course_deg(self) -> float:
        """Rumbo sobre el suelo; parado, el del morro."""
        return bearing_deg(self.vx, self.vy) if self.speed_mps > 1e-9 else self.heading_deg

    @property
    def gps(self) -> Point:
        """Posición que cree tener el dron (sin ruido)."""
        return self.x + self.offset[0], self.y + self.offset[1]


def build_route(config: ScenarioConfig) -> tuple[list[str], list[Point]]:
    """Ids y puntos de la ruta: base, waypoints y vuelta a la base."""
    wps = config.mission.waypoints
    ids = [BASE, *(w.id for w in wps), BASE]
    points = [(0.0, 0.0), *((w.x, w.y) for w in wps), (0.0, 0.0)]
    return ids, points


def aim_point(a: Point, b: Point, believed: Point, lookahead_m: float) -> Point:
    """Punto de mira sobre el tramo a→b: la proyección de la posición que cree tener el dron,
    `lookahead_m` por delante (sin pasar del final del tramo)."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    s = min(length, (believed[0] - a[0]) * u[0] + (believed[1] - a[1]) * u[1] + lookahead_m)
    return a[0] + u[0] * s, a[1] + u[1] * s


# --- Guiado de multirrotor (E7a, paso 2) -------------------------------------------------------
# Funciones puras: el estado (velocidad respecto al aire, integral, modo) vive en el simulador.


def unit(dx: float, dy: float) -> Point:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)


CORNER_OPENING_M = 6.0  # ⚠️ cuánto se puede abrir el dron en una esquina (fija la velocidad de paso)


def corner_speed(route: list[Point], i: int, cruise: float, accel: float) -> float:
    """Velocidad con la que se pasa por el punto `route[i]`: la de crucero en línea recta, 0 con un
    giro de 90° o más (o en el último punto) y, entre medias, la menor de `cruise · cos(giro)` y la
    que deja que el cambio de velocidad con la aceleración limitada no abra la esquina más de
    `CORNER_OPENING_M` (`v² = a · d / sin(giro / 2)`)."""
    if i + 1 >= len(route):
        return 0.0
    u1 = unit(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1])
    u2 = unit(route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
    cos_turn = u1[0] * u2[0] + u1[1] * u2[1]
    if cos_turn <= 0.0:
        return 0.0
    half_sin = math.sqrt(max(0.0, (1.0 - cos_turn) / 2.0))  # sin(giro / 2)
    limit = math.sqrt(accel * CORNER_OPENING_M / half_sin) if half_sin > 1e-6 else cruise
    return min(cruise * cos_turn, limit)


def speed_profile(dist: float, v_pass: float, cruise: float, accel: float, radius: float) -> float:
    """Velocidad sobre el suelo hacia un punto a `dist`: la de crucero, frenando para llegar con
    `v_pass` al borde del radio de aceptación (`v² = v_pass² + 2·a·d`; se frena hasta medio radio
    para que siga habiendo velocidad al entrar en el radio)."""
    return min(cruise, math.sqrt(v_pass**2 + 2.0 * accel * max(0.0, dist - 0.5 * radius)))


def limit_air_velocity(g: Point, wind: Point, v_max: float) -> Point:
    """Velocidad respecto al aire que da la velocidad sobre el suelo `g` con ese viento
    (`g − viento`), sin pasar de `v_max`. Si no cabe, se reduce `g` (se frena a lo largo del
    tramo antes que dejar de compensar el viento); si el viento supera `v_max`, se compensa lo que
    se puede y el dron deriva a sotavento."""
    va = (g[0] - wind[0], g[1] - wind[1])
    if math.hypot(*va) <= v_max:
        return va
    g2 = g[0] ** 2 + g[1] ** 2
    if g2 > 1e-12:
        gw = g[0] * wind[0] + g[1] * wind[1]
        disc = gw * gw - g2 * (wind[0] ** 2 + wind[1] ** 2 - v_max**2)
        k = (gw + math.sqrt(disc)) / g2 if disc >= 0 else gw / g2
        k = max(0.0, min(1.0, k))
        va = (k * g[0] - wind[0], k * g[1] - wind[1])
    m = math.hypot(*va)
    return (va[0] * v_max / m, va[1] * v_max / m) if m > v_max else va
