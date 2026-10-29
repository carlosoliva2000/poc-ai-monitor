"""Cliente del bus contra un servidor WebSocket falso local (sin la plataforma real)."""

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from synthetic import Maker, envelope
from websockets.asyncio.server import Server, ServerConnection, serve

from ai_module.bus_client import (
    BusClient,
    default_backoff,
    fetch_mission_plan,
    ws_url_from_platform,
)
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope

Handler = Callable[[ServerConnection], Awaitable[None]]


def port_of(server: Server) -> int:
    return server.sockets[0].getsockname()[1]


def event_json(maker: Maker, t: float, seq: int) -> str:
    return json.dumps({"op": "event", "event": envelope(maker.gps(t, 0.0, 0.0), seq).model_dump()})


async def with_timeout(coro: Awaitable[Any], seconds: float = 5.0) -> Any:
    return await asyncio.wait_for(coro, seconds)


def test_url_helpers_and_backoff() -> None:
    assert ws_url_from_platform("http://127.0.0.1:8100") == "ws://127.0.0.1:8100/ws"
    assert ws_url_from_platform("http://127.0.0.1:8100/") == "ws://127.0.0.1:8100/ws"
    assert ws_url_from_platform("https://host") == "wss://host/ws"
    assert [default_backoff(n) for n in range(7)] == [0.5, 1.0, 2.0, 4.0, 8.0, 10.0, 10.0]


def test_hello_subscribe_receive_and_publish() -> None:
    received: list[dict] = []
    published = asyncio.Event()
    maker = Maker()

    async def handler(ws: ServerConnection) -> None:
        await ws.send(
            json.dumps(
                {
                    "op": "state",
                    "status": "running",
                    "scenario": "demo",
                    "run_id": "r1",
                    "sim_time": 1.0,
                    "speed": 1.0,
                    "wait_agent": False,
                    "interactive": False,
                    "active_faults": [],
                    "cursor": 1,
                    "total_events": 10,
                }
            )
        )
        await ws.send(json.dumps({"op": "error", "message": "algo"}))
        await ws.send("esto no es JSON")
        await ws.send(event_json(maker, 1.0, 7))
        async for raw in ws:
            received.append(json.loads(raw))
            if received[-1]["op"] == "publish":
                published.set()

    async def scenario() -> list[Envelope]:
        async with serve(handler, "127.0.0.1", 0) as server:
            url = f"http://127.0.0.1:{port_of(server)}"
            events: list[Envelope] = []
            async with BusClient(url) as bus:
                async for event in bus.events():
                    events.append(event)
                    detection = maker.event(
                        # Cualquier evento `ai` válido sirve para probar la publicación.
                        EventType.DETECTION_CLEARED,
                        1.0,
                        {
                            "detection_id": "det-0001",
                            "rule": "ROUTE_DEVIATION",
                            "duration_s": 1.0,
                            "max_value": 2.0,
                        },
                    )
                    await bus.publish(detection)
                    await with_timeout(published.wait())
                    break
                assert bus.sim_time == 1.0
            return events

    events = asyncio.run(scenario())
    assert [e.event_id for e in events] == ["gps-000001"] and events[0].seq == 7
    assert received[0] == {"op": "hello", "client": "ai-module"}
    assert received[1]["op"] == "subscribe"
    patterns = received[1]["patterns"]
    assert "citadel.pub.evt.air.>" in patterns and "citadel.pub.evt.ai.>" in patterns
    # el agente no recibe los fallos inyectados ni el modo interactivo (dominio `sim`)
    assert not any("FaultInjected" in p or "InteractiveModeChanged" in p for p in patterns)
    assert "citadel.pub.evt.>" not in patterns and "citadel.pub.evt.sim.>" not in patterns
    assert received[2]["op"] == "publish"
    assert received[2]["event"]["type"] == "DetectionCleared"
    assert "seq" not in received[2]["event"] and "ingestion_time" not in received[2]["event"]


def test_unknown_ops_are_dropped_without_errors() -> None:
    maker = Maker()

    async def handler(ws: ServerConnection) -> None:
        await ws.send(json.dumps({"op": "surprise", "x": 1}))
        await ws.send(json.dumps({"x": 1}))  # sin `op`
        await ws.send(json.dumps([1, 2]))  # JSON válido, pero no un objeto
        await ws.send(event_json(maker, 1.0, 7))
        await ws.wait_closed()

    async def scenario() -> tuple[list[str], int]:
        async with serve(handler, "127.0.0.1", 0) as server:
            url = f"http://127.0.0.1:{port_of(server)}"
            async with BusClient(url) as bus:
                seen: list[str] = []
                async for message in bus.messages():
                    seen.append(message.op)
                    break
                return seen, bus.connections

    seen, connections = asyncio.run(scenario())
    assert seen == ["event"] and connections == 1


def test_reconnects_after_the_server_closes_the_connection() -> None:
    connections: list[list[dict]] = []
    maker = Maker()
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(ws: ServerConnection) -> None:
        messages: list[dict] = []
        connections.append(messages)
        messages.append(json.loads(await ws.recv()))
        messages.append(json.loads(await ws.recv()))
        await ws.send(event_json(maker, float(len(connections)), len(connections)))
        if len(connections) == 1:
            await ws.close()  # el servidor corta la primera conexión
        else:
            await ws.wait_closed()

    reconnected: list[int] = []

    async def scenario() -> list[str]:
        async with serve(handler, "127.0.0.1", 0) as server:
            url = f"http://127.0.0.1:{port_of(server)}"

            async def on_connected() -> None:
                reconnected.append(len(reconnected) + 1)

            async with BusClient(url, sleep=fake_sleep, on_connected=on_connected) as bus:
                ids = []

                async def collect() -> None:
                    async for event in bus.events():
                        ids.append(event.event_id)
                        if len(ids) == 2:
                            return

                await with_timeout(collect())
                return ids

    ids = asyncio.run(scenario())
    assert ids == ["gps-000001", "gps-000002"]
    assert len(connections) == 2
    for messages in connections:  # tras reconectar vuelve a saludar y suscribirse
        assert [m["op"] for m in messages] == ["hello", "subscribe"]
    assert reconnected == [1, 2]


def test_retries_with_growing_waits_until_the_server_appears() -> None:
    maker = Maker()
    delays: list[float] = []
    server_holder: dict[str, Server] = {}

    async def handler(ws: ServerConnection) -> None:
        await ws.recv()
        await ws.recv()
        await ws.send(event_json(maker, 1.0, 1))
        await ws.wait_closed()

    async def scenario() -> tuple[str, list[float]]:
        # Reserva un puerto libre y lo suelta; el servidor "aparece" tras tres esperas.
        probe = await serve(handler, "127.0.0.1", 0)
        port = port_of(probe)
        probe.close()
        await probe.wait_closed()

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)
            if len(delays) == 3:
                server_holder["s"] = await serve(handler, "127.0.0.1", port)

        try:
            async with BusClient(f"http://127.0.0.1:{port}", sleep=fake_sleep) as bus:
                async for event in bus.events():
                    return event.event_id, delays
        finally:
            server_holder["s"].close()
        raise AssertionError("sin eventos")

    event_id, waits = asyncio.run(scenario())
    assert event_id == "gps-000001"
    assert waits == [0.5, 1.0, 2.0]


def test_publish_without_connection_raises() -> None:
    maker = Maker()

    async def scenario() -> None:
        bus = BusClient("http://127.0.0.1:1")
        await bus.publish(maker.gps(0.0, 0.0, 0.0))

    with pytest.raises(ConnectionError):
        asyncio.run(scenario())


# --- Bootstrap del plan por HTTP -----------------------------------------------------------


def run_http_server(body: dict | None, status: int = 200) -> tuple[HTTPServer, list[str]]:
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            paths.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, paths


def test_fetch_mission_plan_ok_and_not_ok() -> None:
    plan = Maker().plan().payload | {"next_waypoint": "P1"}
    server, paths = run_http_server({"ok": True, "result": plan})
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        assert asyncio.run(fetch_mission_plan(url)) == plan
        assert paths == ["/api/tools/get_mission_plan"]
    finally:
        server.shutdown()

    server, _ = run_http_server({"ok": False, "error": "sin escenario"})
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        assert asyncio.run(fetch_mission_plan(url)) is None
    finally:
        server.shutdown()


def test_fetch_mission_plan_unreachable_returns_none() -> None:
    assert asyncio.run(fetch_mission_plan("http://127.0.0.1:1", timeout_s=1.0)) is None
