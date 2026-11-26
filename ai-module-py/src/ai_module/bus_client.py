"""Cliente asíncrono del bus de la plataforma por WebSocket (`/ws`). Solo lee y publica eventos:
no hay tools HTTP (v1.3).

Uso típico:

    async with BusClient("http://127.0.0.1:8100") as bus:
        async for event in bus.events():
            ...
            await bus.publish(draft)

Al conectar manda `hello` como `ai-module` y se suscribe a `DEFAULT_PATTERNS` (mundo, IA, operador
y ciclo de vida de la ejecución; no los fallos inyectados ni el modo interactivo). Si se cae la
conexión, `events()` reconecta solo con una espera creciente y vuelve a suscribirse.

Cliente de la librería `websockets` (API asíncrona moderna, `websockets.asyncio.client`).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Annotated

from pydantic import Field, TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from poc_contracts.enums import ClientKind
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.ws import (
    ErrorMessage,
    EventMessage,
    Hello,
    Publish,
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
# Lista blanca: el cliente solo entiende estos mensajes del servidor; cualquier otro `op` se
# descarta sin validarlo (defensa en profundidad: lo que no se espera no entra en el módulo).
_EXPECTED_OPS = frozenset({"event", "state", "error"})
_SERVER_MESSAGE: TypeAdapter[EventMessage | StateMessage | ErrorMessage] = TypeAdapter(
    Annotated[EventMessage | StateMessage | ErrorMessage, Field(discriminator="op")]
)


def _op_of(raw: str | bytes) -> object:
    """El `op` del mensaje, o `None` si no es un objeto JSON con `op`."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data.get("op") if isinstance(data, dict) else None


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
    ) -> None:
        self.platform_url = platform_url
        self.ws_url = ws_url or ws_url_from_platform(platform_url)
        self.patterns = list(patterns)
        self._backoff = backoff
        self._sleep = sleep
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
        if self._ws is None:
            raise ConnectionError("client closed")
        return self._ws

    async def messages(self) -> AsyncIterator[EventMessage | StateMessage | ErrorMessage]:
        """Mensajes válidos del servidor; reconecta si la conexión se cae."""
        while not self._closed:
            ws = await self._ensure_connected()
            try:
                async for raw in ws:
                    op = _op_of(raw)
                    if op not in _EXPECTED_OPS:
                        log.debug("unexpected server message dropped (op=%r)", op)
                        continue
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
