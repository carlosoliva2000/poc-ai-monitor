"""Ficheros de `runs/` (`contracts/eventos.md` §8.2 a §8.4 y §8.6).

`events.jsonl` son `EventDraft`; aquí están `plan.json`, `truth.json` y `labels.json` (los escribe
el generador en `runs/<escenario>/`) y `run_meta.json` (lo escribe la plataforma en
`runs/<escenario>/<run_id>/`).
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import Cause, LabelType, Rule, SensorSource
from .payloads import Waypoint


class RunFile(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanSample(RunFile):
    """Estado previsto en el vuelo sin perturbaciones, cada segundo."""

    t: float
    x: float
    y: float
    speed_mps: float
    heading_deg: float


class PlanFile(RunFile):
    mission_id: str
    cruise_speed_mps: float
    altitude_m: float
    acceptance_radius_m: float
    duration_s: float
    waypoints: list[Waypoint]
    trajectory: list[PlanSample]


class TruthSample(RunFile):
    """Estado real cada segundo. `course_deg`: rumbo sobre el suelo; `heading_deg`: el del morro."""

    t: float
    x: float
    y: float
    speed_mps: float
    heading_deg: float
    course_deg: float


class TruthWind(RunFile):
    """Viento real (media y racha) cada segundo, con `from_deg` de procedencia."""

    t: float
    speed_mps: float
    gust_mps: float
    from_deg: float


class TruthFile(RunFile):
    """Verdad del vuelo. El agente nunca la ve."""

    duration_s: float
    trajectory: list[TruthSample]
    wind: list[TruthWind]


class Label(RunFile):
    id: str = Field(pattern=r"^[AF]\d+$")
    type: LabelType
    source: SensorSource | None
    start_s: float
    end_s: float
    expected_rules: list[Rule] = Field(min_length=1)
    expected_cause: Cause
    also_accepted_causes: list[Cause]
    eval_window: tuple[float, float]

    @model_validator(mode="after")
    def _check(self) -> "Label":
        is_fault = self.type in (LabelType.SOURCE_SILENT, LabelType.GPS_LOSS)
        if is_fault != (self.source is not None):
            raise ValueError("`source` es obligatoria en los fallos y null en el resto")
        if self.eval_window[0] != self.start_s or self.eval_window[1] < self.end_s:
            raise ValueError("eval_window va de start_s a end_s o más allá")
        return self


class LabelsFile(RunFile):
    labels: list[Label]


class SpeedChange(RunFile):
    sim_time: float
    value: float


class FlagChange(RunFile):
    sim_time: float
    value: bool


class RunMeta(RunFile):
    """`run_meta.json` de una ejecución: lo que no está en el timeline. Los valores son los del
    primer play o paso; los cambios posteriores van en `*_changes`, con el instante."""

    scenario: str
    run_id: str
    speed: float
    speed_changes: list[SpeedChange]
    wait_agent: bool
    wait_agent_changes: list[FlagChange]
    interactive: bool
    interactive_changes: list[FlagChange]
