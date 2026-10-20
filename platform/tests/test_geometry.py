import math

import pytest

from platform_app.geometry import (
    angle_diff_deg,
    bearing_deg,
    closest_on_route,
    distance_to_route,
    project_on_segment,
)


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [(0, 1, 0), (1, 0, 90), (0, -1, 180), (-1, 0, 270), (1, 1, 45)],
)
def test_bearing_zero_is_north_clockwise(dx: float, dy: float, expected: float) -> None:
    assert bearing_deg(dx, dy) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(10, 350, 20), (350, 10, -20), (90, 90, 0), (0, 180, -180), (181, 0, -179)],
)
def test_angle_diff_takes_the_short_way(a: float, b: float, expected: float) -> None:
    assert angle_diff_deg(a, b) == pytest.approx(expected)


def test_projection_clamps_to_segment_ends() -> None:
    a, b = (0.0, 0.0), (100.0, 0.0)
    assert project_on_segment((50.0, 30.0), a, b) == ((50.0, 0.0), 30.0)
    assert project_on_segment((-20.0, 0.0), a, b)[0] == (0.0, 0.0)
    assert project_on_segment((130.0, 40.0), a, b)[1] == pytest.approx(50.0)


def test_degenerate_segment_is_a_point() -> None:
    assert project_on_segment((3.0, 4.0), (0.0, 0.0), (0.0, 0.0))[1] == pytest.approx(5.0)


def test_distance_to_route_uses_the_nearest_leg() -> None:
    route = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
    assert distance_to_route((50.0, 10.0), route) == pytest.approx(10.0)
    assert distance_to_route((90.0, 50.0), route) == pytest.approx(10.0)
    point, dist = closest_on_route((130.0, 100.0), route)
    assert point == (100.0, 100.0)
    assert dist == pytest.approx(30.0)
    assert math.isclose(distance_to_route((0.0, 0.0), route), 0.0)
