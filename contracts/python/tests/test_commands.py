"""Comandos del instructor (v0.18): validación, evento, mensaje del WebSocket y escenario."""

import pytest
from pydantic import TypeAdapter, ValidationError

from helpers import draft
from poc_contracts.commands import InstructorControl, ScheduledCommand, WindCommandParams
from poc_contracts.enums import ClientKind, ConversationId, EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import AgentReply, OperatorMessage
from poc_contracts.scenario import ScenarioConfig
from poc_contracts.topics import client_can_publish, topic_for
from poc_contracts.ws import ClientMessage

PARAMS = {"from_deg": 45.0, "speed_mps": 8.0, "ramp_s": 10.0, "duration_s": 60.0}
EVENT = {"command": "set_wind", "params": PARAMS, "issued_by": "panel", "text": None}


def test_instructor_command_event_is_a_sim_event_of_the_platform() -> None:
    event = EventDraft.model_validate(draft(EventType.INSTRUCTOR_COMMAND, EVENT, "cmd-0001"))
    assert event.topic == "citadel.pub.evt.sim.instructor.InstructorCommand.v1"
    assert event.source == "platform-player" and event.asset is None and not event.ephemeral
    # el módulo de IA solo publica en `ai` y la web en `ops`: nadie puede publicarlo por el bus
    assert not client_can_publish(ClientKind.WEB, event.topic)
    assert not client_can_publish(ClientKind.AI_MODULE, event.topic)
    with pytest.raises(ValidationError):
        EventDraft.model_validate(draft(EventType.INSTRUCTOR_COMMAND, EVENT, "sim-0001"))


def test_wind_command_ranges() -> None:
    assert WindCommandParams.model_validate({**PARAMS, "speed_mps": 40.0})
    for bad in ({"speed_mps": 40.1}, {"ramp_s": 0}, {"duration_s": 1801}):
        with pytest.raises(ValidationError):
            WindCommandParams.model_validate({**PARAMS, **bad})
    with pytest.raises(ValidationError):  # todos los campos son obligatorios
        WindCommandParams.model_validate({"from_deg": 0.0, "speed_mps": 1.0})
    assert WindCommandParams.model_validate({**PARAMS, "from_deg": 360.0}).from_deg == 0.0
    assert WindCommandParams.model_validate({**PARAMS, "duration_s": None}).duration_s is None


def test_control_instructor_message() -> None:
    adapter = TypeAdapter(ClientMessage)
    ok = {"op": "control", "action": "instructor", "value": EVENT}
    assert adapter.validate_python(ok).value.command.value == "set_wind"  # type: ignore[union-attr]
    cancel = {"command": "cancel_wind", "params": None, "issued_by": "panel", "text": None}
    assert adapter.validate_python({**ok, "value": cancel})
    for bad in (
        {**EVENT, "issued_by": "scenario"},
        {**EVENT, "issued_by": "llm"},  # sin la frase original
        {**EVENT, "command": "cancel_wind"},  # cancelar no lleva parámetros
        {**EVENT, "extra": 1},
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python({**ok, "value": bad})
    assert InstructorControl.model_validate({**EVENT, "issued_by": "llm", "text": "north 8 m/s"})


def test_instructor_chat_uses_its_own_topics_and_sources() -> None:
    conv = ConversationId.INSTRUCTOR
    assert topic_for(EventType.OPERATOR_MESSAGE, conv).endswith("ops.instructor.OperatorMessage.v1")
    assert topic_for(EventType.AGENT_REPLY, conv).endswith("ai.instructor.AgentReply.v1")
    message = draft(
        EventType.OPERATOR_MESSAGE, {"conversation_id": "instructor", "text": "x"}, "ops-0001", conv
    )
    assert (
        message["source"] == "web-instructor"
    )  # ni `get_events` (`operator`) ni el monitor lo ven
    assert EventDraft.model_validate(message)
    monitor = draft(
        EventType.OPERATOR_MESSAGE,
        {"conversation_id": "monitor", "text": "x"},
        "ops-0002",
        ConversationId.MONITOR,
    )
    assert monitor["source"] == "web-operator"
    reply = draft(
        EventType.AGENT_REPLY,
        {"conversation_id": "instructor", "reply_to": "ops-0001", "text": "ok", "tool_calls": []},
        "ai-0001",
        conv,
    )
    assert reply["source"] == "ai-chat-instructor" and EventDraft.model_validate(reply)


def test_chat_payloads_stay_backwards_compatible() -> None:
    assert (
        OperatorMessage.model_validate({"conversation_id": "monitor", "text": "hi"}).context is None
    )
    reply = AgentReply.model_validate(
        {"conversation_id": "monitor", "reply_to": "ops-1", "text": "x", "tool_calls": []}
    )
    assert reply.proposal is None


def test_scheduled_commands_in_the_scenario() -> None:
    from pathlib import Path

    import yaml

    raw = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "scenarios" / "nominal.yaml").read_text()
    )
    assert ScenarioConfig.model_validate(raw).commands == []  # opcional
    raw["commands"] = [{"at_s": 95.0, "command": "set_wind", "params": PARAMS}]
    config = ScenarioConfig.model_validate(raw)
    assert config.commands == [ScheduledCommand(at_s=95.0, command="set_wind", params=PARAMS)]
    raw["commands"] = [{"at_s": 95.0, "command": "set_wind", "params": None}]
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(raw)
