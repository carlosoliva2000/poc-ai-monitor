"""Extremo a extremo con la plataforma real y un LLM falso (≈ 60 s): el monitor y los dos procesos
del asistente comparten el bus; lo que publican llega y no se repite ningún id.

Lo encontró un ensayo con la web: los tres numeraban `ai-0001`… y la plataforma rechazaba los
textos del asistente («an event with id … already exists») sin que ninguna prueba lo notara. Ahora
cada proceso lleva su etiqueta (`ai-m-0001`, `ai-a-0001`, `ai-i-0001`).
"""

import asyncio
import json
import logging
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.client import connect

from ai_module.assistant import __main__ as student
from ai_module.assistant.config import load_config
from ai_module.assistant.llm import LlmResult
from ai_module.instructor import __main__ as instr
from ai_module.situation.__main__ import SituationProcess

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


class RoutingLlm:
    """Contesta según el papel, siempre con algo que pasa las comprobaciones."""

    async def complete(self, role: Any, system: str, user: str, tools: Any = None) -> LlmResult:
        name = role.name
        if name == "explain":
            return LlmResult("The drone is off the route. Follow it on the radar.", None, None, 0.1)
        if name == "hypothesis":
            args = {"summary": "No known cause fits.", "ranked": [], "checks": []}
            return LlmResult("", "propose_hypothesis", args, 0.1)
        if name == "translator":
            args = {"from_direction": "north", "speed": "12", "unit": "m/s"}
            return LlmResult("", "propose_wind", args, 0.1)
        if name == "report":
            args = {"summary": "The flight had incidents.", "incidents": [], "recommendations": []}
            return LlmResult("", "write_report", args, 0.1)
        if name == "debrief":
            return LlmResult("", "write_debrief", {"summary": "Compared.", "points": []}, 0.1)
        return LlmResult("The drone is following the planned route.", None, None, 0.1)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def operator_message(n: int, conversation: str, text: str, sim_time: float) -> dict[str, Any]:
    source = "web-instructor" if conversation == "instructor" else "web-operator"
    return {
        "event_id": f"ops-{n:04d}", "type": "OperatorMessage", "source": source, "asset": None,
        "topic": f"citadel.pub.evt.ops.{conversation}.OperatorMessage.v1", "sim_time": sim_time,
        "event_time": "2026-10-20T10:00:00Z", "causation_id": None, "ephemeral": False,
        "payload": {"conversation_id": conversation, "text": text},
    }  # fmt: skip


async def drive(url: str, port: int) -> list[dict[str, Any]]:
    """Un cliente `web`: carga `demo`, hace dos preguntas y recoge todo hasta el debriefing."""
    seen: list[dict[str, Any]] = []
    async with connect(f"ws://127.0.0.1:{port}/ws") as ws:
        await ws.send(json.dumps({"op": "hello", "client": "web"}))
        await ws.send(json.dumps({"op": "subscribe", "patterns": ["citadel.pub.evt.>"]}))
        for action, value in (
            ("load", "demo"),
            ("speed", 16),
            ("interactive", True),
            ("play", None),
        ):
            await ws.send(json.dumps({"op": "control", "action": action, "value": value}))
        asked = False
        deadline = time.monotonic() + 120
        types: set[str] = set()
        while time.monotonic() < deadline:
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if message["op"] != "event":
                continue
            event = message["event"]
            seen.append(event)
            types.add(event["type"])
            if event["type"] == "MissionStarted" and not asked:
                asked = True
                for i, (conv, text) in enumerate(
                    (
                        ("monitor", "What is happening?"),
                        ("instructor", "wind from the north at 12 m/s"),
                    ),
                    1,
                ):
                    publish = {
                        "op": "publish",
                        "event": operator_message(i, conv, text, event["sim_time"]),
                    }
                    await ws.send(json.dumps(publish))
            if {"ReportGenerated", "DebriefGenerated"} <= types:
                break
    return seen


def test_the_monitor_and_both_assistants_share_the_bus_without_repeating_an_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    port = free_port()
    platform = subprocess.Popen(
        ["uv", "run", "--project", str(REPO / "platform"), "python", "-m", "platform_app.app",
         "--port", str(port)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/api/state", timeout=1).read()
                break
            except OSError:
                time.sleep(0.3)
        else:
            pytest.fail("the platform did not start")
        config = load_config()
        llm = RoutingLlm()

        async def main() -> list[dict[str, Any]]:
            tasks = [
                asyncio.create_task(SituationProcess(url).run()),
                asyncio.create_task(student.AssistantProcess(url, config, llm).serve()),
                asyncio.create_task(instr.InstructorProcess(url, config, llm).serve()),
            ]
            await asyncio.sleep(1.5)  # que se suscriban antes de cargar
            try:
                return await drive(url, port)
            finally:
                for task in tasks:
                    task.cancel()

        with caplog.at_level(logging.WARNING, logger="ai_module.bus_client"):
            events = asyncio.run(main())
    finally:
        platform.terminate()
        platform.wait(10)

    errors = [r.message for r in caplog.records if "platform error" in r.message]
    assert not errors, errors[:3]
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids))
    kinds = {e["type"] for e in events}
    assert {"IncidentUpdated", "IncidentEnriched", "ReportGenerated", "DebriefGenerated"} <= kinds
    replies = {e["payload"]["conversation_id"] for e in events if e["type"] == "AgentReply"}
    assert replies == {"monitor", "instructor"}  # las dos respuestas llegaron
    assert sys.version_info >= (3, 12)
