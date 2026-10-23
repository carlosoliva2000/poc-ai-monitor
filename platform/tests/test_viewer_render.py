"""El visor se pinta sin ventana (backend Agg) a partir del estado, sin errores."""

import json
import queue

import matplotlib
import pytest

matplotlib.use("Agg")

from platform_app.paths import RUNS_DIR  # noqa: E402
from platform_app.viewer import PlatformLink, drone_marker, make_figure  # noqa: E402
from platform_app.viewer_state import ViewerState  # noqa: E402


def state_at(name: str, until_s: float) -> ViewerState:
    state = ViewerState(connected=True)
    state.apply_message(
        {"op": "state", "status": "running", "scenario": name, "run_id": "r", "sim_time": until_s,
         "speed": 16.0, "wait_agent": False, "interactive": True,
         "active_faults": [{"source": "gps", "mode": "loss", "origin": "manual"}],
         "cursor": 1, "total_events": 1}
    )  # fmt: skip
    state.set_plan(json.loads((RUNS_DIR / name / "plan.json").read_text(encoding="utf-8")))
    truth = json.loads((RUNS_DIR / name / "truth.json").read_text(encoding="utf-8"))
    truth["trajectory"] = [s for s in truth["trajectory"] if s["t"] <= until_s]
    state.set_truth(truth)
    state.show_truth = True
    for line in (RUNS_DIR / name / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["sim_time"] > until_s:
            break
        state.apply_message({"op": "event", "event": event})
    return state


@pytest.mark.parametrize(("name", "until_s"), [("faults", 270.0), ("demo", 200.0)])
def test_the_viewer_draws_a_frame(name: str, until_s: float, tmp_path) -> None:
    fig, renderer = make_figure()
    state = state_at(name, until_s)
    renderer.draw(state)
    path = tmp_path / "viewer.png"
    fig.savefig(path)
    assert path.stat().st_size > 10_000
    assert renderer.status_text.get_text() == state.status_line()
    renderer.draw(ViewerState())  # sin datos tampoco falla


def test_drone_marker_exists_for_any_heading() -> None:
    for heading in (0.0, 30.0, 208.0, 359.9):
        assert drone_marker(heading).get_path().vertices.shape == (5, 2)


def test_the_link_turns_http_into_a_websocket_url() -> None:
    link = PlatformLink("http://127.0.0.1:8100/", queue.Queue())
    assert link.ws_url == "ws://127.0.0.1:8100/ws"
    assert link.send({"op": "control", "action": "play", "value": None}) is False  # sin conexión
