"""Controlador del dron y bucle de simulación (física 2D, paso de 0,1 s).

- Velocidad respecto al aire = `cruise_speed` en la dirección del rumbo (acelera con `max_accel`).
- Velocidad respecto al suelo = velocidad respecto al aire + viento.
- Guiado con punto de mira sobre el tramo: se proyecta la posición que CREE tener el dron (el
  GPS, sin ruido) sobre el tramo pendiente y se apunta a un punto `lookahead_m` por delante. El
  rumbo gira hacia él con el giro limitado a `max_turn_rate`. No compensa el viento de forma
  integral: con viento lateral `w` queda un error `lookahead · tan(asin(w / v))`.
- El waypoint cambia cuando el GPS está a menos de `acceptance_radius_m`.
- Secuestro: el objetivo pasa a `target`; al recuperar el mando vuelve a seguir el tramo pendiente.
- Spoofing: GPS = real + desfase creciente; el controlador usa el GPS, así que el dron se desvía.
"""

import math
from dataclasses import dataclass

from poc_contracts.scenario import ScenarioConfig

from ..geometry import Point, angle_diff_deg, bearing_deg
from .disturbances import is_hijacked, spoof_offset, wind_at

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


@dataclass(frozen=True)
class Flight:
    samples: list[Sample]
    route_ids: list[str]  # BASE, WP1…, BASE: el índice es el de `WaypointReached`
    route: list[Point]
    reached: list[tuple[int, int]]  # (paso, índice en la ruta) de cada waypoint alcanzado
    completed: bool

    @property
    def end_n(self) -> int:
        return self.samples[-1].n


def build_route(config: ScenarioConfig) -> tuple[list[str], list[Point]]:
    """Ids y puntos de la ruta: base, waypoints y vuelta a la base."""
    wps = config.mission.waypoints
    ids = [BASE, *(w.id for w in wps), BASE]
    points = [(0.0, 0.0), *((w.x, w.y) for w in wps), (0.0, 0.0)]
    return ids, points


def fly(config: ScenarioConfig, perturbed: bool) -> Flight:
    """Vuela la misión; con `perturbed=False` (plan) sin viento, spoofing ni secuestro."""
    d = config.drone
    ids, route = build_route(config)
    spoofing = config.spoofing if perturbed else None
    hijack = config.hijack if perturbed else None
    target = (hijack.target.x, hijack.target.y) if hijack else (0.0, 0.0)
    max_steps = round(config.max_duration_s / STEP_S)

    x = y = speed = 0.0
    heading = bearing_deg(route[1][0], route[1][1])
    i = 1
    n = 0
    samples = [Sample(0, x, y, 0.0, 0.0, heading, (0.0, 0.0))]
    reached: list[tuple[int, int]] = []

    while n < max_steps and i < len(route):
        t = round(n * STEP_S, 6)
        off = spoof_offset(t, spoofing)
        gx, gy = x + off[0], y + off[1]
        if is_hijacked(t, hijack):
            aim = target
        else:
            a, b = route[i - 1], route[i]
            if math.hypot(b[0] - gx, b[1] - gy) < d.acceptance_radius_m:
                reached.append((n, i))
                i += 1
                continue
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            s = min(length, (gx - a[0]) * u[0] + (gy - a[1]) * u[1] + d.lookahead_m)
            aim = (a[0] + u[0] * s, a[1] + u[1] * s)
        err = angle_diff_deg(bearing_deg(aim[0] - gx, aim[1] - gy), heading)
        step = d.max_turn_rate_dps * STEP_S
        heading = (heading + max(-step, min(step, err))) % 360.0
        speed = min(d.cruise_speed_mps, speed + d.max_accel_mps2 * STEP_S)
        wx, wy = wind_at(t, config.wind).vector() if perturbed else (0.0, 0.0)
        vx = speed * math.sin(math.radians(heading)) + wx
        vy = speed * math.cos(math.radians(heading)) + wy
        x += vx * STEP_S
        y += vy * STEP_S
        n += 1
        samples.append(
            Sample(n, x, y, vx, vy, heading, spoof_offset(round(n * STEP_S, 6), spoofing))
        )
    return Flight(samples, ids, route, reached, completed=i >= len(route))
