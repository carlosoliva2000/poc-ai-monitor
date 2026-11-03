"""`monitor_usage`: uso de skills, rechazos y contexto sobre trazas sintéticas."""

import json
from pathlib import Path
from typing import Any

from ai_module.monitor_usage import (
    expected_decision,
    load_experiment,
    rejection_type,
    render,
)

OBJECTIVE = "- Open alerts: none\n- Recent GPS alert (open or closed ≤ 60 s ago): no\n"


def tool(name: str, arguments: dict[str, Any], result: Any, error: str | None = None) -> dict:
    return {
        "id": f"c-{name}",
        "name": name,
        "arguments": json.dumps(arguments),
        "result": result,
        "error": error,
    }


def call(index: int, *tools: dict) -> dict:
    return {"index": index, "prompt_tokens": 3000 + 500 * index, "completion_tokens": 50,
            "finish_reason": "stop", "tool_calls": list(tools)}  # fmt: skip


METRICS = {
    "since": 0, "until": 1, "gps_radar": {"disagreed": False},
    "wind": {"notable": True, "with_drift": True}, "gps_max_step_m": 1.0,
}  # fmt: skip


def write_run(folder: Path, calls: list[dict], rejections: list | None = None) -> None:
    run = folder / "runs" / "perfil" / "wind" / "r1"
    run.mkdir(parents=True)
    events = [
        {"event_id": "det-0001", "type": "DetectionRaised",
         "payload": {"detection_id": "det-0001", "rule": "ROUTE_DEVIATION"}},
    ]  # fmt: skip
    (run / "timeline.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    record = {
        "invocation_id": "inv-0001", "agent": "monitor", "deterministic": False,
        "causation_ids": ["det-0001"], "duration_s": 2.0,
        "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": OBJECTIVE}],
        "calls": calls, "skills_loaded": [], "guardrail_rejections": rejections or [],
    }  # fmt: skip
    (run / "llm_trace.jsonl").write_text(json.dumps(record) + "\n")


def decision(cause: str) -> dict:
    return tool("publish_alert", {"cause": cause}, {"ok": True, "alert_id": "ai-0001"})


def test_skill_loaded_before_deciding_and_decision_matches(tmp_path: Path) -> None:
    calls = [
        call(1, tool("load_skill", {"name": "route-deviation"}, "text")),
        call(2, tool("get_track_metrics", {}, METRICS)),
        call(3, decision("WIND")),
    ]
    write_run(tmp_path, calls)
    [inv] = load_experiment(tmp_path)
    assert (inv.rule, inv.kind, inv.expected_skill) == (
        "ROUTE_DEVIATION",
        "raised",
        "route-deviation",
    )
    assert inv.loaded_expected and inv.loaded_before_decision and inv.matches is True
    assert inv.iterations == 3 and inv.decision == "publish_alert" and inv.cause == "WIND"


def test_a_skill_that_does_not_exist_and_a_decision_that_differs(tmp_path: Path) -> None:
    calls = [
        call(1, tool("load_skill", {"name": "source-silence"}, None, error="unknown skill")),
        call(2, tool("get_track_metrics", {}, METRICS)),
        call(3, decision("HIJACK")),
    ]
    rejection = [
        {"tool": "publish_alert", "errors": ["checks.link_anomalous = null does not match"]}
    ]
    write_run(tmp_path, calls, rejection)
    [inv] = load_experiment(tmp_path)
    assert inv.nonexistent == ["source-silence"] and inv.loaded == [] and not inv.loaded_expected
    assert inv.matches is False  # la skill dice WIND (viento notable y a favor)
    assert inv.rejections == ["link_anomalous"]


def test_deciding_before_loading_the_skill(tmp_path: Path) -> None:
    calls = [
        call(1, decision("UNKNOWN")),
        call(2, tool("load_skill", {"name": "route-deviation"}, "t")),
    ]
    write_run(tmp_path, calls)
    [inv] = load_experiment(tmp_path)
    assert inv.loaded_expected and inv.loaded_before_decision is False


def test_expected_decisions_by_rule() -> None:
    gps = tool("get_events", {"source": "gps"}, {"events": [{"fix": "none"}]})
    metrics = tool("get_track_metrics", {}, {**METRICS, "gps_radar": {"disagreed": True}})
    text, valid = expected_decision("GPS_DEGRADED", "raised", OBJECTIVE, [(1, metrics)])
    assert valid == {"cause:GPS_JAMMING"}
    _, valid = expected_decision(
        "SOURCE_DISCREPANCY", "raised", OBJECTIVE, [(1, gps), (2, metrics)]
    )
    assert valid == {"cause:GPS_JAMMING"}
    open_jamming = OBJECTIVE.replace("Open alerts: none", "Open alerts: ai-0001 GPS_JAMMING")
    _, valid = expected_decision("SOURCE_DISCREPANCY", "raised", open_jamming, [(1, metrics)])
    assert valid == {"ack"}
    _, valid = expected_decision("SOURCE_SILENT", "raised", OBJECTIVE, [])
    assert valid == {"cause:SENSOR_FAULT", "cause:UNKNOWN"}
    recovery = OBJECTIVE.replace(
        "no\n", "yes — ai-0003 GPS_SPOOFING (open). If this warning is the GPS recovery: cause "
        "GPS_SPOOFING, supersedes ai-0003\n",
    )  # fmt: skip
    _, valid = expected_decision("ROUTE_DEVIATION", "raised", recovery, [(1, metrics)])
    assert valid == {"cause:GPS_SPOOFING"}
    text, valid = expected_decision("ROUTE_DEVIATION", "raised", OBJECTIVE, [])
    assert valid is None and text.startswith("no data")
    _, valid = expected_decision("ROUTE_DEVIATION", "cleared", OBJECTIVE, [(1, metrics)])
    assert valid is None


def test_rejection_types() -> None:
    assert rejection_type("Nothing changes: use acknowledge_detection") == "nothing_changes"
    assert rejection_type("ai-0001 (WIND) is open: use supersedes ai-0001 …") == "duplicate_cause"
    assert rejection_type("evidence 'x' comes from an earlier warning; request it again") == (
        "history_evidence"
    )
    assert rejection_type("something new") == "other"


def test_render_has_the_sections(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        [
            call(1, tool("load_skill", {"name": "route-deviation"}, "t")),
            call(2, decision("UNKNOWN")),
        ],
    )
    text = render(load_experiment(tmp_path))
    for title in ("### Coste", "### Por regla", "### Por escenario", "### Rechazos por tipo"):
        assert title in text
    assert "ROUTE_DEVIATION" in text and "100% (1/1)" in text
