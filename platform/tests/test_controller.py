"""Controlador y bucle de física: tramo recto, error estacionario con viento, límites y desvíos."""

import math

import pytest
from pydantic import ValidationError

from helpers import scenario_config
from platform_app.generator.controller import STEP_S, Flight, fly
from platform_app.geometry import angle_diff_deg, distance_to_route
from poc_contracts.scenario import ScenarioConfig

NO_WIND = {"base": {"speed_mps": 0.0, "gust_mps": 0.0, "from_deg": 0.0}, "episodes": []}


def straight_leg_config(wind: dict | None = None) -> ScenarioConfig:
    """Un solo tramo recto hacia el este (BASE -> WP1 a 3 km) y vuelta."""
    mission = {
        "id": "MSN-TEST",
        "waypoints": [{"id": "WP1", "x": 3000.0, "y": 0.0}],
        "return_to_base": True,
    }
    return scenario_config("nominal", mission=mission, wind=wind or NO_WIND)


def deviation(flight: Flight, t_from: float, t_to: float) -> list[float]:
    return [
        distance_to_route((s.x, s.y), flight.route) for s in flight.samples if t_from <= s.t <= t_to
    ]


def test_straight_leg_without_wind_has_no_cross_track_error() -> None:
    flight = fly(straight_leg_config(), perturbed=True)
    assert max(deviation(flight, 0.0, 150.0)) < 0.5
    assert flight.completed
    assert [i for _, i in flight.reached] == [1, 2]


def test_cruise_speed_is_reached_and_never_exceeded_without_wind() -> None:
    cfg = straight_leg_config()
    flight = fly(cfg, perturbed=True)
    speeds = [s.speed_mps for s in flight.samples[1:]]
    assert max(speeds) == pytest.approx(cfg.drone.cruise_speed_mps)
    assert flight.samples[100].speed_mps == pytest.approx(cfg.drone.cruise_speed_mps)  # t = 10 s


def test_acceleration_and_turn_rate_limits() -> None:
    cfg = scenario_config("nominal", wind=NO_WIND)
    flight = fly(cfg, perturbed=True)
    max_dv = cfg.drone.max_accel_mps2 * STEP_S
    max_dh = cfg.drone.max_turn_rate_dps * STEP_S
    for prev, cur in zip(flight.samples[1:], flight.samples[2:], strict=False):
        assert cur.speed_mps - prev.speed_mps <= max_dv + 1e-9
        assert abs(angle_diff_deg(cur.heading_deg, prev.heading_deg)) <= max_dh + 1e-9


@pytest.mark.parametrize("wind_mps", [4.0, 6.0])
def test_crosswind_steady_state_error_matches_lookahead_formula(wind_mps: float) -> None:
    """Con viento lateral `w` el error estacionario es `lookahead · tan(asin(w / v))`."""
    wind = {"base": {"speed_mps": wind_mps, "gust_mps": wind_mps, "from_deg": 0.0}, "episodes": []}
    cfg = straight_leg_config(wind)  # tramo hacia el este, viento del norte: empuja al sur
    flight = fly(cfg, perturbed=True)
    expected = cfg.drone.lookahead_m * math.tan(math.asin(wind_mps / cfg.drone.cruise_speed_mps))
    mid = [s for s in flight.samples if 1000.0 < s.x < 2000.0]
    assert mid, "el dron debe cruzar el tramo central"
    for s in mid:
        assert -s.y == pytest.approx(expected, rel=0.1)  # desviado al sur


def test_wind_does_not_matter_in_the_planned_flight() -> None:
    windy = fly(scenario_config("viento"), perturbed=False)
    calm = fly(scenario_config("nominal", wind=NO_WIND), perturbed=False)
    assert [(s.x, s.y) for s in windy.samples] == [(s.x, s.y) for s in calm.samples]


def test_plan_ignores_spoofing_and_hijack() -> None:
    plan = fly(scenario_config("demo"), perturbed=False)
    nominal_plan = fly(scenario_config("nominal"), perturbed=False)
    assert [(s.x, s.y) for s in plan.samples] == [(s.x, s.y) for s in nominal_plan.samples]


def test_waypoints_are_reached_in_order_within_the_acceptance_radius() -> None:
    cfg = scenario_config("nominal")
    flight = fly(cfg, perturbed=True)
    assert [i for _, i in flight.reached] == [1, 2, 3, 4, 5]
    for n, i in flight.reached:
        s = flight.samples[n]
        gx, gy = s.gps
        wx, wy = flight.route[i]
        assert math.hypot(wx - gx, wy - gy) < cfg.drone.acceptance_radius_m
    assert flight.route_ids == ["BASE", "WP1", "WP2", "WP3", "WP4", "BASE"]


def test_spoofing_pulls_the_drone_away_while_the_gps_stays_on_route() -> None:
    cfg = scenario_config("spoofing")
    flight = fly(cfg, perturbed=True)
    s = flight.samples[round(215.0 / STEP_S)]
    assert distance_to_route(s.gps, flight.route) < 15.0  # lo que cree
    assert distance_to_route((s.x, s.y), flight.route) > 50.0  # lo que ocurre
    after = flight.samples[round(cfg.spoofing.end_s / STEP_S)]
    assert after.offset == (0.0, 0.0)  # el GPS vuelve a la verdad de golpe


def test_hijack_heads_for_the_target_then_rejoins_the_route() -> None:
    cfg = scenario_config("secuestro")
    h = cfg.hijack
    flight = fly(cfg, perturbed=True)
    target = (h.target.x, h.target.y)

    def dist(t: float) -> float:
        s = flight.samples[round(t / STEP_S)]
        return math.hypot(target[0] - s.x, target[1] - s.y)

    assert dist(h.end_s) < dist(h.start_s + 5.0) - 300.0  # se acerca al destino con rumbo firme
    assert max(deviation(flight, h.start_s, h.end_s)) > 300.0
    assert flight.completed
    assert max(deviation(flight, flight.samples[-1].t - 15.0, flight.samples[-1].t)) < 15.0


def test_timeout_ends_the_flight_without_completing_it() -> None:
    cfg = scenario_config("nominal", max_duration_s=60.0)
    flight = fly(cfg, perturbed=True)
    assert not flight.completed
    assert flight.samples[-1].t == pytest.approx(60.0)


def test_return_to_base_false_is_rejected_by_the_scenario_model() -> None:
    mission = {**scenario_config("nominal").mission.model_dump(), "return_to_base": False}
    with pytest.raises(ValidationError, match="return_to_base"):
        scenario_config("nominal", mission=mission)


def test_same_inputs_give_the_same_flight() -> None:
    a = fly(scenario_config("demo"), perturbed=True)
    b = fly(scenario_config("demo"), perturbed=True)
    assert a.samples == b.samples
