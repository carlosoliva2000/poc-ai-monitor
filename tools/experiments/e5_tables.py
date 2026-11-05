"""E5 · tabla por modelo y serie frente a `actual`, con media y rango entre repeticiones.

    uv run --project ai-module-py python tools/experiments/e5_tables.py \\
        --out experiments/e5-tablas.md

Lee `eval.json`, `llm_trace.jsonl` y el manifiesto de cada ejecución (`demo` y `faults`) de las
matrices de la fase y de la base `experiments/e14-4-final` (perfil `actual`, que no se repite). Un
valor es la media por ejecución y, entre paréntesis, el mínimo y el máximo; con una sola ejecución,
solo el valor. Los tokens de prompt de modelos con otro tokenizador no son comparables uno a uno
(unas 1,3 veces más con los modelos de pago).
"""

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO / "experiments"
SCENARIOS = ("demo", "faults")
# (nombre, experimento, perfil)
SERIES = [
    ("actual (Qwen3-14B)", "e14-4-final", "actual"),
    ("Haiku A", "e5-haiku-a", "claude-haiku-5-5"),
    ("Haiku A0", "e5-haiku-a0", "claude-haiku-5-5-a0"),
    ("Haiku B", "e5-haiku-b", "claude-haiku-5-5-b"),
    ("Sonnet A", "e5-sonnet-a", "claude-sonnet-5-5"),
    ("Sonnet A0", "e5-sonnet-a0", "claude-sonnet-5-5-a0"),
    ("Sonnet B", "e5-sonnet-b", "claude-sonnet-5-5-b"),
]
# (clave, título, decimales)
METRICS = [
    ("labels_ok", "Etiquetas ✅", 1),
    ("fallbacks", "Fallbacks", 1),
    ("false_alarms", "Falsas alarmas", 1),
    ("open_alerts", "Alertas abiertas", 1),
    ("contradictions", "Frases que contradicen", 1),
    ("checks_mismatches", "Checks≠tools", 1),
    ("recovery_misses", "Recuperaciones sin fase", 1),
    ("rejections", "Rechazos (llamadas)", 1),
    ("iter_p50", "Iteraciones p50", 1),
    ("iter_max", "Iteraciones máx.", 0),
    ("monitor_calls", "Llamadas del monitor", 1),
    ("prompt_k", "Prompt (miles de tokens)", 0),
    ("output_k", "Salida (miles de tokens)", 1),
    ("reasoning_k", "Razonamiento (miles de tokens)", 1),
    ("lat_p50", "Latencia llamada p50 (s)", 1),
    ("lat_p95", "Latencia llamada p95 (s)", 1),
    ("inv_max_s", "Invocación más larga (s)", 1),
    ("wall_s", "Ejecución en reloj (s)", 0),
    ("cost_usd", "Coste (USD)", 4),
]


@dataclass
class RunMetrics:
    scenario: str
    rep: int
    values: dict[str, float]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def count(value: Any) -> int:
    """Un contador de `eval.json` que unas veces es un número y otras una lista."""
    return len(value) if isinstance(value, list) else int(value)


def run_metrics(folder: Path, scenario: str, rep: int, manifest_run: dict[str, Any]) -> RunMetrics:
    ev = json.loads((folder / "eval.json").read_text(encoding="utf-8"))
    monitor = ev["agents"].get("monitor", {})
    iterations: list[int] = []
    inv_durations: list[float] = []
    for line in (folder / "llm_trace.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["agent"] == "monitor" and record["calls"]:
            iterations.append(len(record["calls"]))
            inv_durations.append(record.get("duration_s", 0.0))
    agents = ev["agents"].values()
    contradictions = ev["contradictions"]
    mismatches = ev["checks_mismatches"]
    values = {
        "labels_ok": sum(1 for x in ev["labels"] if x["verdict"] == "✅"),
        "fallbacks": ev["fallbacks"],
        "false_alarms": ev["false_alarms"],
        "open_alerts": count(ev["open_alerts"]),
        "contradictions": len(contradictions)
        if isinstance(contradictions, list)
        else contradictions,
        "checks_mismatches": len(mismatches["mismatches"]) if isinstance(mismatches, dict) else 0,
        "recovery_misses": len(ev["recovery_misses"])
        if isinstance(ev["recovery_misses"], list)
        else 0,
        "rejections": monitor.get("rejections", 0),
        "iter_p50": statistics.median(iterations) if iterations else 0,
        "iter_max": max(iterations, default=0),
        "monitor_calls": monitor.get("llm_calls", 0),
        "prompt_k": sum(a.get("prompt_tokens", 0) for a in agents) / 1000,
        "output_k": sum(a.get("completion_tokens", 0) for a in agents) / 1000,
        "reasoning_k": sum(a.get("reasoning_tokens", 0) or 0 for a in agents) / 1000,
        "lat_p50": monitor.get("latency_p50", 0),
        "lat_p95": monitor.get("latency_p95", 0),
        "inv_max_s": max(inv_durations, default=0.0),
        "wall_s": manifest_run.get("wall_s", 0),
        "cost_usd": manifest_run.get("cost_usd", 0),
    }
    return RunMetrics(scenario, rep, values)


def load_series(experiment: str, profile: str) -> list[RunMetrics]:
    folder = EXPERIMENTS / experiment
    if not (folder / "manifest.json").exists():
        return []
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    out: list[RunMetrics] = []
    for entry in manifest["runs"]:
        if entry["profile"] != profile or entry["scenario"] not in SCENARIOS:
            continue
        if entry["status"] != "ok":
            continue
        run = folder / "runs" / profile / entry["scenario"] / f"r{entry['rep']}"
        out.append(run_metrics(run, entry["scenario"], entry["rep"], entry))
    return out


def cell(values: list[float], decimals: int, show_range: bool = True) -> str:
    if not values:
        return "–"
    mean = statistics.mean(values)
    text = f"{mean:.{decimals}f}"
    if show_range and len(values) > 1 and min(values) != max(values):
        text += f" ({min(values):.{decimals}f}–{max(values):.{decimals}f})"
    return text


def render(all_series: dict[str, list[RunMetrics]]) -> str:
    lines = [
        "# E5 · modelos de pago frente a `actual`",
        "",
        __doc__.split("\n\n")[2].replace("\n", " "),
        "",
        "Series: **A** con las ayudas de `actual`, **A0** con ellas y sin razonamiento previo "
        "(Sonnet: `between_tools`, que solo quita el razonamiento previo), **B** sin ayudas. "
        "`actual`: 3 repeticiones; Haiku: 3; Sonnet: 1.",
        "",
    ]
    for scenario in SCENARIOS:
        lines += [f"## {scenario}", ""]
        names = [n for n, runs in all_series.items() if any(r.scenario == scenario for r in runs)]
        lines += ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for key, title, decimals in METRICS:
            row = []
            for name in names:
                values = [r.values[key] for r in all_series[name] if r.scenario == scenario]
                row.append(cell(values, decimals))
            lines.append(f"| {title} | " + " | ".join(row) + " |")
        lines.append("")
    lines += ["## Coste de la serie (USD, suma de sus ejecuciones)", ""]
    lines += ["| Serie | Ejecuciones | Coste |", "|---|---|---|"]
    for name, runs in all_series.items():
        if runs and any(r.values["cost_usd"] for r in runs):
            total = sum(r.values["cost_usd"] for r in runs)
            lines.append(f"| {name} | {len(runs)} | {total:.4f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=EXPERIMENTS / "e5-tablas.md")
    args = parser.parse_args(argv)
    all_series = {name: load_series(exp, profile) for name, exp, profile in SERIES}
    all_series = {n: r for n, r in all_series.items() if r}
    args.out.write_text(render(all_series), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(
            {n: [{"scenario": r.scenario, "rep": r.rep, **r.values} for r in runs]
             for n, runs in all_series.items()},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )  # fmt: skip
    print(f"{args.out} ({len(all_series)} series)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
