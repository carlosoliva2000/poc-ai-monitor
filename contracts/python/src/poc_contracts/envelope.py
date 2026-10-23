"""Sobre común a todos los eventos (`contracts/eventos.md` §2)."""

from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from .enums import ConversationId, EventType
from .payloads import PAYLOAD_MODELS, Payload
from .topics import (
    EVENT_SPECS,
    asset_for,
    matches_id_prefix,
    source_for,
    topic_for,
)

# ISO 8601 UTC con `Z`, con o sin fracción de segundo.
IsoUtc = Annotated[
    str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
]


class EventDraft(BaseModel):
    """Evento tal como lo escribe el generador o lo publica un cliente: sin `seq` ni
    `ingestion_time`, que pone el bus."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    topic: str
    type: EventType
    source: str
    asset: str | None = None
    sim_time: float = Field(ge=0)
    event_time: IsoUtc
    causation_id: str | None = None
    ephemeral: bool = False
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _check_consistency(self) -> "EventDraft":
        """El payload, el topic, el `source`, el `asset`, el id y `ephemeral` cuadran con `type`."""
        model = PAYLOAD_MODELS[self.type]
        try:
            parsed = model.model_validate(self.payload)
        except ValidationError as exc:
            raise ValueError(f"invalid payload for {self.type.value}: {exc}") from exc

        raw_conversation = getattr(parsed, "conversation_id", None)
        conversation = ConversationId(raw_conversation) if raw_conversation else None
        spec = EVENT_SPECS[self.type]

        expected_topic = topic_for(self.type, conversation)
        if self.topic != expected_topic:
            raise ValueError(f"expected topic {expected_topic!r}, received {self.topic!r}")
        expected_source = source_for(self.type, conversation)
        if self.source != expected_source:
            raise ValueError(f"expected source {expected_source!r}, received {self.source!r}")
        routing = expected_topic.split(".")[4]
        expected_asset = asset_for(spec.domain, routing)
        if self.asset != expected_asset:
            raise ValueError(f"expected asset {expected_asset!r}, received {self.asset!r}")
        if not matches_id_prefix(self.event_id, self.type):
            raise ValueError(
                f"event_id {self.event_id!r} lacks the prefix {spec.id_prefix!r} "
                f"of {self.type.value}"
            )
        if self.ephemeral != spec.ephemeral:
            raise ValueError(f"ephemeral must be {spec.ephemeral} in {self.type.value}")
        return self

    def typed_payload(self) -> Payload:
        """El payload como modelo de su tipo."""
        return PAYLOAD_MODELS[self.type].model_validate(self.payload)


class Envelope(EventDraft):
    """Evento ya publicado: el bus añade `seq` e `ingestion_time`."""

    seq: int = Field(ge=0)
    ingestion_time: IsoUtc
