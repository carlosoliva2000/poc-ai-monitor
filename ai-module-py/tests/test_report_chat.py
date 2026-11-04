"""Informe y chats con un LLM falso: informe mínimo marcado, chat en su propia tarea,
historial de 12 mensajes, texto fijo antes del informe y streaming con trozos efímeros."""

import asyncio
from pathlib import Path

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    call,
    detection_event,
    make_runtime,
    reset_ids,
    run,
    text_response,
    tool_response,
)
from test_monitor_state import alert

from ai_module.agent.assets import Assets
from ai_module.chat import Chat
from ai_module.monitor import Monitor
from ai_module.report import ReportAgent
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import Envelope

SUMMARY = {
    "mission_id": "T", "duration_s": 100.0, "mission_completed": True,
    "completion_reason": "returned_to_base", "distance_m": {"gps": 1.0, "radar": 1.0},
    "waypoints_planned": [], "waypoints_reached": [],
    "detections_by_rule": {"ROUTE_DEVIATION": 1}, "alerts_by_cause": {"WIND": 1},
    "alerts_open": 1, "alerts_closed": 0,
}  # fmt: skip


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def operator_message(conversation: str, text: str, number: int = 1) -> Envelope:
    event_type = EventType.OPERATOR_MESSAGE
    return Envelope(
        event_id=f"ops-{number:04d}",
        topic=f"citadel.pub.evt.ops.{conversation}.OperatorMessage.v1",
        type=event_type,
        source="web-operator",
        asset=None,
        seq=number,
        sim_time=50.0,
        event_time="2026-10-20T10:00:50Z",
        ingestion_time="2026-10-20T10:00:50.000Z",
        payload={"conversation_id": conversation, "text": text},
    )


def of_type(published: list, event_type: EventType) -> list:
    return [e for e in published if e.type == event_type]


# --- Informe -----------------------------------------------------------------------------------


NARRATIVE = """## Summary
El dron voló con viento.

## What was seen
### A1
La desviación creció hasta 40 m con viento notable.

## Recommendations
1. Revisar el viento antes de despegar.
"""

ANNEX = """## Assessment
- **Support:** respaldada por las comprobaciones, pero tardó.

## Technical recommendations
1. Reducir el retraso del monitor.
"""

LEGACY_NARRATIVE = """## Resumen
El dron voló con viento.

## Qué se vio
### A1
La desviación creció hasta 40 m con viento notable.

## Valoración del monitor
Respaldada por las comprobaciones, pero tardó.

## Recomendaciones
1. Revisar el viento antes de despegar.
"""

FROZEN = Path(__file__).resolve().parents[2] / "agent-assets-v13"


def windy_state(rt) -> None:
    rt.set_run("wind", "20261021-000000")
    rt.state.apply(detection_event("raised", "det-1", 5.0))
    rt.state.apply(alert("ai-0001", ["det-1"], cause="WIND", t=6.0))
    rt.state.apply(alert("ai-0002", ["det-1"], cause="WIND", supersedes="ai-0001", t=20.0))
    rt.clock.observe(100.0)


def test_mission_report_and_annex_are_two_calls_in_one_report(tmp_path: Path) -> None:
    llm = FakeLlm(Script(text_response(NARRATIVE), text_response(ANNEX)))
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_flight_summary": SUMMARY}))
    windy_state(rt)
    markdown = run(ReportAgent(rt, Monitor(rt)).generate("wind", "20261021-000000", "plr-0009"))
    # los hechos son del módulo; la narrativa, del LLM, en su sitio
    assert markdown.startswith("# Mission report T\n\n**Scenario:** wind · **Duration:** 01:40")
    assert "## Summary\n\nEl dron voló con viento." in markdown
    assert "### A1 · Wind (high, confidence 0.8)" in markdown
    assert "first alert at T+00:06." in markdown and "diagnosis delay" not in markdown
    assert "**Last alert:** ai-0002 at T+00:20" in markdown
    assert "- **What was seen:** La desviación creció hasta 40 m con viento notable." in markdown
    assert "- **Status:** OPEN at the end." in markdown
    # la misión termina con las recomendaciones operativas; el anexo, lo último
    head, annex = markdown.split("## Annex: monitor self-assessment\n\n")
    assert "1. Revisar el viento antes de despegar." in head and "## Limitations" in head
    assert "Monitor assessment" not in head and "Monitor figures" not in head
    assert annex.startswith("**Monitor figures** (written by the module): 0 invocations")
    assert "### Assessment\n\n- **Support:** respaldada por las comprobaciones" in annex
    assert "### Technical recommendations\n\n1. Reducir el retraso del monitor." in annex
    [event] = of_type(published, EventType.REPORT_GENERATED)
    assert event.payload == {"run_id": "20261021-000000", "markdown": markdown, "alerts_count": 1}
    assert event.source == "ai-report" and event.causation_id == "plr-0009"
    assert (tmp_path / "wind" / "20261021-000000" / "informe.md").read_text() == markdown + "\n"
    # dos llamadas sin tools, dos trazas del agente `report`, una sola actividad
    assert len(llm.requests) == 2 and all(r["tools"] == [] for r in llm.requests)
    assert [r["agent"] for r in rt.trace.records] == ["report", "report"]
    assert not any(r["fallback"] for r in rt.trace.records)
    assert llm.requests[0]["sampling"]["temperature"] == 0.7
    system, user = (m["content"] for m in llm.requests[0]["messages"])
    assert "## What was seen" in system and "<<" not in system and "<<" not in user
    assert '"mission_id":"T"' in user and "MSN" not in user
    assert "### A1 · Wind" in user and "Monitor ai-0002" in user and "OPEN at the end" in user
    # la misión no recibe retrasos, rechazos ni ayudas, ni las horas del monitor
    assert "Guardrail rejections" not in user and "Active model aids" not in user
    assert "first alert at" not in user and "Monitor ai-0002 at" not in user
    annex_system, annex_user = (m["content"] for m in llm.requests[1]["messages"])
    assert "self-assessment" in annex_system and "<<" not in annex_system + annex_user
    assert "### Guardrail rejections" in annex_user and "### Active model aids" in annex_user
    assert "first alert at T+00:06" in annex_user and "Monitor ai-0002 at T+00:20" in annex_user
    assert [e.payload["state"] for e in of_type(published, EventType.AGENT_ACTIVITY)] == [
        "started", "finished",
    ]  # fmt: skip


def test_a_failed_annex_leaves_the_mission_report_whole(tmp_path: Path) -> None:
    llm = FakeLlm(Script(text_response(NARRATIVE), RuntimeError("caído")))
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_flight_summary": SUMMARY}))
    windy_state(rt)
    markdown = run(ReportAgent(rt, Monitor(rt)).generate("wind", "20261021-000000", None))
    assert "## Summary\n\nEl dron voló con viento." in markdown
    assert "Report with the module's facts" not in markdown
    annex = markdown.split("## Annex: monitor self-assessment\n\n")[1]
    assert annex.count("Not available: the agent did not write this section.") == 2
    assert [r["fallback"] for r in rt.trace.records] == [False, True]  # misión bien, anexo no
    assert of_type(published, EventType.REPORT_GENERATED)[0].payload["alerts_count"] == 1


def test_frozen_assets_keep_the_single_call_report_with_the_assessment_in_the_middle(
    tmp_path: Path,
) -> None:
    llm = FakeLlm(Script(text_response(LEGACY_NARRATIVE)))
    assets = Assets(FROZEN)
    rt, _ = make_runtime(tmp_path, llm, FakePlatform({"get_flight_summary": SUMMARY}), assets)
    windy_state(rt)
    markdown = run(ReportAgent(rt, Monitor(rt)).generate("wind", "20261021-000000", None))
    assert len(llm.requests) == 1 and "Annex" not in markdown
    assert "first alert at T+00:06 (diagnosis delay: 1.0 s of simulation)" in markdown
    assert "**Monitor figures** (written by the module): 0 invocations" in markdown
    assert "\n\nRespaldada por las comprobaciones, pero tardó.\n" in markdown
    assert "1. Revisar el viento antes de despegar." in markdown and "## Limitations" in markdown
    user = llm.requests[0]["messages"][1]["content"]
    assert "### Guardrail rejections" in user and "### Active model aids" in user


@pytest.mark.parametrize("policy", [Script("   "), Script(RuntimeError("caído"))])
def test_report_without_narrative_keeps_the_facts_and_is_marked(
    tmp_path: Path, policy: Script
) -> None:
    rt, published = make_runtime(
        tmp_path, FakeLlm(policy), FakePlatform({"get_flight_summary": SUMMARY})
    )
    rt.set_run("wind", "r1")
    rt.state.apply(alert("ai-0001", ["det-1"], cause="WIND"))
    markdown = run(ReportAgent(rt, Monitor(rt)).generate("wind", "r1", None))
    assert "Report with the module's facts and without narrative" in markdown
    assert "### A1 · Wind" in markdown and "OPEN at the end" in markdown
    assert markdown.count("Not available: the agent did not write this section.") == 5
    assert rt.trace.records[0]["fallback"] is True
    assert of_type(published, EventType.REPORT_GENERATED)[0].payload["alerts_count"] == 1


def test_report_waits_for_the_monitor_to_drain(tmp_path: Path) -> None:
    rt, published = make_runtime(tmp_path, FakeLlm(Script(text_response("# I"))))
    rt.set_run("v", "r")
    monitor = Monitor(rt)
    monitor._idle.clear()  # el monitor sigue con una invocación

    async def scenario() -> None:
        task = asyncio.create_task(ReportAgent(rt, monitor).generate("v", "r", None))
        await asyncio.sleep(0.05)
        assert not task.done()
        monitor._idle.set()
        await asyncio.wait_for(task, 5)

    run(scenario())
    assert len(of_type(published, EventType.REPORT_GENERATED)) == 1


# --- Chats --------------------------------------------------------------------------------------


def test_monitor_chat_streams_chunks_and_replies(tmp_path: Path) -> None:
    llm = FakeLlm(
        Script(
            tool_response(call("get_my_alerts"), content="Miro."),
            text_response("Hay una alerta de viento"),
        )
    )
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_my_alerts": {"alerts": []}}))
    rt.clock.observe(50.0)
    chat = Chat(rt, ConversationId.MONITOR)
    question = operator_message("monitor", "¿qué alertas hay?")
    run(chat.answer(question))
    chunks = of_type(published, EventType.AGENT_REPLY_CHUNK)
    assert chunks and all(c.ephemeral and c.source == "ai-chat-monitor" for c in chunks)
    assert all(c.payload["reply_to"] == "ops-0001" for c in chunks)
    [reply] = of_type(published, EventType.AGENT_REPLY)
    assert reply.payload["text"] == "Miro. Hay una alerta de viento"
    assert (
        reply.payload["tool_calls"] == ["get_my_alerts"] and reply.payload["reply_to"] == "ops-0001"
    )
    assert reply.topic.endswith("ai.monitor.AgentReply.v1") and not reply.ephemeral
    assert llm.requests[0]["stream"] is True
    system = llm.requests[0]["messages"][0]["content"]
    assert "T+00:50" in system and "<<" not in system  # el sistema se rehace con el instante
    assert [e.payload["agent"] for e in of_type(published, EventType.AGENT_ACTIVITY)] == [
        "chat-monitor", "chat-monitor",
    ]  # fmt: skip
    trace = rt.trace.records[0]
    assert trace["agent"] == "chat-monitor" and trace["conversation_id"] == "monitor"


def test_chat_history_keeps_the_last_twelve_messages_and_rebuilds_the_system(
    tmp_path: Path,
) -> None:
    llm = FakeLlm(lambda m, t, s: text_response(f"respuesta {len(m)}"))
    rt, _ = make_runtime(tmp_path, llm)
    chat = Chat(rt, ConversationId.MONITOR)
    for n in range(1, 10):
        rt.clock.observe(float(n * 10))
        run(chat.answer(operator_message("monitor", f"pregunta {n}", n)))
    assert len(chat.history) == 12
    last = llm.requests[-1]["messages"]
    assert last[0]["role"] == "system" and "T+01:30" in last[0]["content"]
    assert [m["role"] for m in last[1:-1]] == ["user", "assistant"] * 6  # 12 mensajes de historial
    assert last[1]["content"] == "pregunta 3" and last[-1]["content"] == "pregunta 9"
    assert [m["role"] for m in last].count("system") == 1


def test_report_chat_answers_a_fixed_text_before_the_report(tmp_path: Path) -> None:
    llm = FakeLlm(Script("no debería llamarse"))
    rt, published = make_runtime(tmp_path, llm)
    report = ReportAgent(rt, Monitor(rt))
    chat = Chat(rt, ConversationId.REPORT, report)
    run(chat.answer(operator_message("report", "¿qué pasó?")))
    [reply] = of_type(published, EventType.AGENT_REPLY)
    assert reply.payload["text"] == rt.assets.agent("chat_report").no_report_reply
    assert "There is no report yet" in reply.payload["text"] and reply.source == "ai-chat-report"
    assert llm.requests == [] and rt.trace.records == []
    # con el informe, el LLM recibe el informe en el prompt de sistema
    report.markdown = "# Informe de prueba"
    run(chat.answer(operator_message("report", "¿qué pasó?", 2)))
    assert "# Informe de prueba" in llm.requests[0]["messages"][0]["content"]


def test_chat_runs_in_its_own_task_without_waiting_for_the_monitor(tmp_path: Path) -> None:
    llm = FakeLlm(Script("respuesta rápida"))
    rt, published = make_runtime(tmp_path, llm)
    monitor = Monitor(rt)
    monitor._busy = True  # el monitor está ocupado en una invocación larga
    monitor._idle.clear()
    chat = Chat(rt, ConversationId.MONITOR)

    async def scenario() -> None:
        task = asyncio.create_task(chat.run_forever())
        chat.submit(operator_message("monitor", "¿sigues ahí?"))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if of_type(published, EventType.AGENT_REPLY):
                break
        task.cancel()

    run(scenario())
    assert len(of_type(published, EventType.AGENT_REPLY)) == 1
    assert monitor._busy and not monitor._idle.is_set()  # el chat no tocó la cola del monitor


def test_chat_survives_a_llm_error(tmp_path: Path) -> None:
    rt, published = make_runtime(tmp_path, FakeLlm(Script(RuntimeError("caído"))))
    run(Chat(rt, ConversationId.MONITOR).answer(operator_message("monitor", "hola")))
    [reply] = of_type(published, EventType.AGENT_REPLY)
    assert "I could not answer" in reply.payload["text"]
