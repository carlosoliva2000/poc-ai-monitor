"""API y WebSocket de la plataforma (`contracts/eventos.md` §5 y §6). Un solo proceso.

Arranque: `uv run --project platform python -m platform_app.app` (127.0.0.1:8100).

Cada cliente del WebSocket tiene una cola de salida; el bus (síncrono) solo hace `put_nowait`
en ella con `call_soon_threadsafe`, así que publicar nunca espera a un cliente lento.
"""

import argparse
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import (
    APIRouter,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, TypeAdapter, ValidationError

from poc_contracts.api import (
    ScenarioInfo,
    ScenariosResponse,
    TimelineResponse,
    ToolError,
    ToolOk,
)
from poc_contracts.enums import ClientKind, EventType, PlayerStatus
from poc_contracts.envelope import Envelope
from poc_contracts.run_files import PlanFile, TruthFile
from poc_contracts.topics import client_can_publish, topic_domain, topic_matches
from poc_contracts.ws import (
    ClientMessage,
    ControlFault,
    ControlInteractive,
    ControlLoad,
    ControlPause,
    ControlPlay,
    ControlReset,
    ControlSpeed,
    ControlStep,
    ControlWaitAgent,
    ErrorMessage,
    EventMessage,
    Hello,
    PlayerState,
    Publish,
    StateMessage,
    Subscribe,
)

from .bus import Bus
from .generator.scenario_io import list_scenarios, load_scenario
from .paths import RUNS_DIR, SCENARIOS_DIR
from .player import Player, PlayerError
from .timeline import Timeline
from .tools import ToolContext, ToolFailure, call_tool

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8100
STATE_PERIOD_S = 0.5
WEB_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000"]
_MESSAGE = TypeAdapter(ClientMessage)


class Client:
    """Una conexión WebSocket: tipo de cliente, patrones suscritos y cola de salida."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.kind: ClientKind | None = None
        self.patterns: list[str] = []
        self.queue: asyncio.Queue[str] = asyncio.Queue()

    def send(self, message: BaseModel) -> None:
        """Encola un mensaje; se puede llamar desde cualquier hilo."""
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, message.model_dump_json())
        except RuntimeError:  # el bucle del cliente ya se cerró
            log.debug("client loop closed, message dropped")

    def on_event(self, event: Envelope) -> None:
        """Handler del bus: reenvía los eventos de los topics a los que se ha suscrito."""
        if any(topic_matches(p, event.topic) for p in self.patterns):
            self.send(EventMessage(event=event))


class Hub:
    """Clientes conectados y difusión del estado."""

    def __init__(self, player: Player) -> None:
        self.player = player
        self.clients: set[Client] = set()

    def state_message(self) -> StateMessage:
        return StateMessage(**self.player.state().model_dump())

    def broadcast_state(self) -> None:
        if not self.clients:
            return
        message = self.state_message()
        for client in list(self.clients):
            client.send(message)


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'message'}: {e['msg']}" for e in exc.errors()[:3]
    )


def _generated_duration(runs_dir: Path, name: str) -> float | None:
    """Duración del escenario generado (`sim_time` del último evento), o `None` si no existe."""
    path = runs_dir / name / "events.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return float(json.loads(lines[-1])["sim_time"]) if lines else None


def _handle_control(player: Player, message: Any) -> None:
    match message:
        case ControlLoad():
            player.load(message.value)
        case ControlPlay():
            player.play()
        case ControlPause():
            player.pause()
        case ControlStep():
            player.step()
        case ControlReset():
            player.reset()
        case ControlSpeed():
            player.set_speed(message.value)
        case ControlWaitAgent():
            player.set_wait_agent(message.value)
        case ControlInteractive():
            player.set_interactive(message.value)
        case ControlFault():
            f = message.value
            player.fault(f.source, f.mode, f.active)


def _handle_message(app: FastAPI, client: Client, text: str) -> None:
    """Valida y ejecuta un mensaje del cliente; los errores vuelven como `error`."""
    bus: Bus = app.state.bus
    player: Player = app.state.player
    try:
        message = _MESSAGE.validate_python(json.loads(text))
    except json.JSONDecodeError:
        client.send(ErrorMessage(message="the message is not valid JSON"))
        return
    except ValidationError as exc:
        client.send(ErrorMessage(message=f"invalid message: {_describe(exc)}"))
        return

    if isinstance(message, Hello):
        if client.kind is not None and client.kind != message.client:
            client.send(
                ErrorMessage(message="the client already introduced itself as another type")
            )
            return
        client.kind = message.client
        return
    if client.kind is None:
        client.send(ErrorMessage(message="the first message must be hello"))
        return
    if isinstance(message, Subscribe):
        client.patterns += [p for p in message.patterns if p not in client.patterns]
        return
    if isinstance(message, Publish):
        event = message.event
        if not client_can_publish(client.kind, event.topic):
            domain = topic_domain(event.topic)
            client.send(
                ErrorMessage(
                    message=f"client {client.kind.value!r} cannot publish in the domain {domain!r}"
                )
            )
        elif bus.timeline.get(event.event_id) is not None:
            client.send(ErrorMessage(message=f"an event with id {event.event_id!r} already exists"))
        else:
            bus.publish(event)
        return
    if client.kind != ClientKind.WEB:
        client.send(ErrorMessage(message="only clients of type web can send control"))
        return
    try:
        _handle_control(player, message)
    except PlayerError as exc:
        client.send(ErrorMessage(message=str(exc)))
    except Exception as exc:
        log.exception("control failed")
        client.send(ErrorMessage(message=f"error interno: {exc}"))


async def _pump(ws: WebSocket, client: Client) -> None:
    """Vacía la cola de salida del cliente hacia el socket."""
    try:
        while True:
            await ws.send_text(await client.queue.get())
    except Exception:
        log.debug("client sender stopped")


async def _state_ticker(hub: Hub) -> None:
    while True:
        await asyncio.sleep(STATE_PERIOD_S)
        if hub.player.status == PlayerStatus.RUNNING:
            hub.broadcast_state()


def create_app(
    *,
    runs_dir: Path = RUNS_DIR,
    scenarios_dir: Path = SCENARIOS_DIR,
    run_clock: bool = True,
    wait_timeout_s: float | None = None,
) -> FastAPI:
    """Crea la aplicación. `run_clock=False` desactiva el reloj de pared (las pruebas avanzan el
    reproductor a mano)."""
    bus = Bus(Timeline())
    options: dict[str, Any] = {} if wait_timeout_s is None else {"wait_timeout_s": wait_timeout_s}
    player = Player(bus, runs_dir=runs_dir, scenarios_dir=scenarios_dir, **options)
    hub = Hub(player)
    player.listeners.append(hub.broadcast_state)
    tools = ToolContext(bus.timeline, lambda: player.sim_time)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks = []
        if run_clock:
            tasks = [
                asyncio.create_task(player.run_clock()),
                asyncio.create_task(_state_ticker(hub)),
            ]
        yield
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        player.shutdown()

    app = FastAPI(title="poc-ai-monitor platform", lifespan=lifespan)
    app.state.bus, app.state.player, app.state.hub = bus, player, hub
    app.add_middleware(
        CORSMiddleware, allow_origins=WEB_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )

    api = APIRouter(prefix="/api")

    @api.get("/scenarios")
    def scenarios() -> ScenariosResponse:
        infos = []
        for name in list_scenarios(scenarios_dir):
            duration = _generated_duration(runs_dir, name)
            infos.append(
                ScenarioInfo(
                    name=name,
                    description=load_scenario(name, scenarios_dir).description,
                    generated=duration is not None,
                    duration_s=duration,
                )
            )
        return ScenariosResponse(scenarios=infos)

    @api.get("/state")
    def state() -> PlayerState:
        return player.state()

    @api.get("/plan")
    def plan() -> PlanFile:
        if player.plan is None:
            raise HTTPException(status_code=404, detail="no scenario is loaded")
        return player.plan

    @api.get("/truth")
    def truth() -> TruthFile:
        try:
            return player.truth()
        except PlayerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.get("/timeline")
    def timeline(
        source: str | None = None,
        type: EventType | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int | None = Query(default=None, ge=0),
    ) -> dict[str, Any]:
        """Sin corte temporal: es para la web y la evaluación. Con `limit`, los últimos."""
        found, truncated = bus.timeline.query(
            source=source, type=type, since=since, until=until, limit=limit
        )
        return TimelineResponse(events=found, truncated=truncated).model_dump(mode="json")

    @api.post("/tools/{name}")
    async def run_tool(name: str, request: Request) -> ToolOk | ToolError:
        raw = await request.body()
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return ToolError(error="the body is not valid JSON")
        if not isinstance(args, dict):
            return ToolError(error="the arguments must be a JSON object")
        if player.config is None:
            return ToolError(error="no scenario is loaded")
        try:
            return ToolOk(result=call_tool(tools, name, args))
        except ToolFailure as exc:
            return ToolError(error=str(exc))

    app.include_router(api)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        client = Client(asyncio.get_running_loop())
        hub.clients.add(client)
        subscription = bus.subscribe("citadel.>", client.on_event)
        client.send(hub.state_message())
        sender = asyncio.create_task(_pump(ws, client))
        try:
            while True:
                _handle_message(app, client, await ws.receive_text())
        except WebSocketDisconnect:
            log.debug("client disconnected")
        finally:
            bus.unsubscribe(subscription)
            hub.clients.discard(client)
            sender.cancel()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Platform: player, bus, API and WebSocket")
    parser.add_argument("--port", type=int, default=PORT, help=f"port (default {PORT})")
    parser.add_argument(
        "--wait-timeout", type=float, help="seconds the player waits for the agent (default 90)"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(
        create_app(wait_timeout_s=args.wait_timeout), host=HOST, port=args.port, log_level="info"
    )


if __name__ == "__main__":
    main()
