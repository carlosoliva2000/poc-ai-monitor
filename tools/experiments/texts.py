"""Textos de una matriz para revisar su calidad: no evalúa nada, solo los extrae y los junta.

    uv run --project ai-module-py python tools/experiments/texts.py \\
        --out experiments/e13-textos.md --scenarios demo,faults --rep 1 \\
        actual=experiments/e12-cierre qwen3-14b-fp8=experiments/e13-qwen3-14b-fp8

Cada fuente es `nombre=carpeta_del_experimento[:perfil]` (el perfil se puede omitir si la carpeta
`runs/` tiene uno solo). Lee `timeline.jsonl`, `eval.json` e `informe.md` de
`<experimento>/runs/<perfil>/<escenario>/r<rep>/`. Por escenario saca, sin recortar nada:

- por etiqueta (A1, F1…), con cada modelo uno detrás de otro: las alertas publicadas (T+,
  causa, severidad, confianza, `summary`, `explanation`, `recommendation`) y los cierres y
  reconocimientos (`reason`);
- por pregunta, las respuestas completas de los chats;
- del informe, las secciones que escribe el modelo (Summary, What was seen, Monitor assessment,
  Recommendations y, desde la Fase 14.1, las Technical recommendations del anexo).
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NO_LABEL = "(no label)"
ALERT_FIELDS = ("summary", "explanation", "recommendation")


@dataclass
class Source:
    name: str
    experiment: Path
    profile: str | None = None


@dataclass
class Run:
    """Los textos de un modelo en un escenario."""

    source: str
    folder: Path
    alerts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ends: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    chats: list[tuple[str, str, str | None]] = field(default_factory=list)
    report: dict[str, str] = field(default_factory=dict)
    seen: dict[str, tuple[str, str]] = field(default_factory=dict)


def parse_source(text: str) -> Source:
    name, sep, rest = text.partition("=")
    if not sep or not name or not rest:
        raise ValueError(f"source must be name=folder[:profile], got {text!r}")
    folder, _, profile = rest.partition(":")
    return Source(name, Path(folder), profile or None)


def clock(sim_time: float) -> str:
    seconds = int(sim_time)
    return f"T+{seconds // 60:02d}:{seconds % 60:02d}"


def run_folder(source: Source, scenario: str, rep: int) -> Path | None:
    runs = source.experiment / "runs"
    profile = source.profile
    if profile is None:
        profiles = sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
        if len(profiles) != 1:
            raise ValueError(f"{source.name}: say the profile ({profiles} in {runs})")
        profile = profiles[0]
    folder = runs / profile / scenario / f"r{rep}"
    return folder if folder.is_dir() else None


def read_events(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def label_of_alerts(eval_json: dict[str, Any]) -> dict[str, str]:
    """`alert_id` → etiqueta, según la evaluación (`alert_severities`)."""
    mapping: dict[str, str] = {}
    for label, alerts in eval_json.get("alert_severities", {}).items():
        for alert in alerts:
            mapping[alert["alert_id"]] = label
    return mapping


def split_sections(markdown: str, prefix: str) -> dict[str, str]:
    """Trozos del Markdown que empiezan en un título con `prefix` (`## ` o `### `); termina en
    el siguiente título del mismo nivel o de uno superior."""
    level = len(prefix) - 1
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in markdown.splitlines():
        match = re.match(r"(#+) ", line)
        if match and len(match.group(1)) <= level:
            current = (
                sections.setdefault(line[len(prefix) :].strip(), [])
                if line.startswith(prefix)
                else None
            )
        elif current is not None:
            current.append(line)
    return {title: "\n".join(lines).strip() for title, lines in sections.items()}


def model_report_sections(
    markdown: str,
) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """Secciones del informe escritas por el modelo: (por título, «What was seen» por etiqueta).
    Formato anterior a la Fase 14.1: Summary, Monitor assessment y Recommendations. Desde la 14.1
    (informe de misión con anexo): Summary y Recommendations, y del anexo la valoración (como
    «Monitor assessment») y las «Technical recommendations»."""
    top = split_sections(markdown, "## ")
    wanted: dict[str, str] = {}
    if "Summary" in top:
        wanted["Summary"] = top["Summary"]
    assessment = top.get("Monitor assessment", "")
    # El primer párrafo («Monitor figures») lo escribe el módulo, no el modelo.
    paragraphs = [
        p for p in re.split(r"\n\s*\n", assessment) if not p.startswith("**Monitor figures**")
    ]
    if paragraphs:
        wanted["Monitor assessment"] = "\n\n".join(paragraphs).strip()
    annex = next((v for k, v in top.items() if k.startswith("Annex")), "")
    if annex:
        parts = split_sections(annex, "### ")
        if "Assessment" in parts:
            wanted["Monitor assessment"] = parts["Assessment"]
        if "Technical recommendations" in parts:
            wanted["Technical recommendations"] = parts["Technical recommendations"]
    if "Recommendations" in top:
        wanted["Recommendations"] = top["Recommendations"]
    seen: dict[str, tuple[str, str]] = {}
    anomalies = top.get("Anomalies", "")
    for title, body in split_sections(anomalies, "### ").items():
        match = re.search(r"^- \*\*What was seen:\*\* (.*)$", body, re.M)
        if match:
            seen[title.split(" ")[0]] = (title, match.group(1).strip())
    return wanted, seen


def load_run(source: Source, folder: Path) -> Run:
    run = Run(source.name, folder)
    eval_path = folder / "eval.json"
    labels = label_of_alerts(json.loads(eval_path.read_text("utf-8"))) if eval_path.exists() else {}
    events = read_events(folder / "timeline.jsonl")
    questions: dict[str, tuple[str, str]] = {}
    answers: dict[str, str] = {}
    by_detection: dict[str, str] = {}
    for event in events:
        payload = event.get("payload", {})
        if event.get("type") == "AnomalyDetected":
            label = labels.get(payload.get("alert_id", ""), NO_LABEL)
            for detection in payload.get("detection_ids", []):
                by_detection.setdefault(detection, label)
    for event in events:
        payload = event.get("payload", {})
        kind = event.get("type")
        if kind == "AnomalyDetected":
            label = labels.get(payload.get("alert_id", ""), NO_LABEL)
            run.alerts.setdefault(label, []).append(event)
        elif kind in ("AlertClosed", "DetectionAcknowledged"):
            # un fallback no lleva alert_id: se asigna por la detección
            label = labels.get(payload.get("alert_id") or "")
            label = label or by_detection.get(payload.get("detection_id", ""), NO_LABEL)
            run.ends.setdefault(label, []).append(event)
        elif kind == "OperatorMessage":
            questions[event["event_id"]] = (payload["conversation_id"], payload["text"])
        elif kind == "AgentReply":
            answers[payload["reply_to"]] = payload["text"]
    run.chats = [(conv, text, answers.get(eid)) for eid, (conv, text) in questions.items()]
    report = folder / "informe.md"
    if report.exists():
        run.report, run.seen = model_report_sections(report.read_text(encoding="utf-8"))
    return run


def quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines()) or ">"


def alert_block(event: dict[str, Any]) -> list[str]:
    p = event["payload"]
    head = (
        f"- **{clock(event['sim_time'])}** · alert `{p.get('alert_id')}` · "
        f"cause `{p.get('cause')}` · "
        f"severity `{p.get('severity')}` · confidence `{p.get('confidence')}`"
    )
    if p.get("fallback"):
        head += " · **fallback**"
    if p.get("supersedes"):
        head += f" · supersedes `{p['supersedes']}`"
    lines = [head, ""]
    for name in ALERT_FIELDS:
        lines += [
            f"  **{name}**",
            "",
            *("  " + q for q in quote(str(p.get(name) or "")).splitlines()),
            "",
        ]
    return lines


def end_block(event: dict[str, Any]) -> list[str]:
    p = event["payload"]
    what = "closure" if event["type"] == "AlertClosed" else "acknowledgement"
    ref = p.get("alert_id") or p.get("detection_id")
    head = f"- **{clock(event['sim_time'])}** · {what} of `{ref}`"
    if p.get("fallback"):
        head += " · **fallback**"
    return [head, "", *("  " + q for q in quote(str(p.get("reason") or "")).splitlines()), ""]


def render(scenarios: list[str], by_scenario: dict[str, list[Run]], missing: list[str]) -> str:
    out = ["# Texts for quality review", ""]
    out += [
        "Extracted as they are, nothing is cut or evaluated. One block per model, in turn.",
        "",
    ]
    for gap in missing:
        out += [f"- missing: {gap}", ""]
    for scenario in scenarios:
        runs = by_scenario.get(scenario, [])
        out += [f"## Scenario `{scenario}`", ""]
        labels: list[str] = []
        for run in runs:
            for label in [*run.alerts, *run.ends]:
                if label not in labels:
                    labels.append(label)
        for label in sorted(labels, key=lambda x: (x == NO_LABEL, x)):
            out += [f"### Alert {label}", ""]
            for run in runs:
                events = sorted(
                    [*run.alerts.get(label, []), *run.ends.get(label, [])],
                    key=lambda e: (e["sim_time"], e["seq"]),
                )
                if not events and label == NO_LABEL:
                    continue
                out += [f"#### {run.source} · {label}", ""]
                if not events:
                    out += ["_no alert, closure or acknowledgement_", ""]
                for event in events:
                    out += (
                        alert_block(event)
                        if event["type"] == "AnomalyDetected"
                        else end_block(event)
                    )
        out += ["### Chats", ""]
        questions: list[tuple[str, str]] = []
        for run in runs:
            for conv, text, _ in run.chats:
                if (conv, text) not in questions:
                    questions.append((conv, text))
        for conv, text in questions:
            out += [f"#### {conv} · {text}", ""]
            for run in runs:
                answer = next((a for c, t, a in run.chats if (c, t) == (conv, text)), None)
                out += [f"**{run.source}**", "", quote(answer) if answer else "_no answer_", ""]
        out += ["### Report (sections written by the model)", ""]
        for title in (
            "Summary",
            "Monitor assessment",
            "Recommendations",
            "Technical recommendations",
        ):
            if title == "Technical recommendations" and not any(title in r.report for r in runs):
                continue  # solo los informes con anexo (Fase 14.1) lo tienen
            out += [f"#### {title}", ""]
            for run in runs:
                out += [f"**{run.source}**", "", quote(run.report.get(title, "_missing_")), ""]
        out += ["The report numbers its anomalies itself (A1, A2…), not like the labels above.", ""]
        seen_labels = sorted({label for run in runs for label in run.seen})
        for label in seen_labels:
            out += [f"#### What was seen · report {label}", ""]
            for run in runs:
                title, text = run.seen.get(label, ("", "_missing_"))
                out += [f"**{run.source}**" + (f" — {title}" if title else ""), "", quote(text), ""]
    return "\n".join(out).rstrip() + "\n"


def build(sources: list[Source], scenarios: list[str], rep: int) -> str:
    by_scenario: dict[str, list[Run]] = {}
    missing: list[str] = []
    for scenario in scenarios:
        for source in sources:
            folder = run_folder(source, scenario, rep)
            if folder is None:
                missing.append(f"{source.name} · {scenario} · r{rep}")
                continue
            by_scenario.setdefault(scenario, []).append(load_run(source, folder))
    return render(scenarios, by_scenario, missing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sources", nargs="+", help="nombre=carpeta[:perfil]")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenarios", default="demo,faults")
    parser.add_argument("--rep", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        sources = [parse_source(s) for s in args.sources]
        text = build(sources, args.scenarios.split(","), args.rep)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
