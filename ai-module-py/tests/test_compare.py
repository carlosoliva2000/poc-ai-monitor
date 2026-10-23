"""`compare.md`: aciertos k/N, estabilidad, no latinos, cortes, latencia y tokens."""

import json
from pathlib import Path
from typing import Any

from ai_module.compare import load_runs, render, signature, write_compare


def label(
    id: str,
    verdict: str = "✅",
    causes: list[str] | None = None,
    chains: int = 1,
    closures: int = 1,
) -> dict[str, Any]:
    return {"id": id, "verdict": verdict, "causes": causes or ["WIND"], "chains": chains,
            "closures": closures}  # fmt: skip


def eval_json(labels: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "resumen",
        "labels": labels,
        "false_alarms": 0,
        "fallbacks": 0,
        "open_alerts": [],
        "contradictions": [],
        "non_latin": {
            "monitor": {"texts_with_non_latin": 0},
            "report": {"texts_with_non_latin": 0},
            "chat-monitor": {"texts_with_non_latin": 1},
            "chat-report": {"texts_with_non_latin": 0},
        },
        "agents": {
            "monitor": {
                "rejections": 2, "length_cuts": 1, "prompt_tokens": 1000, "completion_tokens": 100,
                "reasoning_tokens": 30, "reasoning_tokens_reported": True, "reasoning_chars": 90,
            },
            "report": {
                "rejections": 0, "length_cuts": 0, "prompt_tokens": 500, "completion_tokens": 50,
                "reasoning_tokens": 0, "reasoning_tokens_reported": True, "reasoning_chars": 0,
            },
        },
    }  # fmt: skip
    data.update(overrides)
    return data


def make_experiment(tmp_path: Path, evals: dict[tuple[str, str, int], dict | None]) -> Path:
    """`evals`: (perfil, escenario, rep) → eval.json (o `None`: la ejecución falló)."""
    profiles = sorted({p for p, _, _ in evals})
    scenarios = sorted({s for _, s, _ in evals})
    reps = max(k for _, _, k in evals)
    runs = []
    for (profile, scenario, rep), data in evals.items():
        runs.append({"profile": profile, "scenario": scenario, "rep": rep,
                     "status": "ok" if data else "failed"})  # fmt: skip
        if data:
            folder = tmp_path / "runs" / profile / scenario / f"r{rep}"
            folder.mkdir(parents=True)
            (folder / "eval.json").write_text(json.dumps(data))
            call = {"latency_s": 1.0 + rep, "prompt_tokens": 1, "completion_tokens": 1}
            record = {"agent": "monitor", "deterministic": False, "duration_s": 5.0 * rep,
                      "calls": [call]}  # fmt: skip
            (folder / "llm_trace.jsonl").write_text(json.dumps(record) + "\n")
    manifest = {"id": "x", "profiles": {p: {} for p in profiles}, "scenarios": scenarios,
                "reps": reps, "assets_fingerprint": "e28d071e856efb09" + "0" * 48,
                "vllm_version": "0.31.0", "git": {"commit": "abc" * 13, "dirty": True},
                "runs": runs}  # fmt: skip
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def test_hits_are_k_over_n_and_equal_repetitions_are_stable(tmp_path: Path) -> None:
    good = eval_json([label("A1"), label("A2", causes=["GPS_SPOOFING"])])
    bad = eval_json([label("A1"), label("A2", "⚠️", ["GPS_SPOOFING", "HIJACK"], chains=2)])
    folder = make_experiment(
        tmp_path,
        {("p1", "demo", 1): good, ("p1", "demo", 2): good, ("p1", "demo", 3): bad,
         ("p2", "demo", 1): good, ("p2", "demo", 2): good, ("p2", "demo", 3): good},
    )  # fmt: skip
    text = write_compare(folder).read_text()
    rows = {
        line.split("|")[1].strip(): line for line in text.splitlines() if line.startswith("| `")
    }
    assert "A1 3/3 · A2 2/3" in rows["`p1`"]  # aciertos y cadenas: A2 falla 1 vez de 3
    assert "A1 3/3 · A2 3/3" in rows["`p2`"]
    assert "estable (3/3)" in rows["`p2`"]
    assert "2/3 iguales — otras:" in rows["`p1`"] and "×2 cadenas" in rows["`p1`"]
    assert "1 / 0 / 3" not in rows["`p2`"]  # no latinos: monitor / informe / chats
    assert "0 / 0 / 3" in rows["`p2`"]  # un chat con caracteres no latinos por repetición
    assert "3 / 0 / 0" in rows["`p2`"]  # cortes por longitud del monitor
    assert "1500 / 150 / 30" in rows["`p2`"]  # tokens medios por ejecución
    assert "3.0 s / 4.0 s" in rows["`p2`"]  # p50 / p95 de las llamadas del monitor
    assert "e28d071e856efb09" in text and "con cambios sin guardar" in text


def test_a_failed_run_counts_against_the_hits_and_is_listed(tmp_path: Path) -> None:
    good = eval_json([label("A1")])
    folder = make_experiment(tmp_path, {("p", "wind", 1): good, ("p", "wind", 2): None})
    text = write_compare(folder).read_text()
    row = next(line for line in text.splitlines() if line.startswith("| `p`"))
    assert "A1 1/2" in row and "(1 sin resultado)" in row
    assert "r2: sin resultado (failed)" in text and "1/2 iguales" in row


def test_signature_ignores_the_text_and_uses_causes_chains_closures_and_open_alerts() -> None:
    a = type("R", (), {})()
    a.eval = eval_json([label("A1")], summary="uno")
    b = type("R", (), {})()
    b.eval = eval_json([label("A1")], summary="otro")
    assert signature(a) == signature(b)  # type: ignore[arg-type]
    b.eval = eval_json([label("A1", closures=0)])
    assert signature(a) != signature(b)  # type: ignore[arg-type]
    b.eval = eval_json([label("A1")], open_alerts=["ai-0001"])
    assert signature(a) != signature(b)  # type: ignore[arg-type]


def test_scenario_without_labels_says_so_and_reports_false_alarms(tmp_path: Path) -> None:
    run = eval_json([], false_alarms=2)
    folder = make_experiment(tmp_path, {("p", "nominal", 1): run})
    manifest, records = load_runs(folder)
    text = render(manifest, records)
    assert "sin etiquetas" in text and "| 2 |" in text
