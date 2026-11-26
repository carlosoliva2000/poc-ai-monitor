"""API REST del simulador (`/api/v1`, `contracts/api/README.md`): modelos de las respuestas.

Es la cara del simulador como plataforma externa (despliegue en CITADEL): endpoints por asset
con su propio formato (`AssetMessage`: una cabecera propia y, en `data`, el payload de los eventos
del contrato del bus), control del ejercicio e *injects* del instructor. Los modelos de las
órdenes (`FaultControl`, `InstructorControl`) y del estado (`PlayerState`) son los del WebSocket.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .payloads import Inject
from .ws import Speed


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetType(StrEnum):
    DRONE = "drone"
    RADAR = "radar"
    WEATHER_STATION = "weather_station"
    GROUND_STATION = "ground_station"


class LifecycleType(StrEnum):
    """Mensajes de ciclo de vida de la ejecución: salen por todos los assets, con su `seq`."""

    RUN_STARTED = "RunStarted"
    RUN_RESET = "RunReset"
    RUN_FINISHED = "RunFinished"


class AssetInfo(_Model):
    """Un asset del inventario, con su configuración (lo que se sabe de él de antemano)."""

    id: str
    type: AssetType
    name: str
    subject: str
    """De quién habla: `d1` (radar y estación de tierra) o `zone1` (estación meteorológica)."""
    message_types: list[str]
    """Tipos de mensaje que publica, sin los de ciclo de vida."""
    config: dict[str, float | str]
    """Ficha del asset: unidades del SI (m, s, m/s). Nunca lleva viento, fallos ni la verdad."""


class AssetsResponse(_Model):
    """Respuesta de `GET /assets`."""

    scenario_loaded: bool
    assets: list[AssetInfo]
    """Vacío mientras no hay escenario cargado (la ficha sale del escenario)."""


class AssetMessage(_Model):
    """Un mensaje de un asset, en su formato propio (sin topics, `source` ni `ephemeral`)."""

    seq: int = Field(ge=1)
    """Orden de publicación en este asset; crece siempre (no se reinicia al cargar otra ejecución
    ni al reiniciarla)."""
    run_id: str
    asset_id: str
    subject: str
    type: str
    """El tipo del evento del contrato (`PositionUpdated`…) o un `LifecycleType`."""
    id: str
    """El `event_id` del contrato (`gps-000061`); los de ciclo de vida, `run-<run_id>-<tipo>`."""
    sim_time: float
    time_utc: str
    """Tiempo del ejercicio (`event_time` del contrato): `t0` del escenario + `sim_time`."""
    received_utc: str
    """Reloj de pared al publicarse (`ingestion_time` del contrato)."""
    data: dict[str, Any]
    """El payload del evento del contrato, sin cambios."""


class MessagesPage(_Model):
    """Respuesta de `GET /assets/{id}/messages`: una página con cursor numérico (`seq`)."""

    asset_id: str
    messages: list[AssetMessage]
    next: int
    """El `seq` del último mensaje examinado: el `since` de la página siguiente."""
    has_more: bool


class AssetState(_Model):
    """Respuesta de `GET /assets/{id}/state`: el último mensaje de cada tipo."""

    asset_id: str
    run_id: str | None
    status: str
    sim_time: float
    last: dict[str, AssetMessage]


class Heartbeat(_Model):
    """`event: heartbeat` del flujo (sin `id`): la fuente callada no es una conexión caída."""

    run_id: str | None
    status: str
    sim_time: float
    """Hasta aquí ha llegado el ejercicio: no vendrá nada de este asset con un `sim_time` menor."""
    speed: float


class Gap(_Model):
    """`event: gap`: se pidió desde un `seq` que ya no se conserva."""

    requested: int
    first_available: int


class LoadRequest(_Model):
    scenario: str


class SpeedRequest(_Model):
    value: Speed


class InteractiveRequest(_Model):
    value: StrictBool


class InjectsResponse(_Model):
    """Lo programado en el ejercicio (la verdad: solo por la parte del instructor)."""

    run_id: str | None
    injects: list[Inject]


class ApiError(_Model):
    """Cuerpo de los errores 404 y 409 (los de validación son los 422 de FastAPI)."""

    detail: str


StreamKind = Literal["message", "heartbeat", "gap"]
