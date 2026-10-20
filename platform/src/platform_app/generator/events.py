"""Sobres de los eventos del escenario: id, topic, `source` y hora."""

from datetime import UTC, datetime, timedelta

from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.scenario import ScenarioConfig
from poc_contracts.topics import EVENT_SPECS, asset_for, routing_for, source_for, topic_for

# Anchura mínima del número del id: gps-000061, rad-000042, met-0008…
_ID_WIDTH = {"gps": 6, "rad": 6}


def event_time(t0: str, sim_time: float) -> str:
    """`t0 + sim_time` en ISO 8601 UTC; con milisegundos solo si hacen falta."""
    base = datetime.fromisoformat(t0).astimezone(UTC) + timedelta(seconds=sim_time)
    if base.microsecond == 0:
        return base.strftime("%Y-%m-%dT%H:%M:%SZ")
    return base.strftime("%Y-%m-%dT%H:%M:%S.") + f"{base.microsecond // 1000:03d}Z"


def make_event(
    config: ScenarioConfig, event_type: EventType, sim_time: float, number: int, payload: dict
) -> EventDraft:
    """Evento del generador (sin `seq` ni `ingestion_time`), validado."""
    spec = EVENT_SPECS[event_type]
    width = _ID_WIDTH.get(spec.id_prefix, 4)
    return EventDraft(
        event_id=f"{spec.id_prefix}-{number:0{width}d}",
        topic=topic_for(event_type),
        type=event_type,
        source=source_for(event_type),
        asset=asset_for(spec.domain, routing_for(event_type)),
        sim_time=sim_time,
        event_time=event_time(config.t0, sim_time),
        payload=payload,
    )
