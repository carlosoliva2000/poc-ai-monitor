"""Los hechos del informe, escritos por el módulo de forma determinista.

La cronología, los T+ de detección, alerta y cierre, la severidad, el estado y las evidencias de
cada anomalía salen del estado del monitor (`MonitorState`), no del LLM. El LLM solo redacta el
resumen, «qué se vio» de cada anomalía, la valoración del monitor y las recomendaciones
(`parse_narrative` lee su respuesta). Este módulo es puro: sin E/S y probado.

Una **anomalía** es una cadena de alertas (cada una sustituye a la anterior con `supersedes`): se
cuenta con la hora y la severidad de su primera alerta y, si cambian, las de la última.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .monitor_state import CHECK_LABELS, AlertRecord, DetectionRecord, MonitorState
from .outbox import format_t

CAUSE_NAMES = {
    "WIND": "Wind",
    "HIJACK": "Drone hijacking",
    "GPS_SPOOFING": "GPS spoofing",
    "SENSOR_FAULT": "Sensor fault",
    "GPS_JAMMING": "GPS loss or interference",
    "UNKNOWN": "Unknown cause",
}
SEVERITY_NAMES = {"low": "low", "medium": "medium", "high": "high"}
COMPLETION_NAMES = {"returned_to_base": "returned to base", "timeout": "timed out"}
AID_NAMES = {
    "tool_choice": 'tool_choice "required" (always answering with a tool call)',
    "final_iteration_response_tools_only": "last iteration with only the response tools",
    "require_checks": "mandatory checks (`checks`) before the cause",
    "coherence_guardrail": "coherence guardrail, including the exclusive GPS recovery",
    "computed_facts": "facts computed by the platform (notable wind, GPS–radar "
    "discrepancy, GPS jump)",
    "source_silent_own_alert": "own alert for a silent source (no acknowledgement, no superseding "
    "an alert of another cause)",
    "no_duplicate_cause": "no new alert with the cause of an open one (supersede or acknowledge)",
}
CLOSE_GAP_S = 5.0  # desfase entre el fin de la detección y el cierre a partir del cual se explica
MISSING = "Not available: the agent did not write this section."
LIMITATIONS = (
    "The data is simulated and the monitor only saw what had happened up to each instant. The "
    "times, severities, statuses and evidence in this report are written by the module from the "
    'events; the summary, "what was seen", the assessment and the recommendations are written by '
    "a language model with that same data, without knowing what the simulator really did."
)


def num(value: float, decimals: int = 1) -> str:
    """Número con punto decimal."""
    return f"{value:.{decimals}f}"


def cause_name(cause: str) -> str:
    return CAUSE_NAMES.get(cause, cause)


def severity_name(severity: str) -> str:
    return SEVERITY_NAMES.get(severity, severity)


@dataclass
class Anomaly:
    """Una cadena de alertas del monitor y las detecciones que atiende."""

    label: str
    chain: list[AlertRecord]
    """De la primera alerta a la vigente."""
    detections: list[DetectionRecord]

    @property
    def first(self) -> AlertRecord:
        return self.chain[0]

    @property
    def last(self) -> AlertRecord:
        return self.chain[-1]

    @property
    def detected_at(self) -> float:
        return min((d.since for d in self.detections), default=self.first.sim_time)

    @property
    def delay_s(self) -> float:
        return max(0.0, self.first.sim_time - self.detected_at)

    @property
    def closed_at(self) -> float | None:
        return self.last.closed_at

    @property
    def changes(self) -> str:
        """Qué cambió entre la primera alerta y la última."""
        changes = []
        if self.last.cause != self.first.cause:
            changes.append(f"cause {cause_name(self.first.cause)} → {cause_name(self.last.cause)}")
        if self.last.severity != self.first.severity:
            changes.append(
                f"severity {severity_name(self.first.severity)} → "
                f"{severity_name(self.last.severity)}"
            )
        return "; ".join(changes) or "no change of cause or severity"

    @property
    def status(self) -> str:
        """Estado final: abierta, o cerrada por el monitor. Con «esperar al agente» el cierre sale
        a la hora en que terminó la última detección; si se desvía más de `CLOSE_GAP_S` (sin
        esperar, el monitor responde mientras la simulación avanza), se añade cuándo terminó."""
        if self.closed_at is None:
            return "OPEN at the end"
        text = f"closed by the monitor at {format_t(self.closed_at)}"
        ends = [d.closed_at for d in self.detections]
        if ends and None not in ends:
            last_end = max(e for e in ends if e is not None)
            if self.closed_at - last_end > CLOSE_GAP_S:
                text += f" (the last detection of the chain ended at {format_t(last_end)})"
        return text

    def evidence_ids(self) -> list[str]:
        seen: dict[str, None] = {}
        for alert in self.chain:
            seen.update(dict.fromkeys(alert.evidence_ids))
        return list(seen)


@dataclass
class ReportFacts:
    anomalies: list[Anomaly]
    without_alert: list[DetectionRecord]
    """Detecciones que el monitor reconoció o dejó sin alerta."""
    labels: dict[str, str] = field(default_factory=dict)
    """`alert_id` → etiqueta de su anomalía (`A1`…)."""


def build_facts(state: MonitorState) -> ReportFacts:
    anomalies: list[Anomaly] = []
    for head in (a for a in state.alerts.values() if a.superseded_by is None):
        chain = [head]
        while chain[-1].supersedes in state.alerts:
            chain.append(state.alerts[chain[-1].supersedes])  # type: ignore[index]
        chain.reverse()
        detections = sorted(state.detections_of(head.alert_id), key=lambda d: d.since)
        anomalies.append(Anomaly("", chain, detections))
    anomalies.sort(key=lambda a: (a.first.sim_time, a.first.alert_id))
    labels: dict[str, str] = {}
    for number, anomaly in enumerate(anomalies, 1):
        anomaly.label = f"A{number}"
        labels.update({alert.alert_id: anomaly.label for alert in anomaly.chain})
    without_alert = [d for d in state.detections.values() if state.head(d.alert_id) is None]
    return ReportFacts(anomalies, without_alert, labels)


# --- Partes del informe que escribe el módulo ---------------------------------------------------


def header(scenario: str, summary: dict[str, Any] | None, facts: ReportFacts) -> str:
    if summary is None:
        return f"# Mission report\n\n**Scenario:** {scenario} · flight data not available"
    completed = summary["mission_completed"]
    reason = COMPLETION_NAMES.get(summary["completion_reason"], "no reason")
    reached = len(summary["waypoints_reached"])
    planned = len(summary["waypoints_planned"])
    open_alerts = sum(1 for a in facts.anomalies if a.closed_at is None)
    return (
        f"# Mission report {summary['mission_id']}\n\n"
        f"**Scenario:** {scenario} · **Duration:** {format_t(summary['duration_s'])[2:]} · "
        f"**Mission completed:** {'yes' if completed else 'no'} ({reason}) · "
        f"**Waypoints reached:** {reached} of {planned} · "
        f"**Anomalies:** {len(facts.anomalies)} (open at the end: {open_alerts})"
    )


def timeline_table(state: MonitorState, facts: ReportFacts, summary: dict[str, Any] | None) -> str:
    rows: list[tuple[float, int, str, str]] = []
    if summary is not None:
        rows.append((0.0, 0, "Mission", f"Start of mission {summary['mission_id']}"))
        end = COMPLETION_NAMES.get(summary["completion_reason"], "the mission had not finished")
        rows.append((summary["duration_s"], 5, "Mission", f"End of mission: {end}"))
    for d in state.detections.values():
        source = f" {d.source}" if d.source else ""
        opened = severity_name(d.opened_severity or d.severity)
        what = f"{d.detection_id} {d.rule}{source} ({opened}): {d.message}"
        rows.append((d.since, 1, "Detector", what))
        for at, severity, _, message in d.updates:
            what = (
                f"{d.detection_id} {d.rule}{source} rises to {severity_name(severity)}: {message}"
            )
            rows.append((at, 1, "Detector", what))
        if d.closed_at is not None:
            peak = f"; maximum {num(d.max_value)} {d.unit}" if d.max_value is not None else ""
            lasted = f"lasted {num(d.closed_at - d.since, 0)} s{peak}"
            rows.append(
                (
                    d.closed_at,
                    3,
                    "Detector",
                    f"{d.detection_id} {d.rule}{source} cleared ({lasted})",
                )
            )
    for anomaly in facts.anomalies:
        for alert in anomaly.chain:
            replaces = f", supersedes {alert.supersedes}" if alert.supersedes else ""
            what = (
                f"Alert {alert.alert_id} ({anomaly.label}): {cause_name(alert.cause)} "
                f"({severity_name(alert.severity)}, confidence {alert.confidence:g}){replaces}"
            )
            if alert.fallback:
                what += " [fallback: the agent did not conclude]"
            rows.append((alert.sim_time, 2, "Monitor", what))
        if anomaly.closed_at is not None:
            what = f"Closure of alert {anomaly.last.alert_id} ({anomaly.label})"
            rows.append((anomaly.closed_at, 4, "Monitor", what))
    rows.sort(key=lambda r: (r[0], r[1]))
    lines = ["| Time | Source | What happened |", "|---|---|---|"]
    lines += [
        f"| {format_t(t)} | {source} | {text.replace('|', '/')} |" for t, _, source, text in rows
    ]
    return "\n".join(lines)


def anomaly_section(anomaly: Anomaly, seen: str) -> str:
    first, last = anomaly.first, anomaly.last
    rules = ", ".join(dict.fromkeys(d.rule for d in anomaly.detections)) or "no detection"
    lines = [
        f"### {anomaly.label} · {cause_name(first.cause)} "
        f"({severity_name(first.severity)}, confidence {first.confidence:g})",
        f"- **When:** detection at {format_t(anomaly.detected_at)} ({rules}), first alert at "
        f"{format_t(first.sim_time)} (diagnosis delay: {num(anomaly.delay_s)} s of "
        "simulation).",
    ]
    if last is not first:
        lines.append(
            f"- **Last alert:** {last.alert_id} at {format_t(last.sim_time)} ({anomaly.changes}; "
            f"{len(anomaly.chain)} alerts in the chain)."
        )
    lines.append(f"- **What was seen:** {seen}")
    lines.append(f"- **Evidence:** {_evidence(anomaly)}.")
    lines.append(f"- **Status:** {anomaly.status}.")
    return "\n".join(lines)


def _evidence(anomaly: Anomaly) -> str:
    detections = ", ".join(d.detection_id for d in anomaly.detections) or "none"
    events = anomaly.evidence_ids()
    shown = ", ".join(events[:6]) + (f" and {len(events) - 6} more" if len(events) > 6 else "")
    return f"detections {detections}; events cited by the monitor: {shown or 'none'}"


def without_alert_section(facts: ReportFacts) -> str:
    if not facts.without_alert:
        return ""
    lines = ["## Detections without an alert", ""]
    for d in facts.without_alert:
        end = format_t(d.closed_at) if d.closed_at is not None else "still open"
        source = f" {d.source}" if d.source else ""
        lines.append(f"- {d.detection_id} {d.rule}{source}: from {format_t(d.since)} to {end}.")
    return "\n".join(lines)


def assemble(
    scenario: str,
    summary: dict[str, Any] | None,
    state: MonitorState,
    facts: ReportFacts,
    narrative: "Narrative",
    note: str = "",
    figures: str = "",
) -> str:
    """El informe completo: los hechos del módulo con la narrativa del LLM en su sitio."""
    blocks = [header(scenario, summary, facts)]
    if note:
        blocks.append(f"> {note}")
    blocks += ["## Summary\n\n" + (narrative.summary or MISSING)]
    blocks += ["## Timeline\n\n" + timeline_table(state, facts, summary)]
    if facts.anomalies:
        sections = [
            anomaly_section(a, narrative.seen.get(a.label) or MISSING) for a in facts.anomalies
        ]
        blocks.append("## Anomalies\n\n" + "\n\n".join(sections))
    else:
        blocks.append("## Anomalies\n\nThe monitor published no alerts.")
    if (orphans := without_alert_section(facts)) != "":
        blocks.append(orphans)
    assessment = (figures + "\n\n" if figures else "") + (narrative.assessment or MISSING)
    blocks += ["## Monitor assessment\n\n" + assessment]
    blocks += ["## Recommendations\n\n" + (narrative.recommendations or MISSING)]
    blocks += ["## Limitations\n\n" + LIMITATIONS]
    return "\n\n".join(blocks)


# --- Lo que se le entrega al LLM ---------------------------------------------------------------


def anomalies_for_llm(facts: ReportFacts) -> str:
    """Cada anomalía con lo que dijo el monitor y lo que vio el detector, para «qué se vio»."""
    if not facts.anomalies:
        return "There were no alerts."
    blocks = []
    for anomaly in facts.anomalies:
        lines = [
            f"### {anomaly.label} · {cause_name(anomaly.first.cause)} — detection at "
            f"{format_t(anomaly.detected_at)}, first alert at "
            f"{format_t(anomaly.first.sim_time)}, {anomaly.status}"
        ]
        for d in anomaly.detections:
            peak = f", maximum {num(d.max_value)} {d.unit}" if d.max_value is not None else ""
            source = f" {d.source}" if d.source else ""
            lines.append(
                f"- Detector {d.detection_id} {d.rule}{source} at {format_t(d.since)}: "
                f'"{d.message}" (value {num(d.value)} {d.unit}, '
                f"threshold {num(d.threshold)} {d.unit}{peak})"
            )
            for at, severity, value, _ in d.updates:
                lines.append(
                    f"  · at {format_t(at)} rises to {severity_name(severity)} "
                    f"(value {num(value)} {d.unit})"
                )
        for alert in anomaly.chain:
            lines.append(_alert_line(alert))
        if len(anomaly.chain) > 1:
            lines.append(f"- Changes from the first alert to the last: {anomaly.changes}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _alert_line(alert: AlertRecord, max_chars: int = 600) -> str:
    explanation = alert.explanation
    if len(explanation) > max_chars:
        explanation = explanation[:max_chars] + "…"
    if alert.checks:
        checks = "; ".join(
            f"{CHECK_LABELS[k]}: {'yes' if v else 'no' if v is False else 'not looked at'}"
            for k, v in alert.checks.items()
        )
    else:
        checks = "no checks (fallback alert)"
    return (
        f"- Monitor {alert.alert_id} at {format_t(alert.sim_time)}: {cause_name(alert.cause)} "
        f'({severity_name(alert.severity)}, confidence {alert.confidence:g}) "{alert.summary}". '
        f"Explanation: {explanation} Checks: {checks}."
    )


@dataclass
class MonitorStats:
    """Cifras de las invocaciones del monitor de la ejecución (de las trazas)."""

    invocations: int
    with_llm: int
    mean_s: float
    max_s: float
    fallbacks: int
    rejections: list[dict[str, Any]]
    """Cada rechazo de un guardrail: `{"tool", "errors"}`."""
    aids: list[str]

    @property
    def deterministic(self) -> int:
        return self.invocations - self.with_llm


def monitor_stats(records: list[dict[str, Any]], aids: dict[str, Any]) -> MonitorStats:
    monitor = [r for r in records if r["agent"] == "monitor"]
    durations = [r["duration_s"] for r in monitor if not r.get("deterministic")]
    return MonitorStats(
        invocations=len(monitor),
        with_llm=len(durations),
        mean_s=sum(durations) / len(durations) if durations else 0.0,
        max_s=max(durations, default=0.0),
        fallbacks=sum(1 for r in monitor if r.get("fallback")),
        rejections=[e for r in monitor for e in r.get("guardrail_rejections", [])],
        aids=[AID_NAMES[k] for k, v in aids.items() if k in AID_NAMES and v not in (False, "auto")],
    )


def figures_line(stats: MonitorStats, facts: ReportFacts) -> str:
    """Las cifras del monitor, escritas por el módulo: el LLM no puede contradecirlas."""
    open_alerts = sum(1 for a in facts.anomalies if a.closed_at is None)
    return (
        f"**Monitor figures** (written by the module): {stats.invocations} invocations "
        f"({stats.with_llm} with LLM and {stats.deterministic} deterministic) · wall-clock "
        f"duration per LLM invocation: mean {num(stats.mean_s, 0)} s, maximum "
        f"{num(stats.max_s, 0)} s · fallbacks: {stats.fallbacks} · guardrail rejections: "
        f"{len(stats.rejections)} · alerts open at the end: {open_alerts} · active aids: "
        f"{'; '.join(stats.aids) or 'none'}."
    )


def assessment_facts(
    facts: ReportFacts, records: list[dict[str, Any]], aids: dict[str, Any]
) -> str:
    """Retrasos, fallbacks, rechazos de los guardrails y ayudas activas, para la valoración."""
    stats = monitor_stats(records, aids)
    lines = ["### Delays"]
    for a in facts.anomalies:
        lines.append(
            f"- {a.label}: the first alert arrived {num(a.delay_s)} s of simulation after "
            f"the detection; the monitor invocation that published it took "
            f"{_wall(records, a.first.alert_id)} of wall clock."
        )
    if not facts.anomalies:
        lines.append("- There were no alerts.")
    if stats.with_llm:
        lines.append(
            f"- Monitor invocations with LLM: {stats.with_llm}; mean wall-clock duration "
            f"{num(stats.mean_s, 0)} s, maximum {num(stats.max_s, 0)} s."
        )
    fallback_alerts = [a.alert_id for x in facts.anomalies for a in x.chain if a.fallback]
    lines += [
        "",
        "### Fallbacks",
        f"- Number of fallbacks (the module answered for the monitor because it did not "
        f"conclude): {stats.fallbacks}. Fallback alerts: {', '.join(fallback_alerts) or 'none'}.",
        f"- Detections without an alert: {len(facts.without_alert)}. Alerts open at the end: "
        f"{sum(1 for a in facts.anomalies if a.closed_at is None)}.",
    ]
    lines += [
        "",
        "### Guardrail rejections",
        f"- Number of monitor calls rejected by the guardrails: {len(stats.rejections)}.",
    ]
    if stats.rejections:
        by_tool: dict[str, int] = {}
        for rejection in stats.rejections:
            by_tool[rejection["tool"]] = by_tool.get(rejection["tool"], 0) + 1
        lines.append("- By tool: " + ", ".join(f"{t} {n}" for t, n in sorted(by_tool.items())))
        messages = dict.fromkeys(
            _short(error) for rejection in stats.rejections for error in rejection["errors"]
        )
        lines += [f'- Reason: "{message}"' for message in list(messages)[:6]]
    lines += ["", "### Active model aids"]
    lines += [f"- {name}" for name in stats.aids] or ["- None."]
    return "\n".join(lines)


def _wall(records: list[dict[str, Any]], alert_id: str) -> str:
    for record in records:
        if record["agent"] == "monitor" and any(
            p.get("event_id") == alert_id for p in record.get("published", [])
        ):
            return f"{record['duration_s']:.0f} s"
    return "an unknown time"


def _short(text: str, limit: int = 180) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


# --- Lo que devuelve el LLM -------------------------------------------------------------------


@dataclass
class Narrative:
    summary: str = ""
    seen: dict[str, str] = field(default_factory=dict)
    assessment: str = ""
    recommendations: str = ""

    @property
    def empty(self) -> bool:
        return not (self.summary or self.seen or self.assessment or self.recommendations)


HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$")
LABEL_RE = re.compile(r"^\s*(?:#{1,6}\s*|\*\*|[-*]\s+)?(A\d+)\b[\s:.·\-—*]*(.*)$")
# Prefijos de los títulos (sin acentos, en minúsculas): inglés y, para las ejecuciones antiguas,
# castellano.
SECTIONS = (
    ("summary", "summary"),
    ("summary", "resumen"),
    ("seen", "what was seen"),
    ("seen", "que se vio"),
    ("assessment", "monitor assessment"),
    ("assessment", "valoracion"),
    ("recommendations", "recommendations"),
    ("recommendations", "recomendaciones"),
)


def _plain(text: str) -> str:
    stripped = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").strip(" *:")


def _unfence(text: str) -> str:
    """Si el LLM envuelve su respuesta en un bloque de código, se queda con el contenido (y se
    descarta lo que escriba después del bloque)."""
    lines = text.strip().splitlines()
    if not lines or not lines[0].lstrip().startswith("```"):
        return text
    body: list[str] = []
    for line in lines[1:]:
        if line.strip().startswith("```"):
            break
        body.append(line)
    return "\n".join(body)


def parse_narrative(text: str, labels: list[str]) -> Narrative:
    """Lee los cuatro apartados de la respuesta del LLM por sus títulos (`## Summary`,
    `## What was seen` con un `### A1` por anomalía, `## Monitor assessment` y
    `## Recommendations`). Lo que falte queda vacío; cualquier otro apartado que escriba se
    ignora."""
    parts: dict[str, list[str]] = {}
    current: str | None = None
    for line in _unfence(text).splitlines():
        heading = HEADING_RE.match(line)
        if heading is not None and len(heading.group(1)) <= 2:  # título de apartado
            title = _plain(heading.group(2))
            current = next((key for key, prefix in SECTIONS if title.startswith(prefix)), None)
            if current is not None:
                parts.setdefault(current, [])
        elif current is not None:
            parts[current].append(line)
    narrative = Narrative(
        summary="\n".join(parts.get("summary", [])).strip(),
        assessment="\n".join(parts.get("assessment", [])).strip(),
        recommendations="\n".join(parts.get("recommendations", [])).strip(),
    )
    narrative.seen = _split_seen(parts.get("seen", []), labels)
    return narrative


def _split_seen(lines: list[str], labels: list[str]) -> dict[str, str]:
    seen: dict[str, list[str]] = {}
    label: str | None = None
    for line in lines:
        match = LABEL_RE.match(line)
        if match is not None and match.group(1) in labels:
            label = match.group(1)
            seen.setdefault(label, [])
            if match.group(2).strip(" *·—-:"):
                seen[label].append(match.group(2).strip())
        elif label is not None:
            seen[label].append(line)
    return {k: " ".join(" ".join(v).split()) for k, v in seen.items() if "".join(v).strip()}
