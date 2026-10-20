"""Enumerados cerrados de `contracts/eventos.md`."""

from enum import StrEnum


class SensorSource(StrEnum):
    """Fuentes que se pueden silenciar y en las que puede saltar `SOURCE_SILENT`."""

    GPS = "gps"
    RADAR = "radar"
    METEO = "meteo"
    LINK = "link"
    BATTERY = "battery"


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
    SIMULATION_STARTED = "SimulationStarted"
    SIMULATION_PAUSED = "SimulationPaused"
    SIMULATION_RESUMED = "SimulationResumed"
    SIMULATION_FINISHED = "SimulationFinished"
    SIMULATION_RESET = "SimulationReset"
    INTERACTIVE_MODE_CHANGED = "InteractiveModeChanged"
    FAULT_INJECTED = "FaultInjected"
    FAULT_CLEARED = "FaultCleared"
    DETECTION_RAISED = "DetectionRaised"
    DETECTION_UPDATED = "DetectionUpdated"
    DETECTION_CLEARED = "DetectionCleared"
    ANOMALY_DETECTED = "AnomalyDetected"
    ALERT_CLOSED = "AlertClosed"
    REPORT_GENERATED = "ReportGenerated"
    OPERATOR_MESSAGE = "OperatorMessage"
    AGENT_REPLY = "AgentReply"
    AGENT_REPLY_CHUNK = "AgentReplyChunk"
    AGENT_ACTIVITY = "AgentActivity"


class Rule(StrEnum):
    """Reglas del detector."""

    ROUTE_DEVIATION = "ROUTE_DEVIATION"
    SOURCE_DISCREPANCY = "SOURCE_DISCREPANCY"
    SOURCE_SILENT = "SOURCE_SILENT"
    GPS_DEGRADED = "GPS_DEGRADED"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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


class Trend(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class CompletionReason(StrEnum):
    RETURNED_TO_BASE = "returned_to_base"
    TIMEOUT = "timeout"


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


class ConversationId(StrEnum):
    MONITOR = "monitor"
    REPORT = "report"


class AgentName(StrEnum):
    MONITOR = "monitor"
    REPORT = "report"
    CHAT_MONITOR = "chat-monitor"
    CHAT_REPORT = "chat-report"


class ActivityState(StrEnum):
    STARTED = "started"
    FINISHED = "finished"


class LabelType(StrEnum):
    """Tipo de anomalía de `labels.json`."""

    WIND = "wind"
    HIJACK = "hijack"
    GPS_SPOOFING = "gps_spoofing"
    SOURCE_SILENT = "source_silent"
    GPS_LOSS = "gps_loss"


class ClientKind(StrEnum):
    WEB = "web"
    AI_MODULE = "ai-module"


class PlayerStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
