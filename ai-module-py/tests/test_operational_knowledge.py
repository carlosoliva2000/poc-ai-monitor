"""Conocimiento operativo por causa (Fase 14.2): se inyecta por marcador y es criterio, no
frases ni valores fijos."""

import importlib.util
import re
import sys
from pathlib import Path

from ai_module.agent.assets import OPERATIONAL_KNOWLEDGE, Assets

REPO = Path(__file__).resolve().parents[2]
ASSETS = Assets()
TEXT = (REPO / "agent-assets" / OPERATIONAL_KNOWLEDGE).read_text(encoding="utf-8")
CAUSES = ("spoofing", "loss or interference", "hijacking", "sensor fault", "wind", "unknown")


def test_the_monitor_prompt_carries_the_knowledge_of_every_cause() -> None:
    prompt = ASSETS.system_prompt(ASSETS.agent("monitor"))
    assert "<<" not in prompt
    for cause in CAUSES:
        assert re.search(rf"\*\*[^*]*{cause}[^*]*:\*\*", prompt, re.IGNORECASE), cause
    assert "no generic security formulas" in prompt


def test_the_frozen_assets_do_not_use_the_marker() -> None:
    frozen = Assets(REPO / "agent-assets-v13")
    assert "operational_knowledge" not in frozen.system_prompt(frozen.agent("monitor"))


def test_the_file_gives_no_fixed_severity_or_confidence_and_stays_short() -> None:
    body = re.sub(r"<!--.*?-->", "", TEXT, flags=re.S)
    assert not re.search(r"\b(low|medium|high)\b", body, re.IGNORECASE)
    assert not re.search(r"confidence|\d", body, re.IGNORECASE)
    # ≤ 500 tokens: ~1,4 tokens por palabra en inglés; la medida real está en el informe de fase
    assert len(body.split()) * 1.4 <= 500


def test_the_file_has_no_internal_names_and_no_copy_of_other_prompts() -> None:
    spec = importlib.util.spec_from_file_location(
        "text_metrics", REPO / "tools" / "experiments" / "text_metrics.py"
    )
    assert spec and spec.loader
    tm = importlib.util.module_from_spec(spec)
    sys.modules["text_metrics"] = tm
    spec.loader.exec_module(tm)
    names, _enums, bools = tm.find_names(TEXT)
    assert names == [] and bools == []
