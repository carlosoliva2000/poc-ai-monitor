"""API `/api/v1`: control del ejercicio e *injects* del instructor.

Lo importante: la misma validación que el WebSocket, la verdad solo por la parte del instructor y
que una orden por REST llega a los clientes de `/ws` igual que si la hubiera dado la web.
"""

import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api import OFF, control, drain, hello

from platform_app.app import create_app

WIND = {
    "command": "set_wind",
    "params": {"from_deg": 350, "speed_mps": 12, "ramp_s": 10, "duration_s": 60},
    "issued_by": "panel",
    "text": None,
}
API = "/api/v1"


@pytest.fixture
def client(runs_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(runs_dir=runs_dir, run_clock=False)) as c:
        yield c


def player(client: TestClient):  # noqa: ANN201
    return client.app.state.player  # type: ignore[attr-defined]


def test_same_validation_as_the_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello(ws, "web")
        # sin modo interactivo: el mismo error por las dos caras
        client.post(f"{API}/exercise/load", json={"scenario": "nominal"})
        fault = {"source": "radar", "mode": "mute", "active": True}
        rest = client.post(f"{API}/instructor/faults", json=fault)
        ws_error = [m for m in control(ws, "fault", fault) if m["op"] == "error"]
        assert rest.status_code == 409 and rest.json()["detail"] == OFF == ws_error[0]["message"]
        rest = client.post(f"{API}/instructor/commands", json=WIND)
        ws_error = [m for m in control(ws, "instructor", WIND) if m["op"] == "error"]
        assert rest.status_code == 409 and rest.json()["detail"] == ws_error[0]["message"]
        # con el modo encendido: `cancel_wind` sin viento del instructor es un error en las dos
        assert client.put(f"{API}/exercise/interactive", json={"value": True}).status_code == 200
        cancel = {"command": "cancel_wind", "params": None, "issued_by": "panel", "text": None}
        rest = client.post(f"{API}/instructor/commands", json=cancel)
        ws_error = [m for m in control(ws, "instructor", cancel) if m["op"] == "error"]
        assert rest.status_code == 409 and rest.json()["detail"] == ws_error[0]["message"]


def test_invalid_bodies_are_rejected_before_the_player(client: TestClient) -> None:
    client.post(f"{API}/exercise/load", json={"scenario": "nominal"})
    client.put(f"{API}/exercise/interactive", json={"value": True})
    loss_on_radar = {"source": "radar", "mode": "loss", "active": True}
    assert client.post(f"{API}/instructor/faults", json=loss_on_radar).status_code == 422
    assert client.put(f"{API}/exercise/speed", json={"value": 3}).status_code == 422
    too_fast = copy.deepcopy(WIND)
    too_fast["params"]["speed_mps"] = 99
    assert client.post(f"{API}/instructor/commands", json=too_fast).status_code == 422
    llm_without_text = {**WIND, "issued_by": "llm"}
    assert client.post(f"{API}/instructor/commands", json=llm_without_text).status_code == 422
    assert client.post(f"{API}/exercise/load", json={"scenario": "nope"}).status_code == 404
    assert player(client).state().active_faults == []  # nada llegó al reproductor


ORDERS_WITHOUT_SCENARIO = [
    ("play", None, "post", "/exercise/play", None),
    ("pause", None, "post", "/exercise/pause", None),
    ("step", None, "post", "/exercise/step", None),
    ("reset", None, "post", "/exercise/reset", None),
    ("speed", 4.0, "put", "/exercise/speed", {"value": 4}),
    ("fault", {"source": "radar", "mode": "mute", "active": True}, "post", "/instructor/faults",
     {"source": "radar", "mode": "mute", "active": True}),
    ("instructor", WIND, "post", "/instructor/commands", WIND),
]  # fmt: skip


@pytest.mark.parametrize(("action", "value", "method", "path", "body"), ORDERS_WITHOUT_SCENARIO)
def test_an_order_without_a_scenario_says_so_on_both_faces(
    client: TestClient, action: str, value: Any, method: str, path: str, body: Any
) -> None:
    """«no scenario is loaded» y no «interactive mode is off», por REST (409) y por `/ws`."""
    rest = getattr(client, method)(f"{API}{path}", json=body)
    assert rest.status_code == 409 and rest.json()["detail"] == "no scenario is loaded"
    with client.websocket_connect("/ws") as ws:
        hello(ws, "web")
        errors = [m for m in control(ws, action, value) if m["op"] == "error"]
        assert [e["message"] for e in errors] == ["no scenario is loaded"]
    assert client.get(f"{API}/exercise").json()["speed"] == 1.0  # no cambió nada


def test_orders_without_a_scenario_are_conflicts(client: TestClient) -> None:
    assert client.get(f"{API}/instructor/truth").status_code == 404
    assert client.get(f"{API}/instructor/injects").json() == {"run_id": None, "injects": []}


def test_rest_state_is_the_websocket_state(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello(ws, "web")
        state = [m for m in control(ws, "load", "nominal") if m["op"] == "state"][-1]
        rest = client.get(f"{API}/exercise").json()
        assert {k: v for k, v in state.items() if k != "op"} == rest
    assert client.get(f"{API}/exercise/scenarios").json() == client.get("/api/scenarios").json()


def test_truth_and_injects_only_on_the_instructor_side(client: TestClient) -> None:
    client.post(f"{API}/exercise/load", json={"scenario": "demo"})
    injects = client.get(f"{API}/instructor/injects").json()
    assert {i["type"] for i in injects["injects"]} == {"wind", "gps_spoofing", "hijack"}
    player(client).play()
    player(client).advance(30.0)
    truth = client.get(f"{API}/instructor/truth").json()
    assert truth["trajectory"] and truth["trajectory"][-1]["t"] <= player(client).sim_time
    # los assets no lo traen, ni en el inventario ni en sus mensajes
    for asset in ("d1", "radar-1", "meteo-1", "gcs-1"):
        text = client.get(f"{API}/assets/{asset}/messages", params={"limit": 10000}).text
        for hidden in ("ExerciseInjects", "hijack", "spoof", "emitters_active", "leg_index"):
            assert hidden not in text, (asset, hidden)


def _normalise(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Quita lo que depende del reloj de pared o del `run_id` (marca de tiempo de la carga)."""
    out = []
    for message in copy.deepcopy(messages):
        if message["op"] == "event":
            event = message["event"]
            event.pop("ingestion_time")
            event["payload"].pop("run_id", None)
        else:
            message.pop("run_id", None)
        out.append(message)
    return out


def _steps(
    do: Any, client: TestClient, ws: Any, received: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """La misma secuencia de órdenes; `do(action, value)` las da por REST o por el WebSocket."""
    do("load", "nominal")
    do("play", None)
    player(client).advance(5.0)
    do("speed", 4.0)
    do("interactive", True)
    do("fault", {"source": "radar", "mode": "mute", "active": True})
    player(client).advance(2.0)
    do("instructor", WIND)
    player(client).advance(2.0)
    do("pause", None)
    do("step", None)
    do("reset", None)
    received += drain(ws)
    return received


def test_a_rest_order_reaches_ws_clients_like_a_web_order(runs_dir: Path) -> None:
    """Con un cliente `web` del `/ws` conectado, controlar por REST da lo mismo que por `control`"""

    def rest(client: TestClient):  # noqa: ANN202
        routes = {
            "load": ("post", "/exercise/load", lambda v: {"scenario": v}),
            "play": ("post", "/exercise/play", lambda v: None),
            "pause": ("post", "/exercise/pause", lambda v: None),
            "step": ("post", "/exercise/step", lambda v: None),
            "reset": ("post", "/exercise/reset", lambda v: None),
            "speed": ("put", "/exercise/speed", lambda v: {"value": v}),
            "interactive": ("put", "/exercise/interactive", lambda v: {"value": v}),
            "fault": ("post", "/instructor/faults", lambda v: v),
            "instructor": ("post", "/instructor/commands", lambda v: v),
        }

        def do(action: str, value: Any) -> None:
            method, path, body = routes[action]
            response = getattr(client, method)(f"{API}{path}", json=body(value))
            assert response.status_code == 200, (action, response.text)

        return do

    def ws_control(ws: Any, received: list[dict[str, Any]]):  # noqa: ANN202
        def do(action: str, value: Any) -> None:
            # el servidor procesa el mensaje de forma asíncrona: se espera a que acabe
            ws.send_json({"op": "control", "action": action, "value": value})
            received.extend(drain(ws))

        return do

    results = []
    for via in ("rest", "ws"):
        app = create_app(runs_dir=runs_dir, run_clock=False)
        with TestClient(app) as client, client.websocket_connect("/ws") as ws:
            hello(ws, "web", "citadel.pub.evt.>")
            received: list[dict[str, Any]] = []
            do = rest(client) if via == "rest" else ws_control(ws, received)
            results.append(_normalise(_steps(do, client, ws, received)))
    rest_messages, ws_messages = results
    assert any(m["op"] == "event" and m["event"]["type"] == "FaultInjected" for m in rest_messages)
    assert any(
        m["op"] == "event" and m["event"]["type"] == "InstructorCommand" for m in ws_messages
    )
    assert [m["op"] for m in rest_messages].count("error") == 0
    assert rest_messages == ws_messages
