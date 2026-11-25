"""Simulador v2, pasos 3 y 4: estimador a bordo, receptor GPS, radar con posición y estación."""

import math
import statistics

import pytest

from helpers import scenario_config
from platform_app.generator.build import generate
from platform_app.generator.simulator import Simulator
from poc_contracts.scenario import ScenarioConfig


def v2(name: str = "nominal", **over: object) -> ScenarioConfig:
    """Escenario con los valores de un multirrotor."""
    base = scenario_config(name)
    drone = {**base.drone.model_dump(), "acceptance_radius_m": 5.0, "max_turn_rate_dps": 100.0}
    return scenario_config(name, **{"drone": drone, **over})


def sensors_with(name: str = "nominal", **blocks: dict) -> dict:
    sensors = scenario_config(name).sensors.model_dump()
    for block, values in blocks.items():
        sensors[block].update(values)
    return sensors


def of_type(run, event_type: str) -> list:
    return [e for e in run.events if e.type == event_type]


def test_the_trajectory_depends_on_the_noise_but_not_on_publishing_events() -> None:
    """Con el estimador la trayectoria depende del ruido (otra semilla, otra trayectoria), pero un
    vuelo sin eventos es el de la ejecución con eventos y dos generaciones coinciden."""
    cfg = v2()
    first, second = generate(cfg), generate(cfg)
    assert first.truth == second.truth and first.events == second.events
    physics = Simulator(cfg, events=False).run_physics()
    live = [(round(s.x, 2), round(s.y, 2)) for s in physics.samples if round(s.t * 10) % 10 == 0]
    assert live == [(s.x, s.y) for s in first.truth.trajectory][: len(live)]
    other = generate(v2(seed=7))
    assert other.truth.trajectory != first.truth.trajectory


def test_the_estimator_learns_the_wind_without_a_wind_sensor() -> None:
    """El viento de base es de 2 m/s del 300°: a los 100 s el viento estimado a bordo lo da."""
    status = [e.payload for e in of_type(generate(v2()), "AutopilotStatus") if e.sim_time > 100]
    assert abs(statistics.mean(p["wind_est_speed_mps"] for p in status) - 2.0) < 0.6
    assert abs(statistics.mean(p["wind_est_from_deg"] for p in status) - 300.0) < 25.0


def test_the_gps_error_has_memory_and_sats_and_hdop_vary_slowly() -> None:
    run = generate(v2())
    truth = {s.t: s for s in run.truth.trajectory}
    gps = [e for e in of_type(run, "PositionUpdated") if e.sim_time in truth]
    err = [e.payload["x"] - truth[e.sim_time].x for e in gps]
    mean = statistics.mean(err)
    lag5 = [(a - mean) * (b - mean) for a, b in zip(err, err[5:], strict=False)]
    assert statistics.mean(lag5) / statistics.pvariance(err) > 0.3  # blanco: ≈ 0
    sats = [e.payload["sats"] for e in gps]
    hdop = [e.payload["hdop"] for e in gps]
    assert max(abs(a - b) for a, b in zip(sats, sats[1:], strict=False)) <= 1
    assert max(abs(a - b) for a, b in zip(hdop, hdop[1:], strict=False)) < 0.15
    assert min(sats) >= 12 and max(sats) <= 16 and min(hdop) > 0.5 and max(hdop) < 1.1


def test_without_gps_the_estimate_keeps_the_last_estimated_wind() -> None:
    """Pérdida de GPS de 45 s: con el viento constante, la estima (con el último viento estimado)
    apenas deriva; si el viento cambia durante la pérdida, la estima no lo sabe y el dron se
    desvía por `dead_reckoning`."""
    loss = [{"source": "gps", "mode": "loss", "start_s": 245.0, "end_s": 290.0}]
    calm = generate(v2(faults=loss))
    assert max(s.ref_dist_m for s in calm.truth.trajectory if 245 <= s.t <= 300) < 15.0
    gust = {"start_s": 250.0, "end_s": 300.0, "ramp_s": 5.0, "speed_mps": 14.0, "from_deg": 0.0}
    wind = {"base": scenario_config().wind.base.model_dump(), "episodes": [gust]}
    windy = generate(v2(faults=loss, wind=wind))
    assert max(s.ref_dist_m for s in windy.truth.trajectory if 245 <= s.t <= 300) > 25.0
    causes = {r.facets["drone.cause"] for r in windy.states if 250 <= r.t <= 295}
    assert "dead_reckoning" in causes


def test_the_estimator_absorbs_a_slow_spoofing_so_the_innovation_stays_small() -> None:
    """El engaño crece 1,5 m/s: la innovación no lo delata (< 6 m) y el viento estimado se separa
    del real, mientras el dron se va decenas de metros de la ruta."""
    run = generate(v2("spoofing"))
    during = [e.payload for e in of_type(run, "AutopilotStatus") if 200 <= e.sim_time <= 215]
    assert max(p["innovation_m"] for p in during) < 6.0
    assert max(s.ref_dist_m for s in run.truth.trajectory if 200 <= s.t <= 225) > 40.0
    est = max(p["wind_est_speed_mps"] for p in during)
    assert abs(est - 2.0) > 0.8  # el real son 2 m/s


def test_the_radar_loses_precision_with_distance_and_does_not_reach_beyond_its_range() -> None:
    sensors = sensors_with(radar={"sigma_m": 1.0, "sigma_per_km_m": 15.0, "max_range_m": 1800.0})
    run = generate(v2(sensors=sensors))
    truth = {s.t: s for s in run.truth.trajectory}
    near, far = [], []
    for e in of_type(run, "TrackUpdated"):
        s = truth.get(e.sim_time)
        if s is None:
            continue
        dist = math.hypot(s.x, s.y)
        assert dist <= 1800.0 + 1.0  # fuera de alcance no hay traza
        error = math.hypot(e.payload["x"] - s.x, e.payload["y"] - s.y)
        (near if dist < 600 else far if dist > 1300 else []).append(error)
    assert statistics.mean(far) > 2.0 * statistics.mean(near)
    away = [r for r in run.states if math.hypot(*_xy(truth, r.t)) > 1800.0]
    assert away and all(r.facets["radar.availability"] == "out_of_range" for r in away)


def _xy(truth: dict, t: float) -> tuple[float, float]:
    return truth[t].x, truth[t].y


def test_the_station_measures_a_fraction_of_the_wind_with_a_delay() -> None:
    """Escalón de viento de 10 m/s a T+100: la estación (factor 0,8, media de 30 s) sube poco a poco
    hasta 8 m/s."""
    sensors = sensors_with(meteo={"sigma_mps": 0.0, "sigma_deg": 0.0, "factor": 0.8, "lag_s": 30.0})
    step = {"start_s": 100.0, "end_s": 400.0, "ramp_s": 1.0, "speed_mps": 10.0, "from_deg": 0.0}
    wind = {"base": {"speed_mps": 0.0, "from_deg": 0.0}, "episodes": [step]}
    run = generate(v2(sensors=sensors, wind=wind))
    speed = {e.sim_time: e.payload["speed_mps"] for e in of_type(run, "WindReported")}
    assert speed[90.0] == 0.0
    assert 1.5 < speed[110.0] < 4.0 and 4.0 < speed[120.0] < 6.5  # sube con el retraso
    assert speed[150.0] == pytest.approx(8.0, abs=0.3)  # factor 0,8 · 10 m/s
