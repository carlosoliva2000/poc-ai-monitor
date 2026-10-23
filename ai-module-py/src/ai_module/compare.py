"""Comparativa de un experimento: `experiments/<id>/compare.md`.

    uv run --project ai-module-py python -m ai_module.compare experiments/<id>

Lee `manifest.json` y, de cada ejecución copiada en `runs/<perfil>/<escenario>/r<k>/`, su
`eval.json` y su `llm_trace.jsonl`. Por perfil y escenario resume los aciertos por etiqueta
(k/N), cadenas, fallbacks, alertas abiertas, frases que contradicen, caracteres no latinos,
rechazos de guardrails, respuestas cortadas por longitud, latencia, tokens y estabilidad (si las N
repeticiones dan las mismas causas, cadenas y cierres). Es puro: no ejecuta nada.
"""

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NON_LATIN_AGENTS = ("monitor", "report", "chat-monitor", "chat-report")


@dataclass
class RunRecord:
    profile: str
    scenario: str
    rep: int
    status: str
    """`ok` | `failed` | `missing` (sin `eval.json`)."""
    eval: dict[str, Any] = field(default_factory=dict)
    calls: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    """Llamadas al LLM de la traza, por agente."""
    durations: list[float] = field(default_factory=list)
    """Duración de las invocaciones del monitor con LLM."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_runs(folder: Path) -> tuple[dict[str, Any], list[RunRecord]]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    records = []
    for run in manifest["runs"]:
        path = folder / "runs" / run["profile"] / run["scenario"] / f"r{run['rep']}"
        eval_path = path / "eval.json"
        record = RunRecord(run["profile"], run["scenario"], run["rep"], run["status"])
        if eval_path.exists():
            record.eval = json.loads(eval_path.read_text(encoding="utf-8"))
            for t in read_jsonl(path / "llm_trace.jsonl"):
                record.calls.setdefault(t["agent"], []).extend(t["calls"])
                if t["agent"] == "monitor" and not t.get("deterministic"):
                    record.durations.append(t["duration_s"])
        else:
            record.status = "missing" if record.status == "ok" else record.status
        records.append(record)
    return manifest, records


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def fmt(value: float | None, unit: str = "", decimals: int = 1) -> str:
    return "n/d" if value is None else f"{value:.{decimals}f}{unit}"


def signature(record: RunRecord) -> tuple[Any, ...]:
    """Causas, cadenas y cierres por etiqueta, más las alertas abiertas al final."""
    labels = sorted(record.eval.get("labels", []), key=lambda lb: lb["id"])
    return (
        tuple((lb["id"], tuple(lb["causes"]), lb["chains"], lb["closures"]) for lb in labels),
        len(record.eval.get("open_alerts", [])),
    )


def describe(sig: tuple[Any, ...]) -> str:
    labels, open_alerts = sig
    parts = [f"{i} {'/'.join(c) or '—'} ×{ch} cadenas, {cl} cierres" for i, c, ch, cl in labels]
    return "; ".join(parts) + f"; {open_alerts} abiertas"


def stability(runs: list[RunRecord], planned: int) -> str:
    done = [r for r in runs if r.status == "ok"]
    if not done:
        return "n/d"
    counts = Counter(signature(r) for r in done)
    sig, top = counts.most_common(1)[0]
    if len(counts) == 1 and len(done) == planned:
        return f"estable ({len(done)}/{planned})" if planned > 1 else "1 repetición"
    text = f"{top}/{planned} iguales"
    others = [describe(s) for s in counts if s != sig]
    return text + (" — otras: " + " | ".join(others) if others else "")


def total(runs: list[RunRecord], getter: Any) -> int:
    return sum(getter(r.eval) for r in runs if r.status == "ok")


def hits_by_label(runs: list[RunRecord], planned: int) -> str:
    verdicts: dict[str, list[str]] = {}
    for r in runs:
        if r.status == "ok":
            for lb in r.eval["labels"]:
                verdicts.setdefault(lb["id"], []).append(lb["verdict"])
    if not verdicts:
        return "sin etiquetas" if any(r.status == "ok" for r in runs) else "n/d"
    return " · ".join(
        f"{label} {sum(v == '✅' for v in v_list)}/{planned}"
        for label, v_list in sorted(verdicts.items())
    )


def chains_summary(runs: list[RunRecord], planned: int) -> str:
    """Cuántas veces cada etiqueta tuvo exactamente una cadena."""
    ones: Counter[str] = Counter()
    seen: set[str] = set()
    for r in runs:
        if r.status == "ok":
            for lb in r.eval["labels"]:
                seen.add(lb["id"])
                ones[lb["id"]] += lb["chains"] == 1
    if not seen:
        return "—"
    return " · ".join(f"{label} {ones[label]}/{planned}" for label in sorted(seen))


def agent_total(runs: list[RunRecord], agent: str, key: str) -> int:
    return total(runs, lambda e: e["agents"].get(agent, {}).get(key, 0))


def non_latin(runs: list[RunRecord]) -> str:
    """Textos con caracteres no latinos: monitor / informe / chats."""

    def count(*agents: str) -> int:
        return total(
            runs,
            lambda e: sum(
                e.get("non_latin", {}).get(a, {}).get("texts_with_non_latin", 0) for a in agents
            ),
        )

    return f"{count('monitor')} / {count('report')} / {count('chat-monitor', 'chat-report')}"


def length_cuts(runs: list[RunRecord]) -> str:
    cuts = {
        a: agent_total(runs, a, "length_cuts")
        for a in ("monitor", "report", "chat-monitor", "chat-report")
    }
    return f"{cuts['monitor']} / {cuts['report']} / {cuts['chat-monitor'] + cuts['chat-report']}"


def mean_tokens(runs: list[RunRecord]) -> str:
    done = [r for r in runs if r.status == "ok"]
    if not done:
        return "n/d"

    def per_run(key: str) -> float:
        return statistics.fmean(sum(a.get(key, 0) for a in r.eval["agents"].values()) for r in done)

    reported = any(
        a.get("reasoning_tokens_reported") for r in done for a in r.eval["agents"].values()
    )
    chars = statistics.fmean(
        sum(a.get("reasoning_chars", 0) for a in r.eval["agents"].values()) for r in done
    )
    reasoning = f"{per_run('reasoning_tokens'):.0f}" if reported else f"n/d ({chars:.0f} car.)"
    return f"{per_run('prompt_tokens'):.0f} / {per_run('completion_tokens'):.0f} / {reasoning}"


def latency(runs: list[RunRecord]) -> str:
    """Por llamada del monitor, y por invocación (p50 / p95)."""
    calls = [c["latency_s"] for r in runs for c in r.calls.get("monitor", [])]
    durations = [d for r in runs for d in r.durations]
    per_call = f"{fmt(percentile(calls, 0.5), ' s')} / {fmt(percentile(calls, 0.95), ' s')}"
    p50, p95 = percentile(durations, 0.5), percentile(durations, 0.95)
    return f"{per_call} · inv. {fmt(p50, ' s')} / {fmt(p95, ' s')}"


HEADERS = [
    "Perfil", "Aciertos (✅ por etiqueta)", "1 cadena", "Falsas alarmas", "Fallbacks",
    "Alertas abiertas", "Frases que contradicen", "No latinos (monitor / informe / chats)",
    "Rechazos guardrails",
    "Cortes por longitud (monitor / informe / chats)", "Latencia monitor p50 / p95",
    "Tokens por ejecución (prompt / respuesta / razonamiento)", "Estabilidad",
]  # fmt: skip


def row(profile: str, runs: list[RunRecord], planned: int) -> list[str]:
    failed = sum(r.status != "ok" for r in runs)
    name = f"`{profile}`" + (f" ({failed} sin resultado)" if failed else "")
    return [
        name,
        hits_by_label(runs, planned),
        chains_summary(runs, planned),
        str(total(runs, lambda e: e["false_alarms"])),
        str(total(runs, lambda e: e["fallbacks"])),
        str(total(runs, lambda e: len(e["open_alerts"]))),
        str(total(runs, lambda e: len(e["contradictions"]))),
        non_latin(runs),
        str(sum(agent_total(runs, a, "rejections") for a in NON_LATIN_AGENTS)),
        length_cuts(runs),
        latency(runs),
        mean_tokens(runs),
        stability(runs, planned),
    ]


def render(manifest: dict[str, Any], records: list[RunRecord]) -> str:
    profiles = list(manifest["profiles"])
    scenarios = list(manifest["scenarios"])
    reps = manifest["reps"]
    git = manifest.get("git", {})
    dirty = " (con cambios sin guardar)" if git.get("dirty") else ""
    names = ", ".join(f"`{p}`" for p in profiles)
    lines = [
        f"# Comparativa · {manifest['id']}",
        "",
        f"Perfiles: {names} · escenarios: {', '.join(scenarios)} · repeticiones: {reps} · "
        f"huella de `agent-assets`: {manifest.get('assets_fingerprint', 'n/d')[:16]} · "
        f"vLLM: {manifest.get('vllm_version', 'n/d')} · repositorio: "
        f"{git.get('commit', 'n/d')[:10]}{dirty}",
        "",
        "Los contadores (falsas alarmas, fallbacks, alertas abiertas, frases, rechazos, cortes, "
        "no latinos) son **sumas de las N repeticiones**; los tokens, la media por ejecución; "
        "la latencia, percentiles de todas las llamadas del monitor (y de sus invocaciones).",
    ]
    for scenario in scenarios:
        lines += [
            "",
            f"## {scenario}",
            "",
            "| " + " | ".join(HEADERS) + " |",
            "|" + "---|" * len(HEADERS),
        ]
        for profile in profiles:
            runs = [r for r in records if r.profile == profile and r.scenario == scenario]
            lines.append("| " + " | ".join(row(profile, runs, reps)) + " |")
    lines += ["", "## Detalle de las repeticiones", ""]
    for scenario in scenarios:
        for profile in profiles:
            runs = [r for r in records if r.profile == profile and r.scenario == scenario]
            lines.append(f"- **{scenario} · `{profile}`**")
            for r in runs:
                if r.status != "ok":
                    lines.append(f"  - r{r.rep}: sin resultado ({r.status})")
                else:
                    lines.append(f"  - r{r.rep}: {r.eval['summary']} — {describe(signature(r))}")
    return "\n".join(lines) + "\n"


def write_compare(folder: Path) -> Path:
    manifest, records = load_runs(folder)
    path = folder / "compare.md"
    path.write_text(render(manifest, records), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera compare.md de un experimento")
    parser.add_argument("folder", type=Path, help="experiments/<id>")
    args = parser.parse_args(argv)
    print(f"→ {write_compare(args.folder)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
