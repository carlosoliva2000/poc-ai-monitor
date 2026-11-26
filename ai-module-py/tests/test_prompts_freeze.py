"""Los prompts del asistente están congelados (E7d): si cambian, el asistente no arranca."""

import shutil
from pathlib import Path

import pytest

from ai_module.assistant import freeze
from ai_module.assistant.config import ASSETS_DIR


def test_the_committed_prompts_are_frozen() -> None:
    """Falla si se toca un prompt, un esquema de tools, el glosario o `assistant.yaml` sin
    refrescar la congelación (`tools/assistant/freeze_prompts.py`)."""
    assert (ASSETS_DIR / freeze.FREEZE_FILE).exists()
    assert freeze.verify().startswith("prompts frozen")


def test_a_changed_prompt_stops_the_assistant_and_says_which(tmp_path: Path) -> None:
    assets = tmp_path / "agent-assets"
    shutil.copytree(ASSETS_DIR, assets)
    freeze.write(assets)
    assert freeze.verify(assets).startswith("prompts frozen")
    with (assets / "prompts" / "explain.md").open("a", encoding="utf-8") as handle:
        handle.write("One more rule.\n")
    with pytest.raises(freeze.FreezeError, match=r"prompts/explain\.md"):
        freeze.verify(assets)
    (assets / freeze.FREEZE_FILE).unlink()
    assert "not frozen" in freeze.verify(assets)  # sin congelación no hay nada que comprobar


def test_every_prompt_tool_file_and_the_glossary_are_in_the_freeze() -> None:
    names = {str(p) for p in freeze.frozen_files()}
    expected = {"assistant.yaml", "glossary.yaml", "prompts/chat.md", "prompts/translator.md",
                "prompts/report.md", "prompts/debrief.md", "instructor_tools.json"}  # fmt: skip
    assert expected <= names
