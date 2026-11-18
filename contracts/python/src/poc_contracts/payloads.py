"""Payloads de los eventos (`contracts/eventos.md` §4)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .commands import CommandBody, WindCommandParams
from .enums import (
    ActivityState,
    AgentName,
    AlertPhase,
    AlertStatus,
    AutopilotMode,
    Cause,
    CommandIssuer,
    CompletionReason,
    ConversationId,
    DecidedBy,
    EventType,
    FaultMode,
    FaultOrigin,
    GpsFix,
    InstructorCommandName,
    PauseReason,
    Rule,
    SensorSource,
    Severity,
    ToolCallStatus,
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
    mission_controller_id: str
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
    """Posición del GPS. Con `simulator.gps_receiver`, **sin fix** (`fix: none`, `sats: 0`) el
    receptor no da posición, altitud, velocidad ni rumbo: van a `null` (la estima del dron va en
    `AutopilotStatus`). Sin ese interruptor, sin fix publica su posición estimada (v0.19)."""

    x: float | None
    y: float | None
    alt_m: float | None
    speed_mps: float | None
    course_deg: float | None
    fix: GpsFix
    sats: int
    hdop: float


class TrackUpdated(Payload):
    x: float
    y: float
    speed_mps: float
    course_deg: float


class WindReported(Payload):
    speed_mps: float
    from_deg: float


class LinkStatus(Payload):
    """Enlace de mando medido por **nuestra estación** (v1.0). Con `simulator.link_physics`:
    `rssi_dbm` y `latency_ms` (`null` si no llega nada) y `packet_loss_pct` (paquetes perdidos desde
    el último estado; 100 con el enlace caído). `controller_id` es de antes de la v1.0: se retira al
    cerrar la E7a (paso 7b) y no lo publica el enlace con física (desde tierra el controlador
    ajeno no se ve: queda solo en la verdad)."""

    controller_id: str | None = None
    rssi_dbm: float | None
    latency_ms: float | None
    packet_loss_pct: float | None = None


class BatteryStatus(Payload):
    """Batería. Con `simulator.battery_model` lleva además la potencia consumida y el tiempo
    restante al ritmo actual."""

    battery_pct: float
    power_w: float | None = None
    time_remaining_s: float | None = None


class GnssStatus(Payload):
    """Estado del receptor GNSS (v1.0, cada 1 s): `h_acc_m` es la precisión horizontal que dice el
    receptor, `cn0_dbhz` la relación portadora/ruido media y `agc_db` el control automático de
    ganancia (0 = nominal; baja con potencia cercana)."""

    h_acc_m: float
    cn0_dbhz: float
    agc_db: float


class AutopilotStatus(Payload):
    """Estado del autopiloto (v1.0, cada 1 s): modo, rumbo del **morro**, velocidad respecto al
    aire, viento estimado a bordo (m/s y procedencia), innovación (|GPS − estima|, m; `null` sin
    GPS: la estima no se corrige) y la **estima** del dron: posición (`est_x`, `est_y`), velocidad
    y rumbo sobre el suelo (lo que el GPS ya no da sin fix)."""

    mode: AutopilotMode
    heading_deg: float
    airspeed_mps: float
    wind_est_speed_mps: float
    wind_est_from_deg: float
    innovation_m: float | None
    est_x: float
    est_y: float
    ground_speed_mps: float
    course_deg: float


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


class InstructorCommand(Payload, CommandBody):
    """Comando del instructor aplicado por la plataforma (v0.18). El agente no ve este evento.

    `issued_by`: `panel`, `llm` (propuesta confirmada; `text` es la frase original) o `scenario`.
    """

    issued_by: CommandIssuer
    text: str | None


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
        elif self.rule == Rule.LINK_ANOMALY:
            if self.source != SensorSource.LINK:
                raise ValueError("LINK_ANOMALY exige `source: link`")
            if self.unit != "ms":
                raise ValueError(
                    "LINK_ANOMALY mide la latencia en milisegundos: `unit` debe ser 'ms'"
                )
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
    phase: AlertPhase = AlertPhase.ACTIVE
    """Fase de la alerta (v0.14): `active` por defecto; `recovering` en la recuperación del GPS."""
    decided_by: DecidedBy | None = None
    """Quién la decidió (v0.19): `table` (la tabla de decisión, `monitor.engine: table` o
    `hybrid`) o `llm`. Sin el campo, el LLM (las alertas anteriores a la v0.19)."""
    rule_id: str | None = None
    """v0.19: la fila de la tabla de decisión que dio la causa (`C05`…), solo con `table`."""


class AlertClosed(Payload):
    alert_id: str
    reason: str
    as_of_sim_time: float


class EnrichHypothesis(Payload):
    """Hipótesis del LLM en una alerta `UNKNOWN` del híbrido (v0.19): **no es un diagnóstico**.
    Causa de la lista cerrada (nunca `UNKNOWN`), confianza de 0,4 como mucho y evidencias que el
    módulo consultó al decidir la alerta."""

    cause: Cause
    confidence: float = Field(ge=0, le=0.4)
    evidence_event_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_cause(self) -> "EnrichHypothesis":
        if self.cause == Cause.UNKNOWN:
            raise ValueError("a hypothesis names a cause other than UNKNOWN")
        return self


class AlertEnriched(Payload):
    """Interpretación del LLM de una alerta que decidió la tabla (`monitor.engine: hybrid`,
    v0.19). Llega después de la alerta y no la cambia: causa, severidad, confianza y fase son las
    de la tabla. `alert_status` es el estado de la alerta al publicarse. El `causation_id` del
    sobre es el `alert_id`."""

    alert_id: str
    text: str = Field(min_length=1)
    hypothesis: EnrichHypothesis | None
    decided_by: DecidedBy
    as_of_sim_time: float
    alert_status: AlertStatus

    @model_validator(mode="after")
    def _check_decided_by(self) -> "AlertEnriched":
        if self.decided_by != DecidedBy.LLM:
            raise ValueError("an enrichment is written by the llm")
        return self


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


class ActiveWind(Payload):
    """Viento del instructor en curso, tal como lo conoce la web (`remaining_s: null` = sin fin)."""

    from_deg: float
    speed_mps: float
    remaining_s: float | None


class OperatorContext(Payload):
    """Contexto que la web añade a la pregunta del chat del instructor (v0.18)."""

    active_wind: ActiveWind | None


class OperatorMessage(Payload):
    conversation_id: ConversationId
    text: str
    context: OperatorContext | None = None  # solo `instructor`


class AgentReplyChunk(Payload):
    conversation_id: ConversationId
    reply_to: str
    delta: str


class InstructorProposal(Payload):
    """Propuesta del agente del instructor (no publica nada: la web la enseña y, si el instructor
    confirma, manda el comando). `defaults_used`: los parámetros que el modelo rellenó solo."""

    command: InstructorCommandName
    params: WindCommandParams | None
    defaults_used: list[str]


class AgentReply(Payload):
    conversation_id: ConversationId
    reply_to: str
    text: str
    tool_calls: list[str]
    proposal: InstructorProposal | None = None  # solo `instructor`


class AgentActivity(Payload):
    agent: AgentName
    state: ActivityState
    invocation_id: str
    causation_id: str | None


class AgentToolCall(Payload):
    """Una llamada a tool de un agente, solo para depurar en la web (recortada)."""

    agent: AgentName
    invocation_id: str
    index: Annotated[int, Field(ge=1)]
    iteration: Annotated[int, Field(ge=1)]
    tool: str
    arguments: str
    status: ToolCallStatus
    result: str | None
    error: str | None
    truncated: bool


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
    EventType.GNSS_STATUS: GnssStatus,
    EventType.AUTOPILOT_STATUS: AutopilotStatus,
    EventType.SIMULATION_STARTED: SimulationStarted,
    EventType.SIMULATION_PAUSED: SimulationPaused,
    EventType.SIMULATION_RESUMED: SimulationResumed,
    EventType.SIMULATION_FINISHED: SimulationFinished,
    EventType.SIMULATION_RESET: SimulationReset,
    EventType.INTERACTIVE_MODE_CHANGED: InteractiveModeChanged,
    EventType.FAULT_INJECTED: FaultInjected,
    EventType.FAULT_CLEARED: FaultCleared,
    EventType.INSTRUCTOR_COMMAND: InstructorCommand,
    EventType.DETECTION_RAISED: DetectionRaised,
    EventType.DETECTION_UPDATED: DetectionUpdated,
    EventType.DETECTION_CLEARED: DetectionCleared,
    EventType.DETECTION_ACKNOWLEDGED: DetectionAcknowledged,
    EventType.ANOMALY_DETECTED: AnomalyDetected,
    EventType.ALERT_CLOSED: AlertClosed,
    EventType.ALERT_ENRICHED: AlertEnriched,
    EventType.REPORT_GENERATED: ReportGenerated,
    EventType.OPERATOR_MESSAGE: OperatorMessage,
    EventType.AGENT_REPLY: AgentReply,
    EventType.AGENT_REPLY_CHUNK: AgentReplyChunk,
    EventType.AGENT_ACTIVITY: AgentActivity,
    EventType.AGENT_TOOL_CALL: AgentToolCall,
}
