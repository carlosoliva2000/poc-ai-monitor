"""Informe del alumno y debriefing del instructor (E7d): los hechos los escribe el código, el LLM
solo frases; sin el LLM los hechos se quedan."""

import asyncio
from dataclasses import replace
from typing import Any

from test_assistant import FakeBus, FakeLlm, build_flow, make_env, tool

from ai_module.assistant import __main__ as student
from ai_module.assistant.config import load_config
from ai_module.assistant.llm import LlmResult
from ai_module.instructor import __main__ as instr
from poc_contracts.enums import EventType
from poc_contracts.topics import topic_matches

BASE = load_config()
CONFIG = replace(BASE, queue=replace(BASE.queue, report_settle_s=0.0))


def finished() -> Any:
    return make_env(
        {
            "event_id": "plr-0099", "type": "SimulationFinished", "source": "platform-player",
            "topic": "citadel.pub.evt.sim.player.SimulationFinished.v1", "asset": None,
            "sim_time": 572.0, "event_time": "2026-10-20T10:09:32Z", "causation_id": None,
            "ephemeral": False, "payload": {"scenario": "x", "run_id": "r1"},
        },
        9000,
    )  # fmt: skip


def report_call(**over: Any) -> LlmResult:
    args = {
        "summary": "The wind pushed the drone off the route, then the GPS was spoofed.",
        "incidents": [
            {"number": 1, "note": "The drone drifted and came back on its own."},
            {"number": 2, "note": "The radar showed the real position while the GPS did not."},
            {"number": 3, "note": "The drone left the route while the link was lost."},
        ],
        "recommendations": ["Check the onboard wind estimate against the weather station."],
        **over,
    }  # fmt: skip
    return LlmResult("", "write_report", args, 0.3)


def run_student(llm: FakeLlm) -> tuple[FakeBus, student.AssistantProcess]:
    async def main() -> tuple[FakeBus, student.AssistantProcess]:
        process = student.AssistantProcess("http://127.0.0.1:1", CONFIG, llm)
        bus = FakeBus()
        process.bus = bus  # type: ignore[assignment]
        for event in build_flow():
            await process.handle(event)
        await process.queue.idle()
        bus.published.clear()
        await process.handle(finished())
        await asyncio.sleep(0.1)
        await process.queue.idle()
        return bus, process

    return asyncio.run(main())


def test_the_report_has_the_codes_facts_and_the_llms_sentences() -> None:
    llm = FakeLlm("An interpretation.", report_call())
    bus, process = run_student(llm)
    report = next(d for d in bus.published if d.type == EventType.REPORT_GENERATED)
    md = report.payload["markdown"]
    assert report.source == "ai-report" and report.payload["alerts_count"] == 3
    # hechos escritos por el código, con sus horas
    assert "opened as Command link lost at T+06:12" in md and "renamed to Hijack at T+06:28" in md
    assert "Largest radar distance from the planned route" in md
    # frases del LLM, ya comprobadas
    assert "The wind pushed the drone off the route" in md and "## Recommendations" in md
    assert process.store.report == md  # el chat del informe lo recibe
    acts = [d.payload["state"] for d in bus.published if d.type == EventType.AGENT_ACTIVITY]
    assert acts == ["started", "finished"]


def test_a_report_the_llm_cannot_write_keeps_the_facts() -> None:
    bad = report_call(summary="The drone flew 9999 m away.")  # una cifra que no estaba
    bus, _ = run_student(FakeLlm("Text.", bad, bad))
    md = next(d for d in bus.published if d.type == EventType.REPORT_GENERATED).payload["markdown"]
    assert "Not available" in md and "opened as" in md and "9999" not in md


def test_a_report_without_incidents_needs_no_llm() -> None:
    async def main() -> tuple[FakeBus, FakeLlm]:
        llm = FakeLlm("x")
        process = student.AssistantProcess("http://127.0.0.1:1", CONFIG, llm)
        bus = FakeBus()
        process.bus = bus  # type: ignore[assignment]
        await process.handle(finished())
        await asyncio.sleep(0.1)
        await process.queue.idle()
        return bus, llm

    bus, llm = asyncio.run(main())
    report = next(d for d in bus.published if d.type == EventType.REPORT_GENERATED)
    assert "No incidents were opened" in report.payload["markdown"] and not llm.calls


def test_the_debriefing_has_the_truth_compared_with_what_was_detected_and_is_instructor_only() -> (
    None
):
    async def main() -> FakeBus:
        llm = FakeLlm(
            LlmResult("", "write_debrief", {
                "summary": "The system saw the injected events.",
                "points": ["Discuss how fast the hijack was named."],
            }, 0.3)
        )  # fmt: skip
        process = instr.InstructorProcess("http://127.0.0.1:1", CONFIG, llm)
        bus = FakeBus()
        process.bus = bus  # type: ignore[assignment]
        for event in build_flow():
            if event.type != EventType.OPERATOR_MESSAGE:
                await process.handle(event)
        await process.handle(finished())
        await asyncio.sleep(0.1)
        await process.queue.idle()
        return bus

    bus = asyncio.run(main())
    debrief = next(d for d in bus.published if d.type == EventType.DEBRIEF_GENERATED)
    md = debrief.payload["markdown"]
    assert ".ai.instructor." in debrief.topic and debrief.source == "ai-debrief"
    assert not any(topic_matches(p, debrief.topic) for p in student.PATTERNS)  # el alumno no lo ve
    assert "## Injected and detected" in md and "Detected as" in md
    assert "The system saw the injected events." in md and debrief.payload["injects_count"] >= 1
    assert tool  # el helper de la hipótesis no se usa aquí
