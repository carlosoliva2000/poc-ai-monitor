"""Topics y comodines (`contracts/eventos.md` §3)."""

import pytest

from poc_contracts.enums import ClientKind, ConversationId, EventType
from poc_contracts.topics import (
    EPHEMERAL_TYPES,
    EVENT_SPECS,
    client_can_publish,
    topic_for,
    topic_matches,
    validate_pattern,
)

POSITION = "citadel.pub.evt.air.d1.PositionUpdated.v1"
DETECTION = "citadel.pub.evt.ai.d1.DetectionRaised.v1"


@pytest.mark.parametrize(
    ("pattern", "topic", "expected"),
    [
        ("citadel.pub.evt.>", POSITION, True),
        ("citadel.pub.evt.air.d1.>", POSITION, True),
        ("citadel.pub.evt.air.d1.>", DETECTION, False),
        ("citadel.pub.evt.ai.d1.>", DETECTION, True),
        ("citadel.pub.evt.ai.d1.*.v1", DETECTION, True),
        ("citadel.pub.evt.ai.d1.*", DETECTION, False),  # el topic lleva `.v1`: sobra un segmento
        ("citadel.*.evt.ai.d1.*.v1", DETECTION, True),
        ("citadel.pub.evt.air.d1.PositionUpdated.v1", POSITION, True),
        ("citadel.pub.evt.air.d1.PositionUpdated.v1.>", POSITION, False),  # `>` exige algo más
        ("citadel.pub.evt.air.d1", POSITION, False),
        (">", POSITION, True),
    ],
)
def test_topic_matches(pattern: str, topic: str, expected: bool) -> None:
    assert topic_matches(pattern, topic) is expected


@pytest.mark.parametrize(
    "pattern", ["citadel.*.evt.ai.d1.Detection*", "citadel.>.evt", "citadel..evt", "a.b>"]
)
def test_invalid_patterns(pattern: str) -> None:
    with pytest.raises(ValueError):
        validate_pattern(pattern)


def test_every_event_type_has_a_spec_and_topic() -> None:
    assert set(EVENT_SPECS) == set(EventType)
    for event_type, spec in EVENT_SPECS.items():
        conversation = ConversationId.MONITOR if spec.routing is None else None
        topic = topic_for(event_type, conversation)
        assert topic.startswith("citadel.pub.evt.") and topic.endswith(f"{event_type.value}.v1")


def test_ephemeral_and_client_domains() -> None:
    assert {
        EventType.AGENT_REPLY_CHUNK,
        EventType.AGENT_ACTIVITY,
        EventType.AGENT_TOOL_CALL,
    } == EPHEMERAL_TYPES
    assert client_can_publish(ClientKind.AI_MODULE, DETECTION)
    assert not client_can_publish(ClientKind.AI_MODULE, POSITION)
    assert client_can_publish(ClientKind.WEB, "citadel.pub.evt.ops.monitor.OperatorMessage.v1")
    assert not client_can_publish(ClientKind.WEB, DETECTION)
    assert not client_can_publish(ClientKind.WEB, "citadel.pub.evt.sim.player.FaultInjected.v1")


def test_ids_of_the_ai_module_may_carry_the_tag_of_their_process() -> None:
    """v1.4: `ai-0001` sigue valiendo y `ai-a-0001` (una letra minúscula: el proceso) también;
    así los procesos del módulo que comparten bus no se pisan los ids."""
    from poc_contracts.enums import EventType
    from poc_contracts.topics import matches_id_prefix

    for good in ("ai-0001", "ai-m-0001", "ai-a-12345", "ai-i-0007"):
        assert matches_id_prefix(good, EventType.INCIDENT_ENRICHED), good
    assert matches_id_prefix("act-a-0001", EventType.AGENT_ACTIVITY)
    assert matches_id_prefix("chk-i-0001", EventType.AGENT_REPLY_CHUNK)
    for bad in ("ai-aa-0001", "ai-A-0001", "ai-a-", "ai--0001", "gps-a-0001"):
        assert not matches_id_prefix(bad, EventType.INCIDENT_ENRICHED), bad
