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


class _Fault(Payload):
    source: SensorSource
    origin: FaultOrigin


class FaultInjected(_Fault):
    """Fuente silenciada. El agente no ve este evento."""


class FaultCleared(_Fault):
    """Fuente reactivada. El agente no ve este evento."""


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


class AlertClosed(Payload):
    alert_id: str
    reason: str
    as_of_sim_time: float


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
    EventType.FAULT_INJECTED: FaultInjected,
    EventType.FAULT_CLEARED: FaultCleared,
    EventType.DETECTION_RAISED: DetectionRaised,
    EventType.DETECTION_UPDATED: DetectionUpdated,
    EventType.DETECTION_CLEARED: DetectionCleared,
    EventType.ANOMALY_DETECTED: AnomalyDetected,
    EventType.ALERT_CLOSED: AlertClosed,
    EventType.REPORT_GENERATED: ReportGenerated,
    EventType.OPERATOR_MESSAGE: OperatorMessage,
    EventType.AGENT_REPLY: AgentReply,
    EventType.AGENT_REPLY_CHUNK: AgentReplyChunk,
    EventType.AGENT_ACTIVITY: AgentActivity,
}
