"""Enumerados cerrados de `contracts/eventos.md`."""

from enum import StrEnum


class SensorSource(StrEnum):
    """Fuentes que se pueden silenciar y en las que puede saltar `SOURCE_SILENT`."""

    GPS = "gps"
    RADAR = "radar"
    METEO = "meteo"
    LINK = "link"
    BATTERY = "battery"


class AutopilotMode(StrEnum):
    """Modo del autopiloto (v1.0): `mission`, o el failsafe activo (volver, mantener, aterrizar)."""

    MISSION = "mission"
    FAILSAFE_RETURN = "failsafe_return"
    FAILSAFE_HOLD = "failsafe_hold"
    FAILSAFE_LAND = "failsafe_land"


class ToolSource(StrEnum):
    """Valores del parámetro `source` de `get_events` (nunca el dominio `sim`)."""

    GPS = "gps"
    RADAR = "radar"
    METEO = "meteo"
    LINK = "link"
    BATTERY = "battery"
    MISSION = "mission"
    DETECTOR = "detector"
    MONITOR = "monitor"
    OPERATOR = "operator"


class EventSource(StrEnum):
    """`source` de `get_events` (v0.17): las fuentes de `ToolSource` o `all` (todas a la vez)."""

    ALL = "all"
    GPS = "gps"
    RADAR = "radar"
    METEO = "meteo"
    LINK = "link"
    BATTERY = "battery"
    MISSION = "mission"
    DETECTOR = "detector"
    MONITOR = "monitor"
    OPERATOR = "operator"


class EventType(StrEnum):
    """Tipos de evento (último segmento del topic sin la versión)."""

    MISSION_PLANNED = "MissionPlanned"
    MISSION_STARTED = "MissionStarted"
    WAYPOINT_REACHED = "WaypointReached"
    MISSION_COMPLETED = "MissionCompleted"
    POSITION_UPDATED = "PositionUpdated"
    TRACK_UPDATED = "TrackUpdated"
    WIND_REPORTED = "WindReported"
    LINK_STATUS = "LinkStatus"
    BATTERY_STATUS = "BatteryStatus"
    GNSS_STATUS = "GnssStatus"
    AUTOPILOT_STATUS = "AutopilotStatus"
    SIMULATION_STARTED = "SimulationStarted"
    SIMULATION_PAUSED = "SimulationPaused"
    SIMULATION_RESUMED = "SimulationResumed"
    SIMULATION_FINISHED = "SimulationFinished"
    SIMULATION_RESET = "SimulationReset"
    INTERACTIVE_MODE_CHANGED = "InteractiveModeChanged"
    FAULT_INJECTED = "FaultInjected"
    FAULT_CLEARED = "FaultCleared"
    INSTRUCTOR_COMMAND = "InstructorCommand"
    DETECTION_RAISED = "DetectionRaised"
    DETECTION_UPDATED = "DetectionUpdated"
    DETECTION_CLEARED = "DetectionCleared"
    DETECTION_ACKNOWLEDGED = "DetectionAcknowledged"
    ANOMALY_DETECTED = "AnomalyDetected"
    ALERT_CLOSED = "AlertClosed"
    ALERT_ENRICHED = "AlertEnriched"
    INCIDENT_UPDATED = "IncidentUpdated"
    INCIDENT_ENRICHED = "IncidentEnriched"
    REPORT_GENERATED = "ReportGenerated"
    OPERATOR_MESSAGE = "OperatorMessage"
    AGENT_REPLY = "AgentReply"
    AGENT_REPLY_CHUNK = "AgentReplyChunk"
    AGENT_ACTIVITY = "AgentActivity"
    AGENT_TOOL_CALL = "AgentToolCall"


class Rule(StrEnum):
    """Reglas del detector."""

    ROUTE_DEVIATION = "ROUTE_DEVIATION"
    SOURCE_DISCREPANCY = "SOURCE_DISCREPANCY"
    SOURCE_SILENT = "SOURCE_SILENT"
    GPS_DEGRADED = "GPS_DEGRADED"
    LINK_ANOMALY = "LINK_ANOMALY"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertPhase(StrEnum):
    """Fase de una alerta (v0.14): `active` mientras el problema sigue; `recovering` cuando el
    GPS ha vuelto tras un engaño o una pérdida y el dron corrige hacia la ruta."""

    ACTIVE = "active"
    RECOVERING = "recovering"


class DecidedBy(StrEnum):
    """Quién decidió una alerta (v0.19): la tabla de decisión del módulo o el LLM del monitor."""

    TABLE = "table"
    LLM = "llm"


class Cause(StrEnum):
    """Causas del diagnóstico (`REPLAY` queda reservada para el futuro)."""

    WIND = "WIND"
    HIJACK = "HIJACK"
    GPS_SPOOFING = "GPS_SPOOFING"
    SENSOR_FAULT = "SENSOR_FAULT"
    GPS_JAMMING = "GPS_JAMMING"
    UNKNOWN = "UNKNOWN"


class AlertStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SUPERSEDED = "superseded"


class IncidentKind(StrEnum):
    """Tipo de incidente del monitor de situación (v1.1). Coincide con las causas de
    `states.jsonl`, más `LINK_LOSS`, `GPS_DEGRADED` y `BATTERY` (sin causa de desviación) y
    `UNDETERMINED` (salida del sistema con confianza baja, no una etiqueta de la verdad)."""

    WIND = "WIND"
    GPS_SPOOFING = "GPS_SPOOFING"
    HIJACK = "HIJACK"
    LINK_LOSS = "LINK_LOSS"
    GPS_DEGRADED = "GPS_DEGRADED"
    DEAD_RECKONING = "DEAD_RECKONING"
    BATTERY = "BATTERY"
    UNDETERMINED = "UNDETERMINED"


class IncidentState(StrEnum):
    """Estado de un incidente (v1.1): un incidente cambia de estado, no se sustituye."""

    OPEN = "open"
    RECOVERING = "recovering"
    CLOSED = "closed"


class IncidentChange(StrEnum):
    """Qué cambió en esta revisión del incidente (v1.1)."""

    OPENED = "opened"
    STATE = "state"
    RENAMED = "renamed"
    SEVERITY = "severity"
    EVIDENCE = "evidence"
    CLOSED = "closed"


class ConfidenceLevel(StrEnum):
    """Confianza en niveles (v1.1): confirmado (≥ 0,9), probable (0,6–0,9), posible (< 0,6)."""

    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    POSSIBLE = "possible"


class EnrichRole(StrEnum):
    """Papel del texto del asistente sobre un incidente (v1.1)."""

    EXPLAIN = "explain"
    HYPOTHESIS = "hypothesis"


class Trend(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class RouteTrend(StrEnum):
    """Si el dron se acerca o se aleja de la ruta en los últimos segundos (v0.17, `now`)."""

    APPROACHING = "approaching"
    MOVING_AWAY = "moving_away"
    STEADY = "steady"


class CompletionReason(StrEnum):
    RETURNED_TO_BASE = "returned_to_base"
    TIMEOUT = "timeout"
    LANDED = "landed"


class PauseReason(StrEnum):
    USER = "user"
    WAITING_AGENT = "waiting_agent"


class FaultMode(StrEnum):
    """Tipo de fallo: `mute` (la fuente no se publica) o `loss` (solo GPS: pérdida de señal)."""

    MUTE = "mute"
    LOSS = "loss"


class FaultOrigin(StrEnum):
    MANUAL = "manual"
    SCENARIO = "scenario"


class GpsFix(StrEnum):
    NONE = "none"
    FIX_2D = "2d"
    FIX_3D = "3d"


class InstructorCommandName(StrEnum):
    """Comandos del instructor (v0.18). Más adelante caben otros sin romper el evento."""

    SET_WIND = "set_wind"
    CANCEL_WIND = "cancel_wind"


class CommandIssuer(StrEnum):
    """Quién emite un comando: el panel, el LLM del instructor (confirmado) o el escenario."""

    PANEL = "panel"
    LLM = "llm"
    SCENARIO = "scenario"


class ConversationId(StrEnum):
    MONITOR = "monitor"
    REPORT = "report"
    INSTRUCTOR = "instructor"


class AgentName(StrEnum):
    MONITOR = "monitor"
    REPORT = "report"
    CHAT_MONITOR = "chat-monitor"
    CHAT_REPORT = "chat-report"
    CHAT_INSTRUCTOR = "chat-instructor"


class ActivityState(StrEnum):
    STARTED = "started"
    FINISHED = "finished"


class ToolCallStatus(StrEnum):
    """Resultado de una llamada a tool (`AgentToolCall`)."""

    OK = "ok"
    ERROR = "error"
    REJECTED = "rejected"
    ABORTED = "aborted"


class LabelType(StrEnum):
    """Tipo de anomalía de `labels.json`."""

    WIND = "wind"
    HIJACK = "hijack"
    GPS_SPOOFING = "gps_spoofing"
    SOURCE_SILENT = "source_silent"
    GPS_LOSS = "gps_loss"
    GPS_DEGRADED = "gps_degraded"  # E6: episodio de degradación del GPS (con fix)
    LINK_DEGRADED = "link_degraded"  # E6: episodio de degradación del enlace


class ClientKind(StrEnum):
    WEB = "web"
    AI_MODULE = "ai-module"


class PlayerStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
