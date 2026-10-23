"""Extremo a extremo (marca `e2e`): plataforma real + módulo de IA real + servidor LLM falso.

`run.py --scenario demo --wait-agent --speed 16` con «esperar al agente»: no debe haber esperas
agotadas ni detecciones sin respuesta, y la evaluación se genera. Tarda unos 45 s.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import ai_module.agent.llm as llm_module
from ai_module.agent.llm import OpenAiLlm
from ai_module.testing.fake_llm import FakeLlmServer
from ai_module.testing.fake_llm import demo_policy as policy

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


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
        assert informe.startswith("# Mission report") and "Informe de prueba." in informe
        trace = [json.loads(line) for line in (folder / "llm_trace.jsonl").read_text().splitlines()]
        agents = {t["agent"] for t in trace}
        assert {"monitor", "report", "chat-monitor", "chat-report"} <= agents
        # cada petición al servidor llevó el muestreo explícito; el monitor, `required`
        for r in server.requests:
            system = r["messages"][0]["content"]
            chat = "now the human **operator** is talking to you" in system
            monitor = not chat and "report agent" not in system[:80]
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
