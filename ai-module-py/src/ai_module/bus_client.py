"""Cliente asíncrono del bus de la plataforma por WebSocket (`/ws`) y HTTP (`/api/tools`).

Uso típico:

    async with BusClient("http://127.0.0.1:8100") as bus:
        async for event in bus.events():
            ...
            await bus.publish(draft)

Al conectar manda `hello` como `ai-module` y se suscribe a `DEFAULT_PATTERNS` (mundo, IA, operador
y ciclo de vida de la ejecución; no los fallos inyectados ni el modo interactivo). Si se cae la
conexión, `events()` reconecta solo con una espera creciente y vuelve a suscribirse; después de
cada conexión llama a `on_connected` (la usa el módulo para pedir el plan de la misión por HTTP si
arranca con la simulación ya en marcha).

Cliente de la librería `websockets` (API asíncrona moderna, `websockets.asyncio.client`).
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Any

from pydantic import TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from poc_contracts.enums import ClientKind
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.ws import (
    ErrorMessage,
    EventMessage,
    Hello,
    Publish,
    ServerMessage,
    StateMessage,
    Subscribe,
)

log = logging.getLogger(__name__)

DEFAULT_PLATFORM = "http://127.0.0.1:8100"
# Lo que necesita el módulo: el mundo (dron, radar, meteo), la IA, el operador y el ciclo de vida
# de la ejecución. Quedan fuera los fallos inyectados y el modo interactivo (dominio `sim`): el
# agente solo ve sus efectos.
DEFAULT_PATTERNS = (
    "citadel.pub.evt.air.>",
    "citadel.pub.evt.env.>",
    "citadel.pub.evt.ai.>",
    "citadel.pub.evt.ops.>",
    "citadel.pub.evt.sim.player.SimulationStarted.v1",
    "citadel.pub.evt.sim.player.SimulationReset.v1",
    "citadel.pub.evt.sim.player.SimulationFinished.v1",
)
_SERVER_MESSAGE = TypeAdapter(ServerMessage)


def default_backoff(attempt: int) -> float:
    """Espera (s) antes del intento `attempt` (0, 1, 2…): 0,5 s, 1 s, 2 s… con tope de 10 s."""
    return min(0.5 * 2**attempt, 10.0)


def ws_url_from_platform(platform_url: str) -> str:
    """`http://host:puerto` -> `ws://host:puerto/ws`."""
    base = platform_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base.removeprefix("https://")
    elif base.startswith("http://"):
        base = "ws://" + base.removeprefix("http://")
    return base if base.endswith("/ws") else base + "/ws"


def _post_tool(platform_url: str, name: str, args: dict[str, Any], timeout_s: float) -> Any:
    request = urllib.request.Request(
        f"{platform_url.rstrip('/')}/api/tools/{name}",
        data=json.dumps(args).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read())


async def call_platform_tool(
    platform_url: str, name: str, args: dict[str, Any], timeout_s: float = 10.0
) -> Any:
    """`POST /api/tools/{name}`: devuelve el `result`; lanza `PlatformToolError` si la plataforma
    responde `ok: false` o no responde."""
    try:
        body = await asyncio.to_thread(_post_tool, platform_url, name, args, timeout_s)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise PlatformToolError(f"la plataforma no responde: {exc}") from exc
    if not isinstance(body, dict) or not body.get("ok"):
        message = body.get("error") if isinstance(body, dict) else None
        raise PlatformToolError(str(message or f"respuesta inesperada: {body!r}"))
    return body.get("result")


class PlatformToolError(Exception):
    """Una tool de datos de la plataforma ha fallado (mensaje en español)."""


async def fetch_mission_plan(platform_url: str, timeout_s: float = 5.0) -> dict[str, Any] | None:
    """Pide el plan a la tool `get_mission_plan` (`POST /api/tools/get_mission_plan`).

    Devuelve el `result` (el payload de `MissionPlanned` más `next_waypoint`) o `None` si la
    llamada falla o responde `ok: false` (p. ej. todavía no hay escenario cargado).
    """
    try:
        body = await asyncio.to_thread(_post_tool, platform_url, "get_mission_plan", {}, timeout_s)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        log.warning("get_mission_plan failed: %s", exc)
        return None
    if not isinstance(body, dict) or not body.get("ok"):
        log.info("get_mission_plan not available: %s", body)
        return None
    result = body.get("result")
    return result if isinstance(result, dict) else None


class BusClient:
    """Conexión al bus con reconexión simple."""

    def __init__(
        self,
        platform_url: str = DEFAULT_PLATFORM,
        *,
        ws_url: str | None = None,
        patterns: tuple[str, ...] = DEFAULT_PATTERNS,
        backoff: Callable[[int], float] = default_backoff,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_connected: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.platform_url = platform_url
        self.ws_url = ws_url or ws_url_from_platform(platform_url)
        self.patterns = list(patterns)
        self._backoff = backoff
        self._sleep = sleep
        self._on_connected = on_connected
        self._ws: ClientConnection | None = None
        self._closed = False
        self.sim_time: float | None = None  # `sim_time` del último mensaje `state`
        self.connections = 0  # conexiones establecidas (la primera y las reconexiones)

    async def __aenter__(self) -> "BusClient":
        await self._ensure_connected()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        self._closed = True
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _ensure_connected(self) -> ClientConnection:
        """Conecta (con reintentos y espera creciente) si no hay conexión viva."""
        attempt = 0
        while self._ws is None and not self._closed:
            try:
                ws = await connect(self.ws_url)
                await ws.send(Hello(client=ClientKind.AI_MODULE).model_dump_json())
                await ws.send(Subscribe(patterns=self.patterns).model_dump_json())
            except (OSError, ConnectionClosed, TimeoutError) as exc:
                delay = self._backoff(attempt)
                log.warning("cannot connect to %s (%s); retrying in %.1fs", self.ws_url, exc, delay)
                attempt += 1
                await self._sleep(delay)
                continue
            self._ws = ws
            self.connections += 1
            log.info("connected to %s", self.ws_url)
            if self._on_connected is not None:
                await self._on_connected()
        if self._ws is None:
            raise ConnectionError("client closed")
        return self._ws

    async def messages(self) -> AsyncIterator[EventMessage | StateMessage | ErrorMessage]:
        """Mensajes válidos del servidor; reconecta si la conexión se cae."""
        while not self._closed:
            ws = await self._ensure_connected()
            try:
                async for raw in ws:
                    try:
                        message = _SERVER_MESSAGE.validate_json(raw)
                    except ValidationError as exc:
                        log.warning("invalid server message ignored: %s", exc)
                        continue
                    if isinstance(message, StateMessage):
                        # solo el reloj: `active_faults` e `interactive` no se guardan
                        self.sim_time = message.sim_time
                    elif isinstance(message, ErrorMessage):
                        log.warning("platform error: %s", message.message)
                    yield message
            except ConnectionClosed:
                pass
            if self._ws is ws:
                self._ws = None
            if not self._closed:
                log.warning("connection lost; reconnecting")

    async def events(self) -> AsyncIterator[Envelope]:
        """Solo los eventos del bus (mensajes `event`)."""
        async for message in self.messages():
            if isinstance(message, EventMessage):
                yield message.event

    async def publish(self, draft: EventDraft) -> None:
        """Publica un evento (el módulo de IA solo puede publicar en topics `ai`)."""
        if self._ws is None:
            raise ConnectionError("not connected to the bus")
        await self._ws.send(Publish(event=draft).model_dump_json())
