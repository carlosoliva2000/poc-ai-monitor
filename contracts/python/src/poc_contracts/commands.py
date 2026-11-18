"""Comandos del instructor (v0.18): viento puesto en directo o programado en el escenario.

Los comparten la plataforma (que los aplica y publica `InstructorCommand`), el escenario
(`commands:`), el mensaje `control` → `instructor` del WebSocket y el agente del instructor
(que solo propone). Unidades: m/s y grados; el viento se nombra por la dirección de procedencia.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import CommandIssuer, InstructorCommandName

MAX_WIND_SPEED_MPS = 40.0
MAX_RAMP_S = 120.0
MAX_DURATION_S = 1800.0


class WindCommandParams(BaseModel):
    """Los mismos parámetros que un episodio de viento del escenario, más la duración.

    `from_deg` y `speed_mps` empujan al dron; `ramp_s` suaviza la subida y la bajada.
    `duration_s: null` = hasta nuevo aviso. Sin racha desde el contrato v1.0.
    """

    model_config = ConfigDict(extra="forbid")

    from_deg: float = Field(ge=0, le=360)
    speed_mps: float = Field(ge=0, le=MAX_WIND_SPEED_MPS)
    ramp_s: float = Field(gt=0, le=MAX_RAMP_S)
    duration_s: float | None = Field(gt=0, le=MAX_DURATION_S)

    @field_validator("from_deg")
    @classmethod
    def _normalize_direction(cls, value: float) -> float:
        return value % 360.0  # 360 es el norte


class CommandBody(BaseModel):
    """`set_wind` lleva sus parámetros; `cancel_wind` no (termina el viento del instructor)."""

    model_config = ConfigDict(extra="forbid")

    command: InstructorCommandName
    params: WindCommandParams | None

    @model_validator(mode="after")
    def _check_params(self) -> "CommandBody":
        if self.command == InstructorCommandName.SET_WIND and self.params is None:
            raise ValueError("set_wind needs params")
        if self.command == InstructorCommandName.CANCEL_WIND and self.params is not None:
            raise ValueError("cancel_wind takes no params")
        return self


class ScheduledCommand(CommandBody):
    """Comando programado en el YAML del escenario (`commands:`) en `at_s`."""

    at_s: float = Field(ge=0)


class InstructorControl(CommandBody):
    """Valor de `control` → `instructor`: lo que manda la web (panel o propuesta confirmada)."""

    issued_by: CommandIssuer
    text: str | None

    @model_validator(mode="after")
    def _check_issuer(self) -> "InstructorControl":
        if self.issued_by == CommandIssuer.SCENARIO:
            raise ValueError("issued_by scenario is only for commands scheduled in a scenario")
        if self.issued_by == CommandIssuer.LLM and not (self.text or "").strip():
            raise ValueError("a command issued by the llm carries the original text")
        return self
