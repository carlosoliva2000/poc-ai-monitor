"""Construcción de los eventos que publica el módulo de IA (`ai-monitor`, `ai-report`, chats).

El `event_time` es `t0 + sim_time`; `t0` se deduce de cualquier evento recibido (`event_time -
sim_time`), igual que hace el detector.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import PAYLOAD_MODELS
from poc_contracts.topics import EVENT_SPECS, asset_for, routing_for, source_for, topic_for

from .ids import IdAllocator

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def format_t(sim_time: float) -> str:
    """`T+mm:ss` del instante simulado."""
    total = int(sim_time)
    return f"T+{total // 60:02d}:{total % 60:02d}"


class EventFactory:
    def __init__(self, ids: IdAllocator) -> None:
        self.ids = ids
        self._t0 = EPOCH

    def observe(self, event: EventDraft) -> None:
        """Aprende `t0` de un evento recibido."""
        moment = datetime.fromisoformat(event.event_time.replace("Z", "+00:00"))
        self._t0 = moment - timedelta(seconds=event.sim_time)

    def event_time(self, sim_time: float) -> str:
        moment = self._t0 + timedelta(seconds=sim_time)
        if moment.microsecond == 0:
            return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"

    def make(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        sim_time: float,
        causation_id: str | None = None,
        conversation: ConversationId | None = None,
        event_id: str | None = None,
    ) -> EventDraft:
        """Evento con id nuevo (`ai-…`, o el dado), validado contra el modelo de su payload."""
        spec = EVENT_SPECS[event_type]
        PAYLOAD_MODELS[event_type].model_validate(payload)
        return EventDraft(
            event_id=event_id or self.ids.next(spec.id_prefix),
            topic=topic_for(event_type, conversation),
            type=event_type,
            source=source_for(event_type, conversation),
            asset=asset_for(spec.domain, routing_for(event_type, conversation)),
            sim_time=sim_time,
            event_time=self.event_time(sim_time),
            causation_id=causation_id,
            ephemeral=spec.ephemeral,
            payload=payload,
        )
