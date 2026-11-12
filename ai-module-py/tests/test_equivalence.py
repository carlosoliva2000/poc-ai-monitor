"""`tools/experiments/equivalence.py`: compara decisiones, no textos."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "experiments"))
import equivalence  # noqa: E402


def alert(cause: str, severity: str, as_of: float, phase: str = "active", text: str = "x") -> dict:
    return {
        "event_id": "ai-1", "type": "AnomalyDetected", "sim_time": as_of,
        "payload": {"cause": cause, "severity": severity, "phase": phase, "supersedes": None,
                    "fallback": False, "as_of_sim_time": as_of, "summary": text},
    }  # fmt: skip


def write(folder: Path, events: list[dict], late: int = 0) -> Path:
    folder.mkdir(parents=True)
    (folder / "timeline.jsonl").write_text("\n".join(json.dumps(e) for e in events), "utf-8")
    (folder / "llm_trace.jsonl").write_text(json.dumps({"events_after_as_of": late}), "utf-8")
    return folder


def test_same_decisions_with_other_texts_and_other_publication_times_are_equal(tmp_path) -> None:
    a = write(tmp_path / "a", [alert("WIND", "medium", 106.0, text="one")])
    b = write(tmp_path / "b", [{**alert("WIND", "medium", 106.0, text="other"), "sim_time": 300.0}])
    lines, diffs = equivalence.compare(a, b)
    assert diffs == [] and "IGUALES" not in "\n".join(lines)
    assert equivalence.main([str(a), str(b)]) == 0


def test_a_different_cause_phase_or_start_is_a_difference(tmp_path) -> None:
    a = write(tmp_path / "a", [alert("WIND", "medium", 106.0)])
    for name, other in (
        ("cause", alert("UNKNOWN", "medium", 106.0)),
        ("phase", alert("WIND", "medium", 106.0, phase="recovering")),
        ("as_of", alert("WIND", "medium", 106.5)),
    ):
        b = write(tmp_path / name, [other])
        assert equivalence.compare(a, b)[1], name
        assert equivalence.main([str(a), str(b)]) == 1


def test_the_late_events_are_reported(tmp_path) -> None:
    a = write(tmp_path / "a", [], late=0)
    b = write(tmp_path / "b", [], late=3)
    assert "posteriores al as_of: 3" in "\n".join(equivalence.compare(a, b)[0])
