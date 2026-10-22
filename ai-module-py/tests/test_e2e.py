"""Extremo a extremo (marca `e2e`): plataforma real + módulo de IA real + servidor LLM falso.

`run.py --scenario demo --wait-agent --speed 16` con «esperar al agente»: no debe haber esperas
agotadas ni detecciones sin respuesta, y la evaluación se genera. Tarda unos 45 s.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fake_llm_server import FakeLlmServer

import ai_module.agent.llm as llm_module
from ai_module.agent.llm import OpenAiLlm

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


def policy(body: dict[str, Any]) -> dict[str, Any]:
    """Decisión del LLM falso según el prompt: monitor, informe o chat."""
    system = body["messages"][0]["content"]
    messages = body["messages"]
    if "agente de informe" in system:
        text = "## Resumen\n\nInforme de prueba.\n\n## Valoración del monitor\n\nSegún los eventos."
        return {"content": text}
    if "ahora te habla el **operador**" in system:
        return {"content": "Respuesta de prueba del chat con datos."}
    user = messages[1]["content"]
    pending = list(dict.fromkeys(re.findall(r"(?:detección|Nueva detección) (det-\d+)", user)))
    last_open = re.search(r"de la alerta (ai-\d+)", user)
    open_alert = re.search(r"Alertas abiertas: (ai-\d+)", user)
    if last_open:
        return {"tool_calls": [("close_alert", {"alert_id": last_open.group(1), "reason": "ok"})]}
    if open_alert:
        args = {"detection_ids": pending, "alert_id": open_alert.group(1), "reason": "igual"}
        return {"tool_calls": [("acknowledge_detection", args)]}
    triggers = re.search(r'"trigger_event_ids":\[([^\]]*)\]', user)
    ids = re.findall(r'"([^"]+)"', triggers.group(1) if triggers else "") or ["gps-000001"]
    checks = {"gps_alert_recent": False, "gps_radar_disagreed": False, "wind_notable": False,
              "wind_with_drift": False, "link_checked": False, "link_anomalous": None}  # fmt: skip
    alert = {"detection_ids": pending, "checks": checks, "cause": "UNKNOWN", "severity": "medium",
             "confidence": 0.4, "summary": "prueba", "explanation": "e", "recommendation": "r",
             "evidence_event_ids": ids[:2]}  # fmt: skip
    return {"tool_calls": [("publish_alert", alert)]}


def test_demo_end_to_end_with_a_fake_llm() -> None:
    with FakeLlmServer(policy) as server:
        result = subprocess.run(
            ["uv", "run", "--project", "platform", "python", "-m", "platform_app.run",
             "--scenario", "demo", "--speed", "16", "--wait-agent", "--port", "8199",
             "--llm-url", server.url, "--ask", "monitor:200:¿Cómo vas?",
             "--ask", "report:end:¿Qué pasó?", "--evaluate"],
            cwd=REPO, capture_output=True, text=True, timeout=400,
        )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    folder = Path(re.search(r"→ (.+)/eval\.md", out).group(1))  # type: ignore[union-attr]
    try:
        data = json.loads((folder / "eval.json").read_text())
        assert data["timeouts"] == 0 and data["unanswered"] == []
        assert "ACK" in out or "ALERTA" in out
        assert "INFORME" in out and "Respuesta de prueba del chat" in out
        informe = (folder / "informe.md").read_text()
        assert informe.startswith("# Informe de la misión") and "Informe de prueba." in informe
        trace = [json.loads(line) for line in (folder / "llm_trace.jsonl").read_text().splitlines()]
        agents = {t["agent"] for t in trace}
        assert {"monitor", "report", "chat-monitor", "chat-report"} <= agents
        # cada petición al servidor llevó el muestreo explícito; el monitor, `required`
        for r in server.requests:
            system = r["messages"][0]["content"]
            chat = "ahora te habla el **operador**" in system
            monitor = not chat and "informe" not in system[:80]
            facts = monitor or chat  # monitor y chats: sobre hechos, temperatura 0 y sin top_k
            assert r["repetition_penalty"] == 1.05
            assert r["top_k"] == (-1 if facts else 20)
            if "tools" in r:  # el informe no lleva tools (y, sin ellas, tampoco tool_choice)
                assert r["tool_choice"] == ("required" if monitor else "auto")
            else:  # sin tools (el informe y los chats de la demo) tampoco hay tool_choice
                assert not monitor and "tool_choice" not in r
            assert r["temperature"] == (0 if facts else 0.7)
        # el timeline siguió creciendo después de SimulationFinished (informe y chats)
        lines = (folder / "timeline.jsonl").read_text().splitlines()
        types = [json.loads(line)["type"] for line in lines]
        assert types.index("SimulationFinished") < types.index("ReportGenerated") < len(types) - 1
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_openai_client_is_the_official_sdk() -> None:
    assert llm_module.AsyncOpenAI.__module__.startswith("openai")
    assert OpenAiLlm.__name__ == "OpenAiLlm"
