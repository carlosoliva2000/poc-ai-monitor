"""E6: `tools/experiments/e6_report.py` reúne las métricas de varias matrices por fuente."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_evaluate_e6_apart import HIJACK, builder

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "e6_report", REPO / "tools" / "experiments" / "e6_report.py"
)
assert _spec and _spec.loader
e6_report = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("e6_report", e6_report)
_spec.loader.exec_module(e6_report)


def test_report_counts_labels_and_marks_differences(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    folders = {}
    for name, cause in (("good", "HIJACK"), ("bad", "WIND")):
        b = builder(runs / name, [HIJACK])
        d = b.raised("det-0001", 102.0, "LINK_ANOMALY", "link")
        b.alert("ai-0002", 103.0, cause, d, ["det-0001"])
        folders[name] = b.write()
    matrix = tmp_path / "matrix"
    matrix.mkdir()
    manifest = {"runs": [
        {"profile": p, "scenario": "nominal", "rep": 1, "status": "ok", "run_id": "x"}
        for p in ("good", "bad")
    ]}  # fmt: skip
    (matrix / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    sources = []
    for p in ("good", "bad"):
        s = e6_report.parse_source(f"{p}={matrix}:{p}", runs / p)
        s.runs["nominal"] = folders[p]
        sources.append(s)
    totals = {s.name: e6_report.collect(s, ["nominal"]) for s in sources}
    assert totals["good"].labels == {"nominal/A1": "✅"}
    assert totals["bad"].labels == {"nominal/A1": "❌"}
    md = e6_report.render(sources, totals, ["nominal"])
    assert (
        "| nominal/A1 ⟵ | ✅ | ❌ |" in md
        and "| Etiquetas ✅ / con veredicto | **1/1** | **0/1** |" in md
    )


_bspec = importlib.util.spec_from_file_location(
    "e6_blind", REPO / "tools" / "experiments" / "e6_blind.py"
)
assert _bspec and _bspec.loader
e6_blind = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(e6_blind)


def test_blind_pairs_hide_the_source_and_keep_the_key_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"
    folders = {}
    for name in ("L", "H"):
        b = builder(runs / name, [HIJACK])
        d = b.raised("det-0001", 102.0, "LINK_ANOMALY", "link")
        b.alert("ai-0002", 103.0, "HIJACK", d, ["det-0001"], texts={"summary": f"by {name}"})
        if name == "H":
            payload = {"alert_id": "ai-0002", "text": "Interpreted.", "hypothesis": None}
            b.ev("AlertEnriched", 104.0, payload, "ai-enricher", id="ai-0003")
        folders[name] = b.write()
    # cada fuente, su carpeta (en la matriz real las dos están bajo la misma raíz)
    monkeypatch.setattr(
        e6_blind, "runs_of", lambda spec, _root: (spec[0], {"nominal": folders[spec[0]]})
    )
    out = tmp_path / "ciego"
    assert e6_blind.main(["L=m:L", "H=m:H", "--runs-root", ".", "--out", str(out)]) == 0
    pares = (out / "pares.md").read_text(encoding="utf-8")
    key = json.loads((out / "clave.json").read_text(encoding="utf-8"))["pairs"]
    assert pares.count("## P") == 1 and "ai-0002" not in pares and "Interpreted." in pares
    assert "by L" in pares and "by H" in pares
    assert sorted(key["P01"][x] for x in "AB") == ["H", "L"]
