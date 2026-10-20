"""Geometría plana mínima del detector: x hacia el este, y hacia el norte (metros)."""

import math
from collections.abc import Sequence

Point = tuple[float, float]


def distance(a: Point, b: Point) -> float:
    """Distancia euclídea entre dos puntos."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def distance_to_segment(p: Point, a: Point, b: Point) -> float:
    """Distancia del punto `p` al segmento `a`–`b`."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return distance(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return distance(p, (a[0] + t * dx, a[1] + t * dy))


def distance_to_route(p: Point, route: Sequence[Point]) -> float:
    """Distancia del punto `p` a la polilínea `route` (al menos un punto)."""
    if len(route) == 1:
        return distance(p, route[0])
    return min(distance_to_segment(p, route[i], route[i + 1]) for i in range(len(route) - 1))


def interpolate(a: Point, b: Point, fraction: float) -> Point:
    """Punto a `fraction` (0–1) del camino de `a` a `b`."""
    return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
