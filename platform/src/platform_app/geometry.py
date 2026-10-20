"""Geometría plana: x hacia el este, y hacia el norte; rumbos en grados (0 = norte, horario)."""

import math
from collections.abc import Sequence

Point = tuple[float, float]


def bearing_deg(dx: float, dy: float) -> float:
    """Rumbo (0–360, 0 = norte) del vector (dx, dy)."""
    return math.degrees(math.atan2(dx, dy)) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Diferencia a − b normalizada a [−180, 180)."""
    return (a - b + 540.0) % 360.0 - 180.0


def project_on_segment(p: Point, a: Point, b: Point) -> tuple[Point, float]:
    """Punto más cercano de p en el segmento a–b y su distancia a p."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) if l2 else 0.0
    q = (a[0] + t * dx, a[1] + t * dy)
    return q, math.hypot(p[0] - q[0], p[1] - q[1])


def closest_on_route(p: Point, route: Sequence[Point]) -> tuple[Point, float]:
    """Punto más cercano de p en la polilínea `route` y su distancia (desviación de ruta)."""
    best = min(
        (project_on_segment(p, route[i], route[i + 1]) for i in range(len(route) - 1)),
        key=lambda r: r[1],
    )
    return best


def distance_to_route(p: Point, route: Sequence[Point]) -> float:
    """Distancia de p a la polilínea `route`."""
    return closest_on_route(p, route)[1]
