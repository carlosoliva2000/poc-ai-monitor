"""Topics, ids y orígenes (`source`) de cada tipo de evento, y comodines del bus.

Forma del topic: `citadel.pub.evt.<domain>.<routing>.<event>.v1` (`contracts/eventos.md` §3).
"""

import re
from dataclasses import dataclass

from .enums import ClientKind, ConversationId, EventType

NAMESPACE = "citadel"
CLASSIFICATION = "pub"
KIND = "evt"
VERSION = "v1"
TOPIC_PREFIX = f"{NAMESPACE}.{CLASSIFICATION}.{KIND}"

SIM_DOMAIN = "sim"


@dataclass(frozen=True)
class EventSpec:
    """Cómo se publica un tipo de evento. `None` en `routing`/`source`: lo da `conversation_id`."""

    domain: str
    routing: str | None
    id_prefix: str
    source: str | None
    ephemeral: bool = False


_T = EventType
EVENT_SPECS: dict[EventType, EventSpec] = {
    _T.MISSION_PLANNED: EventSpec("air", "d1", "mis", "d1-mission"),
    _T.MISSION_STARTED: EventSpec("air", "d1", "mis", "d1-mission"),
    _T.WAYPOINT_REACHED: EventSpec("air", "d1", "mis", "d1-mission"),
    _T.MISSION_COMPLETED: EventSpec("air", "d1", "mis", "d1-mission"),
    _T.POSITION_UPDATED: EventSpec("air", "d1", "gps", "d1-gps"),
    _T.TRACK_UPDATED: EventSpec("air", "d1", "rad", "radar-1"),
    _T.WIND_REPORTED: EventSpec("env", "zone1", "met", "meteo-1"),
    _T.LINK_STATUS: EventSpec("air", "d1", "lnk", "d1-link"),
    _T.BATTERY_STATUS: EventSpec("air", "d1", "bat", "d1-bat"),
    _T.GNSS_STATUS: EventSpec("air", "d1", "gns", "d1-gnss"),
    _T.AUTOPILOT_STATUS: EventSpec("air", "d1", "apl", "d1-autopilot"),
    _T.SIMULATION_STARTED: EventSpec(SIM_DOMAIN, "player", "plr", "platform-player"),
    _T.SIMULATION_PAUSED: EventSpec(SIM_DOMAIN, "player", "plr", "platform-player"),
    _T.SIMULATION_RESUMED: EventSpec(SIM_DOMAIN, "player", "plr", "platform-player"),
    _T.SIMULATION_FINISHED: EventSpec(SIM_DOMAIN, "player", "plr", "platform-player"),
    _T.SIMULATION_RESET: EventSpec(SIM_DOMAIN, "player", "plr", "platform-player"),
    _T.INTERACTIVE_MODE_CHANGED: EventSpec(SIM_DOMAIN, "player", "plr", "platform-player"),
    _T.FAULT_INJECTED: EventSpec(SIM_DOMAIN, "player", "sim", "platform-player"),
    _T.FAULT_CLEARED: EventSpec(SIM_DOMAIN, "player", "sim", "platform-player"),
    _T.INSTRUCTOR_COMMAND: EventSpec(SIM_DOMAIN, "instructor", "cmd", "platform-player"),
    # v1.4: lo programado en el ejercicio (de `labels.json`), solo para el proceso del instructor
    _T.EXERCISE_INJECTS: EventSpec(SIM_DOMAIN, "instructor", "inj", "platform-player"),
    _T.DETECTION_RAISED: EventSpec("ai", "d1", "det", "ai-detector"),
    _T.DETECTION_UPDATED: EventSpec("ai", "d1", "det", "ai-detector"),
    _T.DETECTION_CLEARED: EventSpec("ai", "d1", "det", "ai-detector"),
    _T.DETECTION_ACKNOWLEDGED: EventSpec("ai", "d1", "ai", "ai-monitor"),
    _T.ANOMALY_DETECTED: EventSpec("ai", "d1", "ai", "ai-monitor"),
    _T.ALERT_CLOSED: EventSpec("ai", "d1", "ai", "ai-monitor"),
    # E6 (v0.19): fuente propia para que ninguna tool de datos lo devuelva (los chats no lo ven)
    _T.ALERT_ENRICHED: EventSpec("ai", "d1", "ai", "ai-enricher"),
    # v1.1: monitor de situación (incidentes) y asistente (su texto, con la fuente de AlertEnriched)
    _T.INCIDENT_UPDATED: EventSpec("ai", "d1", "ai", "ai-monitor"),
    _T.INCIDENT_ENRICHED: EventSpec("ai", "d1", "ai", "ai-enricher"),
    _T.REPORT_GENERATED: EventSpec("ai", "d1", "ai", "ai-report"),
    # v1.4: debriefing del instructor (con la verdad): `ai.instructor`, que el alumno no recibe
    _T.DEBRIEF_GENERATED: EventSpec("ai", "instructor", "ai", "ai-debrief"),
    _T.OPERATOR_MESSAGE: EventSpec("ops", None, "ops", "web-operator"),
    _T.AGENT_REPLY: EventSpec("ai", None, "ai", None),
    _T.AGENT_REPLY_CHUNK: EventSpec("ai", None, "chk", None, ephemeral=True),
    _T.AGENT_ACTIVITY: EventSpec("ai", "agent", "act", "ai-module", ephemeral=True),
    _T.AGENT_TOOL_CALL: EventSpec("ai", "agent", "tcl", "ai-module", ephemeral=True),
}

EPHEMERAL_TYPES: frozenset[EventType] = frozenset(
    t for t, spec in EVENT_SPECS.items() if spec.ephemeral
)

# `source` del sobre de las respuestas de cada chat.
CHAT_SOURCES: dict[ConversationId, str] = {
    ConversationId.MONITOR: "ai-chat-monitor",
    ConversationId.REPORT: "ai-chat-report",
    ConversationId.INSTRUCTOR: "ai-chat-instructor",
}

# `source` del sobre de `OperatorMessage` cuando no es el del operador: el chat del instructor no
# comparte fuente con el del monitor para que `get_events` (`operator`) nunca lo devuelva.
OPERATOR_SOURCES: dict[ConversationId, str] = {ConversationId.INSTRUCTOR: "web-instructor"}

# Dominios en los que puede publicar cada cliente del WebSocket.
CLIENT_DOMAINS: dict[ClientKind, frozenset[str]] = {
    ClientKind.WEB: frozenset({"ops"}),
    ClientKind.AI_MODULE: frozenset({"ai"}),
}

_ASSETS: dict[tuple[str, str], str] = {
    ("air", "d1"): "d1",
    ("ai", "d1"): "d1",
    ("env", "zone1"): "zone1",
}


def routing_for(event_type: EventType, conversation_id: ConversationId | None = None) -> str:
    """Segmento `routing` del topic; para el chat lo da `conversation_id`."""
    routing = EVENT_SPECS[event_type].routing
    if routing is not None:
        return routing
    if conversation_id is None:
        raise ValueError(f"{event_type} needs conversation_id for its topic")
    return conversation_id.value


def source_for(event_type: EventType, conversation_id: ConversationId | None = None) -> str:
    """`source` del sobre; para `AgentReply`/`AgentReplyChunk` lo da `conversation_id`."""
    source = EVENT_SPECS[event_type].source
    if event_type == EventType.OPERATOR_MESSAGE and conversation_id in OPERATOR_SOURCES:
        return OPERATOR_SOURCES[conversation_id]
    if source is not None:
        return source
    if conversation_id is None:
        raise ValueError(f"{event_type} needs conversation_id for its source")
    return CHAT_SOURCES[conversation_id]


def asset_for(domain: str, routing: str) -> str | None:
    """Valor de `asset` según el topic: `d1`, `zone1` o `None`."""
    return _ASSETS.get((domain, routing))


def topic_for(event_type: EventType, conversation_id: ConversationId | None = None) -> str:
    """Topic completo de un tipo de evento."""
    spec = EVENT_SPECS[event_type]
    routing = routing_for(event_type, conversation_id)
    return f"{TOPIC_PREFIX}.{spec.domain}.{routing}.{event_type.value}.{VERSION}"


def topic_domain(topic: str) -> str | None:
    """Dominio (cuarto segmento) de un topic, o `None` si no tiene la forma esperada."""
    parts = topic.split(".")
    return parts[3] if len(parts) == 7 else None


def matches_id_prefix(event_id: str, event_type: EventType) -> bool:
    """`True` si `event_id` es `<prefijo>-<número>` con el prefijo del tipo, o (v1.4)
    `<prefijo>-<letra>-<número>` con la etiqueta de un proceso del módulo de IA (`ai-a-0001`)."""
    return (
        re.fullmatch(rf"{EVENT_SPECS[event_type].id_prefix}(?:-[a-z])?-\d+", event_id) is not None
    )


def client_can_publish(client: ClientKind, topic: str) -> bool:
    """Web solo publica en `ops`; el módulo de IA, solo en `ai`."""
    return topic_domain(topic) in CLIENT_DOMAINS[client]


def validate_pattern(pattern: str) -> None:
    """Comprueba un patrón de suscripción: `*` y `>` solo como segmento entero, `>` el último."""
    segments = pattern.split(".")
    for i, seg in enumerate(segments):
        if not seg:
            raise ValueError(f"pattern with an empty segment: {pattern!r}")
        if seg != "*" and seg != ">" and ("*" in seg or ">" in seg):
            raise ValueError(f"wildcards apply to whole segments: {pattern!r}")
        if seg == ">" and i != len(segments) - 1:
            raise ValueError(f"'>' can only be the last segment: {pattern!r}")


def topic_matches(pattern: str, topic: str) -> bool:
    """Comodines al estilo NATS: `*` = un segmento, `>` = uno o más segmentos restantes."""
    pat = pattern.split(".")
    top = topic.split(".")
    for i, seg in enumerate(pat):
        if seg == ">":
            return i == len(pat) - 1 and len(top) > i
        if i >= len(top) or (seg != "*" and seg != top[i]):
            return False
    return len(pat) == len(top)
