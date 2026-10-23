"""Mensajes del WebSocket `/ws` (`contracts/eventos.md` §5). Todos llevan el campo `op`."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, model_validator

from .enums import ClientKind, FaultMode, FaultOrigin, PlayerStatus, SensorSource
from .envelope import Envelope, EventDraft
from .topics import validate_pattern

SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)


def _check_speed(value: float) -> float:
    if value not in SPEEDS:
        raise ValueError(f"invalid speed: {value} (values: {SPEEDS})")
    return value


Speed = Annotated[float, AfterValidator(_check_speed)]
Pattern = Annotated[str, AfterValidator(lambda p: (validate_pattern(p), p)[1])]


class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Cliente -> plataforma -------------------------------------------------------------------


class Hello(_Message):
    """Primer mensaje de cada cliente."""

    op: Literal["hello"] = "hello"
    client: ClientKind


class Subscribe(_Message):
    """Se suscribe a patrones de topic (acumula con los anteriores)."""

    op: Literal["subscribe"] = "subscribe"
    patterns: list[Pattern] = Field(min_length=1)


class Publish(_Message):
    """Publica un evento en el bus. Va **sin** `seq` ni `ingestion_time`."""

    op: Literal["publish"] = "publish"
    event: EventDraft


class FaultControl(_Message):
    """Valor de `control` → `fault`: activa (`active: true`) o termina un fallo de una fuente.

    Solo con el modo interactivo encendido. `loss` solo existe para el GPS.
    """

    source: SensorSource
    mode: FaultMode
    active: StrictBool

    @model_validator(mode="after")
    def _check_mode(self) -> "FaultControl":
        if self.mode == FaultMode.LOSS and self.source != SensorSource.GPS:
            raise ValueError("`loss` only exists for the GPS")
        return self


class ControlLoad(_Message):
    op: Literal["control"] = "control"
    action: Literal["load"] = "load"
    value: str


class ControlPlay(_Message):
    op: Literal["control"] = "control"
    action: Literal["play"] = "play"
    value: None = None


class ControlPause(_Message):
    op: Literal["control"] = "control"
    action: Literal["pause"] = "pause"
    value: None = None


class ControlStep(_Message):
    op: Literal["control"] = "control"
    action: Literal["step"] = "step"
    value: None = None


class ControlReset(_Message):
    op: Literal["control"] = "control"
    action: Literal["reset"] = "reset"
    value: None = None


class ControlSpeed(_Message):
    op: Literal["control"] = "control"
    action: Literal["speed"] = "speed"
    value: Speed


class ControlWaitAgent(_Message):
    op: Literal["control"] = "control"
    action: Literal["wait_agent"] = "wait_agent"
    value: StrictBool


class ControlInteractive(_Message):
    op: Literal["control"] = "control"
    action: Literal["interactive"] = "interactive"
    value: StrictBool


class ControlFault(_Message):
    op: Literal["control"] = "control"
    action: Literal["fault"] = "fault"
    value: FaultControl


Control = Annotated[
    ControlLoad
    | ControlPlay
    | ControlPause
    | ControlStep
    | ControlReset
    | ControlSpeed
    | ControlWaitAgent
    | ControlInteractive
    | ControlFault,
    Field(discriminator="action"),
]

ClientMessage = Annotated[Hello | Subscribe | Publish | Control, Field(discriminator="op")]


# --- Plataforma -> cliente -------------------------------------------------------------------


class EventMessage(_Message):
    """Un evento del bus (sobre completo, con `seq` e `ingestion_time`)."""

    op: Literal["event"] = "event"
    event: Envelope


class ActiveFault(_Message):
    """Un fallo en curso: la fuente, el tipo y quién lo activó."""

    source: SensorSource
    mode: FaultMode
    origin: FaultOrigin


class PlayerState(_Message):
    """Estado del reproductor, común al mensaje `state` y a `GET /api/state`."""

    status: PlayerStatus
    scenario: str | None
    run_id: str | None
    sim_time: float
    speed: float
    wait_agent: bool
    interactive: bool
    active_faults: list[ActiveFault]
    cursor: int
    total_events: int


class StateMessage(PlayerState):
    """Se envía al conectar, al cambiar y cada 0,5 s mientras corre."""

    op: Literal["state"] = "state"


class ErrorMessage(_Message):
    op: Literal["error"] = "error"
    message: str


ServerMessage = Annotated[EventMessage | StateMessage | ErrorMessage, Field(discriminator="op")]
