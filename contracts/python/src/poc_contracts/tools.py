"""Argumentos y resultados de las tools (`contracts/eventos.md` §7).

Los esquemas que ve el modelo están en `agent-assets/tools.json`; estos modelos son los que
validan en la plataforma (argumentos de las tools de datos) y en el módulo de IA (`publish_alert`).
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from .enums import AlertStatus, Cause, CompletionReason, EventType, Severity, ToolSource, Trend
from .payloads import MissionPlanned, Summary


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


MAX_LAST_N = 50


def _clamp_last_n(value: int) -> int:
    """Entre 1 y 50: un valor fuera de rango se recorta en vez de devolver un error al modelo."""
    return max(1, min(value, MAX_LAST_N))


# --- Argumentos ------------------------------------------------------------------------------


class NoArgs(_Model):
    """`get_mission_plan` y `get_flight_summary` no reciben argumentos."""


class GetEventsArgs(_Model):
    source: ToolSource
    type: EventType | None = None
    last_n: Annotated[int, AfterValidator(_clamp_last_n)] = 10
    since: float | None = None
    until: float | None = None


class GetTrackMetricsArgs(_Model):
    since: float
    until: float


class GetMyAlertsArgs(_Model):
    only_open: bool = False


class PublishAlertArgs(_Model):
    detection_ids: list[str] = Field(min_length=1)
    cause: Cause
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    summary: Summary
    explanation: str
    recommendation: str
    evidence_event_ids: list[str] = Field(min_length=1)
    supersedes: str | None = None


class CloseAlertArgs(_Model):
    alert_id: str
    reason: str


class LoadSkillArgs(_Model):
    name: str


# --- Resultados ------------------------------------------------------------------------------


class CompactEvent(BaseModel):
    """Evento compacto: id, tipo, `sim_time`, `t` y los campos de su payload (sin el resto del
    sobre). Los campos del payload varían según el tipo, de ahí `extra="allow"`."""

    model_config = ConfigDict(extra="allow")

    event_id: str
    type: EventType
    sim_time: float
    t: Annotated[str, StringConstraints(pattern=r"^T\+\d{2,}:\d{2}$")]


class GetEventsResult(_Model):
    events: list[CompactEvent]
    truncated: bool


class MissionPlanResult(MissionPlanned):
    """Payload de `MissionPlanned` más el siguiente waypoint pendiente (`None` al terminar)."""

    next_waypoint: str | None


class MetricStat(_Model):
    mean: float
    max: float
    trend: Trend | None
    """`None` con menos de 3 muestras."""


class SourcePair(_Model):
    """Un valor por fuente de posición; `None` si esa fuente no tiene datos."""

    gps: float | None
    radar: float | None


class SampleCounts(_Model):
    gps: int
    radar: int


class TrackMetrics(_Model):
    """Resultado de `get_track_metrics`. Sin datos de una fuente no se inventa nada: lo que
    depende de ella va a `None` y `samples` lleva el recuento real."""

    since: float
    until: float
    gps_deviation_from_plan_m: MetricStat | None
    radar_deviation_from_plan_m: MetricStat | None
    gps_radar_distance_m: MetricStat | None
    drift_direction_deg: float | None
    course_deg: SourcePair
    bearing_to_next_waypoint_deg: float | None
    next_waypoint: str | None
    mean_speed_mps: SourcePair
    samples: SampleCounts
    gps_available: bool
    radar_available: bool
    last_seen_sim_time: SourcePair
    first_event_ids: list[str]
    last_event_ids: list[str]


class AlertSummary(_Model):
    alert_id: str
    cause: Cause
    severity: Severity
    confidence: float
    summary: str
    status: AlertStatus
    sim_time: float


class MyAlertsResult(_Model):
    alerts: list[AlertSummary]


class DistanceBySource(_Model):
    gps: float | None
    radar: float | None


class ReachedWaypoint(_Model):
    waypoint_id: str
    sim_time: float


class DetectionsByRule(_Model):
    """Siempre con las cuatro reglas (0 si no hubo detecciones)."""

    ROUTE_DEVIATION: int
    SOURCE_DISCREPANCY: int
    SOURCE_SILENT: int
    GPS_DEGRADED: int


class AlertsByCause(_Model):
    """Siempre con las seis causas (0 si no hubo alertas)."""

    WIND: int
    HIJACK: int
    GPS_SPOOFING: int
    SENSOR_FAULT: int
    GPS_JAMMING: int
    UNKNOWN: int


class FlightSummary(_Model):
    """Resultado de `get_flight_summary`. Nunca incluye información del dominio `sim`."""

    mission_id: str
    duration_s: float
    mission_completed: bool
    completion_reason: CompletionReason | None
    distance_m: DistanceBySource
    waypoints_planned: list[str]
    waypoints_reached: list[ReachedWaypoint]
    detections_by_rule: DetectionsByRule
    alerts_by_cause: AlertsByCause
    alerts_open: int
    alerts_closed: int


class PublishAlertOk(_Model):
    ok: Literal[True] = True
    alert_id: str


class PublishAlertRejected(_Model):
    ok: Literal[False] = False
    errors: list[str]


# Tools de datos (plataforma) y locales (módulo de IA): nombre -> (argumentos, resultado).
# `close_alert` y `load_skill` no tienen resultado definido en el contrato (son locales).
TOOL_MODELS: dict[str, tuple[type[BaseModel], type[BaseModel] | None]] = {
    "get_events": (GetEventsArgs, GetEventsResult),
    "get_mission_plan": (NoArgs, MissionPlanResult),
    "get_track_metrics": (GetTrackMetricsArgs, TrackMetrics),
    "get_my_alerts": (GetMyAlertsArgs, MyAlertsResult),
    "get_flight_summary": (NoArgs, FlightSummary),
    "publish_alert": (PublishAlertArgs, None),
    "close_alert": (CloseAlertArgs, None),
    "load_skill": (LoadSkillArgs, None),
}

# Resultado de `publish_alert`: uno de estos dos.
PublishAlertResult = Annotated[PublishAlertOk | PublishAlertRejected, Field(discriminator="ok")]
