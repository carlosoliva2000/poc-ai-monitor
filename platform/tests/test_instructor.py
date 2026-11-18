"""Comandos del instructor (v0.18): viento por comando, validación, aplicación con rampa y
duración, cancelación, relevo, determinismo del escenario y etiquetas."""

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from helpers import make_player, scenario_config
from platform_app.generator.build import generate
from platform_app.generator.disturbances import CommandWind, wind_at
from platform_app.generator.scenario_io import load_scenario
from platform_app.generator.simulator import Simulator
from platform_app.player import INTERACTIVE_OFF_MESSAGE_COMMANDS, PlayerError
from poc_contracts.commands import InstructorControl, WindCommandParams
from poc_contracts.enums import CommandIssuer, EventType


def params(**kw: float | None) -> WindCommandParams:
    base = {
        "from_deg": 0.0,
        "speed_mps": 12.0,
        "ramp_s": 10.0,
        "duration_s": 60.0,
    }
    return WindCommandParams.model_validate({**base, **kw})


def set_wind(
    issued_by: CommandIssuer = CommandIssuer.PANEL, **kw: float | None
) -> InstructorControl:
    text = "wind from the north" if issued_by == CommandIssuer.LLM else None
    return InstructorControl(
        command="set_wind", params=params(**kw), issued_by=issued_by, text=text
    )


CANCEL = InstructorControl(command="cancel_wind", params=None, issued_by="panel", text=None)


def fly(sim: Simulator, seconds: float) -> list:
    events = []
    for _ in range(round(seconds / 0.1)):
        events += sim.step()
    return events


def live() -> Simulator:
    sim = Simulator(scenario_config("nominal"))
    sim.start()
    return sim


# --- Validación ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"speed_mps": 41.0},  # por encima de 40 m/s
        {"speed_mps": -1.0},
        {"from_deg": 361.0},
        {"ramp_s": 0.0},
        {"ramp_s": 121.0},
        {"duration_s": 0.0},
        {"duration_s": 1801.0},
    ],
)
def test_wind_params_are_validated(bad: dict) -> None:
    with pytest.raises(ValidationError):
        params(**bad)


def test_wind_params_accept_the_limits_and_normalize_360() -> None:
    p = params(from_deg=360.0, speed_mps=40.0, duration_s=None)
    assert p.from_deg == 0.0 and p.duration_s is None


def test_command_needs_params_only_when_it_sets_wind() -> None:
    with pytest.raises(ValidationError):
        InstructorControl(command="set_wind", params=None, issued_by="panel", text=None)
    with pytest.raises(ValidationError):
        InstructorControl(command="cancel_wind", params=params(), issued_by="panel", text=None)
    with pytest.raises(ValidationError):  # el LLM lleva la frase original
        InstructorControl(command="set_wind", params=params(), issued_by="llm", text=None)
    with pytest.raises(ValidationError):  # `scenario` solo existe en el YAML
        InstructorControl(command="set_wind", params=params(), issued_by="scenario", text=None)


# --- El viento ----------------------------------------------------------------------------------


def test_command_wind_ramps_holds_and_returns_to_the_scenario_wind() -> None:
    base = scenario_config("nominal").wind  # 2 m/s, del 300°
    c = CommandWind(100.0, params())  # 12 m/s, del N, 60 s, rampa 10 s
    assert wind_at(99.0, base, [c]) == wind_at(99.0, base)
    assert wind_at(100.0, base, [c]).speed_mps == pytest.approx(2.0)  # arranca en el viento base
    assert wind_at(105.0, base, [c]).speed_mps == pytest.approx(7.0)
    full = wind_at(130.0, base, [c])
    assert (full.speed_mps, full.from_deg) == (12.0, 0.0)
    assert wind_at(155.0, base, [c]).speed_mps == pytest.approx(7.0)  # baja con la misma rampa
    assert wind_at(160.5, base, [c]) == wind_at(160.5, base)  # acabó: el del escenario


def test_command_wind_without_duration_lasts_until_cancelled() -> None:
    base = scenario_config("nominal").wind
    c = CommandWind(10.0, params(duration_s=None))
    assert wind_at(5000.0, base, [c]).speed_mps == 12.0


def test_command_wind_replaces_the_scenario_episode() -> None:
    wind = scenario_config("wind").wind  # episodio de 12 m/s del 350° entre 95 y 150 s
    c = CommandWind(100.0, params(from_deg=90.0, speed_mps=5.0, ramp_s=5.0))
    w = wind_at(120.0, wind, [c])
    assert (w.speed_mps, w.from_deg) == (5.0, 90.0)  # no se suma al episodio


# --- Simulador en directo -----------------------------------------------------------------------


def test_live_command_publishes_its_event_and_the_station_measures_it() -> None:
    sim = live()
    fly(sim, 40.0)
    body = set_wind()
    sim.apply_command(body, body.issued_by, body.text)
    events = fly(sim, 80.0)
    commands = [e for e in events if e.type == EventType.INSTRUCTOR_COMMAND]
    assert [(e.event_id, e.sim_time, e.source) for e in commands] == [
        ("cmd-0001", 40.0, "platform-player")
    ]
    assert commands[0].topic == "citadel.pub.evt.sim.instructor.InstructorCommand.v1"
    assert commands[0].payload["issued_by"] == "panel"
    assert commands[0].payload["params"]["speed_mps"] == 12.0
    full = [
        e.payload
        for e in events
        if e.type == EventType.WIND_REPORTED and 60.0 <= e.sim_time <= 80.0
    ]
    assert len(full) == 3  # T+60, T+70 y T+80
    assert all(10.0 < w["speed_mps"] < 14.0 for w in full)
    assert all(min(w["from_deg"], 360.0 - w["from_deg"]) < 30.0 for w in full)  # del norte
    truth = sim.truth().wind
    assert next(w for w in truth if w.t == 60.0).speed_mps == 12.0
    assert next(w for w in truth if w.t == 105.0).speed_mps == pytest.approx(2.0)  # ya acabó


def test_live_command_pushes_the_drone() -> None:
    plain, windy = live(), live()
    fly(plain, 100.0)
    body = set_wind(speed_mps=16.0, from_deg=270.0)
    fly(windy, 40.0)
    windy.apply_command(body, body.issued_by, body.text)
    fly(windy, 60.0)
    a, b = plain.samples[-1], windy.samples[-1]
    assert math.hypot(a.x - b.x, a.y - b.y) > 30.0


def test_cancel_ramps_down_from_the_current_level() -> None:
    sim = live()
    fly(sim, 20.0)
    sim.apply_command(set_wind(duration_s=None), CommandIssuer.PANEL)
    fly(sim, 40.0)  # ya al nivel completo
    assert sim.instructor_wind_active()
    sim.apply_command(CANCEL, CommandIssuer.PANEL)
    assert not sim.instructor_wind_active()
    events = fly(sim, 20.0)
    assert [e.payload["command"] for e in events if e.type == EventType.INSTRUCTOR_COMMAND] == [
        "cancel_wind"
    ]
    wind = {w.t: w for w in sim.truth().wind}
    assert wind[60.0].speed_mps == 12.0
    assert wind[65.0].speed_mps == pytest.approx(7.0)  # baja con la rampa de 10 s
    assert wind[75.0].speed_mps == pytest.approx(2.0)  # y vuelve al viento del escenario
    assert wind[75.0].from_deg == 300.0


def test_cancel_without_instructor_wind_is_an_error() -> None:
    sim = live()
    with pytest.raises(ValueError, match="no instructor wind to cancel"):
        sim.apply_command(CANCEL, CommandIssuer.PANEL)
    sim.apply_command(set_wind(duration_s=10.0), CommandIssuer.PANEL)
    fly(sim, 12.0)  # ya terminó por duración
    with pytest.raises(ValueError, match="no instructor wind to cancel"):
        sim.apply_command(CANCEL, CommandIssuer.PANEL)


def test_a_new_set_wind_replaces_the_previous_one_without_a_jump() -> None:
    sim = live()
    fly(sim, 20.0)
    sim.apply_command(set_wind(duration_s=None), CommandIssuer.PANEL)  # 12 m/s sin fin
    fly(sim, 40.0)
    sim.apply_command(
        set_wind(from_deg=90.0, speed_mps=6.0, ramp_s=10.0, duration_s=30.0),
        CommandIssuer.PANEL,
    )
    fly(sim, 60.0)
    wind = {w.t: w for w in sim.truth().wind}
    assert wind[60.0].speed_mps == 12.0  # el relevo empieza donde estaba el anterior…
    assert wind[65.0].speed_mps == pytest.approx(9.0)  # …y pasa al nuevo sin saltos
    assert wind[70.0].speed_mps == pytest.approx(6.0)  # el nuevo en su nivel
    assert wind[70.0].from_deg == 90.0
    assert wind[91.0].speed_mps == pytest.approx(
        2.0
    )  # al acabar vuelve al escenario, no al anterior
    assert wind[91.0].from_deg == 300.0


def test_commands_without_events_or_perturbations_are_ignored() -> None:
    plan = Simulator(scenario_config("nominal-wind-cmd"), perturbed=False, events=False)
    plan.run_physics()
    assert not plan.instructor_wind_active()
    ref = Simulator(scenario_config("nominal"), perturbed=False, events=False).run_physics()
    assert plan.flight().samples[-1].t == ref.samples[-1].t


# --- Reproductor --------------------------------------------------------------------------------


def test_player_rejects_commands_with_interactive_off(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.play()
    player.advance(20)
    with pytest.raises(PlayerError) as exc:
        player.instructor(set_wind())
    assert str(exc.value) == INTERACTIVE_OFF_MESSAGE_COMMANDS
    assert not [e for e in player.bus.timeline.all() if e.type == EventType.INSTRUCTOR_COMMAND]


def test_player_publishes_the_command_with_origin_and_text(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("nominal")
    player.set_interactive(True)
    player.play()
    player.advance(20)
    player.instructor(set_wind(CommandIssuer.LLM))
    player.advance(1)
    sent = [e for e in player.bus.timeline.all() if e.type == EventType.INSTRUCTOR_COMMAND]
    assert len(sent) == 1
    assert (
        sent[0].payload["issued_by"] == "llm" and sent[0].payload["text"] == "wind from the north"
    )
    player.instructor(CANCEL)
    player.advance(1)
    cancelled = [e for e in player.bus.timeline.all() if e.type == EventType.INSTRUCTOR_COMMAND]
    assert [e.payload["command"] for e in cancelled] == ["set_wind", "cancel_wind"]
    with pytest.raises(PlayerError, match="no instructor wind to cancel"):
        player.instructor(CANCEL)


# --- Escenario programado -----------------------------------------------------------------------


def test_nominal_wind_cmd_is_deterministic_and_equals_the_file(runs_dir: Path) -> None:
    config = load_scenario("nominal-wind-cmd")
    a, b = generate(config), generate(config)
    assert [e.model_dump_json() for e in a.events] == [e.model_dump_json() for e in b.events]
    assert a.truth == b.truth and a.labels == b.labels
    lines = (
        (runs_dir / "nominal-wind-cmd" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert [json.loads(x)["event_id"] for x in lines] == [e.event_id for e in a.events]


def test_nominal_wind_cmd_is_nominal_plus_the_command() -> None:
    nominal, cmd = generate(load_scenario("nominal")), generate(load_scenario("nominal-wind-cmd"))
    assert [e.payload["command"] for e in cmd.events if e.type == EventType.INSTRUCTOR_COMMAND] == [
        "set_wind"
    ]
    scheduled = next(e for e in cmd.events if e.type == EventType.INSTRUCTOR_COMMAND)
    assert (scheduled.sim_time, scheduled.payload["issued_by"]) == (95.0, "scenario")
    # el viento no cambia el ruido de las fuentes que no dependen de él
    for kind in (EventType.LINK_STATUS, EventType.BATTERY_STATUS):
        n = [e.payload for e in nominal.events if e.type == kind]
        c = [e.payload for e in cmd.events if e.type == kind]
        assert c[: len(n)] == n[: len(c)]
    # los eventos anteriores al comando son idénticos
    head = lambda run: [  # noqa: E731
        e.model_dump_json()
        for e in run.events
        if e.sim_time < 95.0 and e.type != EventType.MISSION_PLANNED
    ]
    assert head(nominal) == head(cmd)


def test_scheduled_wind_command_makes_a_wind_label() -> None:
    labels = generate(load_scenario("nominal-wind-cmd")).labels.labels
    assert len(labels) == 1
    a1 = labels[0]
    assert (a1.id, a1.type.value, a1.start_s, a1.end_s) == ("A1", "wind", 95.0, 155.0)
    assert [r.value for r in a1.expected_rules] == ["ROUTE_DEVIATION"]
    assert a1.expected_cause.value == "WIND" and a1.eval_window == (95.0, 215.0)


def test_label_window_ends_when_the_next_command_replaces_or_cancels_it() -> None:
    def cmd(at: float, command: str, p: WindCommandParams | None) -> dict:
        return {"at_s": at, "command": command, "params": p.model_dump() if p else None}

    config = scenario_config(
        "nominal",
        commands=[
            cmd(60.0, "set_wind", params(duration_s=None)),
            cmd(100.0, "set_wind", params(from_deg=90.0, duration_s=30.0)),
            cmd(110.0, "cancel_wind", None),
        ],
    )
    labels = generate(config).labels.labels
    assert [(lb.start_s, lb.end_s) for lb in labels] == [(60.0, 100.0), (100.0, 110.0)]
