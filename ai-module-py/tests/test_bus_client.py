"""Cliente del bus (`bus_client.py`) contra un servidor WebSocket de prueba: conexión, suscripción,
lectura y publicación. Todo con tiempo máximo, para que nunca se cuelgue."""

import asyncio
import json
from typing import Any

from websockets.asyncio.server import ServerConnection, serve

from ai_module.bus_client import DEFAULT_PATTERNS, BusClient, ws_url_from_platform
from ai_module.ids import IdAllocator
from ai_module.outbox import EventFactory
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.ws import EventMessage, StateMessage

TIMEOUT_S = 10.0
STATE = {
    "op": "state", "status": "running", "scenario": "demo", "run_id": "run-1", "sim_time": 12.5,
    "speed": 4.0, "interactive": False, "active_faults": [], "cursor": 3, "total_events": 90,
}  # fmt: skip


def an_event() -> dict[str, Any]:
    """Un evento completo del bus (el que mandaría la plataforma)."""
    draft = EventFactory(IdAllocator()).make(
        EventType.AGENT_ACTIVITY,
        {"agent": "monitor", "state": "started", "invocation_id": "inv-0001", "causation_id": None},
        sim_time=12.0,
    )
    full = Envelope(
        **draft.model_dump(mode="json"), seq=1, ingestion_time="2026-11-25T10:00:00.000Z"
    )
    return full.model_dump(mode="json")


class FakeServer:
    """Guarda lo que recibe y manda lo que se le da al conectarse el cliente."""

    def __init__(self, to_send: list[str]) -> None:
        self.to_send = to_send
        self.received: list[dict[str, Any]] = []
        self.published = asyncio.Event()

    async def handler(self, ws: ServerConnection) -> None:
        for raw in self.to_send:
            await ws.send(raw)
        async for raw in ws:
            message = json.loads(raw)
            self.received.append(message)
            if message["op"] == "publish":
                self.published.set()


def test_the_client_says_hello_subscribes_reads_messages_and_publishes() -> None:
    server = FakeServer([json.dumps(STATE), json.dumps({"op": "event", "event": an_event()})])

    async def scenario() -> list[object]:
        async with serve(server.handler, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            got: list[object] = []
            async with BusClient(f"http://127.0.0.1:{port}") as bus:
                async for message in bus.messages():
                    got.append(message)
                    if isinstance(message, EventMessage):
                        break
                draft = EventFactory(IdAllocator()).make(
                    EventType.AGENT_ACTIVITY,
                    {"agent": "monitor", "state": "finished", "invocation_id": "inv-0001",
                     "causation_id": None},
                    sim_time=13.0,
                )  # fmt: skip
                await bus.publish(draft)
                await server.published.wait()
                assert bus.sim_time == 12.5 and bus.connections == 1
            return got

    got = asyncio.run(asyncio.wait_for(scenario(), TIMEOUT_S))
    assert isinstance(got[0], StateMessage) and isinstance(got[1], EventMessage)
    hello, subscribe, publish = server.received[:3]
    assert hello == {"op": "hello", "client": "ai-module"}
    assert subscribe == {"op": "subscribe", "patterns": list(DEFAULT_PATTERNS)}
    assert publish["op"] == "publish" and publish["event"]["event_id"] == "act-0001"


def test_what_the_client_does_not_expect_is_dropped() -> None:
    server = FakeServer(
        [
            "not json",
            json.dumps({"op": "truth", "run_id": "x", "t": 1.0}),  # la posición real: nunca entra
            json.dumps({"op": "event", "event": {"event_id": "broken"}}),  # evento inválido
            json.dumps({"op": "event", "event": an_event()}),
        ]
    )

    async def scenario() -> list[object]:
        async with serve(server.handler, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            async with BusClient(f"http://127.0.0.1:{port}") as bus:
                return [event async for event in _first(bus)]

    async def _first(bus: BusClient):  # noqa: ANN202
        async for event in bus.events():
            yield event
            return

    events = asyncio.run(asyncio.wait_for(scenario(), TIMEOUT_S))
    assert [e.event_id for e in events] == ["act-0001"]


def test_the_platform_url_becomes_the_websocket_url() -> None:
    assert ws_url_from_platform("http://127.0.0.1:8100") == "ws://127.0.0.1:8100/ws"
    assert ws_url_from_platform("https://host/") == "wss://host/ws"
    assert ws_url_from_platform("ws://host:1/ws") == "ws://host:1/ws"
