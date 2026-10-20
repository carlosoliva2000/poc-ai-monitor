"""Lógica del visor en directo (qué pintar y qué hace cada tecla), sin ventana ni red."""

import json
from pathlib import Path

import pytest

from platform_app.paths import RUNS_DIR
from platform_app.viewer_state import SPEEDS, ViewerState, clock

STATE = {
    "op": "state", "status": "running", "scenario": "demo", "run_id": "r1", "sim_time": 61.0,
    "speed": 4.0, "wait_agent": False, "interactive": False, "active_faults": [],
    "cursor": 10, "total_events": 100,
}  # fmt: skip


def ev(kind: str, payload: dict, t: float = 1.0) -> dict:
    return {"op": "event", "event": {"type": kind, "payload": payload, "sim_time": t}}


def gps(t: float, x: float, y: float, fix: str = "3d") -> dict:
    p = {"x": x, "y": y, "alt_m": 60.0, "speed_mps": 15.0, "heading_deg": 90.0, "fix": fix,
         "sats": 14, "hdop": 0.8}  # fmt: skip
    return ev("PositionUpdated", p, t)


def detection(kind: str, det_id: str, rule: str, since: float, source: str | None = None) -> dict:
    return ev(
        kind,
        {"detection_id": det_id, "rule": rule, "severity": "medium", "source": source,
         "window": {"since": since, "until": since}, "value": 1.0, "threshold": 1.0,
         "unit": "m", "trigger_event_ids": [], "message": "x"},
        since,
    )  # fmt: skip


def live() -> ViewerState:
    state = ViewerState(connected=True)
    state.apply_message(STATE)
    return state


def test_clock_format() -> None:
    assert clock(0) == "T+00:00"
    assert clock(125.4) == "T+02:05"


def test_state_message_updates_the_status_line() -> None:
    s = live()
    line = s.status_line()
    for part in ("demo", "T+01:01", "4×", "running", "esperar al agente: no", "interactivo: no"):
        assert part in line
    s.apply_message(
        {**STATE, "interactive": True, "wait_agent": True,
         "active_faults": [{"source": "radar", "mode": "mute", "origin": "manual"},
                           {"source": "gps", "mode": "loss", "origin": "manual"}]}
    )  # fmt: skip
    line = s.status_line()
    assert "interactivo: SÍ" in line and "esperar al agente: sí" in line
    assert "radar(mute), gps(loss)" in line
    assert s.silenced_sources() == ["radar"]
    assert ViewerState().status_line() == "sin conexión con la plataforma"


def test_gps_trail_drone_and_fix() -> None:
    s = live()
    assert s.drone is None
    s.apply_message(gps(1, 10, 20))
    s.apply_message(gps(2, 11, 21, fix="none"))
    assert s.drone == (11, 21, 90.0)
    assert s.without_fix
    s.apply_message(gps(500, 0, 0))  # la estela solo guarda los últimos 180 s
    assert [p.t for p in s.gps] == [500]


def test_radar_points_wind_and_bounds() -> None:
    s = live()
    s.set_plan({"waypoints": [{"id": "BASE", "x": 0, "y": 0}, {"id": "WP1", "x": 100, "y": 200}]})
    for k in range(60):
        s.apply_message(ev("TrackUpdated", {"x": float(k), "y": 0.0}, k))
    assert len(s.radar) == 45
    s.apply_message(ev("WindReported", {"speed_mps": 12.0, "gust_mps": 15, "from_deg": 0.0}, 10))
    assert s.wind_text().startswith("viento 12.0 m/s del 0°")
    wx, wy = s.wind_vector()
    assert (round(wx, 6), round(wy, 6)) == (0.0, -1.0)  # viento del norte: sopla hacia el sur
    x0, x1, y0, y1 = s.bounds(margin_m=10)
    assert (x0, y0, y1) == (-10, -10, 210) and x1 == 110


def test_plan_comes_from_the_api_and_is_asked_again_on_a_new_run() -> None:
    s = live()
    assert s.needs_plan
    s.set_plan({"waypoints": [{"id": "BASE", "x": 0, "y": 0}, {"id": "WP1", "x": 5, "y": 5}]})
    assert not s.needs_plan and s.route == [(0, 0), (5, 5)]
    s.apply_message(gps(1, 1, 1))
    s.apply_message(ev("SimulationStarted", {"scenario": "viento", "run_id": "r2",
                                             "duration_s": 1.0, "total_events": 1}, 0))  # fmt: skip
    assert s.needs_plan and not s.gps and not s.route
    s.apply_message({**STATE, "run_id": "r2", "scenario": "viento"})  # no vuelve a borrar
    s.apply_message(gps(1, 1, 1))
    s.apply_message({**STATE, "run_id": "r2", "scenario": "viento", "sim_time": 2.0})
    assert len(s.gps) == 1


def test_open_detections_are_highlighted_until_cleared() -> None:
    s = live()
    s.apply_message(detection("DetectionRaised", "det-1", "ROUTE_DEVIATION", 80.0))
    s.apply_message(detection("DetectionRaised", "det-2", "SOURCE_SILENT", 70.0, "radar"))
    assert s.highlight_since() == 70.0
    assert s.detections_lines() == [
        "SOURCE_SILENT (radar) · medium · desde T+01:10",
        "ROUTE_DEVIATION · medium · desde T+01:20",
    ]
    s.apply_message(detection("DetectionUpdated", "det-1", "ROUTE_DEVIATION", 80.0))
    assert len(s.detections) == 2
    s.apply_message(ev("DetectionCleared", {"detection_id": "det-2", "rule": "SOURCE_SILENT"}))
    assert s.highlight_since() == 80.0
    s.apply_message(ev("DetectionCleared", {"detection_id": "det-1", "rule": "ROUTE_DEVIATION"}))
    assert s.highlight_since() is None


def test_truth_is_only_data_for_drawing() -> None:
    s = live()
    s.set_truth(
        {"duration_s": 2, "trajectory": [{"t": 0, "x": 1, "y": 2}, {"t": 1, "x": 3, "y": 4}]}
    )
    assert s.truth == [(1, 2), (3, 4)]


def test_errors_show_as_a_temporary_notice() -> None:
    s = live()
    s.apply_message({"op": "error", "message": "algo falló"}, now=100.0)
    assert "algo falló" in s.status_line(now=101.0)
    assert "algo falló" not in s.status_line(now=200.0)


@pytest.mark.parametrize(
    ("key", "status", "expected"),
    [
        (" ", "paused", {"action": "play", "value": None}),
        ("space", "running", {"action": "pause", "value": None}),
        ("n", "paused", {"action": "step", "value": None}),
        ("0", "paused", {"action": "reset", "value": None}),
        ("+", "paused", {"action": "speed", "value": 8.0}),  # velocidad actual: 4
        ("-", "paused", {"action": "speed", "value": 2.0}),
        ("w", "paused", {"action": "wait_agent", "value": True}),
        ("i", "paused", {"action": "interactive", "value": True}),
    ],
)
def test_keys_send_control_messages(key: str, status: str, expected: dict) -> None:
    s = live()
    s.status = status
    action = s.key_action(key)
    assert action is not None and action.message == {"op": "control", **expected}


def test_speed_keys_stay_inside_the_valid_values() -> None:
    s = live()
    s.speed = SPEEDS[-1]
    assert s.key_action("+").message["value"] == 16.0
    s.speed = SPEEDS[0]
    assert s.key_action("-").message["value"] == 0.5


def test_local_keys() -> None:
    s = live()
    assert s.key_action("t").toggle_truth
    assert s.key_action("l").ask_scenario
    assert s.key_action("x") is None


def test_fault_keys_need_the_interactive_mode() -> None:
    s = live()
    for key in "12345g":
        action = s.key_action(key)
        assert action.message is None and "interactivo" in action.notice
    s.apply_message({**STATE, "interactive": True})
    sources = {"1": "gps", "2": "radar", "3": "meteo", "4": "link", "5": "battery"}
    for key, source in sources.items():
        msg = s.key_action(key).message
        assert msg["action"] == "fault"
        assert msg["value"] == {"source": source, "mode": "mute", "active": True}
    assert s.key_action("g").message["value"] == {"source": "gps", "mode": "loss", "active": True}


def test_fault_keys_toggle_off_an_active_fault() -> None:
    s = live()
    s.apply_message(
        {**STATE, "interactive": True,
         "active_faults": [{"source": "radar", "mode": "mute", "origin": "manual"},
                           {"source": "gps", "mode": "loss", "origin": "manual"}]}
    )  # fmt: skip
    assert s.key_action("2").message["value"] == {
        "source": "radar",
        "mode": "mute",
        "active": False,
    }
    assert s.key_action("g").message["value"] == {"source": "gps", "mode": "loss", "active": False}


def test_a_whole_scenario_file_can_be_applied() -> None:
    """Aplica los eventos de `runs/demo/events.jsonl` (como llegarían por el WebSocket)."""
    s = live()
    path = Path(RUNS_DIR) / "demo" / "events.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        s.apply_message({"op": "event", "event": e})
    assert s.gps and s.radar and s.wind and s.drone


def test_repeated_speed_keys_add_up_before_the_platform_confirms() -> None:
    s = live()
    s.speed = 1.0
    values = [s.key_action("+").message["value"] for _ in range(3)]
    assert values == [2.0, 4.0, 8.0]
