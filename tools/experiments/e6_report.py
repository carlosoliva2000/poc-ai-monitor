"""Métricas de la E6 (paso 4): L, T y H en el conjunto reservado y dentro de la muestra.

    uv run --project ai-module-py python tools/experiments/e6_report.py \\
        --out experiments/e6-resultados.md --runs-root experiments/e6-reservado-generado \\
        T=experiments/e6-reservado-th:table H=experiments/e6-reservado-th:hybrid \\
        L1=experiments/e6-reservado-l:actual:1 L2=experiments/e6-reservado-l:actual:2

Cada fuente es `nombre=carpeta_de_la_matriz:perfil[:repetición]` (por defecto, la 1). Cada
ejecución se vuelve a evaluar en su carpeta de origen (`<runs-root>/<escenario>/<run_id>`, donde
están `labels.json`, `truth.json` y `plan.json`) **en memoria, sin escribir nada**, con el
«`UNKNOWN` honesto» aparte. Por fuente:

- etiquetas: veredictos contando **solo los avisos no ambiguos** (los 🔀 y ❔ van aparte);
- falsas alarmas, avisos dudosos tras un secuestro y avisos ambiguos (estricto y permisivo);
- ciclo de vida: recuperaciones sin `recovering`, alertas abiertas al final sin una etiqueta que
  siga en curso, rechazos de los guardrails, fallbacks, esperas agotadas y avisos sin respuesta;
- retraso de diagnóstico (de la primera detección a la primera alerta aceptada; simulado y de
  reloj) y latencia de la respuesta a cada aviso (reloj);
- en H, el enriquecimiento (publicados, rechazados y latencias).

Al final, la tabla de veredictos por etiqueta, una columna por fuente.
"""

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ai_module import evaluate as ev_mod

REPO = Path(__file__).resolve().parents[2]
OPEN_END_MARGIN_S = 5.0
"""Una alerta abierta al final está justificada si su etiqueta dura hasta el final (± margen)."""


@dataclass
class Source:
    name: str
    matrix: Path
    profile: str
    rep: int
    runs: dict[str, Path] = field(default_factory=dict)
    """Escenario → carpeta de origen de la ejecución."""


def parse_source(text: str, runs_root: Path) -> Source:
    name, _, rest = text.partition("=")
    parts = rest.split(":")
    matrix, profile = REPO / parts[0], parts[1]
    rep = int(parts[2]) if len(parts) > 2 else 1
    manifest = json.loads((matrix / "manifest.json").read_text(encoding="utf-8"))
    source = Source(name, matrix, profile, rep)
    for run in manifest["runs"]:
        if run["profile"] == profile and run["rep"] == rep and run.get("status") == "ok":
            source.runs[run["scenario"]] = runs_root / run["scenario"] / run["run_id"]
    return source


def rel(path: Path) -> str:
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def end_time(data: ev_mod.RunData) -> float:
    finished = [e["sim_time"] for e in data.events if e["type"] == "SimulationFinished"]
    return finished[0] if finished else max((e["sim_time"] for e in data.events), default=0.0)


def unjustified_open(ev: ev_mod.Evaluation) -> list[str]:
    """Alertas abiertas al final sin una etiqueta en curso hasta el final que acepte su causa."""
    end = end_time(ev.data)
    out = []
    for alert in ev.open_alerts:
        cause = alert["payload"]["cause"]
        ok = any(
            lb.end_s >= end - OPEN_END_MARGIN_S and cause in ev_mod.accepted_causes(lb)
            for lb in ev.data.labels
        )
        if not ok:
            out.append(f"{ev.data.scenario} {alert['payload']['alert_id']} {cause}")
    return out


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def p95(values: list[float]) -> float | None:
    return ev_mod.percentile(values, 0.95) if values else None


def num(value: float | None, unit: str = " s") -> str:
    if value is None:
        return "—"
    decimals = 2 if abs(value) < 1 else 1
    return f"{value:.{decimals}f}{unit}".replace(".", ",")


@dataclass
class Totals:
    labels: dict[str, str] = field(default_factory=dict)
    """`escenario/etiqueta` → veredicto."""
    false_alarms: int = 0
    doubtful: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    ambiguous_strict: int = 0
    ambiguous_permissive: int = 0
    honest: list[str] = field(default_factory=list)
    recovery_misses: list[str] = field(default_factory=list)
    open_unjustified: list[str] = field(default_factory=list)
    rejections: int = 0
    fallbacks: int = 0
    timeouts: int = 0
    unanswered: int = 0
    diag_sim: list[float] = field(default_factory=list)
    diag_wall: list[float] = field(default_factory=list)
    response_wall: list[float] = field(default_factory=list)
    enrich_published: int = 0
    enrich_rejected: int = 0
    enrich_wall: list[float] = field(default_factory=list)
    enrich_sim: list[float] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def collect(source: Source, scenarios: list[str]) -> Totals:
    t = Totals()
    for scenario in scenarios:
        folder = source.runs.get(scenario)
        if folder is None or not (folder / "timeline.jsonl").exists():
            t.missing.append(scenario)
            continue
        ev = ev_mod.evaluate(folder, honest_unknown=True)
        for r in ev.results:
            t.labels[f"{scenario}/{r.label.id}"] = r.verdict
            det, alert = r.first_detection, r.first_alert
            if det and alert:
                t.diag_sim.append(alert["sim_time"] - det.event["sim_time"])
                t.diag_wall.append(
                    ev_mod.wall_seconds(det.event["ingestion_time"], alert["ingestion_time"])
                )
        t.false_alarms += len(ev.stray_detections) + len(ev.stray_alerts) + ev.unlabeled_false
        t.doubtful += [
            f"{scenario} {w.label.id}: {', '.join(i.detection_id for i in w.detections)}"
            + (f" · {', '.join(a['payload']['alert_id'] for a in w.alerts)}" if w.alerts else "")
            for w in ev.doubtful
        ]
        for a in ev.ambiguous:
            t.ambiguous.append(
                f"{scenario} {a.item.detection_id} {a.item.rule} "
                f"{ev_mod.fmt_t(a.item.event['sim_time'])} → {a.cause} "
                f"(estricto {'✅' if a.strict_ok else '❌'}, permisivo "
                f"{'✅' if a.permissive_ok else '❌'})"
            )
            t.ambiguous_strict += a.strict_ok
            t.ambiguous_permissive += a.permissive_ok
        t.honest += [f"{scenario} {lb.id} {i.detection_id}" for lb, i in ev.honest]
        t.recovery_misses += [
            f"{scenario} {m.label_id} {m.detection_id} ({m.reason})"
            for m in ev.recovery_misses or []
        ]
        t.open_unjustified += unjustified_open(ev)
        monitor = ev.agents.get("monitor", {})
        t.rejections += monitor.get("rejections", 0)
        t.fallbacks += ev.fallbacks
        t.timeouts += ev.timeouts
        t.unanswered += len(ev.unanswered)
        t.response_wall += [
            x for i in ev.data.items if (x := ev_mod.response_latency(i)) is not None
        ]
        for record in ev.data.trace:
            enrich = record.get("enrich") if record.get("agent") == "enrich" else None
            if not enrich:
                continue
            if enrich.get("published"):
                t.enrich_published += 1
                if enrich.get("enrich_latency_wall_s") is not None:
                    t.enrich_wall.append(enrich["enrich_latency_wall_s"])
                if enrich.get("enrich_latency_sim_s") is not None:
                    t.enrich_sim.append(enrich["enrich_latency_sim_s"])
            elif enrich.get("rejected"):
                t.enrich_rejected += 1
    return t


def counts(t: Totals) -> dict[str, int]:
    marks = list(t.labels.values())
    return {m: marks.count(m) for m in ("✅", "⚠️", "❌", ev_mod.AMBIGUOUS_ONLY, ev_mod.HONEST_ONLY)}


def render(sources: list[Source], totals: dict[str, Totals], scenarios: list[str]) -> str:
    names = [s.name for s in sources]
    lines = [
        "# E6 · Métricas (paso 4)",
        "",
        "Fuentes: "
        + " · ".join(f"**{s.name}** = `{rel(s.matrix)}` {s.profile} r{s.rep}" for s in sources),
        "",
        f"Escenarios ({len(scenarios)}): {', '.join(scenarios)}.",
        "",
        "Veredictos con **solo los avisos no ambiguos**; 🔀 (todos sus avisos ambiguos) y ❔ "
        "(«UNKNOWN honesto») van aparte y no cuentan como acierto ni como fallo.",
        "",
        "## Resumen",
        "",
        "| | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]

    def row(title: str, values: list[str]) -> None:
        lines.append(f"| {title} | " + " | ".join(values) + " |")

    by_name = [totals[n] for n in names]
    c = {n: counts(totals[n]) for n in names}
    scored = {n: c[n]["✅"] + c[n]["⚠️"] + c[n]["❌"] for n in names}
    row("Etiquetas ✅ / con veredicto", [f"**{c[n]['✅']}/{scored[n]}**" for n in names])
    row("⚠️ (alguna causa mal)", [str(c[n]["⚠️"]) for n in names])
    row("❌", [str(c[n]["❌"]) for n in names])
    row("🔀 (solo avisos ambiguos)", [str(c[n][ev_mod.AMBIGUOUS_ONLY]) for n in names])
    row("❔ («UNKNOWN honesto»)", [str(c[n][ev_mod.HONEST_ONLY]) for n in names])
    row("Avisos «UNKNOWN honesto»", [str(len(totals[n].honest)) for n in names])
    row("Falsas alarmas", [str(totals[n].false_alarms) for n in names])
    row("Tramos dudosos tras un secuestro", [str(len(totals[n].doubtful)) for n in names])
    row(
        "Avisos ambiguos (estricto ✅ / permisivo ✅)",
        [
            f"{len(totals[n].ambiguous)} ({totals[n].ambiguous_strict} / "
            f"{totals[n].ambiguous_permissive})"
            for n in names
        ],
    )
    lifecycle = {
        n: len(totals[n].recovery_misses)
        + len(totals[n].open_unjustified)
        + totals[n].rejections
        + totals[n].fallbacks
        for n in names
    }
    row("**Errores de ciclo de vida (suma)**", [f"**{lifecycle[n]}**" for n in names])
    row("· recuperaciones sin `recovering`", [str(len(totals[n].recovery_misses)) for n in names])
    row("· abiertas al final sin etiqueta", [str(len(totals[n].open_unjustified)) for n in names])
    row("· rechazos de los guardrails", [str(totals[n].rejections) for n in names])
    row("· fallbacks", [str(totals[n].fallbacks) for n in names])
    row("Esperas agotadas", [str(totals[n].timeouts) for n in names])
    row("Avisos sin respuesta", [str(totals[n].unanswered) for n in names])
    row("Retraso de diagnóstico, mediana (sim)", [num(median(totals[n].diag_sim)) for n in names])
    row("Retraso de diagnóstico, mediana (reloj)", [num(median(t.diag_wall)) for t in by_name])
    row(
        "Respuesta a cada aviso, mediana / p95 (reloj)",
        [
            f"{num(median(totals[n].response_wall))} / {num(p95(totals[n].response_wall))}"
            for n in names
        ],
    )
    row(
        "Enriquecimiento: publicados / rechazados",
        [
            f"{totals[n].enrich_published} / {totals[n].enrich_rejected}"
            if totals[n].enrich_published or totals[n].enrich_rejected
            else "—"
            for n in names
        ],
    )
    row(
        "Enriquecimiento, mediana / máx. (reloj · sim)",
        [
            f"{num(median(totals[n].enrich_wall))} / "
            f"{num(max(totals[n].enrich_wall) if totals[n].enrich_wall else None)} · "
            f"{num(median(totals[n].enrich_sim))} / "
            f"{num(max(totals[n].enrich_sim) if totals[n].enrich_sim else None)}"
            if totals[n].enrich_wall
            else "—"
            for n in names
        ],
    )
    missing = {n: totals[n].missing for n in names if totals[n].missing}
    if missing:
        lines += ["", "**Ejecuciones que faltan:** " + "; ".join(
            f"{n}: {', '.join(m)}" for n, m in missing.items()
        )]  # fmt: skip

    lines += ["", "## Veredictos por etiqueta", "", "| Etiqueta | " + " | ".join(names) + " |",
              "|---|" + "---|" * len(names)]  # fmt: skip
    keys = list(dict.fromkeys(k for n in names for k in totals[n].labels))
    for key in keys:
        marks = [totals[n].labels.get(key, "·") for n in names]
        flag = " ⟵" if len(set(marks)) > 1 else ""
        lines.append(f"| {key}{flag} | " + " | ".join(marks) + " |")
    lines += ["", "⟵: los veredictos difieren entre fuentes."]

    for title, attr in (
        ("Avisos ambiguos", "ambiguous"),
        ("«UNKNOWN honesto»", "honest"),
        ("Tramos dudosos tras un secuestro", "doubtful"),
        ("Recuperaciones sin `recovering`", "recovery_misses"),
        ("Alertas abiertas al final sin etiqueta en curso", "open_unjustified"),
    ):
        lines += ["", f"## {title}", ""]
        any_item = False
        for n in names:
            items = getattr(totals[n], attr)
            if items:
                any_item = True
                lines.append(f"- **{n}:** " + "; ".join(items))
        if not any_item:
            lines.append("Ninguno.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", help="nombre=carpeta:perfil[:repetición]")
    parser.add_argument("--runs-root", type=Path, default=REPO / "runs")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    sources = [parse_source(s, args.runs_root.resolve()) for s in args.sources]
    scenarios = list(dict.fromkeys(sc for s in sources for sc in s.runs))
    totals = {s.name: collect(s, scenarios) for s in sources}
    args.out.write_text(render(sources, totals, scenarios), encoding="utf-8")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
