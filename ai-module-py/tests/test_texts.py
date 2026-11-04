"""Extracción de textos de una matriz (`tools/experiments/texts.py`): sin LLM ni GPU."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("texts", REPO / "tools" / "experiments" / "texts.py")
assert spec and spec.loader
texts = importlib.util.module_from_spec(spec)
sys.modules["texts"] = texts
spec.loader.exec_module(texts)

REPORT = """# Mission report X

## Summary

The drone flew.
Second line.

## Anomalies

### A1 · Wind (medium, confidence 0.8)
- **When:** at T+01:46.
- **What was seen:** Wind pushed it.
- **Status:** closed.

## Monitor assessment

**Monitor figures** (written by the module): 3 invocations.

- **Support:** it held.

## Recommendations

1. Check the wind.

## Limitations

Not the model.
"""


def event(kind: str, seq: int, sim_time: float, event_id: str, **payload: object) -> dict:
    return {
        "event_id": event_id,
        "type": kind,
        "sim_time": sim_time,
        "seq": seq,
        "payload": payload,
    }


def make_run(root: Path, profile: str, summary: str) -> None:
    folder = root / "runs" / profile / "demo" / "r1"
    folder.mkdir(parents=True)
    events = [
        event("OperatorMessage", 1, 110.0, "ops-1", conversation_id="monitor", text="Why wind?"),
        event(
            "AnomalyDetected", 2, 106.8, "ai-1", alert_id="ai-1", cause="WIND",
            severity="medium", confidence=0.8, summary=summary,
            explanation="Because\nof the gust.", recommendation="Watch.",
        ),
        event("AgentReply", 3, 154.0, "ai-2", reply_to="ops-1", text="Because of the drift."),
        event("AlertClosed", 4, 156.8, "ai-3", alert_id="ai-1", reason="Back on the route."),
        event("AnomalyDetected", 5, 200.0, "ai-4", alert_id="ai-4", cause="X", severity="low",
              confidence=0.1, summary="s", explanation="e", recommendation="r"),
    ]  # fmt: skip
    (folder / "timeline.jsonl").write_text("\n".join(json.dumps(e) for e in events), "utf-8")
    eval_json = {"alert_severities": {"A1": [{"alert_id": "ai-1"}]}}
    (folder / "eval.json").write_text(json.dumps(eval_json), "utf-8")
    (folder / "informe.md").write_text(REPORT, "utf-8")


@pytest.fixture
def sources(tmp_path: Path) -> list:
    make_run(tmp_path / "a", "actual", "The wind drifts it.")
    make_run(tmp_path / "b", "other", "A different summary.")
    return [
        texts.parse_source(f"base={tmp_path / 'a'}"),
        texts.parse_source(f"other={tmp_path / 'b'}:other"),
    ]


def test_the_report_sections_written_by_the_model_are_extracted_without_the_module_figures() -> (
    None
):
    sections, seen = texts.model_report_sections(REPORT)
    assert sections["Summary"] == "The drone flew.\nSecond line."
    assert sections["Monitor assessment"] == "- **Support:** it held."
    assert sections["Recommendations"] == "1. Check the wind."
    assert "Limitations" not in sections
    assert seen == {"A1": ("A1 · Wind (medium, confidence 0.8)", "Wind pushed it.")}


def test_every_text_appears_in_full_and_side_by_side(sources: list) -> None:
    out = texts.build(sources, ["demo"], 1)
    assert out.index("#### base · A1") < out.index("#### other · A1")
    for expected in ("The wind drifts it.", "A different summary.", "> Because", "> of the gust."):
        assert expected in out
    assert "Back on the route." in out and "T+01:46" in out and "T+02:36" in out
    assert "cause `WIND` · severity `medium` · confidence `0.8`" in out
    assert "Because of the drift." in out and "#### monitor · Why wind?" in out
    assert "Check the wind." in out and "Wind pushed it." in out
    assert "Monitor figures" not in out


def test_an_alert_without_a_label_is_not_lost(sources: list) -> None:
    assert "### Alert (no label)" in texts.build(sources, ["demo"], 1)


def test_a_fallback_acknowledgement_without_alert_id_goes_with_its_detection(
    tmp_path: Path,
) -> None:
    make_run(tmp_path / "a", "actual", "s")
    folder = tmp_path / "a" / "runs" / "actual" / "demo" / "r1"
    lines = (folder / "timeline.jsonl").read_text().splitlines()
    first = json.loads(lines[1])
    first["payload"]["detection_ids"] = ["det-1"]
    ack = event("DetectionAcknowledged", 9, 300.0, "ai-9", detection_id="det-1", alert_id=None,
                reason="the agent did not conclude", fallback=True)  # fmt: skip
    lines[1] = json.dumps(first)
    (folder / "timeline.jsonl").write_text("\n".join([*lines, json.dumps(ack)]), "utf-8")
    run = texts.load_run(texts.parse_source(f"x={tmp_path / 'a'}"), folder)
    assert [e["event_id"] for e in run.ends["A1"]] == ["ai-3", "ai-9"]


def test_a_missing_run_is_reported_and_does_not_stop_the_rest(sources: list) -> None:
    out = texts.build(sources, ["demo", "faults"], 1)
    assert "missing: base · faults · r1" in out and "## Scenario `faults`" in out


def test_main_writes_the_file(sources: list, tmp_path: Path) -> None:
    out = tmp_path / "t.md"
    args = ["--out", str(out), "--scenarios", "demo"]
    assert texts.main([*args, f"x={tmp_path / 'a'}"]) == 0
    assert "# Texts for quality review" in out.read_text("utf-8")
    assert texts.main([*args, "wrong"]) == 2


ANNEX_REPORT = """# Mission report X

## Summary

The drone flew.

## Anomalies

### A1 · Wind (medium, confidence 0.8)
- **What was seen:** Wind pushed it.
- **Status:** closed.

## Recommendations

1. Check the wind.

## Limitations

Simulated.

## Annex: monitor self-assessment

**Monitor figures** (written by the module): 3 invocations.

### Assessment

- **Support:** it held.

### Technical recommendations

1. Reduce the delay.
"""


def test_report_with_annex_gives_mission_and_annex_sections() -> None:
    sections, seen = texts.model_report_sections(ANNEX_REPORT)
    assert sections["Summary"] == "The drone flew."
    assert sections["Recommendations"] == "1. Check the wind."
    assert sections["Monitor assessment"] == "- **Support:** it held."
    assert sections["Technical recommendations"] == "1. Reduce the delay."
    assert "Monitor figures" not in "".join(sections.values())
    assert seen["A1"][1] == "Wind pushed it."
