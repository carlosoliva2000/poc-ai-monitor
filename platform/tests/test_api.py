"""REST y WebSocket con `TestClient` (sin reloj de pared: el reproductor avanza a mano)."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from platform_app.app import create_app
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.topics import topic_for

OFF = "el modo interactivo está apagado: actívalo para inyectar fallos"


@pytest.fixture
def client(runs_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(runs_dir=runs_dir, run_clock=False)) as c:
        yield c


def player(client: TestClient):
    return client.app.state.player  # type: ignore[attr-defined]


def drain(ws: WebSocketTestSession) -> list[dict[str, Any]]:
    """Todo lo que ha llegado hasta ahora: se envía un mensaje inválido como marca de fin (los
    mensajes llegan en orden, así que el `error` de la marca va detrás de todo lo anterior)."""
    ws.send_json({"op": "barrier"})
    out = []
    while True:
        message = ws.receive_json()
        if message["op"] == "error" and "'barrier'" in message["message"]:
            return out
        out.append(message)


def hello(ws: WebSocketTestSession, kind: str = "web", *patterns: str) -> list[dict[str, Any]]:
    ws.send_json({"op": "hello", "client": kind})
    if patterns:
        ws.send_json({"op": "subscribe", "patterns": list(patterns)})
    return drain(ws)


def control(ws: WebSocketTestSession, action: str, value: Any = None) -> list[dict[str, Any]]:
    ws.send_json({"op": "control", "action": action, "value": value})
    return drain(ws)


def operator_message(number: int, text: str = "hola") -> dict[str, Any]:
    return EventDraft(
        event_id=f"ops-{number:04d}",
        topic=topic_for(EventType.OPERATOR_MESSAGE, ConversationId.MONITOR),
        type=EventType.OPERATOR_MESSAGE,
        source="web-operator",
        asset=None,
        sim_time=0.0,
        event_time="2026-10-20T10:00:00Z",
        payload={"conversation_id": "monitor", "text": text},
    ).model_dump(mode="json")


def detection_message(number: int) -> dict[str, Any]:
    return {
        "event_id": f"det-{number:04d}",
        "topic": topic_for(EventType.DETECTION_RAISED),
        "type": "DetectionRaised",
        "source": "ai-detector",
        "asset": "d1",
        "sim_time": 40.0,
        "event_time": "2026-10-20T10:00:40Z",
        "causation_id": None,
        "ephemeral": False,
        "payload": {
            "detection_id": f"det-{number:04d}",
            "rule": "ROUTE_DEVIATION",
            "severity": "medium",
            "value": 35.0,
            "threshold": 30.0,
            "unit": "m",
            "source": None,
            "window": {"since": 36.0, "until": 40.0},
            "trigger_event_ids": [],
            "message": "desviación",
        },
    }


# --- WebSocket ------------------------------------------------------------------------------


def test_connect_sends_state_first(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        state = ws.receive_json()
        assert state["op"] == "state"
        assert state["status"] == "idle" and state["scenario"] is None
        assert state["interactive"] is False and state["active_faults"] == []
        assert state["speed"] == 1.0 and state["cursor"] == 0 and state["total_events"] == 0


def test_messages_before_hello_and_garbage_are_rejected(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"op": "subscribe", "patterns": ["citadel.>"]})
        assert ws.receive_json() == {"op": "error", "message": "el primer mensaje debe ser hello"}
        ws.send_text("{no es json")
        assert ws.receive_json()["message"] == "el mensaje no es un JSON válido"
        ws.send_json({"op": "hello", "client": "robot"})
        assert ws.receive_json()["message"].startswith("mensaje no válido")
        hello(ws)
        ws.send_json({"op": "subscribe", "patterns": ["citadel.pub.>.x"]})
        assert ws.receive_json()["message"].startswith("mensaje no válido")


def test_a_second_hello_cannot_change_the_client_kind(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"op": "hello", "client": "web"})
        ws.send_json({"op": "hello", "client": "ai-module"})
        assert ws.receive_json()["message"] == "el cliente ya se presentó con otro tipo"


def test_only_web_clients_can_send_control(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ai:
        ai.receive_json()
        hello(ai, "ai-module")
        for action, value in (("play", None), ("interactive", True), ("load", "nominal")):
            messages = control(ai, action, value)
            assert messages == [
                {"op": "error", "message": "solo los clientes de tipo web pueden enviar control"}
            ]
        with client.websocket_connect("/ws") as web:
            web.receive_json()
            hello(web, "web")
            assert client.get("/api/state").json()["status"] == "idle"  # la IA no cargó nada
            states = [m for m in control(web, "load", "nominal") if m["op"] == "state"]
            assert states and states[-1]["scenario"] == "nominal"


def test_load_play_step_and_subscription_filter(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws, "web", "citadel.pub.evt.sim.>", "citadel.pub.evt.air.d1.MissionPlanned.v1")
        messages = control(ws, "load", "nominal")
        events = [m["event"] for m in messages if m["op"] == "event"]
        assert [e["type"] for e in events] == ["SimulationStarted"]
        assert events[0]["seq"] == 1 and events[0]["payload"]["scenario"] == "nominal"
        states = [m for m in messages if m["op"] == "state"]
        assert states[-1]["scenario"] == "nominal" and states[-1]["status"] == "idle"
        assert states[-1]["total_events"] > 0

        messages = control(ws, "step")
        events = [m["event"] for m in messages if m["op"] == "event"]
        # solo los topics suscritos; el paso desde idle publica además el aviso de pausa
        assert [e["type"] for e in events] == ["MissionPlanned", "SimulationPaused"]
        assert [m for m in messages if m["op"] == "state"][-1]["cursor"] == 1
        control(ws, "step")  # MissionStarted: no llega (no está suscrito)
        assert player(client).state().cursor == 2


def test_play_events_flow_to_subscribers(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws, "web", "citadel.pub.evt.env.>")
        control(ws, "load", "nominal")
        control(ws, "play")
        player(client).advance(35.0)
        events = [m["event"] for m in drain(ws) if m["op"] == "event"]
        assert [e["event_id"] for e in events] == ["met-0001", "met-0002", "met-0003"]
        assert {e["type"] for e in events} == {"WindReported"}
        assert all(e["asset"] == "zone1" and e["seq"] > 0 for e in events)
        assert "." in events[0]["ingestion_time"]


def test_publish_valid_and_rejected(client: TestClient) -> None:
    with (
        client.websocket_connect("/ws") as web,
        client.websocket_connect("/ws") as ai,
    ):
        web.receive_json()
        ai.receive_json()
        hello(web, "web")
        hello(ai, "ai-module", "citadel.pub.evt.ops.>", "citadel.pub.evt.ai.>")
        control(web, "load", "nominal")
        drain(ai)

        web.send_json({"op": "publish", "event": operator_message(1)})
        got = [m["event"] for m in drain(ai) if m["op"] == "event"]
        assert [e["event_id"] for e in got] == ["ops-0001"]
        assert got[0]["seq"] > 0 and got[0]["ingestion_time"]

        # el web no puede publicar en `ai`
        web.send_json({"op": "publish", "event": detection_message(1)})
        errors = [m for m in drain(web) if m["op"] == "error"]
        assert errors == [
            {
                "op": "error",
                "message": "el cliente 'web' no puede publicar en el dominio 'ai'",
            }
        ]
        assert not [m for m in drain(ai) if m["op"] == "event"]

        # el módulo de IA sí, y el web (suscrito) lo recibe; pero no puede publicar en `ops`
        hello(web, "web", "citadel.pub.evt.ai.>")
        ai.send_json({"op": "publish", "event": detection_message(1)})
        got = [m["event"] for m in drain(web) if m["op"] == "event"]
        assert [e["event_id"] for e in got] == ["det-0001"]
        ai.send_json({"op": "publish", "event": operator_message(2)})
        errors = [m for m in drain(ai) if m["op"] == "error"]
        assert "no puede publicar en el dominio 'ops'" in errors[0]["message"]

        # id repetido y evento mal formado
        ai.send_json({"op": "publish", "event": detection_message(1)})
        assert "ya existe" in [m for m in drain(ai) if m["op"] == "error"][0]["message"]
        bad = detection_message(2)
        bad["payload"]["rule"] = "NOPE"
        ai.send_json({"op": "publish", "event": bad})
        assert [m for m in drain(ai) if m["op"] == "error"][0]["message"].startswith("mensaje no")
        assert player(client).bus.timeline.get("det-0002") is None


def test_control_speed_wait_agent_and_validation(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws)
        control(ws, "load", "nominal")
        state = [m for m in control(ws, "speed", 8.0) if m["op"] == "state"][-1]
        assert state["speed"] == 8.0
        state = [m for m in control(ws, "wait_agent", True) if m["op"] == "state"][-1]
        assert state["wait_agent"] is True
        errors = [m for m in control(ws, "speed", 3) if m["op"] == "error"]
        assert errors and errors[0]["message"].startswith("mensaje no válido")
        assert control(ws, "play", None)[-1]["status"] == "running"
        assert control(ws, "pause", None)[-1]["status"] == "paused"
        errors = [m for m in control(ws, "dance") if m["op"] == "error"]
        assert errors


def test_control_without_scenario_reports_a_clear_error(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws)
        assert control(ws, "play") == [
            {"op": "error", "message": "no hay ningún escenario cargado"}
        ]
        assert "desconocido" in control(ws, "load", "marte")[0]["message"]


def test_interactive_and_faults_over_the_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws, "web", "citadel.pub.evt.sim.>")
        control(ws, "load", "nominal")
        fault = {"source": "radar", "mode": "mute", "active": True}

        assert control(ws, "fault", fault) == [{"op": "error", "message": OFF}]
        assert player(client).state().active_faults == []

        messages = control(ws, "interactive", True)
        assert [m["event"]["type"] for m in messages if m["op"] == "event"] == [
            "InteractiveModeChanged"
        ]
        assert [m for m in messages if m["op"] == "state"][-1]["interactive"] is True
        assert control(ws, "interactive", True) == []  # sin cambio: ni evento ni estado

        control(ws, "play")
        player(client).advance(20.0)
        drain(ws)
        messages = control(ws, "fault", fault)
        state = [m for m in messages if m["op"] == "state"][-1]
        assert state["active_faults"] == [{"source": "radar", "mode": "mute", "origin": "manual"}]
        player(client).advance(1.0)
        injected = [m["event"] for m in drain(ws) if m["op"] == "event"]
        assert [(e["type"], e["event_id"]) for e in injected] == [("FaultInjected", "sim-0001")]

        bad = control(ws, "fault", {"source": "radar", "mode": "loss", "active": True})
        assert bad[0]["message"].startswith("mensaje no válido")
        clear = {"source": "radar", "mode": "mute", "active": False}
        assert [m for m in control(ws, "fault", clear) if m["op"] == "state"][-1][
            "active_faults"
        ] == []
        assert state["interactive"] is True


def test_wait_agent_through_the_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws, client.websocket_connect("/ws") as ai:
        ws.receive_json()
        ai.receive_json()
        hello(ws)
        hello(ai, "ai-module")
        control(ws, "load", "nominal")
        control(ws, "wait_agent", True)
        control(ws, "play")
        player(client).advance(30.0)
        ai.send_json({"op": "publish", "event": detection_message(1)})
        states = [m for m in drain(ws) if m["op"] == "state"]
        assert states[-1]["status"] == "paused"
        reply = {
            "event_id": "ai-0001",
            "topic": topic_for(EventType.ANOMALY_DETECTED),
            "type": "AnomalyDetected",
            "source": "ai-monitor",
            "asset": "d1",
            "sim_time": 30.0,
            "event_time": "2026-10-20T10:00:30Z",
            "causation_id": "det-0001",
            "ephemeral": False,
            "payload": {
                "alert_id": "ai-0001",
                "detection_ids": ["det-0001"],
                "cause": "WIND",
                "severity": "low",
                "confidence": 0.8,
                "summary": "viento",
                "explanation": "x",
                "recommendation": "y",
                "evidence_event_ids": ["gps-000001"],
                "supersedes": None,
                "as_of_sim_time": 30.0,
                "fallback": False,
            },
        }
        ai.send_json({"op": "publish", "event": reply})
        states = [m for m in drain(ws) if m["op"] == "state"]
        assert states[-1]["status"] == "running"


# --- REST ------------------------------------------------------------------------------------


def test_scenarios(client: TestClient) -> None:
    body = client.get("/api/scenarios").json()
    names = [s["name"] for s in body["scenarios"]]
    assert names == ["demo", "fallos", "nominal", "secuestro", "spoofing", "viento"]
    demo = body["scenarios"][0]
    assert demo["generated"] is True and demo["duration_s"] == pytest.approx(556.3)
    assert demo["description"]


def test_scenarios_not_generated(tmp_path: Path) -> None:
    with TestClient(create_app(runs_dir=tmp_path, run_clock=False)) as c:
        body = c.get("/api/scenarios").json()
        assert all(s["generated"] is False and s["duration_s"] is None for s in body["scenarios"])
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            hello(ws)
            control(ws, "load", "nominal")  # lo genera antes de cargarlo
        by_name = {s["name"]: s for s in c.get("/api/scenarios").json()["scenarios"]}
        assert by_name["nominal"]["generated"] is True


def test_state_plan_and_truth(client: TestClient) -> None:
    assert client.get("/api/state").json()["status"] == "idle"
    assert client.get("/api/plan").status_code == 404
    assert client.get("/api/truth").status_code == 404
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws)
        control(ws, "load", "demo")
        control(ws, "play")
        player(client).advance(50.3)
    state = client.get("/api/state").json()
    assert state["scenario"] == "demo" and state["status"] == "running"
    assert state["sim_time"] == pytest.approx(50.3)
    plan = client.get("/api/plan").json()
    assert plan["mission_id"] == "MSN-DEMO" and plan["waypoints"][1]["id"] == "WP1"
    truth = client.get("/api/truth").json()
    assert truth["trajectory"][-1]["t"] <= state["sim_time"]
    assert truth["trajectory"][-1]["t"] >= 50.0
    assert truth["wind"][-1]["t"] <= state["sim_time"]


def test_timeline_has_no_time_cut_and_filters(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws)
        control(ws, "load", "nominal")
        player(client).run_to_end()
    everything = client.get("/api/timeline").json()["events"]
    assert (
        everything[0]["type"] == "SimulationStarted"
        and everything[-1]["type"] == "SimulationFinished"
    )
    gps = client.get("/api/timeline", params={"source": "d1-gps", "since": 10, "until": 12}).json()
    assert [e["sim_time"] for e in gps["events"]] == [10.0, 11.0, 12.0]
    last = client.get("/api/timeline", params={"type": "PositionUpdated", "limit": 2}).json()
    assert len(last["events"]) == 2 and last["truncated"] is True
    assert client.get("/api/timeline", params={"type": "Nope"}).status_code == 422


def test_tools_endpoint(client: TestClient) -> None:
    err = client.post("/api/tools/get_events", json={"source": "gps"}).json()
    assert err == {"ok": False, "error": "no hay ningún escenario cargado"}
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws)
        control(ws, "load", "demo")
        control(ws, "play")
        player(client).advance(40.5)
    ok = client.post(
        "/api/tools/get_events", json={"source": "gps", "last_n": 3, "until": 1e9}
    ).json()
    assert ok["ok"] is True
    assert [e["sim_time"] for e in ok["result"]["events"]] == [38.0, 39.0, 40.0]
    assert client.post("/api/tools/get_flight_summary").json()["ok"] is True
    metrics = client.post("/api/tools/get_track_metrics", json={"since": 0, "until": 9999}).json()
    assert metrics["ok"] and metrics["result"]["until"] == pytest.approx(40.5)
    for body in ({"source": "sim"}, {}, {"source": "gps", "last_n": "x"}):
        bad = client.post("/api/tools/get_events", json=body).json()
        assert bad["ok"] is False and bad["error"].startswith("argumentos no válidos")
    assert client.post("/api/tools/nope", json={}).json()["ok"] is False
    assert client.post("/api/tools/get_events", content="{x").json()["ok"] is False
    assert client.post("/api/tools/get_events", json=[1]).json()["ok"] is False


def test_clock_runs_the_player_in_real_time(runs_dir: Path) -> None:
    with TestClient(create_app(runs_dir=runs_dir)) as c, c.websocket_connect("/ws") as ws:
        ws.receive_json()
        hello(ws)
        control(ws, "load", "nominal")
        control(ws, "speed", 16.0)
        control(ws, "play")
        deadline = time.monotonic() + 10
        sim_time = 0.0
        while sim_time < 8.0 and time.monotonic() < deadline:
            time.sleep(0.1)
            sim_time = c.get("/api/state").json()["sim_time"]
        assert sim_time >= 8.0
        pushed = [m for m in drain(ws) if m["op"] == "state"]
        assert pushed and pushed[-1]["status"] == "running"
