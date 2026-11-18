"""Guiado de multirrotor (`simulator.multirotor_guidance`): lo que importa del lazo de velocidad."""

import math

import pytest

from helpers import scenario_config
from platform_app.generator.controller import STEP_S
from platform_app.generator.simulator import Simulator, fly
from platform_app.geometry import angle_diff_deg, distance_to_route
from poc_contracts.scenario import ScenarioConfig

NO_WIND = {"base": {"speed_mps": 0.0, "from_deg": 0.0}, "episodes": []}


def multirotor(
    name: str = "nominal", wind: dict | None = None, **mission: object
) -> ScenarioConfig:
    """Escenario con el guiado de multirrotor y los valores de un multirrotor (radio 5 m, giro
    100 °/s, el yaw máximo del Matrice 300 RTK)."""
    base = scenario_config(name)
    drone = {**base.drone.model_dump(), "acceptance_radius_m": 5.0, "max_turn_rate_dps": 100.0}
    over: dict = {"drone": drone, "simulator": {"multirotor_guidance": True}}
    if wind is not None:
        over["wind"] = wind
    if mission:
        over["mission"] = mission
    return scenario_config(name, **over)


def straight(wind_mps: float, from_deg: float = 0.0) -> ScenarioConfig:
    """Un tramo recto hacia el este (3 km) y vuelta, con viento de base."""
    wind = {"base": {"speed_mps": wind_mps, "from_deg": from_deg}, "episodes": []}
    mission = {
        "id": "MSN-TEST",
        "waypoints": [{"id": "WP1", "x": 3000.0, "y": 0.0}],
        "return_to_base": True,
    }
    return multirotor(wind=wind, **mission)


def test_a_multirotor_holds_the_line_in_a_crosswind_it_can_compensate() -> None:
    """Con 6 m/s de viento lateral (el guiado de hoy se desvía 16 m) se queda en la línea."""
    flight = fly(straight(6.0), perturbed=True)  # viento del norte: empuja al sur
    middle = [s for s in flight.samples if 1000.0 < s.x < 2000.0]
    assert middle and max(abs(s.y) for s in middle) < 3.0
    assert flight.completed


def test_with_a_wind_above_its_airspeed_the_drone_drifts_downwind() -> None:
    """Si el viento lateral supera la velocidad máxima respecto al aire (17 m/s), no se puede
    compensar: deriva a sotavento (al sur) y se desvía decenas de metros."""
    cfg = straight(20.0)
    flight = fly(cfg, perturbed=True)
    assert cfg.drone.max_airspeed_mps < 20.0
    assert -min(s.y for s in flight.samples) > 30.0


def test_the_drone_brakes_for_the_corners_and_stops_at_the_end() -> None:
    """Sin perturbaciones no se abre en las esquinas de `nominal` (< 15 m, umbral de «en ruta») y
    llega a casa casi parado."""
    flight = fly(multirotor(wind=NO_WIND), perturbed=True)
    dev = [distance_to_route((s.x, s.y), flight.route) for s in flight.samples]
    assert max(dev) < 15.0 and flight.completed
    assert flight.samples[-1].speed_mps < 6.0  # frena para llegar (con 15 m/s de crucero)


@pytest.mark.parametrize("name", ["nominal", "demo"])
def test_acceleration_and_yaw_rate_limits(name: str) -> None:
    cfg = multirotor(name)
    flight = fly(cfg, perturbed=False)
    max_dv = cfg.drone.max_accel_mps2 * STEP_S
    max_dh = cfg.drone.max_turn_rate_dps * STEP_S
    for prev, cur in zip(flight.samples[1:], flight.samples[2:], strict=False):
        assert abs(cur.speed_mps - prev.speed_mps) <= max_dv + 1e-9
        assert abs(angle_diff_deg(cur.heading_deg, prev.heading_deg)) <= max_dh + 1e-9


def test_hold_position_cancels_the_wind_and_the_nose_stays() -> None:
    """En `failsafe_hold` la velocidad sobre el suelo es 0 (respecto al aire, igual al viento)."""
    sim = Simulator(straight(8.0), events=False)
    while sim.t < 60.0:
        sim.step()
    sim.set_mode("failsafe_hold")
    held = sim.samples[sim.n]
    heading = held.heading_deg
    while sim.t < 120.0:
        sim.step()
    end = sim.samples[sim.n]
    assert math.hypot(end.x - held.x, end.y - held.y) < 8.0 and end.speed_mps < 0.5
    assert end.heading_deg == pytest.approx(heading)  # la proa no cambia
    assert sim.aux[1100].mode == "failsafe_hold"  # t = 110 s


def test_failsafe_return_goes_straight_home_and_completes() -> None:
    sim = Simulator(straight(0.0), events=False)
    while sim.t < 60.0:
        sim.step()
    sim.set_mode("failsafe_return")
    flight = sim.run_physics()
    assert flight.completed and math.hypot(flight.samples[-1].x, flight.samples[-1].y) < 6.0
    assert flight.samples[-1].t < 140.0  # unos 800 m a casa, frenando al llegar
