"""Simulador v2, pasos 5 y 6: enlace con física, failsafes, batería con consumo y emisores."""

import statistics

import pytest

from helpers import scenario_config
from platform_app.generator.build import generate
from platform_app.generator.energy import power_w
from platform_app.generator.scenario_io import load_scenario
from poc_contracts.scenario import ScenarioConfig

FULL = {
    "multirotor_guidance": True,
    "onboard_estimator": True,
    "gps_receiver": True,
    "radar_geometry": True,
    "ground_station": True,
    "link_physics": True,
    "battery_model": True,
    "emitters": True,
}


def full(name: str = "nominal", drone: dict | None = None, **over: object) -> ScenarioConfig:
    base = scenario_config(name)
    d = {**base.drone.model_dump(), "acceptance_radius_m": 5.0, "max_turn_rate_dps": 100.0}
    d.update(drone or {})
    return scenario_config(name, **{"drone": d, "simulator": FULL, **over})


def of_type(run, event_type: str) -> list:
    return [e for e in run.events if e.type == event_type]


def modes(run) -> list[str]:
    out: list[str] = []
    for s in run.truth.trajectory:
        if not out or out[-1] != s.mode:
            out.append(s.mode)
    return out


def test_a_hijack_is_a_lost_link_for_our_station_and_the_telemetry_has_a_gap() -> None:
    """Secuestro = nuestra estación pierde su enlace: no llega ni GPS, ni receptor, ni autopiloto,
    ni batería, pero el radar sigue; `LinkStatus` dice 100 % de pérdida y no hay controlador."""
    run = generate(full("hijack", drone={"link_loss_action": "return"}))
    h = scenario_config("hijack").hijack
    inside = lambda e: h.start_s + 1 <= e.sim_time < h.end_s  # noqa: E731
    for kind in ("PositionUpdated", "GnssStatus", "AutopilotStatus"):
        assert not [e for e in of_type(run, kind) if inside(e)], kind
    assert [e for e in of_type(run, "TrackUpdated") if inside(e)]  # el radar es independiente
    link = [e.payload for e in of_type(run, "LinkStatus") if inside(e)]
    assert link and all(p["packet_loss_pct"] == 100.0 and p["rssi_dbm"] is None for p in link)
    assert all("controller_id" not in e.payload for e in of_type(run, "LinkStatus"))
    during = [s for s in run.truth.trajectory if h.start_s <= s.t < h.end_s]
    assert all(s.mode == "foreign_control" and not s.link_up for s in during)
    assert "failsafe_return" not in modes(run)  # el dron obedece a otro: no salta nuestro failsafe


@pytest.mark.parametrize(
    ("action", "mode", "ends"),
    [
        ("continue", None, "returned_to_base"),
        ("hold", "failsafe_hold", "timeout"),  # mantiene la posición hasta que acaba el tiempo
        ("return", "failsafe_return", "returned_to_base"),
        ("land", "failsafe_land", "landed"),
    ],
)
def test_the_link_failsafe_acts_after_ten_seconds_without_link(
    action: str, mode: str | None, ends: str
) -> None:
    """`mute` del enlace = enlace caído en los dos sentidos: tras 10 s salta el failsafe con la
    acción configurada (por defecto, seguir el plan)."""
    fault = [{"source": "link", "mode": "mute", "start_s": 100.0, "end_s": 140.0}]
    cfg = full(faults=fault, drone={"link_loss_action": action})
    run = generate(cfg)
    first = next((s.t for s in run.truth.trajectory if s.mode != "mission"), None)
    if mode is None:
        assert first is None
    else:
        assert first is not None and 109.0 <= first <= 112.0  # 100 s + 10 s
        assert mode in modes(run)
    done = of_type(run, "MissionCompleted")[0].payload
    assert done["reason"] == ends and done["completed"] == (ends == "returned_to_base")
    lost = [r for r in run.states if 101 <= r.t <= 139]
    assert all(r.facets["link.availability"] == "lost" for r in lost)


def test_a_weak_link_loses_packets_and_the_station_counts_them() -> None:
    """Con una pérdida de ~50 % llega ~la mitad de la telemetría y `LinkStatus` la mide."""
    link = scenario_config().sensors.link.model_dump() | {"loss_slope_db": 1.0e6}
    run = generate(full(sensors={**scenario_config().sensors.model_dump(), "link": link}))
    flown = int(run.truth.duration_s)
    delivered = len(of_type(run, "PositionUpdated"))
    assert 0.35 < delivered / flown < 0.65
    losses = [e.payload["packet_loss_pct"] for e in of_type(run, "LinkStatus")]
    assert 30.0 < statistics.mean(losses) < 70.0


def test_without_fix_the_gps_gives_no_position_and_the_estimate_goes_in_the_autopilot() -> None:
    loss = [{"source": "gps", "mode": "loss", "start_s": 245.0, "end_s": 290.0}]
    run = generate(full(faults=loss))
    gps = [e.payload for e in of_type(run, "PositionUpdated") if 250 <= e.sim_time <= 285]
    assert gps and all(p["fix"] == "none" and p["sats"] == 0 for p in gps)
    assert all(p[k] is None for p in gps for k in ("x", "y", "alt_m", "speed_mps", "course_deg"))
    pilot = [e.payload for e in of_type(run, "AutopilotStatus") if 250 <= e.sim_time <= 285]
    assert pilot and all(p["innovation_m"] is None for p in pilot)  # sin GPS no se corrige
    assert all(p["ground_speed_mps"] > 5.0 for p in pilot)  # la estima sigue dando velocidad
    truth = {s.t: s for s in run.truth.trajectory}
    assert abs(pilot[0]["est_x"] - truth[250.0].est_x) < 20.0


def test_the_power_curve_is_u_shaped_and_the_battery_drains_faster_against_the_wind() -> None:
    assert power_w(5, 400) < power_w(0, 400) and power_w(15, 400) < power_w(5, 400)
    assert power_w(30, 400) > power_w(20, 400)  # en U: el mínimo está en torno a 20 m/s
    run = generate(load_scenario("endurance"))  # a favor a la ida, de cara a la vuelta
    soc = {s.t: s.battery_soc for s in run.truth.trajectory}
    x = {s.t: s.x for s in run.truth.trajectory}
    per_km_out = (soc[0.0] - soc[250.0]) / (x[250.0] / 1000)
    per_km_back = (soc[300.0] - soc[550.0]) / ((x[300.0] - x[550.0]) / 1000)
    assert per_km_back > 1.4 * per_km_out  # contra el viento cada km cuesta mucho más


def test_endurance_turns_back_before_the_battery_runs_out_and_lands_at_five_percent() -> None:
    """«No llega a casa» con el viento: vuelve por su cuenta; luego 15 % bajo, 7 % crítico (vuelve)
    y 5 % aterriza (PX4)."""
    run = generate(load_scenario("endurance"))
    assert modes(run) == ["mission", "failsafe_return", "failsafe_land"]
    assert max(s.x for s in run.truth.trajectory) < 5000.0  # no llega al punto de giro (6 km)
    first = {}
    for r in run.states:
        for facet in ("battery.endurance", "battery.level"):
            first.setdefault((facet, r.facets[facet]), r.t)
    assert first[("battery.endurance", "cannot_reach_home")] < first[("battery.level", "low")]
    assert first[("battery.level", "low")] < first[("battery.level", "critical")]
    done = of_type(run, "MissionCompleted")[0].payload
    assert done == {"mission_id": "MSN-ENDURANCE", "completed": False, "reason": "landed"}


def test_the_emitters_change_the_receivers_cn0_and_agc_with_their_distance() -> None:
    def mean(run, a, b, field):
        return statistics.mean(
            e.payload[field] for e in of_type(run, "GnssStatus") if a <= e.sim_time < b
        )

    jam = generate(load_scenario("jamming"))  # interferencia: C/N0 baja y AGC baja
    assert mean(jam, 130, 170, "cn0_dbhz") < 35.0 < mean(jam, 20, 90, "cn0_dbhz")
    assert mean(jam, 130, 170, "agc_db") < -5.0
    far = [
        {
            "id": "jammer-far",
            "x": 9000.0,
            "y": 9000.0,
            "power_db": 8.0,
            "start_s": 110.0,
            "end_s": 270.0,
        }
    ]
    far_run = generate(full("jamming", emitters=far))
    assert mean(far_run, 130, 170, "cn0_dbhz") > mean(jam, 130, 170, "cn0_dbhz") + 10.0
    spoof = scenario_config("spoofing").spoofing.model_dump() | {
        "emitter": {"x": 1000.0, "y": 1500.0, "power_db": 12.0}
    }
    run = generate(full("spoofing", spoofing=spoof))  # engaño: C/N0 sube y AGC baja
    base = mean(run, 20, 90, "cn0_dbhz")
    assert mean(run, 190, 220, "cn0_dbhz") > base + 2.0
    assert mean(run, 190, 220, "agc_db") < -1.0
    assert {e.id for e in run.truth.emitters} == {"spoofer-1"}
    active = {s.t: s.emitters_active for s in run.truth.trajectory}
    assert active[200.0] == ["spoofer-1"] and active[50.0] == []
