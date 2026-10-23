"""Payloads de los eventos (`contracts/eventos.md` §4)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .enums import (
    ActivityState,
    AgentName,
    Cause,
    CompletionReason,
    ConversationId,
    EventType,
    FaultMode,
    FaultOrigin,
    GpsFix,
    PauseReason,
    Rule,
    SensorSource,
    Severity,
)


class Payload(BaseModel):
    """Base de todos los modelos del contrato: no admite campos que no estén en el documento."""

    model_config = ConfigDict(extra="forbid")


Summary = Annotated[str, StringConstraints(max_length=160)]


# --- Del escenario ---------------------------------------------------------------------------


class Waypoint(Payload):
    id: str
    x: float
    y: float
    eta_s: float


class MissionPlanned(Payload):
    mission_id: str
    cruise_speed_mps: float
    altitude_m: float
    acceptance_radius_m: float
    waypoints: list[Waypoint]


class MissionStarted(Payload):
    mission_id: str


class WaypointReached(Payload):
    waypoint_id: str
    index: int


class MissionCompleted(Payload):
    mission_id: str
    completed: bool
    reason: CompletionReason


class PositionUpdated(Payload):
    x: float
    y: float
    alt_m: float
    speed_mps: float
    heading_deg: float
    fix: GpsFix
    sats: int
    hdop: float


class TrackUpdated(Payload):
    radar_id: str
    x: float
    y: float
    speed_mps: float
    course_deg: float
    quality: float


class WindReported(Payload):
    station_id: str
    speed_mps: float
    gust_mps: float
    from_deg: float


class LinkStatus(Payload):
    controller_id: str
    rssi_dbm: float
    latency_ms: float


class BatteryStatus(Payload):
    battery_pct: float
    voltage_v: float


# --- Del reproductor -------------------------------------------------------------------------


class SimulationStarted(Payload):
    scenario: str
    run_id: str
    duration_s: float
    total_events: int


class SimulationPaused(Payload):
    reason: PauseReason


class SimulationResumed(Payload):
    pass


class SimulationFinished(Payload):
    scenario: str
    run_id: str


class SimulationReset(Payload):
    pass


class InteractiveModeChanged(Payload):
    """El modo interactivo (que permite inyectar fallos en directo) se enciende o se apaga."""

    interactive: bool


class _Fault(Payload):
    source: SensorSource
    mode: FaultMode
    origin: FaultOrigin

    @model_validator(mode="after")
    def _check_mode(self) -> "_Fault":
        if self.mode == FaultMode.LOSS and self.source != SensorSource.GPS:
            raise ValueError("`loss` only exists for the GPS")
        return self


class FaultInjected(_Fault):
    """Fallo activado (fuente silenciada o pérdida de GPS). El agente no ve este evento."""


class FaultCleared(_Fault):
    """Fallo terminado. El agente no ve este evento."""


# --- Del detector ----------------------------------------------------------------------------


class DetectionWindow(Payload):
    since: float
    until: float


class DetectionRaised(Payload):
    detection_id: str
    rule: Rule
    severity: Severity
    value: float
    threshold: float
    unit: str
    source: SensorSource | None
    window: DetectionWindow
    trigger_event_ids: list[str]
    message: str

    @model_validator(mode="after")
    def _check_source(self) -> "DetectionRaised":
        if self.rule == Rule.SOURCE_SILENT:
            if self.source is None:
                raise ValueError("SOURCE_SILENT exige `source`")
            if self.unit != "s":
                raise ValueError("SOURCE_SILENT mide segundos: `unit` debe ser 's'")
        elif self.rule == Rule.GPS_DEGRADED:
            if self.source != SensorSource.GPS:
                raise ValueError("GPS_DEGRADED exige `source: gps`")
        elif self.source is not None:
            raise ValueError(f"{self.rule} no lleva `source` (debe ser null)")
        return self


class DetectionUpdated(DetectionRaised):
    """Mismo `detection_id` que el `DetectionRaised` y una severidad mayor."""


class DetectionCleared(Payload):
    detection_id: str
    rule: Rule
    duration_s: float
    max_value: float


# --- Del agente monitor ----------------------------------------------------------------------


class AlertChecks(Payload):
    """Comprobaciones que el monitor declara antes de elegir la causa (para que el operador vea
    por qué se decidió). El módulo las contrasta con los resultados de las tools de la
    invocación y con el estado."""

    gps_alert_recent: bool
    """Hay una alerta del GPS abierta o cerrada hace 60 s de tiempo simulado o menos."""
    gps_radar_disagreed: bool
    """`gps_radar.disagreed` del último `get_track_metrics` (falso si no se llamó)."""
    wind_notable: bool
    """`wind.notable` del último `get_track_metrics` (falso si no hay viento o no se llamó)."""
    wind_with_drift: bool
    """`wind.with_drift` del último `get_track_metrics` (falso si no hay viento o no se llamó)."""
    link_checked: bool
    """Se llamó a `get_events` con `source: link` en la invocación."""
    link_anomalous: bool | None
    """Enlace anómalo en esos eventos (otro `controller_id`, salto de RSSI > 10 dB o latencia
    muy superior); `None` si no se miró."""


class AnomalyDetected(Payload):
    alert_id: str
    detection_ids: list[str]
    cause: Cause
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    summary: Summary
    explanation: str
    recommendation: str
    evidence_event_ids: list[str]
    supersedes: str | None
    as_of_sim_time: float
    fallback: bool
    checks: AlertChecks | None = None


class AlertClosed(Payload):
    alert_id: str
    reason: str
    as_of_sim_time: float


class DetectionAcknowledged(Payload):
    """Respuesta del monitor a una detección que no genera una alerta nueva: `alert_id` es la
    alerta abierta a la que pertenece, o `None` si no hace falta alerta. `fallback: true` si lo
    publica el módulo porque el agente no concluyó. El `causation_id` del sobre es el
    `event_id` del evento de detección al que responde."""

    detection_id: str
    alert_id: str | None
    reason: str
    as_of_sim_time: float
    fallback: bool


# --- Del agente de informe -------------------------------------------------------------------


class ReportGenerated(Payload):
    run_id: str
    markdown: str
    alerts_count: int


# --- Del chat --------------------------------------------------------------------------------


class OperatorMessage(Payload):
    conversation_id: ConversationId
    text: str


class AgentReplyChunk(Payload):
    conversation_id: ConversationId
    reply_to: str
    delta: str


class AgentReply(Payload):
    conversation_id: ConversationId
    reply_to: str
    text: str
    tool_calls: list[str]


class AgentActivity(Payload):
    agent: AgentName
    state: ActivityState
    invocation_id: str
    causation_id: str | None


PAYLOAD_MODELS: dict[EventType, type[Payload]] = {
    EventType.MISSION_PLANNED: MissionPlanned,
    EventType.MISSION_STARTED: MissionStarted,
    EventType.WAYPOINT_REACHED: WaypointReached,
    EventType.MISSION_COMPLETED: MissionCompleted,
    EventType.POSITION_UPDATED: PositionUpdated,
    EventType.TRACK_UPDATED: TrackUpdated,
    EventType.WIND_REPORTED: WindReported,
    EventType.LINK_STATUS: LinkStatus,
    EventType.BATTERY_STATUS: BatteryStatus,
    EventType.SIMULATION_STARTED: SimulationStarted,
    EventType.SIMULATION_PAUSED: SimulationPaused,
    EventType.SIMULATION_RESUMED: SimulationResumed,
    EventType.SIMULATION_FINISHED: SimulationFinished,
    EventType.SIMULATION_RESET: SimulationReset,
    EventType.INTERACTIVE_MODE_CHANGED: InteractiveModeChanged,
    EventType.FAULT_INJECTED: FaultInjected,
    EventType.FAULT_CLEARED: FaultCleared,
    EventType.DETECTION_RAISED: DetectionRaised,
    EventType.DETECTION_UPDATED: DetectionUpdated,
    EventType.DETECTION_CLEARED: DetectionCleared,
    EventType.DETECTION_ACKNOWLEDGED: DetectionAcknowledged,
    EventType.ANOMALY_DETECTED: AnomalyDetected,
    EventType.ALERT_CLOSED: AlertClosed,
    EventType.REPORT_GENERATED: ReportGenerated,
    EventType.OPERATOR_MESSAGE: OperatorMessage,
    EventType.AGENT_REPLY: AgentReply,
    EventType.AGENT_REPLY_CHUNK: AgentReplyChunk,
    EventType.AGENT_ACTIVITY: AgentActivity,
}
