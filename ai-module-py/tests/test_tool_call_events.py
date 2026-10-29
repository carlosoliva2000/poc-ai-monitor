"""`AgentToolCall`: cada llamada a tool se publica (efímera, recortada) solo para la web y nadie
del módulo la ve ni la usa; apagada, no se publica nada y el resto no cambia."""

from pathlib import Path
from typing import Any

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    call,
    make_runtime,
    reset_ids,
    run,
    text_response,
    tool_response,
)

from ai_module.agent.assets import Assets
from ai_module.agent.engine import AbortInvocation, AgentEngine, ToolCallRecord
from ai_module.agent.trace import InvocationTrace
from ai_module.chat import Chat
from ai_module.detector import Detector
from ai_module.module import AiModule
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import Envelope
from poc_contracts.topics import EPHEMERAL_TYPES

ASSETS = Assets()
CONFIG = ASSETS.agent("monitor")


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def question(number: int = 1) -> Envelope:
    return Envelope(
        event_id=f"ops-{number:04d}",
        topic="citadel.pub.evt.ops.monitor.OperatorMessage.v1",
        type=EventType.OPERATOR_MESSAGE,
        source="web-operator",
        asset=None,
        seq=number,
        sim_time=50.0,
        event_time="2026-10-20T10:00:50Z",
        ingestion_time="2026-10-20T10:00:50.000Z",
        payload={"conversation_id": "monitor", "text": "¿alertas?"},
    )


def tool_calls_of(published: list) -> list:
    return [e for e in published if e.type == EventType.AGENT_TOOL_CALL]


def engine_records(execute, script: Script) -> list[ToolCallRecord]:
    records: list[ToolCallRecord] = []

    async def listener(record: ToolCallRecord) -> None:
        records.append(record)

    engine = AgentEngine(FakeLlm(script), CONFIG, ASSETS.tool_schemas(CONFIG.active_tools), execute)
    trace = InvocationTrace(invocation_id="inv-1", agent="monitor")
    run(engine.run([{"role": "user", "content": "hola"}], trace, on_tool_call=listener))
    return records


def test_engine_reports_ok_error_rejected_and_aborted_in_order() -> None:
    async def execute(name: str, args: dict[str, Any]) -> Any:
        if name == "get_my_alerts":
            return {"ok": False, "errors": ["bad cause", "no evidence"]}
        if name == "acknowledge_detection":
            raise AbortInvocation("repeated rejection")
        return {"events": []}

    script = Script(
        tool_response(call("get_events", source="gps"), call("get_my_alerts")),
        tool_response(call("hackear_dron")),
        tool_response(call("acknowledge_detection")),
    )
    records = engine_records(execute, script)
    assert [(r.index, r.iteration, r.name, r.status) for r in records] == [
        (1, 1, "get_events", "ok"),
        (2, 1, "get_my_alerts", "rejected"),
        (3, 2, "hackear_dron", "error"),
        (4, 3, "acknowledge_detection", "aborted"),
    ]
    assert records[0].content == '{"events":[]}' and records[0].error is None
    assert records[1].error == "bad cause; no evidence"
    assert records[3].content is None and records[3].error == "repeated rejection"


def test_chat_publishes_one_ephemeral_event_per_call_linked_to_the_question(
    tmp_path: Path,
) -> None:
    llm = FakeLlm(Script(tool_response(call("get_my_alerts")), text_response("Nada")))
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_my_alerts": {"alerts": []}}))
    rt.assets._raw.setdefault("chat", {})["tools_enabled"] = True  # chat con tools
    run(Chat(rt, ConversationId.MONITOR).answer(question()))
    [event] = tool_calls_of(published)
    assert event.ephemeral and event.event_id == "tcl-0001" and event.source == "ai-module"
    assert event.topic.endswith("ai.agent.AgentToolCall.v1") and event.causation_id == "ops-0001"
    assert event.payload["agent"] == "chat-monitor" and event.payload["tool"] == "get_my_alerts"
    assert (event.payload["index"], event.payload["iteration"]) == (1, 1)
    assert event.payload["status"] == "ok" and event.payload["result"] == '{"alerts":[]}'
    # la respuesta no cambia: sigue llevando solo los nombres
    [reply] = [e for e in published if e.type == EventType.AGENT_REPLY]
    assert reply.payload["tool_calls"] == ["get_my_alerts"]
    # y su id no da saltos en los `ai-`
    assert reply.event_id == "ai-0001"


def test_arguments_and_result_are_cut_for_the_web_only() -> None:
    from ai_module.runtime import TOOL_CALL_ARGUMENTS_CHARS, TOOL_CALL_RESULT_CHARS

    assert (TOOL_CALL_ARGUMENTS_CHARS, TOOL_CALL_RESULT_CHARS) == (1000, 2000)


def test_long_results_are_cut_and_marked(tmp_path: Path) -> None:
    llm = FakeLlm(Script(tool_response(call("get_my_alerts")), text_response("ok")))
    big = {"alerts": [], "pad": "x" * 3000}
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_my_alerts": big}))
    rt.assets._raw.setdefault("chat", {})["tools_enabled"] = True  # chat con tools
    run(Chat(rt, ConversationId.MONITOR).answer(question()))
    [event] = tool_calls_of(published)
    assert len(event.payload["result"]) == 2000 and event.payload["truncated"] is True


def test_nothing_is_published_when_switched_off(tmp_path: Path) -> None:
    llm = FakeLlm(Script(tool_response(call("get_my_alerts")), text_response("ok")))
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_my_alerts": {"alerts": []}}))
    rt.assets._raw.setdefault("chat", {})["tools_enabled"] = True  # chat con tools
    rt.tool_call_events = False
    run(Chat(rt, ConversationId.MONITOR).answer(question()))
    assert tool_calls_of(published) == []
    assert [e.payload["tool_calls"] for e in published if e.type == EventType.AGENT_REPLY] == [
        ["get_my_alerts"]
    ]


def test_the_module_ignores_them_when_they_come_back_from_the_bus(tmp_path: Path) -> None:
    llm = FakeLlm(Script(tool_response(call("get_my_alerts")), text_response("ok")))
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_my_alerts": {"alerts": []}}))
    rt.assets._raw.setdefault("chat", {})["tools_enabled"] = True  # chat con tools
    run(Chat(rt, ConversationId.MONITOR).answer(question()))
    [draft] = tool_calls_of(published)
    envelope = Envelope(
        **{**draft.model_dump(), "sim_time": 999.0},
        seq=7,
        ingestion_time="2026-10-20T10:00:50.000Z",
    )
    module = AiModule(rt, Detector(), with_agents=False)
    before = rt.clock.now()
    run(module.handle_event(envelope))
    assert rt.clock.now() == before  # ni siquiera mueve el reloj
    assert rt.index.get("tcl-0001") is None  # no puede ser evidencia de una alerta


def test_tool_call_events_are_ephemeral_by_contract() -> None:
    assert EventType.AGENT_TOOL_CALL in EPHEMERAL_TYPES
