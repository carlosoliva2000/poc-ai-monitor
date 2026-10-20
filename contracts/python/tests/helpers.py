"""Utilidades de las pruebas: construye sobres válidos."""

from typing import Any

from poc_contracts.enums import ConversationId, EventType
from poc_contracts.topics import EVENT_SPECS, asset_for, source_for, topic_for

POSITION = {
    "x": 512.3, "y": 140.8, "alt_m": 60.2, "speed_mps": 15.1,
    "heading_deg": 81.0, "fix": "3d", "sats": 14, "hdop": 0.8,
}  # fmt: skip


def draft(
    event_type: EventType,
    payload: dict[str, Any],
    event_id: str,
    conversation: ConversationId | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Evento sin `seq` ni `ingestion_time` con topic, source y asset correctos."""
    spec = EVENT_SPECS[event_type]
    topic = topic_for(event_type, conversation)
    event: dict[str, Any] = {
        "event_id": event_id,
        "topic": topic,
        "type": event_type.value,
        "source": source_for(event_type, conversation),
        "asset": asset_for(spec.domain, topic.split(".")[4]),
        "sim_time": 61.0,
        "event_time": "2026-10-20T10:01:01Z",
        "causation_id": None,
        "ephemeral": spec.ephemeral,
        "payload": payload,
    }
    event.update(overrides)
    return event


def position_draft(**overrides: Any) -> dict[str, Any]:
    """`PositionUpdated` válido, con los campos indicados sustituidos."""
    event = draft(EventType.POSITION_UPDATED, POSITION, "gps-000061")
    event.update(overrides)
    return event
