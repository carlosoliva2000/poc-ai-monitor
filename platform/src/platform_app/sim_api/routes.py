"""Rutas de la API `/api/v1` (`contracts/api/README.md`): assets, ejercicio e instructor.

Todos los handlers son `async def`: se ejecutan en el bucle de asyncio, el mismo hilo que el
WebSocket y el reloj, porque el reproductor no es seguro entre hilos. Las órdenes pasan por
`apply_control`, igual que las del WebSocket, así que los clientes de `/ws` ven lo mismo.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from poc_contracts.api import ScenarioInfo, ScenariosResponse
from poc_contracts.commands import InstructorControl
from poc_contracts.run_files import TruthFile
from poc_contracts.sim_api import (
    ApiError,
    AssetInfo,
    AssetsResponse,
    AssetState,
    Gap,
    Heartbeat,
    InjectsResponse,
    InteractiveRequest,
    LifecycleType,
    LoadRequest,
    MessagesPage,
    SpeedRequest,
)
from poc_contracts.ws import (
    ControlFault,
    ControlInstructor,
    ControlInteractive,
    ControlLoad,
    ControlPause,
    ControlPlay,
    ControlReset,
    ControlSpeed,
    ControlStep,
    FaultControl,
    PlayerState,
)

from ..control import apply_control, generated_duration
from ..generator.scenario_io import list_scenarios, load_scenario
from ..player import Player, PlayerError
from .assets import ASSET_IDS, INSTRUCTOR, asset_info, message_types
from .feed import Feed, Log

API_VERSION = "1.0.0"
HEARTBEAT_S = 1.0
POLL_S = 0.05
BATCH = 500
DESCRIPTION = (
    "Exercise simulator with a multirotor drone, a radar, a weather station and a ground "
    "station. Per-asset data in its own JSON format (REST and Server-Sent Events), exercise "
    "control and instructor injects."
)
_ERRORS: dict[int | str, dict[str, Any]] = {404: {"model": ApiError}, 409: {"model": ApiError}}
_SSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "`text/event-stream`. `event: message` (id = seq, data = AssetMessage), "
            "`event: heartbeat` (no id, data = Heartbeat) and `event: gap` (data = Gap). "
            "Resume with `Last-Event-ID` or `since`."
        ),
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    },
    404: {"model": ApiError},
}
_LIFECYCLE = {t.value for t in LifecycleType}


def _parse_types(types: str | None, valid: set[str]) -> set[str] | None:
    if not types:
        return None
    wanted = {t.strip() for t in types.split(",") if t.strip()}
    unknown = sorted(wanted - valid)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown message types: {', '.join(unknown)}")
    return wanted


def _sse(event: str, data: str, event_id: int | None = None) -> bytes:
    lines = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {data}")
    return ("\n".join(lines) + "\n\n").encode()


def create_sim_api(player: Player, feed: Feed, scenarios_dir: Path) -> FastAPI:
    """La subaplicación de `/api/v1` (se monta en la plataforma; tiene su propio OpenAPI)."""
    api = FastAPI(
        title="Drone exercise simulator API",
        version=API_VERSION,
        description=DESCRIPTION,
        servers=[{"url": "/api/v1"}],
    )

    def known_asset(asset_id: str) -> str:
        if asset_id not in ASSET_IDS:
            raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id!r}")
        return asset_id

    def run_control(message: Any) -> PlayerState:
        try:
            apply_control(player, message)
        except PlayerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return player.state()

    async def stream(
        log: Log, types: set[str] | None, since: int | None, last_event_id: str | None
    ) -> StreamingResponse:
        if last_event_id is not None:
            try:
                since = int(last_event_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail="Last-Event-ID is not a number"
                ) from exc

        async def events() -> AsyncIterator[bytes]:
            cursor = log.last_seq if since is None else since
            if since is not None and max(since + 1, 1) < log.first_available:
                gap = Gap(requested=since, first_available=log.first_available)
                yield _sse("gap", gap.model_dump_json())
                cursor = log.first_available - 1
            next_heartbeat = 0.0
            while True:
                beat = Heartbeat(  # antes de leer: todo lo anterior a este instante ya está
                    run_id=player.run_id,
                    status=player.status.value,
                    sim_time=player.sim_time,
                    speed=player.speed,
                )
                batch = log.read(cursor, BATCH)
                for message in batch:
                    cursor = message.seq
                    if types is None or message.type in types:
                        yield _sse("message", message.model_dump_json(), message.seq)
                if len(batch) == BATCH:
                    continue
                if time.monotonic() >= next_heartbeat:
                    next_heartbeat = time.monotonic() + HEARTBEAT_S
                    yield _sse("heartbeat", beat.model_dump_json())
                await asyncio.sleep(POLL_S)

        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    @api.get("/assets", tags=["assets"], summary="Asset inventory with its configuration")
    async def assets() -> AssetsResponse:
        config = player.config
        if config is None:
            return AssetsResponse(scenario_loaded=False, assets=[])
        return AssetsResponse(
            scenario_loaded=True, assets=[asset_info(a, config) for a in ASSET_IDS]
        )

    @api.get("/assets/{asset_id}", tags=["assets"], responses=_ERRORS)
    async def asset(asset_id: str) -> AssetInfo:
        known_asset(asset_id)
        if player.config is None:
            raise HTTPException(status_code=404, detail="no scenario is loaded")
        return asset_info(asset_id, player.config)

    @api.get("/assets/{asset_id}/state", tags=["assets"], responses=_ERRORS)
    async def asset_state(asset_id: str) -> AssetState:
        known_asset(asset_id)
        return AssetState(
            asset_id=asset_id,
            run_id=feed.run_id,
            status=player.status.value,
            sim_time=player.sim_time,
            last=dict(feed.last[asset_id]),
        )

    @api.get(
        "/assets/{asset_id}/messages",
        tags=["assets"],
        responses=_ERRORS,
        summary="History of a run, paged by seq",
    )
    async def asset_messages(
        asset_id: str,
        since: int = Query(-1, ge=-1, description="Exclusive: messages with seq > since"),
        limit: int = Query(1000, ge=1, le=10_000),
        types: str | None = Query(None, description="Comma-separated message types"),
        run_id: str | None = Query(None, description="Default: the current run"),
    ) -> MessagesPage:
        known_asset(asset_id)
        if run_id is not None and run_id not in feed.runs:
            raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id!r}")
        wanted = _parse_types(types, set(message_types(asset_id)) | _LIFECYCLE)
        messages, next_seq, has_more = feed.page(asset_id, since, limit, wanted, run_id)
        return MessagesPage(asset_id=asset_id, messages=messages, next=next_seq, has_more=has_more)

    @api.get(
        "/assets/{asset_id}/stream",
        tags=["assets"],
        responses=_SSE,
        response_class=Response,
        summary="Live stream (SSE)",
    )
    async def asset_stream(
        asset_id: str,
        types: str | None = Query(None, description="Comma-separated message types"),
        since: int | None = Query(None, ge=-1, description="Replay seq > since, then go live"),
        last_event_id: str | None = Header(None),
    ) -> Response:
        known_asset(asset_id)
        wanted = _parse_types(types, set(message_types(asset_id)) | _LIFECYCLE)
        return await stream(feed.logs[asset_id], wanted, since, last_event_id)

    @api.get("/exercise", tags=["exercise"], summary="Exercise state")
    async def exercise() -> PlayerState:
        return player.state()

    @api.get("/exercise/scenarios", tags=["exercise"])
    async def scenarios() -> ScenariosResponse:
        infos = []
        for name in list_scenarios(scenarios_dir):
            duration = generated_duration(player.runs_dir, name)
            description = load_scenario(name, scenarios_dir).description
            infos.append(
                ScenarioInfo(
                    name=name,
                    description=description,
                    generated=duration is not None,
                    duration_s=duration,
                )
            )
        return ScenariosResponse(scenarios=infos)

    @api.post("/exercise/load", tags=["exercise"], responses=_ERRORS)
    async def load(body: LoadRequest) -> PlayerState:
        if body.scenario not in list_scenarios(scenarios_dir):
            raise HTTPException(status_code=404, detail=f"unknown scenario: {body.scenario!r}")
        return run_control(ControlLoad(value=body.scenario))

    @api.post("/exercise/play", tags=["exercise"], responses=_ERRORS)
    async def play() -> PlayerState:
        return run_control(ControlPlay())

    @api.post("/exercise/pause", tags=["exercise"], responses=_ERRORS)
    async def pause() -> PlayerState:
        return run_control(ControlPause())

    @api.post("/exercise/step", tags=["exercise"], responses=_ERRORS)
    async def step() -> PlayerState:
        return run_control(ControlStep())

    @api.post("/exercise/reset", tags=["exercise"], responses=_ERRORS)
    async def reset() -> PlayerState:
        return run_control(ControlReset())

    @api.put("/exercise/speed", tags=["exercise"], responses=_ERRORS)
    async def speed(body: SpeedRequest) -> PlayerState:
        return run_control(ControlSpeed(value=body.value))

    @api.put("/exercise/interactive", tags=["exercise"], responses=_ERRORS)
    async def interactive(body: InteractiveRequest) -> PlayerState:
        return run_control(ControlInteractive(value=body.value))

    @api.post(
        "/instructor/faults",
        tags=["instructor"],
        responses=_ERRORS,
        summary="Start or end a fault (interactive mode only)",
    )
    async def fault(body: FaultControl) -> PlayerState:
        return run_control(ControlFault(value=body))

    @api.post(
        "/instructor/commands",
        tags=["instructor"],
        responses=_ERRORS,
        summary="Wind command (interactive mode only)",
    )
    async def command(body: InstructorControl) -> PlayerState:
        return run_control(ControlInstructor(value=body))

    @api.get("/instructor/injects", tags=["instructor"], summary="What the exercise schedules")
    async def injects() -> InjectsResponse:
        return InjectsResponse(run_id=feed.run_id, injects=list(feed.injects))

    @api.get("/instructor/truth", tags=["instructor"], responses=_ERRORS, summary="Ground truth")
    async def truth() -> TruthFile:
        try:
            return player.truth()
        except PlayerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.get(
        "/instructor/stream",
        tags=["instructor"],
        responses=_SSE,
        response_class=Response,
        summary="Instructor events (SSE): faults, commands, injects, interactive mode",
    )
    async def instructor_stream(
        since: int | None = Query(None, ge=-1), last_event_id: str | None = Header(None)
    ) -> Response:
        return await stream(feed.logs[INSTRUCTOR], None, since, last_event_id)

    return api
