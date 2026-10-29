"""Simulador incremental: fallos mute/loss, orden fijo del ruido y equivalencia con el generador."""

import math

import pytest

from helpers import scenario_config
from platform_app.generator.build import generate
from platform_app.generator.simulator import Simulator
from poc_contracts.enums import EventType, FaultMode, FaultOrigin, SensorSource
from poc_contracts.envelope import EventDraft

GPS, RADAR = SensorSource.GPS, SensorSource.RADAR
MANUAL = FaultOrigin.MANUAL


def run_all(sim: Simulator, until_s: float | None = None) -> list[EventDraft]:
    events = sim.start()
    while not sim.finished and (until_s is None or sim.t < until_s):
        events += sim.step()
    return events


def dump(events: list[EventDraft]) -> list[str]:
    return [e.model_dump_json() for e in events]


def test_step_by_step_equals_the_generator() -> None:
    cfg = scenario_config("demo")
    assert dump(run_all(Simulator(cfg))) == dump(generate(cfg).events)


def test_events_come_in_the_contract_order_within_an_instant() -> None:
    order = [
        EventType.WAYPOINT_REACHED,
        EventType.MISSION_COMPLETED,
        EventType.FAULT_INJECTED,
        EventType.FAULT_CLEARED,
        EventType.POSITION_UPDATED,
        EventType.TRACK_UPDATED,
        EventType.WIND_REPORTED,
        EventType.LINK_STATUS,
        EventType.BATTERY_STATUS,
    ]
    events = generate(scenario_config("faults")).events
    for a, b in zip(events, events[1:], strict=False):
        if a.sim_time == b.sim_time and a.type in order and b.type in order:
            assert order.index(a.type) <= order.index(b.type)
        assert a.sim_time <= b.sim_time


def test_a_muted_source_does_not_change_the_noise_of_the_others() -> None:
    cfg = scenario_config("nominal")
    base = run_all(Simulator(cfg))
    sim = Simulator(cfg)
    sim.set_fault(RADAR, FaultMode.MUTE, True, MANUAL)
    muted = run_all(sim)
    others = [
        e for e in muted if e.type != EventType.TRACK_UPDATED and not e.event_id.startswith("sim-")
    ]
    assert dump(others) == dump([e for e in base if e.type != EventType.TRACK_UPDATED])
    assert not [e for e in muted if e.type == EventType.TRACK_UPDATED]


def test_a_mute_does_not_change_the_flight_but_a_loss_does() -> None:
    cfg = scenario_config("nominal")
    base = Simulator(cfg, events=False).run_physics()
    muted = Simulator(cfg)
    muted.set_fault(GPS, FaultMode.MUTE, True, MANUAL)
    run_all(muted)
    assert muted.samples == base.samples

    lossy = Simulator(cfg)
    while lossy.t < 245:
        lossy.step()
    lossy.set_fault(GPS, FaultMode.LOSS, True, MANUAL)
    while lossy.t < 290:
        lossy.step()
    lossy.set_fault(GPS, FaultMode.LOSS, False, MANUAL)
    run_all(lossy)
    drift = max(
        math.hypot(a.x - b.x, a.y - b.y) for a, b in zip(lossy.samples, base.samples, strict=False)
    )
    assert drift > 30


def test_gps_during_a_loss_has_no_fix_and_is_the_estimate() -> None:
    cfg = scenario_config("faults")
    run = generate(cfg)
    during = [
        e for e in run.events if e.type == EventType.POSITION_UPDATED and 245 <= e.sim_time < 290
    ]
    assert len(during) == 45
    assert {(e.payload["fix"], e.payload["sats"]) for e in during} == {("none", 0)}
    assert all(e.payload["hdop"] >= 10 for e in during)
    outside = [
        e
        for e in run.events
        if e.type == EventType.POSITION_UPDATED and not 245 <= e.sim_time < 290
    ]
    assert {e.payload["fix"] for e in outside} == {"3d"}


def test_loss_is_navigation_on_estimate_it_ignores_the_wind() -> None:
    """Sin viento la estima coincide con la verdad; con viento, se separa `viento · tiempo`."""
    calm = scenario_config(
        "nominal", wind={"base": {"speed_mps": 0, "gust_mps": 0, "from_deg": 0}, "episodes": []}
    )
    sim = Simulator(calm)
    while sim.t < 50:
        sim.step()
    sim.set_fault(GPS, FaultMode.LOSS, True, MANUAL)
    while sim.t < 80:
        sim.step()
    assert math.dist(sim._est, (sim.samples[-1].x, sim.samples[-1].y)) < 1e-6  # noqa: SLF001

    windy = Simulator(scenario_config("nominal"))  # 2 m/s de base
    while windy.t < 50:
        windy.step()
    windy.set_fault(GPS, FaultMode.LOSS, True, MANUAL)
    while windy.t < 80:
        windy.step()
    gap = math.dist(windy._est, (windy.samples[-1].x, windy.samples[-1].y))  # noqa: SLF001
    assert gap == pytest.approx(2.0 * 30, rel=0.05)


def test_manual_fault_rules() -> None:
    sim = Simulator(scenario_config("faults"))
    with pytest.raises(ValueError, match="only exists for the GPS"):
        sim.set_fault(RADAR, FaultMode.LOSS, True, MANUAL)
    sim.set_fault(RADAR, FaultMode.MUTE, True, MANUAL)
    with pytest.raises(ValueError, match="already has an active fault"):
        sim.set_fault(RADAR, FaultMode.MUTE, True, MANUAL)
    with pytest.raises(ValueError, match="has no active"):
        sim.set_fault(GPS, FaultMode.MUTE, False, MANUAL)
    sim.set_fault(RADAR, FaultMode.MUTE, False, MANUAL)
    events = sim.start() + sim.step()
    assert [(e.type, e.event_id) for e in events if e.event_id.startswith("sim-")] == [
        (EventType.FAULT_INJECTED, "sim-0001"),
        (EventType.FAULT_CLEARED, "sim-0002"),
    ]


def test_a_scheduled_fault_cannot_be_ended_by_hand() -> None:
    sim = Simulator(scenario_config("faults"))
    while sim.t <= 121:
        sim.step()
    with pytest.raises(ValueError, match="scenario"):
        sim.set_fault(RADAR, FaultMode.MUTE, False, MANUAL)


def test_faults_still_active_when_the_mission_ends_are_cleared() -> None:
    sim = Simulator(scenario_config("nominal"))
    sim.set_fault(SensorSource.BATTERY, FaultMode.MUTE, True, MANUAL)
    events = run_all(sim)
    cleared = [e for e in events if e.type == EventType.FAULT_CLEARED]
    assert len(cleared) == 1
    assert cleared[0].sim_time == sim.samples[-1].t


# --- GPS con `loss` y `mute` a la vez (receptor muerto) -----------------------------------------

MUTE, LOSS = FaultMode.MUTE, FaultMode.LOSS


def advance(sim: Simulator, until_s: float) -> list[EventDraft]:
    """Pasos hasta el instante pedido (excluido); devuelve sus eventos."""
    events: list[EventDraft] = []
    while sim.t < until_s - 1e-9:
        events += sim.step()
    return events


def gps_fixes(events: list[EventDraft]) -> list[str]:
    return [e.payload["fix"] for e in events if e.type == EventType.POSITION_UPDATED]


@pytest.mark.parametrize("inject", [(MUTE, LOSS), (LOSS, MUTE)])
@pytest.mark.parametrize("clear_first", [MUTE, LOSS])
def test_gps_dead_receiver_in_any_order(
    inject: tuple[FaultMode, FaultMode], clear_first: FaultMode
) -> None:
    sim = Simulator(scenario_config("nominal"))
    sim.start()
    advance(sim, 20)
    sim.set_fault(GPS, inject[0], True, MANUAL)
    sim.set_fault(GPS, inject[1], True, MANUAL)
    assert {(s, f.mode) for s, f in sim.active_faults} == {(GPS, MUTE), (GPS, LOSS)}

    both = advance(sim, 40)
    assert gps_fixes(both) == []  # mute: no se publica nada
    assert [e.payload["mode"] for e in both if e.type == EventType.FAULT_INJECTED] == [
        m.value for m in inject
    ]

    sim.set_fault(GPS, clear_first, False, MANUAL)
    other = LOSS if clear_first == MUTE else MUTE
    assert [(s, f.mode) for s, f in sim.active_faults] == [(GPS, other)]
    one = advance(sim, 60)
    if other == LOSS:  # se quitó el mute: vuelven las posiciones, sin fix
        assert len(gps_fixes(one)) == 20 and set(gps_fixes(one)) == {"none"}
    else:  # se quitó el loss: el GPS vuelve a la real pero sigue callado
        assert gps_fixes(one) == []

    sim.set_fault(GPS, other, False, MANUAL)
    assert sim.active_faults == []
    rest = advance(sim, 80)
    assert set(gps_fixes(rest)) == {"3d"} and len(gps_fixes(rest)) >= 19
    cleared = [e.payload["mode"] for e in one + rest if e.type == EventType.FAULT_CLEARED]
    assert cleared == [clear_first.value, other.value]  # un FaultCleared por fallo, en su orden
    ids = [e.event_id for e in both + one + rest if e.event_id.startswith("sim-")]
    assert ids == ["sim-0001", "sim-0002", "sim-0003", "sim-0004"]


def test_gps_dead_receiver_events_are_numbered_one_per_fault() -> None:
    sim = Simulator(scenario_config("nominal"))
    events = sim.start()
    events += advance(sim, 10)
    sim.set_fault(GPS, MUTE, True, MANUAL)
    sim.set_fault(GPS, LOSS, True, MANUAL)
    events += advance(sim, 20)
    sim.set_fault(GPS, LOSS, False, MANUAL)
    sim.set_fault(GPS, MUTE, False, MANUAL)
    events += advance(sim, 25)
    faults = [
        (e.type.value, e.event_id, e.payload["mode"])
        for e in events
        if e.event_id.startswith("sim-")
    ]
    assert faults == [
        ("FaultInjected", "sim-0001", "mute"),
        ("FaultInjected", "sim-0002", "loss"),
        ("FaultCleared", "sim-0003", "loss"),
        ("FaultCleared", "sim-0004", "mute"),
    ]


def test_only_the_gps_accepts_two_faults_and_not_the_same_mode_twice() -> None:
    sim = Simulator(scenario_config("nominal"))
    sim.start()
    sim.set_fault(GPS, LOSS, True, MANUAL)
    with pytest.raises(ValueError, match="already has an active fault"):
        sim.set_fault(GPS, LOSS, True, MANUAL)
    sim.set_fault(GPS, MUTE, True, MANUAL)
    with pytest.raises(ValueError, match="already has an active fault"):
        sim.set_fault(GPS, MUTE, True, MANUAL)
    sim.set_fault(RADAR, MUTE, True, MANUAL)
    with pytest.raises(ValueError, match="already has an active fault"):
        sim.set_fault(RADAR, MUTE, True, MANUAL)
    with pytest.raises(ValueError, match="has no active"):
        sim.set_fault(SensorSource.LINK, MUTE, False, MANUAL)


def test_a_manual_mute_during_the_scheduled_gps_loss_combines_with_it() -> None:
    sim = Simulator(scenario_config("faults"))  # loss programado del GPS en [245, 290)
    sim.start()
    advance(sim, 250)
    sim.set_fault(GPS, MUTE, True, MANUAL)
    assert {(s, f.mode, f.origin) for s, f in sim.active_faults} >= {
        (GPS, LOSS, FaultOrigin.SCENARIO),
        (GPS, MUTE, MANUAL),
    }
    muted = advance(sim, 270)
    assert gps_fixes(muted) == []
    with pytest.raises(ValueError, match="scenario"):
        sim.set_fault(GPS, LOSS, False, MANUAL)
    sim.set_fault(GPS, MUTE, False, MANUAL)
    after = advance(sim, 285)
    assert set(gps_fixes(after)) == {"none"}  # sigue la pérdida programada
    done = advance(sim, 295)
    assert "3d" in gps_fixes(done)


def test_a_scheduled_fault_is_skipped_only_if_the_same_mode_is_already_active() -> None:
    sim = Simulator(scenario_config("faults"))  # radar mute programado en [120, 180)
    sim.start()
    advance(sim, 100)
    sim.set_fault(RADAR, MUTE, True, MANUAL)  # el programado se omite (mismo modo)
    events = advance(sim, 130)
    injected = [e.payload["origin"] for e in events if e.type == EventType.FAULT_INJECTED]
    assert injected == ["manual"]  # solo el manual: el programado no llega a activarse
    assert [(s, f.origin) for s, f in sim.active_faults] == [(RADAR, MANUAL)]
