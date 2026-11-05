"""Uso de skills, rechazos y contexto del monitor, medido sobre las trazas de una o más matrices.

Solo lee ficheros (`llm_trace.jsonl` y `timeline.jsonl` de cada ejecución): no ejecuta nada ni
usa las etiquetas del escenario. Para cada invocación del monitor con LLM saca la regla y el tipo
de aviso, la skill que le corresponde, si el modelo la cargó (y cuándo respecto a su primera
decisión), si cargó otra o una que no existe, y si su decisión coincide con lo que dice la skill
sobre los hechos que vio. Además clasifica los rechazos por tipo y da el contexto por invocación.

Uso: `python -m ai_module.monitor_usage experiments/e10 [experiments/e11-guiado ...] --out f.md`
"""

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent.guardrails import link_is_anomalous, metric_facts

DECISIONS = ("publish_alert", "acknowledge_detection", "close_alert")
SKILL_OF_RULE = {
    "ROUTE_DEVIATION": "route-deviation",
    "SOURCE_DISCREPANCY": "source-discrepancy",
    "SOURCE_SILENT": "source-discrepancy",
    "GPS_DEGRADED": "source-discrepancy",
    "LINK_ANOMALY": "link-anomaly",
}
KIND_OF_TYPE = {
    "DetectionRaised": "raised",
    "DetectionUpdated": "updated",
    "DetectionCleared": "cleared",
}
# (tipo, fragmento del mensaje de rechazo), en orden: gana el primero que coincide
REJECTION_TYPES: list[tuple[str, str]] = [
    ("repeated_call", "same call as before"),
    ("history_evidence", "request it again"),
    ("foreign_fault", "is a different problem"),
    ("link_anomalous", "link_anomalous"),
    ("recovery", "recovery"),
    ("nothing_changes", "Nothing changes"),
    ("duplicate_cause", "is open: use supersedes"),
    ("source_silent", "SOURCE_SILENT"),
    ("ids", "This invocation handles"),
    ("ids", "In this closing warning"),
    ("ids", "detection_ids"),
    ("ids", "alert_id"),
    ("cause_veto", " requires "),
    ("checks", "checks."),
    ("checks", "`checks`"),
    ("evidence", "evidence"),
]


def rejection_type(message: str) -> str:
    for name, fragment in REJECTION_TYPES:
        if fragment in message:
            return name
    return "other"


@dataclass
class Invocation:
    """Una invocación del monitor con LLM, ya interpretada."""

    label: str
    scenario: str
    run: str
    invocation_id: str
    rule: str
    kind: str
    expected_skill: str | None
    loaded: list[str]
    loaded_guided: list[str]
    load_iteration: int | None
    decision_iteration: int | None
    nonexistent: list[str]
    decision: str | None
    cause: str | None
    expected: str
    matches: bool | None
    iterations: int
    prompt_tokens: int
    completion_tokens: int
    first_prompt: int
    max_prompt: int
    duration_s: float
    rejections: list[str] = field(default_factory=list)
    cached_tokens: int | None = None
    compacted_a: int = 0
    compacted_b: int = 0
    redundant_guided: bool = False
    """El modelo volvió a cargar con `load_skill` la skill que ya le dio el modo guiado."""

    @property
    def loaded_expected(self) -> bool | None:
        if self.expected_skill is None:
            return None
        return self.expected_skill in self.loaded or self.expected_skill in self.loaded_guided

    @property
    def loaded_before_decision(self) -> bool | None:
        if self.expected_skill in self.loaded_guided:
            return True  # ya estaba en el primer mensaje
        if self.load_iteration is None:
            return None
        return self.decision_iteration is None or self.load_iteration < self.decision_iteration


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _calls(record: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [(c["index"], t) for c in record["calls"] for t in c.get("tool_calls", [])]


def _args(call: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(call.get("arguments") or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _accepted(call: dict[str, Any]) -> bool:
    result = call.get("result")
    return isinstance(result, dict) and result.get("ok") is True


def expected_decision(
    rule: str, kind: str, objective: str, calls: list[tuple[int, dict[str, Any]]]
) -> tuple[str, set[str] | None]:
    """Qué dice la skill sobre los hechos que vio la invocación. Devuelve una descripción y el
    conjunto de resultados válidos (`cause:X` o `ack`), o `None` si no se puede evaluar."""
    if kind != "raised":
        return "n/a (updated or cleared)", None
    metrics: dict[str, Any] | None = None
    gps_events: list[dict[str, Any]] = []
    link_events: list[dict[str, Any]] | None = None
    for _, call in calls:
        result = call.get("result")
        if call["name"] == "get_track_metrics" and isinstance(result, dict) and "since" in result:
            metrics = result
        if call["name"] == "get_events" and isinstance(result, dict):
            source = _args(call).get("source")
            if source == "gps":
                gps_events = list(result.get("events", []))
            elif source == "link":
                link_events = list(result.get("events", []))
    if rule == "SOURCE_SILENT":
        return "own alert SENSOR_FAULT/UNKNOWN", {"cause:SENSOR_FAULT", "cause:UNKNOWN"}
    if rule == "LINK_ANOMALY":
        if link_events is None:
            return "no data (link not looked at)", None
        if link_is_anomalous(link_events):
            return "cause HIJACK", {"cause:HIJACK"}
        return "cause SENSOR_FAULT/UNKNOWN", {"cause:SENSOR_FAULT", "cause:UNKNOWN"}
    if metrics is None:
        return "no data (get_track_metrics not called)", None
    facts = metric_facts(metrics)
    open_line = re.search(r"- Open alerts: (.*)", objective)
    open_alerts = open_line.group(1) if open_line else ""
    if rule == "GPS_DEGRADED":
        cause = "GPS_JAMMING" if facts["gps_radar_disagreed"] else "SENSOR_FAULT"
        return f"cause {cause}", {f"cause:{cause}"}
    if rule == "SOURCE_DISCREPANCY":
        if "GPS_JAMMING" in open_alerts:
            return "acknowledge (GPS_JAMMING open)", {"ack"}
        if any(e.get("fix") not in (None, "3d") for e in gps_events):
            return "cause GPS_JAMMING", {"cause:GPS_JAMMING"}
        if not gps_events:
            return "no data (GPS fix not looked at)", None
        if facts["gps_radar_disagreed"]:
            return "cause GPS_SPOOFING", {"cause:GPS_SPOOFING"}
        return "cause SENSOR_FAULT/UNKNOWN", {"cause:SENSOR_FAULT", "cause:UNKNOWN"}
    if rule == "ROUTE_DEVIATION":
        recent = re.search(r"Recent GPS alert[^:]*: yes.*?(?:cause|ai-\d+) (\w+)", objective)
        if recent and (facts["gps_radar_disagreed"] or facts["gps_jump"]):
            return f"recovery: cause {recent.group(1)}", {f"cause:{recent.group(1)}"}
        if facts["wind_notable"] and facts["wind_with_drift"]:
            return "cause WIND", {"cause:WIND"}
        if link_events is None:
            return "no data (link not looked at)", None
        if link_is_anomalous(link_events):
            return "cause HIJACK", {"cause:HIJACK"}
        return "cause HIJACK/UNKNOWN", {"cause:HIJACK", "cause:UNKNOWN"}
    return "n/a", None


def _outcome(decision: str | None, cause: str | None) -> str | None:
    if decision is None:
        return None
    if decision == "acknowledge_detection":
        return "ack"
    return f"cause:{cause}" if cause else decision


def read_invocation(
    label: str,
    scenario: str,
    run: str,
    record: dict[str, Any],
    timeline: dict[str, dict[str, Any]],
    rules: dict[str, str],
) -> Invocation:
    cause_ids = record.get("causation_ids") or [""]
    first = timeline.get(cause_ids[0], {})
    kind = KIND_OF_TYPE.get(first.get("type", ""), "?")
    detection_id = (first.get("payload") or {}).get("detection_id", "")
    rule = rules.get(detection_id, "?")
    messages = record.get("messages") or []
    objective = next((m["content"] for m in messages if m.get("role") == "user"), "") or ""
    calls = _calls(record)
    loads = [(i, c) for i, c in calls if c["name"] == "load_skill"]
    loaded = [_args(c).get("name", "") for _, c in loads if c.get("error") is None]
    nonexistent = [_args(c).get("name", "") for _, c in loads if c.get("error") is not None]
    decisions = [(i, c) for i, c in calls if c["name"] in DECISIONS]
    accepted = [c for _, c in decisions if _accepted(c)]
    last = accepted[-1] if accepted else None
    decision = last["name"] if last else None
    cause = _args(last).get("cause") if last and decision == "publish_alert" else None
    expected_text, valid = expected_decision(rule, kind, objective, calls)
    outcome = _outcome(decision, cause)
    matches = None if valid is None or outcome is None else outcome in valid
    expected_skill = SKILL_OF_RULE.get(rule) if kind in ("raised", "updated") else None
    prompts = [c["prompt_tokens"] for c in record["calls"]]
    rejected = [
        rejection_type(e) for r in record.get("guardrail_rejections", []) for e in r["errors"][:1]
    ]
    cached = [c.get("cached_tokens") for c in record["calls"]]
    memory = record.get("memory") or {}
    guided = [s["name"] for s in record.get("skills_loaded", []) if s["by"] == "guided"]
    return Invocation(
        label=label, scenario=scenario, run=run, invocation_id=record["invocation_id"],
        rule=rule, kind=kind, expected_skill=expected_skill, loaded=loaded,
        loaded_guided=guided,
        load_iteration=loads[0][0] if loads else None,
        decision_iteration=decisions[0][0] if decisions else None,
        nonexistent=nonexistent, decision=decision, cause=cause, expected=expected_text,
        matches=matches, iterations=len(record["calls"]), prompt_tokens=sum(prompts),
        completion_tokens=sum(c["completion_tokens"] for c in record["calls"]),
        first_prompt=prompts[0] if prompts else 0, max_prompt=max(prompts, default=0),
        duration_s=record.get("duration_s", 0.0), rejections=rejected,
        cached_tokens=sum(x for x in cached if x) if any(cached) else None,
        compacted_a=int(memory.get("compacted_a", 0)),
        compacted_b=int(memory.get("compacted_b", 0)),
        redundant_guided=any(name in guided for name in loaded),
    )  # fmt: skip


def load_experiment(folder: Path) -> list[Invocation]:
    """Todas las invocaciones con LLM de `<folder>/runs/<perfil>/<escenario>/<rN>/`."""
    found: list[Invocation] = []
    for trace in sorted(folder.glob("runs/*/*/*/llm_trace.jsonl")):
        run_dir = trace.parent
        profile, scenario = run_dir.parents[1].name, run_dir.parent.name
        timeline = {e["event_id"]: e for e in read_jsonl(run_dir / "timeline.jsonl")}
        rules = {
            e["payload"]["detection_id"]: e["payload"]["rule"]
            for e in timeline.values()
            if e["type"] == "DetectionRaised"
        }
        for record in read_jsonl(trace):
            if record.get("agent") != "monitor" or record.get("deterministic"):
                continue
            found.append(read_invocation(f"{folder.name}/{profile}", scenario, run_dir.name,
                                         record, timeline, rules))  # fmt: skip
    return found


def pct(part: int, whole: int) -> str:
    return "—" if whole == 0 else f"{100 * part / whole:.0f}% ({part}/{whole})"


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _cell(value: float | None, digits: int = 1) -> str:
    return "n/d" if value is None else f"{value:.{digits}f}"


def skill_table(invs: list[Invocation], key: str) -> list[str]:
    """Una fila por valor de `key` (`rule` o `scenario`), solo avisos `raised` y `updated`."""
    groups: dict[str, list[Invocation]] = defaultdict(list)
    for inv in invs:
        if inv.expected_skill is not None:
            groups[getattr(inv, key)].append(inv)
    head = key.capitalize()
    lines = [
        f"| {head} | Invocaciones | Skill que le toca | Cargó la suya | Antes de decidir | "
        "Cargó otra | Pidió una que no existe | Decisión = skill (evaluables) | "
        "Iteraciones (media) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, rows in sorted(groups.items()):
        expected = {r.expected_skill for r in rows}
        got = [r for r in rows if r.loaded_expected]
        before = [r for r in got if r.loaded_before_decision]
        other = [r for r in rows if any(s != r.expected_skill for s in r.loaded)]
        missing = [r for r in rows if r.nonexistent]
        evaluable = [r for r in rows if r.matches is not None]
        agree = [r for r in evaluable if r.matches]
        mean = sum(r.iterations for r in rows) / len(rows)
        lines.append(
            f"| {name} | {len(rows)} | {', '.join(sorted(map(str, expected)))} | "
            f"{pct(len(got), len(rows))} | {pct(len(before), len(got))} | "
            f"{pct(len(other), len(rows))} | {pct(len(missing), len(rows))} | "
            f"{pct(len(agree), len(evaluable))} | {mean:.1f} |"
        )
    return lines


def cost_table(invs: list[Invocation]) -> list[str]:
    lines = [
        "| Invocaciones con LLM | Iteraciones p50 / máx. | Latencia de invocación p50 / p95 | "
        "Tokens prompt / respuesta | Rechazos | Pico de prompt en una llamada | "
        "Compactaciones nivel A / B | Tokens de prompt en caché | Recarga la skill guiada |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    its = [float(i.iterations) for i in invs]
    dur = [i.duration_s for i in invs]
    lines.append(
        f"| {len(invs)} | {_cell(percentile(its, 0.5), 0)} / {_cell(max(its, default=None), 0)} | "
        f"{_cell(percentile(dur, 0.5))} s / {_cell(percentile(dur, 0.95))} s | "
        f"{sum(i.prompt_tokens for i in invs)} / {sum(i.completion_tokens for i in invs)} | "
        f"{sum(len(i.rejections) for i in invs)} | "
        f"{max((i.max_prompt for i in invs), default=0)} | "
        f"{sum(i.compacted_a for i in invs)} / {sum(i.compacted_b for i in invs)} | "
        f"{_cached(invs)} | {sum(i.redundant_guided for i in invs)} |"
    )
    return lines


def _cached(invs: list[Invocation]) -> str:
    """Tokens del prompt servidos desde la caché de prefijos, si vLLM los dio."""
    known = [i for i in invs if i.cached_tokens is not None]
    if not known:
        return "n/d"
    cached = sum(i.cached_tokens or 0 for i in known)
    prompt = sum(i.prompt_tokens for i in known)
    return f"{cached} de {prompt} ({100 * cached / max(prompt, 1):.0f}%)"


def rejection_table(invs: list[Invocation]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for inv in invs:
        for kind in inv.rejections:
            counts[kind] += 1
    if not counts:
        return ["Sin rechazos."]
    lines = ["| Tipo | Rechazos |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return lines


def context_series(invs: list[Invocation]) -> list[str]:
    """Tokens de prompt por invocación, en orden, por escenario (primera llamada / pico)."""
    lines = [
        "| Escenario | Ejecución | Primera llamada → pico, por invocación (en orden) |",
        "|---|---|---|",
    ]
    runs: dict[tuple[str, str], list[Invocation]] = defaultdict(list)
    for inv in invs:
        runs[(inv.scenario, inv.run)].append(inv)
    for (scenario, run), rows in sorted(runs.items()):
        series = " · ".join(
            f"{r.first_prompt}→{r.max_prompt}"
            + (
                f" (compacta A{r.compacted_a}/B{r.compacted_b})"
                if r.compacted_a or r.compacted_b
                else ""
            )
            for r in rows
        )
        lines.append(f"| {scenario} | {run} | {series} |")
    return lines


def render(invs: list[Invocation]) -> str:
    out = ["# Uso del monitor: skills, rechazos y contexto", ""]
    out += [
        "Solo invocaciones con LLM. «Decisión = skill» compara la decisión aceptada con lo que "
        "dice la skill sobre los hechos que vio la invocación (solo avisos `raised` con datos "
        "suficientes; los `updated` y `cleared` no se evalúan). «Antes de decidir»: la skill se "
        "cargó en una iteración anterior a la primera llamada de decisión.",
        "",
    ]
    for label in sorted({i.label for i in invs}):
        rows = [i for i in invs if i.label == label]
        out += [f"## {label}", "", "### Coste", ""] + cost_table(rows) + [""]
        out += ["### Por regla (avisos raised y updated)", ""] + skill_table(rows, "rule") + [""]
        out += ["### Por escenario", ""] + skill_table(rows, "scenario") + [""]
        out += ["### Rechazos por tipo", ""] + rejection_table(rows) + [""]
        out += ["### Contexto por invocación", ""] + context_series(rows) + [""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    invs = [i for folder in args.experiments for i in load_experiment(folder)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(invs), encoding="utf-8")
    print(f"{len(invs)} invocations -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
