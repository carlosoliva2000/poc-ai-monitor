"""Respuestas de la API HTTP (`contracts/eventos.md` §6)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .envelope import Envelope


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioInfo(_Model):
    name: str
    description: str
    generated: bool
    """`True` si existe `runs/<name>/events.jsonl`."""
    duration_s: float | None
    """`None` si el escenario no está generado."""


class ScenariosResponse(_Model):
    """Respuesta de `GET /api/scenarios`."""

    scenarios: list[ScenarioInfo]


class TimelineResponse(_Model):
    """Respuesta de `GET /api/timeline`: eventos por `sim_time` y `seq`."""

    events: list[Envelope]
    truncated: bool
    """`True` si `limit` ha recortado el resultado."""


class ToolOk(_Model):
    """Respuesta de `POST /api/tools/{name}` si va bien."""

    ok: Literal[True] = True
    result: Any


class ToolError(_Model):
    """Respuesta de `POST /api/tools/{name}` si falla (argumentos no válidos, tool desconocida…)."""

    ok: Literal[False] = False
    error: str
