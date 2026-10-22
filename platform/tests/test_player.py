"""Reproductor: en directo es idéntico a `events.jsonl`, pausa/paso, reinicio, fallos manuales,
modo interactivo y «esperar al agente». Todo sin tiempo real."""

import json
from pathlib import Path

import pytest

from helpers import make_player, published_drafts
from platform_app.generator.build import generate
from platform_app.generator.scenario_io import load_scenario
from platform_app.paths import RUNS_DIR
from platform_app.player import INTERACTIVE_OFF_MESSAGE, Player, PlayerError
from poc_contracts.enums import EventType, FaultMode, PlayerStatus, SensorSource
from poc_contracts.envelope import Envelope

ALL = ["demo", "fallos", "nominal", "secuestro", "spoofing", "viento"]


def types(player: Player) -> list[str]:
    return [e.type.value for e in player.bus.timeline.all()]


def of_type(player: Player, event_type: EventType) -> list[Envelope]:
    return [e for e in player.bus.timeline.all() if e.type == event_type]


@pytest.mark.parametrize("name", ALL)
def test_live_events_are_identical_to_events_jsonl(runs_dir: Path, name: str) -> None:
    """Obligatoria: sin intervenciones, lo publicado es lo del fichero versionado."""
    player = make_player(runs_dir)
    player.load(name)
    player.run_to_end()
    expected = [
        json.loads(line) for line in (RUNS_DIR / name / "events.jsonl").read_text().splitlines()
    ]
    assert published_drafts(player) == expected
    state = player.state()
    assert state.status == PlayerStatus.FINISHED
    assert state.cursor == state.total_events == len(expected)


def test_seq_is_global_and_numbering_is_split_between_simulator_and_player(
    runs_dir: Path,
) -> None:
    player = make_player(runs_dir)
    player.load("fallos")
    player.run_to_end()
    timeline = player.bus.timeline.all()
    assert [e.seq for e in timeline] == list(range(1, len(timeline) + 1))
    faults = [e for e in timeline if e.type in (EventType.FAULT_INJECTED, EventType.FAULT_CLEARED)]
    assert faults and all(e.event_id.startswith("sim-") for e in faults)
    own = [e for e in timeline if e.event_id.startswith("plr-")]
    assert [e.type.value for e in own] == ["SimulationStarted", "SimulationFinished"]
    assert [e.event_id for e in own] == ["plr-0001", "plr-0002"]
    assert all(e.source == "platform-player" for e in own)


def test_load_publishes_expected_values_and_waits_for_play(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("viento")
    started = player.bus.timeline.all()
    assert [e.type for e in started] == [EventType.SIMULATION_STARTED]
    expected = generate(load_scenario("viento"))
    assert started[0].payload == {
        "scenario": "viento",
        "run_id": player.run_id,
        "duration_s": expected.truth.duration_s,
        "total_events": len(expected.events),
    }
    assert player.state().status == PlayerStatus.IDLE
    player.advance(10)  # sin play no avanza
    assert len(player.bus.timeline) == 1
    player.play()
    assert player.state().status == PlayerStatus.RUNNING
    player.advance(5)
    assert "MissionPlanned" in types(player)


def test_load_generates_the_run_when_missing(tmp_path: Path) -> None:
    player = make_player(tmp_path)
    player.load("nominal")
    assert (tmp_path / "nominal" / "events.jsonl").exists()


def test_unknown_scenario_and_commands_without_scenario(tmp_path: Path) -> None:
    player = make_player(tmp_path)
    with pytest.raises(PlayerError, match="ningún escenario"):
        player.play()
    with pytest.raises(PlayerError, match="desconocido"):
        player.load("../etc")


def test_pause_resume_and_speed(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.play()
    player.advance(20)
    player.pause()
    paused_at = player.sim_time
    player.advance(20)  # en pausa no avanza
    assert player.sim_time == paused_at
    player.play()
    player.set_speed(16)
    assert player.state().speed == 16
    with pytest.raises(PlayerError):
        player.set_speed(3)
    assert types(player).count("SimulationPaused") == 1
    assert types(player).count("SimulationResumed") == 1
    assert of_type(player, EventType.SIMULATION_PAUSED)[0].payload == {"reason": "user"}


def test_step_publishes_one_event_and_pauses(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    seen = []
    for k in range(6):
        player.step()
        assert player.state().cursor == k + 1  # un evento del simulador por paso
        assert player.state().status == PlayerStatus.PAUSED
        seen.append([e for e in player.bus.timeline.all() if not e.event_id.startswith("plr-")][-1])
    assert [e.type.value for e in seen[:3]] == [
        "MissionPlanned",
        "MissionStarted",
        "PositionUpdated",
    ]
    assert player.state().cursor == 6


def test_a_step_from_idle_publishes_paused_so_that_play_resumes_coherently(
    runs_dir: Path,
) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.step()
    assert types(player).count("SimulationPaused") == 1
    assert of_type(player, EventType.SIMULATION_PAUSED)[0].payload == {"reason": "user"}
    player.step()  # ya en pausa: no repite el aviso
    assert types(player).count("SimulationPaused") == 1
    player.play()
    assert types(player).count("SimulationResumed") == 1
    plr = [e.type.value for e in player.bus.timeline.all() if e.event_id.startswith("plr-")]
    assert plr == ["SimulationStarted", "SimulationPaused", "SimulationResumed"]


def test_step_to_the_end_finishes(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    total = player.state().total_events
    for _ in range(total):
        player.step()
    assert player.state().status == PlayerStatus.FINISHED
    assert types(player)[-1] == "SimulationFinished"
    with pytest.raises(PlayerError):
        player.step()


def test_stepping_then_playing_gives_the_same_events(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("viento")
    for _ in range(10):
        player.step()
    player.run_to_end()
    expected = [
        json.loads(line) for line in (RUNS_DIR / "viento" / "events.jsonl").read_text().splitlines()
    ]
    assert published_drafts(player) == expected


def test_reset_reloads_with_new_run_id_and_clean_bus(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.set_interactive(True)  # se conserva entre reinicios
    player.load("nominal")
    first_run = player.run_id
    player.set_speed(4)
    player.play()
    player.advance(30)
    player.reset()
    assert player.run_id != first_run
    assert player.state().status == PlayerStatus.IDLE
    assert player.state().interactive and player.state().speed == 4
    timeline = player.bus.timeline.all()
    assert [e.seq for e in timeline] == [1, 2]
    assert [e.type for e in timeline] == [
        EventType.SIMULATION_STARTED,
        EventType.INTERACTIVE_MODE_CHANGED,
    ]
    assert [e.event_id for e in timeline] == ["plr-0001", "plr-0002"]
    assert player.state().cursor == 0 and player.sim_time == 0.0
    # la ejecución a medias dejó su timeline, con el SimulationReset al final
    old = runs_dir / "nominal" / str(first_run) / "timeline.jsonl"
    assert json.loads(old.read_text().splitlines()[-1])["type"] == "SimulationReset"


def test_timeline_keeps_appending_after_the_dump(runs_dir: Path) -> None:
    """Lo que llega después de `SimulationFinished` (respuestas, informe, chats) también queda."""
    player = make_player(runs_dir)
    player.load("nominal")
    player.run_to_end()
    path = runs_dir / "nominal" / str(player.run_id) / "timeline.jsonl"
    before = len(path.read_text().splitlines())
    late = player.bus.publish(cleared(1, player.sim_time))
    lines = path.read_text().splitlines()
    assert len(lines) == before + 1 == len(player.bus.timeline)
    assert json.loads(lines[-1])["event_id"] == late.event_id
    # al cargar otro escenario el fichero antiguo deja de recibir eventos
    player.load("viento")
    player.bus.publish(cleared(2, 1.0))
    assert len(path.read_text().splitlines()) == before + 2  # solo el SimulationReset de la carga


def test_finishing_dumps_the_timeline(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.run_to_end()
    path = runs_dir / "nominal" / str(player.run_id) / "timeline.jsonl"
    lines = path.read_text().splitlines()
    assert len(lines) == len(player.bus.timeline)
    assert json.loads(lines[-1])["type"] == "SimulationFinished"


def test_load_another_scenario_resets_the_bus(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.run_to_end()
    player.load("viento")
    assert player.state().scenario == "viento"
    assert [e.seq for e in player.bus.timeline.all()] == [1]


# --- Modo interactivo y fallos manuales --------------------------------------------------------


def test_fault_is_rejected_when_interactive_is_off(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.play()
    player.advance(20)
    before = len(player.bus.timeline)
    with pytest.raises(PlayerError) as exc:
        player.fault(SensorSource.RADAR, FaultMode.MUTE, True)
    assert str(exc.value) == INTERACTIVE_OFF_MESSAGE
    assert str(exc.value) == "el modo interactivo está apagado: actívalo para inyectar fallos"
    assert len(player.bus.timeline) == before
    assert player.state().active_faults == []


def test_interactive_mode_changes_are_published_once(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.set_interactive(False)  # sin cambio: nada
    player.set_interactive(True)
    player.set_interactive(True)
    player.set_interactive(False)
    changes = of_type(player, EventType.INTERACTIVE_MODE_CHANGED)
    assert [e.payload for e in changes] == [{"interactive": True}, {"interactive": False}]
    assert all(e.event_id.startswith("plr-") and e.source == "platform-player" for e in changes)


def test_manual_mute_drops_the_source_and_keeps_the_trajectory(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.set_interactive(True)
    player.load("nominal")
    player.play()
    player.advance(30)
    player.fault(SensorSource.RADAR, FaultMode.MUTE, True)
    assert [(f.source, f.mode.value, f.origin.value) for f in player.state().active_faults] == [
        (SensorSource.RADAR, "mute", "manual")
    ]
    player.advance(30)
    player.fault(SensorSource.RADAR, FaultMode.MUTE, False)
    assert player.state().active_faults == []
    player.run_to_end()

    radar_times = [e.sim_time for e in of_type(player, EventType.TRACK_UPDATED)]
    assert not [t for t in radar_times if 30.0 <= t < 60.0]
    assert [t for t in radar_times if t >= 60.0]
    faults = [e for e in player.bus.timeline.all() if e.event_id.startswith("sim-")]
    assert [(e.type.value, e.event_id, e.payload["origin"]) for e in faults] == [
        ("FaultInjected", "sim-0001", "manual"),
        ("FaultCleared", "sim-0002", "manual"),
    ]
    # el resto de eventos es exactamente el del escenario: el mute no cambia nada más
    expected = [
        json.loads(line)
        for line in (RUNS_DIR / "nominal" / "events.jsonl").read_text().splitlines()
    ]
    remaining = [
        e for e in expected if not (e["type"] == "TrackUpdated" and 30.0 <= e["sim_time"] < 60.0)
    ]
    got = [d for d in published_drafts(player) if not d["event_id"].startswith("sim-")]
    assert got == remaining
    # y la trayectoria real es la misma
    assert player.truth().trajectory == generate(load_scenario("nominal")).truth.trajectory


def test_manual_gps_loss_changes_the_trajectory_and_publishes_fix_none(runs_dir: Path) -> None:
    baseline = generate(load_scenario("viento")).truth
    player = make_player(runs_dir)
    player.set_interactive(True)
    player.load("viento")
    player.play()
    player.advance(90)
    player.fault(SensorSource.GPS, FaultMode.LOSS, True)
    player.advance(60)
    player.fault(SensorSource.GPS, FaultMode.LOSS, False)
    player.run_to_end()

    during = [e for e in of_type(player, EventType.POSITION_UPDATED) if 90.0 <= e.sim_time < 150.0]
    assert during
    assert all(e.payload["fix"] == "none" and e.payload["sats"] == 0 for e in during)
    after = [e for e in of_type(player, EventType.POSITION_UPDATED) if e.sim_time > 152.0]
    assert after and all(e.payload["fix"] == "3d" for e in after)

    final = player.truth().trajectory
    gap = max(
        ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
        for a, b in zip(final, baseline.trajectory, strict=False)
    )
    assert gap > 20.0


def test_manual_fault_errors(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.set_interactive(True)
    with pytest.raises(PlayerError, match="ningún escenario"):
        player.fault(SensorSource.RADAR, FaultMode.MUTE, True)
    player.load("fallos")
    player.play()
    player.advance(125)  # el mute del radar del escenario está activo
    with pytest.raises(PlayerError, match="ya tiene un fallo"):
        player.fault(SensorSource.RADAR, FaultMode.MUTE, True)
    with pytest.raises(PlayerError, match="escenario"):
        player.fault(SensorSource.RADAR, FaultMode.MUTE, False)
    with pytest.raises(PlayerError, match="solo existe para el GPS"):
        player.fault(SensorSource.RADAR, FaultMode.LOSS, True)


def test_truth_never_passes_the_current_instant(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("demo")
    player.play()
    player.advance(100.5)
    truth = player.truth()
    assert truth.trajectory[-1].t <= player.sim_time
    assert truth.wind[-1].t <= player.sim_time
    assert truth.trajectory[-1].t >= 100.0


# --- Esperar al agente --------------------------------------------------------------------------


def detection(number: int, sim_time: float, kind: EventType = EventType.DETECTION_RAISED):
    from platform_app.generator.events import make_event

    payload = {
        "detection_id": f"det-{number:04d}",
        "rule": "ROUTE_DEVIATION",
        "severity": "medium",
        "value": 35.0,
        "threshold": 30.0,
        "unit": "m",
        "source": None,
        "window": {"since": sim_time - 4, "until": sim_time},
        "trigger_event_ids": [],
        "message": "desviación",
    }
    return make_event(load_scenario("nominal"), kind, sim_time, number, payload)


def monitor_reply(number: int, causation_id: str, sim_time: float):
    from platform_app.generator.events import make_event

    payload = {
        "alert_id": f"ai-{number:04d}",
        "detection_ids": [causation_id],
        "cause": "WIND",
        "severity": "low",
        "confidence": 0.8,
        "summary": "viento",
        "explanation": "x",
        "recommendation": "y",
        "evidence_event_ids": ["gps-000001"],
        "supersedes": None,
        "as_of_sim_time": sim_time,
        "fallback": False,
    }
    event = make_event(
        load_scenario("nominal"), EventType.ANOMALY_DETECTED, sim_time, number, payload
    )
    return event.model_copy(update={"causation_id": causation_id})


def test_wait_agent_pauses_on_detection_and_resumes_on_the_monitor_reply(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.set_wait_agent(True)
    bus = player.bus
    raised: list[Envelope] = []

    def fake_detector(event: Envelope) -> None:
        # a los 40 s el detector avisa (una vez)
        if event.type == EventType.POSITION_UPDATED and event.sim_time == 40.0 and not raised:
            raised.append(bus.publish(detection(1, event.sim_time)))

    bus.subscribe("citadel.pub.evt.air.d1.>", fake_detector)
    player.play()
    player.advance(60)
    # el monitor no ha contestado: el reproductor está esperando
    assert player.state().status == PlayerStatus.PAUSED
    waiting_at = player.sim_time
    assert of_type(player, EventType.SIMULATION_PAUSED)[-1].payload == {"reason": "waiting_agent"}
    player.advance(30)
    assert player.sim_time == waiting_at
    # un evento del monitor con otro causation_id no reanuda
    bus.publish(monitor_reply(1, "det-9999", waiting_at))
    assert player.state().status == PlayerStatus.PAUSED
    bus.publish(monitor_reply(2, raised[0].event_id, waiting_at))
    assert player.state().status == PlayerStatus.RUNNING
    assert types(player).count("SimulationResumed") == 1
    player.advance(5)
    assert player.sim_time > waiting_at


def cleared(number: int, sim_time: float) -> Envelope:
    from platform_app.generator.events import make_event

    payload = {
        "detection_id": f"det-{number:04d}",
        "rule": "ROUTE_DEVIATION",
        "duration_s": 20.0,
        "max_value": 40.0,
    }
    return make_event(
        load_scenario("nominal"), EventType.DETECTION_CLEARED, sim_time, number + 50, payload
    )


def test_wait_agent_resumes_with_a_detection_acknowledged(runs_dir: Path) -> None:
    """Cualquier evento del monitor con el `causation_id` de la detección reanuda, también la
    respuesta que no crea alerta; un `DetectionUpdated` espera por su propio `event_id`."""
    from platform_app.generator.events import make_event

    def ack(number: int, detection_id: str, causation_id: str, sim_time: float) -> Envelope:
        payload = {
            "detection_id": detection_id,
            "alert_id": None,
            "reason": "sin alerta",
            "as_of_sim_time": sim_time,
            "fallback": False,
        }
        event = make_event(
            load_scenario("nominal"), EventType.DETECTION_ACKNOWLEDGED, sim_time, number, payload
        )
        return event.model_copy(update={"causation_id": causation_id})

    player = make_player(runs_dir)
    player.load("nominal")
    player.set_wait_agent(True)
    player.play()
    player.advance(10)
    raised = player.bus.publish(detection(1, player.sim_time))
    updated = player.bus.publish(detection(2, player.sim_time, EventType.DETECTION_UPDATED))
    assert player.state().status == PlayerStatus.PAUSED
    # el `detection_id` no vale: hay que responder al `event_id` de cada evento de detección
    player.bus.publish(ack(1, "det-0001", "det-0001-no", player.sim_time))
    assert player.state().status == PlayerStatus.PAUSED
    player.bus.publish(ack(2, "det-0001", raised.event_id, player.sim_time))
    assert player.state().status == PlayerStatus.PAUSED
    player.bus.publish(ack(3, "det-0001", updated.event_id, player.sim_time))
    assert player.state().status == PlayerStatus.RUNNING


def test_wait_agent_does_not_pause_on_a_cleared_detection(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.set_wait_agent(True)
    player.play()
    player.advance(10)
    player.bus.publish(cleared(1, player.sim_time))
    assert player.state().status == PlayerStatus.RUNNING


def test_wait_agent_resumes_after_the_wall_clock_timeout(runs_dir: Path) -> None:
    now = [1000.0]
    player = make_player(runs_dir, wait_timeout_s=3.0, wall_clock=lambda: now[0])
    player.load("nominal")
    player.set_wait_agent(True)
    player.play()
    player.advance(10)
    player.bus.publish(detection(1, player.sim_time, EventType.DETECTION_UPDATED))
    assert player.state().status == PlayerStatus.PAUSED
    now[0] += 2.9
    player.check_wait_timeout()
    assert player.state().status == PlayerStatus.PAUSED
    now[0] += 0.2
    player.check_wait_timeout()
    assert player.state().status == PlayerStatus.RUNNING


def test_wait_agent_off_ignores_detections_and_turning_it_off_resumes(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.play()
    player.advance(10)
    player.bus.publish(detection(1, player.sim_time))
    assert player.state().status == PlayerStatus.RUNNING
    player.set_wait_agent(True)
    player.bus.publish(detection(2, player.sim_time))
    assert player.state().status == PlayerStatus.PAUSED
    player.set_wait_agent(False)
    assert player.state().status == PlayerStatus.RUNNING


def test_user_pause_is_not_lifted_by_the_agent(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.set_wait_agent(True)
    player.play()
    player.advance(10)
    player.pause()
    d = player.bus.publish(detection(1, player.sim_time))
    player.bus.publish(monitor_reply(1, d.event_id, player.sim_time))
    assert player.state().status == PlayerStatus.PAUSED
