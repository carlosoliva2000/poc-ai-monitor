"""`agent-assets/`: índice de skills, marcadores, secciones y esquemas de tools."""

import json

import pytest

from ai_module.agent.assets import MARKER_RE, AssetError, Assets, render, sections

ASSETS = Assets()


def test_skills_index_lists_name_and_description() -> None:
    index = ASSETS.skills_index(["route-deviation", "source-discrepancy"])
    assert index.count("\n") == 1
    assert "- `route-deviation`: Úsala cuando el detector lance ROUTE_DEVIATION" in index
    assert ASSETS.skills["report-format"].content.startswith("---\nname: report-format")
    with pytest.raises(AssetError):
        ASSETS.skills_index(["no-existe"])


@pytest.mark.parametrize("agent", ["monitor", "chat_monitor", "report", "chat_report"])
def test_system_prompts_leave_no_marker(agent: str) -> None:
    config = ASSETS.agent(agent)
    values = {
        "t_label": "T+01:00",
        "sim_time": "60",
        "report_markdown": "# Informe",
        "open_alerts": "ninguna",
        "open_detections": "ninguna",
        "report_format": ASSETS.skill_body("report-format"),
    }
    prompt = ASSETS.system_prompt(config, **values)
    assert not MARKER_RE.findall(prompt)
    if config.tools:  # el informe no tiene tools: su prompt no habla de iteraciones
        assert str(config.max_iterations) in prompt
    for skill in config.skills:
        assert f"`{skill}`" in prompt


def test_render_requires_every_marker() -> None:
    assert render("a <<x>> b", x=1) == "a 1 b"
    with pytest.raises(AssetError, match="y"):
        render("a <<x>> <<y>>", x=1)


def test_objective_sections_and_markers() -> None:
    common, secs = sections(ASSETS.prompt("prompts/monitor_objective.md"))
    assert set(secs) == {"batch", "raised", "updated", "cleared", "reminder"}
    assert "<!--" not in common  # los comentarios de la plantilla no llegan al modelo
    values = {
        "t_label": "T+01:46", "sim_time": "106", "open_alerts": "ninguna",
        "open_detections": "ninguna", "last_decisions": "ninguna", "gps_alert_recent": "no",
        "detection_id": "det-1",
        "detection_json": "{}", "related_alerts": "x", "last_open_alert": "ai-1", "count": 2,
        "detection_ids": "det-1, det-2", "pending": "det-1", "detection_since": "100",
    }  # fmt: skip
    for text in [common, *secs.values()]:
        assert not MARKER_RE.findall(render(text, **values))


def test_tool_schemas_are_sent_as_they_are_in_tools_json() -> None:
    config = ASSETS.agent("monitor")
    assert len(config.active_tools) == 8
    schemas = ASSETS.tool_schemas(config.active_tools)
    raw = json.loads((ASSETS.root / "tools.json").read_text(encoding="utf-8"))
    by_name = {t["function"]["name"]: t for t in raw}
    assert [s["function"]["name"] for s in schemas] == [
        t["function"]["name"] for t in raw if t["function"]["name"] in config.active_tools
    ]
    for schema in schemas:
        assert schema == by_name[schema["function"]["name"]]  # idénticos, sin regenerar


def test_disabled_tools_are_filtered_out() -> None:
    config = ASSETS.agent("monitor")
    from dataclasses import replace

    off = replace(config, disabled_tools=["get_track_metrics"])
    assert "get_track_metrics" not in off.active_tools
    assert "get_track_metrics" in config.active_tools
    with pytest.raises(AssetError):
        ASSETS.tool_schemas(["no_existe"])


def test_sampling_is_explicit_for_every_agent() -> None:
    monitor = ASSETS.agent("monitor").sampling()
    assert monitor == {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 800,
        "tool_choice": "required",  # su respuesta es siempre una tool call
        "extra_body": {"top_k": -1, "repetition_penalty": 1.05},
    }
    report = ASSETS.agent("report").sampling()
    assert report["temperature"] == 0.7 and report["top_p"] == 0.8
    assert report["extra_body"] == {"top_k": 20, "repetition_penalty": 1.05}
    assert report["tool_choice"] == "auto"  # nunca por nombre
    for name in ("chat_monitor", "chat_report"):  # los chats responden sobre hechos
        sampling = ASSETS.agent(name).sampling()
        assert sampling["temperature"] == 0.0 and sampling["top_p"] == 1.0
        assert sampling["extra_body"] == {"top_k": -1, "repetition_penalty": 1.05}
        assert sampling["tool_choice"] == "auto"


def test_final_tools_of_the_monitor_are_the_three_responses() -> None:
    config = ASSETS.agent("monitor")
    assert config.final_tools == ["publish_alert", "acknowledge_detection", "close_alert"]
    assert config.last_iteration_tools == config.final_tools
    assert ASSETS.agent("report").last_iteration_tools == ASSETS.agent("report").active_tools


def test_every_skill_and_tool_named_in_agents_yaml_exists() -> None:
    for name in ("monitor", "chat_monitor", "report", "chat_report"):
        config = ASSETS.agent(name)
        ASSETS.skills_index(config.skills)
        ASSETS.tool_schemas(config.tools)
