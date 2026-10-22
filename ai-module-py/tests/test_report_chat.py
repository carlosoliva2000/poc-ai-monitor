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


NARRATIVE = """## Resumen
El dron voló con viento.

## Qué se vio
### A1
La desviación creció hasta 40 m con viento notable.

## Valoración del monitor
Respaldada por las comprobaciones, pero tardó.

## Recomendaciones
1. Revisar el viento antes de despegar.
"""


def test_report_is_published_saved_and_counts_chains(tmp_path: Path) -> None:
    llm = FakeLlm(Script(text_response(NARRATIVE)))
    rt, published = make_runtime(tmp_path, llm, FakePlatform({"get_flight_summary": SUMMARY}))
    rt.set_run("viento", "20261021-000000")
    rt.state.apply(detection_event("raised", "det-1", 5.0))
    rt.state.apply(alert("ai-0001", ["det-1"], cause="WIND", t=6.0))
    rt.state.apply(alert("ai-0002", ["det-1"], cause="WIND", supersedes="ai-0001", t=20.0))
    rt.clock.observe(100.0)
    report = ReportAgent(rt, Monitor(rt))
    markdown = run(report.generate("viento", "20261021-000000", "plr-0009"))
    # los hechos son del módulo; la narrativa, del LLM, en su sitio
    assert markdown.startswith(
        "# Informe de la misión T\n\n**Escenario:** viento · **Duración:** 01:40"
    )
    assert "## Resumen\n\nEl dron voló con viento." in markdown
    assert "### A1 · Viento (alta, confianza 0.8)" in markdown
    assert "primera alerta a T+00:06 (retraso de diagnóstico: 1,0 s de simulación)" in markdown
    assert "**Última alerta:** ai-0002 a T+00:20" in markdown
    assert "- **Qué se vio:** La desviación creció hasta 40 m con viento notable." in markdown
    assert "- **Estado:** ABIERTA al final." in markdown
    assert "**Cifras del monitor** (las escribe el módulo): 0 invocaciones" in markdown
    assert "\n\nRespaldada por las comprobaciones, pero tardó.\n" in markdown
    assert "1. Revisar el viento antes de despegar." in markdown and "## Limitaciones" in markdown
    [event] = of_type(published, EventType.REPORT_GENERATED)
    assert event.payload == {"run_id": "20261021-000000", "markdown": markdown, "alerts_count": 1}
    assert event.source == "ai-report" and event.causation_id == "plr-0009"
    assert (tmp_path / "viento" / "20261021-000000" / "informe.md").read_text() == markdown + "\n"
    trace = rt.trace.records[0]
    assert trace["agent"] == "report" and trace["end_reason"] == "final" and not trace["fallback"]
    assert llm.requests[0]["sampling"]["temperature"] == 0.7
    # una sola llamada y sin tools: los datos van en el prompt
    assert len(llm.requests) == 1 and llm.requests[0]["tools"] == []
    system, user = (m["content"] for m in llm.requests[0]["messages"])
    assert "## Qué se vio" in system and "<<" not in system and "<<" not in user
    assert '"mission_id":"T"' in user and "MSN" not in user
    assert "### A1 · Viento" in user and "Monitor ai-0002" in user and "ABIERTA al final" in user
    assert "### Rechazos de los guardrails" in user and "### Ayudas al modelo activas" in user
    assert [e.payload["state"] for e in of_type(published, EventType.AGENT_ACTIVITY)] == [
        "started", "finished",
    ]  # fmt: skip


@pytest.mark.parametrize("policy", [Script("   "), Script(RuntimeError("caído"))])
def test_report_without_narrative_keeps_the_facts_and_is_marked(
    tmp_path: Path, policy: Script
) -> None:
    rt, published = make_runtime(
        tmp_path, FakeLlm(policy), FakePlatform({"get_flight_summary": SUMMARY})
    )
    rt.set_run("viento", "r1")
    rt.state.apply(alert("ai-0001", ["det-1"], cause="WIND"))
    markdown = run(ReportAgent(rt, Monitor(rt)).generate("viento", "r1", None))
    assert "Informe con los hechos del módulo y sin narrativa" in markdown
    assert "### A1 · Viento" in markdown and "ABIERTA al final" in markdown
    assert markdown.count("No disponible: el agente no redactó este apartado.") == 4
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
    assert "Todavía no hay informe" in reply.payload["text"] and reply.source == "ai-chat-report"
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
    assert "No he podido responder" in reply.payload["text"]
