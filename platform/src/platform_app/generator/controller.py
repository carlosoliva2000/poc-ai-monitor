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
