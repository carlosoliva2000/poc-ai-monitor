"""Evaluación de una ejecución contra las etiquetas del escenario (`labels.json`).

    uv run --project ai-module-py python -m ai_module.evaluate runs/<escenario>/<run_id>

Lee `timeline.jsonl`, `llm_trace.jsonl`, `run_meta.json` (si existe) y la `labels.json` del
escenario, y escribe `eval.md` y `eval.json` en la carpeta de la ejecución. **Es el único módulo
que lee las etiquetas**; el código de los agentes no las usa ni importa nada de aquí.

Atribución: una detección va a la etiqueta cuya `eval_window` la contiene y cuyas
`expected_rules` incluyen su regla (si hay varias, a la de inicio más reciente; en
`SOURCE_SILENT`, la fuente ha de ser la del fallo). Su causa es la de la respuesta al aviso
`DetectionRaised`: la alerta, o la alerta a la que la enlaza el `DetectionAcknowledged`; una
respuesta de fallback es «sin diagnóstico». Acierta si la causa está en
`{expected_cause} ∪ also_accepted_causes`. Los fallos manuales generan etiquetas sintéticas.
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from poc_contracts.enums import Cause, LabelType, Rule
from poc_contracts.run_files import Label, LabelsFile

Event = dict[str, Any]
GPS_CAUSES = {"GPS_SPOOFING", "GPS_JAMMING", "SENSOR_FAULT"}
WAIT_CAP_S = 89.0  # una espera de esta duración llegó al tope de la plataforma (90 s)
NO_DIAGNOSIS = "sin diagnóstico"
NO_ALERT = "sin alerta"
NO_RESPONSE = "sin respuesta"
DETECTION_TYPES = ("DetectionRaised", "DetectionUpdated", "DetectionCleared")
RESPONSE_TYPES = ("AnomalyDetected", "AlertClosed", "DetectionAcknowledged")
KIND_LETTER = {"Raised": "R", "Updated": "U", "Cleared": "C"}


def fmt_t(sim_time: float) -> str:
    total = int(sim_time)
    return f"T+{total // 60:02d}:{total % 60:02d}"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def wall_seconds(start: str, end: str) -> float:
    """Segundos de reloj entre dos `ingestion_time` ISO."""
    return (_parse(end) - _parse(start)).total_seconds()


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _num(value: float | None, unit: str = "", decimals: int = 1) -> str:
    return "—" if value is None else f"{value:.{decimals}f}{unit}".replace(".", ",")


# --- Etiquetas -------------------------------------------------------------------------------


def synthetic_labels(events: list[Event]) -> list[Label]:
    """Etiquetas de los fallos manuales (`FaultInjected` con `origin: manual`)."""
    end_time = max((e["sim_time"] for e in events), default=0.0)
    open_faults: dict[tuple[str, str], Event] = {}
    spans: list[tuple[Event, float]] = []
    for e in events:
        p = e["payload"]
        if e["type"] == "FaultInjected" and p["origin"] == "manual":
            open_faults[(p["source"], p["mode"])] = e
        elif e["type"] == "FaultCleared" and p["origin"] == "manual":
            start = open_faults.pop((p["source"], p["mode"]), None)
            if start is not None:
                spans.append((start, e["sim_time"]))
    spans += [(e, end_time) for e in open_faults.values()]
    labels: list[Label] = []
    for number, (start, end) in enumerate(sorted(spans, key=lambda s: s[0]["sim_time"]), 1):
        p = start["payload"]
        loss = p["mode"] == "loss"
        labels.append(
            Label(
                id=f"F{100 + number}",
                type=LabelType.GPS_LOSS if loss else LabelType.SOURCE_SILENT,
                source=p["source"],
                start_s=start["sim_time"],
                end_s=end,
                expected_rules=(
                    [Rule.GPS_DEGRADED, Rule.SOURCE_DISCREPANCY, Rule.ROUTE_DEVIATION]
                    if loss
                    else [Rule.SOURCE_SILENT]
                ),
                expected_cause=Cause.GPS_JAMMING if loss else Cause.SENSOR_FAULT,
                also_accepted_causes=[Cause.SENSOR_FAULT] if loss else [],
                eval_window=(start["sim_time"], end + 60.0),
            )
        )
    return labels


def accepted_causes(label: Label) -> set[str]:
    return {label.expected_cause.value, *(c.value for c in label.also_accepted_causes)}


# --- Modelo de la ejecución --------------------------------------------------------------------


@dataclass
class Response:
    """Lo que el monitor respondió a un evento de detección."""

    event: Event
    kind: str
    """`alerta` | `supersedes` | `acknowledge` | `cierre`."""
    cause: str | None
    alert_id: str | None
    fallback: bool
    deterministic: bool


@dataclass
class Item:
    """Un evento de detección con sus respuestas y su atribución."""

    event: Event
    label: Label | None = None
    responses: list[Response] = field(default_factory=list)

    @property
    def detection_id(self) -> str:
        return self.event["payload"]["detection_id"]

    @property
    def kind(self) -> str:
        return self.event["type"].removeprefix("Detection")

    @property
    def rule(self) -> str:
        return self.event["payload"]["rule"]

    @property
    def first(self) -> Response | None:
        return self.responses[0] if self.responses else None

    def cause(self) -> str:
        """Causa atribuida a este aviso, por su primera respuesta."""
        r = self.first
        if r is None:
            return NO_RESPONSE
        if r.fallback and r.cause in (None, "UNKNOWN") and r.kind != "cierre":
            return NO_DIAGNOSIS
        return r.cause or NO_ALERT


class RunData:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.scenario = folder.parent.name
        self.events = read_jsonl(folder / "timeline.jsonl")
        self.trace = read_jsonl(folder / "llm_trace.jsonl")
        meta_path = folder / "run_meta.json"
        self.meta: dict[str, Any] = (
            json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        )
        labels_path = folder.parent / "labels.json"
        file_labels = (
            LabelsFile.model_validate_json(labels_path.read_text(encoding="utf-8")).labels
            if labels_path.exists()
            else []
        )
        self.labels: list[Label] = [*file_labels, *synthetic_labels(self.events)]
        self.alerts: dict[str, Event] = {
            e["payload"]["alert_id"]: e for e in self.events if e["type"] == "AnomalyDetected"
        }
        self.closed: dict[str, Event] = {
            e["payload"]["alert_id"]: e for e in self.events if e["type"] == "AlertClosed"
        }
        self.deterministic_ids = {
            p["event_id"] for t in self.trace if t.get("deterministic") for p in t["published"]
        }
        self.items = self._items()

    # --- Alertas y cadenas ----------------------------------------------------------------

    def root_of(self, alert_id: str) -> str:
        seen: set[str] = set()
        while alert_id in self.alerts and alert_id not in seen:
            seen.add(alert_id)
            parent = self.alerts[alert_id]["payload"]["supersedes"]
            if parent is None or parent not in self.alerts:
                break
            alert_id = parent
        return alert_id

    def open_alerts_at_end(self) -> list[Event]:
        superseded = {
            e["payload"]["supersedes"] for e in self.alerts.values() if e["payload"]["supersedes"]
        }
        return [
            e for aid, e in self.alerts.items() if aid not in superseded and aid not in self.closed
        ]

    # --- Avisos, respuestas y atribución ----------------------------------------------------

    def _items(self) -> list[Item]:
        by_cause: dict[str, list[Event]] = defaultdict(list)
        for e in self.events:
            if e["source"] == "ai-monitor" and e["type"] in RESPONSE_TYPES and e["causation_id"]:
                by_cause[e["causation_id"]].append(e)
        items = [
            Item(e, responses=[self._response(r) for r in by_cause.get(e["event_id"], [])])
            for e in self.events
            if e["type"] in DETECTION_TYPES
        ]
        label_of: dict[str, Label | None] = {}
        for item in items:
            if item.kind == "Raised":
                label_of[item.detection_id] = self._attribute(item)
        for item in items:
            item.label = label_of.get(item.detection_id)
        return items

    def _response(self, event: Event) -> Response:
        p = event["payload"]
        deterministic = event["event_id"] in self.deterministic_ids
        if event["type"] == "AnomalyDetected":
            kind = "supersedes" if p["supersedes"] else "alerta"
            return Response(event, kind, p["cause"], p["alert_id"], p["fallback"], deterministic)
        alert = self.alerts.get(p["alert_id"]) if p["alert_id"] else None
        cause = alert["payload"]["cause"] if alert else None
        kind = "cierre" if event["type"] == "AlertClosed" else "acknowledge"
        fallback = False if kind == "cierre" else p["fallback"]
        return Response(event, kind, cause, p["alert_id"], fallback, deterministic)

    def _attribute(self, item: Item) -> Label | None:
        p = item.event["payload"]
        t = item.event["sim_time"]
        candidates = [
            lb
            for lb in self.labels
            if lb.eval_window[0] <= t <= lb.eval_window[1]
            and Rule(p["rule"]) in lb.expected_rules
            and (
                p["rule"] != "SOURCE_SILENT" or lb.source is None or lb.source.value == p["source"]
            )
        ]
        return max(candidates, key=lambda lb: lb.start_s, default=None)


# --- Análisis ----------------------------------------------------------------------------------


@dataclass
class LabelResult:
    label: Label
    raised: list[Item]
    wrong: list[Item]
    first_detection: Item | None
    first_alert: Event | None
    chains: int
    verdict: str


def analyze_labels(data: RunData) -> list[LabelResult]:
    out = []
    for label in data.labels:
        ok = accepted_causes(label)
        raised = [i for i in data.items if i.kind == "Raised" and i.label is label]
        wrong = [i for i in raised if i.cause() not in ok]
        window = label.eval_window
        mine = data_items_of(data, label)
        detection_ids = {i.detection_id for i in mine}
        answered_by = {r.alert_id for i in mine for r in i.responses if r.alert_id}
        alerts = [
            e
            for e in data.alerts.values()
            if window[0] <= e["sim_time"] <= window[1]
            and not e["payload"]["fallback"]
            and e["payload"]["cause"] in ok
            and (
                detection_ids & set(e["payload"]["detection_ids"])
                or e["payload"]["alert_id"] in answered_by
            )
        ]
        roots = {
            data.root_of(r.alert_id)
            for i in data_items_of(data, label)
            for r in i.responses
            if r.alert_id and r.kind != "cierre"
        }
        if alerts and not wrong and raised:
            verdict = "✅"
        elif alerts:
            verdict = "⚠️"
        else:
            verdict = "❌"
        out.append(
            LabelResult(
                label,
                raised,
                wrong,
                min(raised, key=lambda i: i.event["sim_time"], default=None),
                min(alerts, key=lambda e: e["sim_time"], default=None),
                len(roots),
                verdict,
            )  # fmt: skip
        )
    return out


def data_items_of(data: RunData, label: Label) -> list[Item]:
    return [i for i in data.items if i.label is label]


def false_alarms(data: RunData) -> tuple[list[Item], list[Event]]:
    """Avisos `Raised` sin etiqueta y alertas fuera de toda ventana de evaluación."""
    stray_detections = [i for i in data.items if i.kind == "Raised" and i.label is None]
    stray_alerts = [
        e
        for e in data.alerts.values()
        if not any(lb.eval_window[0] <= e["sim_time"] <= lb.eval_window[1] for lb in data.labels)
    ]
    return stray_detections, stray_alerts


def treated_as_recovery(item: Item) -> bool:
    """El agente trató este aviso como recuperación tras un engaño o una pérdida del GPS: lo
    respondió con una alerta (o enlazándolo a una) con causa del GPS."""
    r = item.first
    return bool(r and r.kind in ("alerta", "supersedes", "acknowledge") and r.cause in GPS_CAUSES)


def row_mark(item: Item) -> str:
    r = item.first
    if r is None:
        return "❌"
    if item.kind == "Cleared":
        return "❌" if r.fallback else "✅"
    if item.label is None:
        return "⚠️"
    return "✅" if item.cause() in accepted_causes(item.label) else "❌"


def response_text(item: Item) -> str:
    r = item.first
    if r is None:
        return NO_RESPONSE
    names = {
        "alerta": f"alerta {r.alert_id}",
        "supersedes": f"alerta {r.alert_id} (sustituye)",
        "acknowledge": f"ack → {r.alert_id or NO_ALERT}",
        "cierre": f"cierre {r.alert_id}",
    }
    extra = " · determinista" if r.deterministic else ""
    extra += " · fallback" if r.fallback else ""
    more = f" (+{len(item.responses) - 1})" if len(item.responses) > 1 else ""
    return names[r.kind] + extra + more


def response_latency(item: Item) -> float | None:
    r = item.first
    if r is None:
        return None
    return wall_seconds(item.event["ingestion_time"], r.event["ingestion_time"])


# --- Agente, esperas y modo sin esperar ----------------------------------------------------------


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))] if ordered else 0.0


def agent_stats(trace: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for agent in sorted({t["agent"] for t in trace}):
        records = [t for t in trace if t["agent"] == agent]
        calls = [c for t in records for c in t["calls"]]
        latencies = [c["latency_s"] for c in calls]
        tools = Counter(tc["name"] for c in calls for tc in c["tool_calls"])
        model_skills = sum(1 for t in records for s in t["skills_loaded"] if s["by"] == "model")
        guided_skills = sum(1 for t in records for s in t["skills_loaded"] if s["by"] == "guided")
        stats[agent] = {
            "invocations": len(records),
            "llm_invocations": sum(1 for t in records if not t.get("deterministic")),
            "deterministic": sum(1 for t in records if t.get("deterministic")),
            "iterations": sum(t["iterations"] for t in records),
            "llm_calls": len(calls),
            "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
            "completion_tokens": sum(c["completion_tokens"] for c in calls),
            "max_prompt_tokens": max((c["prompt_tokens"] for c in calls), default=0),
            "latency_mean": statistics.fmean(latencies) if latencies else 0.0,
            "latency_p50": percentile(latencies, 0.5),
            "latency_max": max(latencies, default=0.0),
            "tools": dict(tools),
            "skills_by_model": model_skills,
            "skills_guided": guided_skills,
            "invalid_json": sum(t["invalid_json"] for t in records),
            "rejections": sum(len(t["guardrail_rejections"]) for t in records),
            "reminders": sum(t["reminders"] for t in records),
            "fallbacks": sum(1 for t in records if t["fallback"]),
            "fallback_closes": sum(1 for t in records if t["fallback_close"]),
            "unseen_evidence": sum(t["unseen_evidence"] for t in records),
            "end_reasons": dict(Counter(t["end_reason"] for t in records)),
        }
    return stats


def waits(data: RunData) -> list[dict[str, Any]]:
    """Cada pausa por «esperar al agente», con su duración de reloj y si había un chat en curso."""
    out = []
    pause: Event | None = None
    for e in data.events:
        if e["type"] == "SimulationPaused" and e["payload"]["reason"] == "waiting_agent":
            pause = e
        elif e["type"] in ("SimulationResumed", "SimulationFinished", "SimulationReset") and pause:
            start, end = pause["ingestion_time"], e["ingestion_time"]
            chat = any(
                t["agent"].startswith("chat-") and t["wall_start"] <= end and t["wall_end"] >= start
                for t in data.trace
            )
            out.append(
                {"sim_time": pause["sim_time"], "wall_s": wall_seconds(start, end), "chat": chat}
            )
            pause = None
    return out


def no_wait_stats(data: RunData) -> dict[str, Any]:
    monitor = [t for t in data.trace if t["agent"] == "monitor" and not t.get("deterministic")]
    delays = []
    for item in data.items:
        r = item.first
        if r is not None and item.kind != "Cleared":
            delays.append(r.event["sim_time"] - item.event["sim_time"])
    lags = [
        p_time - t["as_of"]
        for t in monitor
        for p_time in [data_time(data, p["event_id"]) for p in t["published"]]
        if p_time is not None
    ]
    return {
        "response_delay_max": max(delays, default=0.0),
        "response_delay_mean": statistics.fmean(delays) if delays else 0.0,
        "queue_max": max((t["queue_at_start"] for t in monitor), default=0),
        "batches_gt1": sum(1 for t in monitor if len(t["causation_ids"]) > 1),
        "lag_max": max(lags, default=0.0),
        "lag_mean": statistics.fmean(lags) if lags else 0.0,
        "arrived_during": sum(t["queue_at_start"] for t in monitor),
    }


def data_time(data: RunData, event_id: str) -> float | None:
    for e in data.events:
        if e["event_id"] == event_id:
            return e["sim_time"]
    return None


# --- Informe -----------------------------------------------------------------------------------


@dataclass
class Evaluation:
    data: RunData
    results: list[LabelResult]
    stray_detections: list[Item]
    stray_alerts: list[Event]
    unanswered: list[Item]
    agents: dict[str, dict[str, Any]]
    wait_list: list[dict[str, Any]]
    timeouts: int
    fallbacks: int
    overall: str
    open_alerts: list[Event]


def evaluate(folder: Path) -> Evaluation:
    data = RunData(folder)
    results = analyze_labels(data)
    stray_detections, stray_alerts = false_alarms(data)
    wait_list = waits(data)
    agents = agent_stats(data.trace)
    marks = {r.verdict for r in results}
    overall = "❌" if "❌" in marks else "⚠️" if "⚠️" in marks else "✅"
    if not results and (stray_detections or stray_alerts):
        overall = "❌"
    return Evaluation(
        data,
        results,
        stray_detections,
        stray_alerts,
        [i for i in data.items if not i.responses],
        agents,
        wait_list,
        sum(1 for w in wait_list if w["wall_s"] >= WAIT_CAP_S),
        agents.get("monitor", {}).get("fallbacks", 0),
        overall,
        data.open_alerts_at_end(),
    )


def summary_line(ev: Evaluation) -> str:
    ok = sum(1 for r in ev.results if r.verdict == "✅")
    false = len(ev.stray_detections) + len(ev.stray_alerts)
    return (
        f"{ev.overall} {ok}/{len(ev.results)} anomalías y fallos diagnosticados · "
        f"{false} falsas alarmas · {ev.fallbacks} fallbacks · {ev.timeouts} esperas agotadas · "
        f"{len(ev.unanswered)} detecciones sin respuesta · "
        f"{len(ev.open_alerts)} alertas abiertas al final"
    )


AID_NAMES = {
    "tool_choice": "tool_choice",
    "final_iteration_response_tools_only": "última iteración solo con las respuestas",
    "require_checks": "checks obligatorios",
    "coherence_guardrail": "guardrail de coherencia",
    "computed_facts": "hechos calculados",
}


def aids_line(aids: dict[str, Any] | None) -> str:
    """Las ayudas al modelo que había activas (interruptores del monitor)."""
    if not aids:
        return "- Ayudas al modelo: n/d"
    parts = []
    for key, label in AID_NAMES.items():
        value = aids.get(key)
        parts.append(
            f"{label} = {value}" if key == "tool_choice" else f"{label}: {'sí' if value else 'no'}"
        )
    return "- Ayudas al modelo: " + " · ".join(parts)


def header(ev: Evaluation) -> list[str]:
    data = ev.data
    first = next((t for t in data.trace if t["agent"] == "monitor"), None)
    s = first["sampling"] if first else {}
    extra = s.get("extra_body", {})
    wall = data.meta.get("wall_s")
    if wall is None and data.events:
        wall = wall_seconds(data.events[0]["ingestion_time"], data.events[-1]["ingestion_time"])
    return [
        f"# Evaluación · {data.scenario} · {data.folder.name}",
        "",
        f"**{summary_line(ev)}**",
        "",
        f"- Modelo: `{first['model'] if first else 'n/d'}` · "
        f"temperature {s.get('temperature', 'n/d')}"
        f" · top_p {s.get('top_p', 'n/d')} · top_k {extra.get('top_k', 'n/d')}"
        f" · repetition_penalty {extra.get('repetition_penalty', 'n/d')}"
        f" · max_tokens {s.get('max_tokens', 'n/d')}",
        f"- `guided_mode`: {first['guided_mode'] if first else 'n/d'} · esperar al agente: "
        f"{data.meta.get('wait_agent', 'n/d')} · velocidad: {data.meta.get('speed', 'n/d')}× · "
        f"duración en reloj: {_num(wall, ' s', 0)}",
        aids_line(first.get("aids") if first else None),
    ]


def labels_section(ev: Evaluation) -> list[str]:
    lines = [
        "",
        "## 1. Anomalías y fallos",
        "",
        "| Etiqueta | Tipo | Ventana | Primera detección | Retraso detección | Primera alerta "
        "aceptada (conf.) | Retraso diagnóstico (sim / reloj) | Cadenas | Veredicto |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in ev.results:
        lb = r.label
        det = r.first_detection
        alert = r.first_alert
        det_text = f"{det.rule} {fmt_t(det.event['sim_time'])}" if det else "—"
        det_delay = det.event["sim_time"] - lb.start_s if det else None
        alert_text = (
            f"{alert['payload']['cause']} {fmt_t(alert['sim_time'])} "
            f"({alert['payload']['confidence']:g})"
            if alert
            else "—"
        )
        sim_delay = wall_delay = None
        if alert and det:
            sim_delay = alert["sim_time"] - det.event["sim_time"]
            wall_delay = wall_seconds(det.event["ingestion_time"], alert["ingestion_time"])
        label_type = lb.type.value + (f" {lb.source.value}" if lb.source else "")
        lines.append(
            f"| {lb.id} | {label_type} | {fmt_t(lb.start_s)}–{fmt_t(lb.end_s)} | {det_text} | "
            f"{_num(det_delay, ' s')} | {alert_text} | {_num(sim_delay, ' s')} / "
            f"{_num(wall_delay, ' s')} | {r.chains} | {r.verdict} |"
        )
        for item in r.wrong:
            lines.append(
                f"|  |  |  | ↳ {item.detection_id} {item.rule} {fmt_t(item.event['sim_time'])} "
                f"atribuido a **{item.cause()}** (esperado: {lb.expected_cause.value}) "
                "| | | | | ❌ |"
            )
    if not ev.results:
        lines.append("| — | sin anomalías ni fallos | | | | | | | |")
    return lines


def responses_section(ev: Evaluation) -> list[str]:
    lines = [
        "",
        "## 2. Respuesta a cada detección",
        "",
        "| T+ | Aviso | Regla | Fuente | Detección | Respuesta | Causa atribuida | ✔ "
        "| Latencia (reloj) | Nota |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in ev.data.items:
        p = item.event["payload"]
        note = ""
        if item.label and item.label.type == LabelType.HIJACK and item.kind == "Raised":
            if item.rule == "ROUTE_DEVIATION":
                note = (
                    "tratado como recuperación ❌"
                    if treated_as_recovery(item)
                    else "no tratado como recuperación ✅"
                )
        elif item.label is None and item.kind != "Cleared":
            note = "falsa alarma"
        lines.append(
            f"| {fmt_t(item.event['sim_time'])} | {KIND_LETTER[item.kind]} | {item.rule} | "
            f"{p.get('source') or '—'} | {item.detection_id} | {response_text(item)} | "
            f"{item.cause() if item.kind != 'Cleared' else '—'} | {row_mark(item)} | "
            f"{_num(response_latency(item), ' s')} | {note} |"
        )
    if not ev.data.items:
        lines.append("| — | sin detecciones | | | | | | | | |")
    return lines


def false_section(ev: Evaluation) -> list[str]:
    lines = ["", "## 3. Falsas alarmas", ""]
    if not ev.stray_detections and not ev.stray_alerts:
        return lines + ["Ninguna."]
    for item in ev.stray_detections:
        lines.append(
            f"- Detección {item.detection_id} {item.rule} a {fmt_t(item.event['sim_time'])} "
            "fuera de toda ventana de evaluación."
        )
    for alert in ev.stray_alerts:
        p = alert["payload"]
        lines.append(
            f"- Alerta {p['alert_id']} ({p['cause']}) a {fmt_t(alert['sim_time'])} fuera de toda "
            "ventana de evaluación."
        )
    return lines


def agents_section(ev: Evaluation) -> list[str]:
    lines = ["", "## 4. Agente", ""]
    if not ev.agents:
        return lines + ["Sin trazas (módulo de IA sin agentes)."]
    for name, s in ev.agents.items():
        tools = ", ".join(f"{k}: {v}" for k, v in sorted(s["tools"].items())) or "ninguna"
        lines += [
            f"### {name}",
            f"- Invocaciones: {s['invocations']} ({s['llm_invocations']} con LLM, "
            f"{s['deterministic']} deterministas) · iteraciones: {s['iterations']} · "
            f"llamadas al LLM: {s['llm_calls']}",
            f"- Tokens: prompt {s['prompt_tokens']}, completion {s['completion_tokens']} · "
            f"**máximo de prompt en una llamada: {s['max_prompt_tokens']}**",
            f"- Latencia por llamada: media {_num(s['latency_mean'], ' s')}, "
            f"p50 {_num(s['latency_p50'], ' s')}, máx. {_num(s['latency_max'], ' s')}",
            f"- Llamadas por tool: {tools}",
            f"- Skills cargadas por el modelo: {s['skills_by_model']} · precargadas por el modo "
            f"guiado: {s['skills_guided']}",
            f"- JSON inválido: {s['invalid_json']} · rechazos de guardrails: {s['rejections']} · "
            f"recordatorios: {s['reminders']} · fallbacks: {s['fallbacks']} · cierres de fallback: "
            f"{s['fallback_closes']} · evidencias no vistas: {s['unseen_evidence']}",
            f"- Cómo terminaron: {s['end_reasons']}",
        ]
    return lines


def waits_section(ev: Evaluation) -> list[str]:
    lines = ["", "## 5. Esperas al agente", ""]
    if not ev.wait_list:
        return lines + ["Ninguna (el reproductor no esperó al agente)."]
    durations = [w["wall_s"] for w in ev.wait_list]
    lines.append(
        f"{len(durations)} esperas · media {_num(statistics.fmean(durations), ' s')} · máxima "
        f"{_num(max(durations), ' s')} · {ev.timeouts} agotadas (≥ {WAIT_CAP_S:g} s)."
    )
    lines += ["", "| T+ | Espera (reloj) | Chat en curso |", "|---|---|---|"]
    for w in ev.wait_list:
        lines.append(
            f"| {fmt_t(w['sim_time'])} | {_num(w['wall_s'], ' s')} "
            f"| {'sí' if w['chat'] else 'no'} |"
        )
    return lines


def no_wait_section(ev: Evaluation) -> list[str]:
    if ev.data.meta.get("wait_agent", False) or not ev.agents:
        return []
    s = no_wait_stats(ev.data)
    return [
        "",
        "## 6. Sin esperar al agente",
        "",
        "- Latencia de respuesta en tiempo simulado: "
        f"media {_num(s['response_delay_mean'], ' s')}, "
        f"máxima {_num(s['response_delay_max'], ' s')}",
        f"- Cola máxima al empezar una invocación: {s['queue_max']} · lotes de más de una "
        f"detección: {s['batches_gt1']} · detecciones llegadas durante invocaciones: "
        f"{s['arrived_during']}",
        f"- Desfase (`sim_time` al publicar − `as_of`): media {_num(s['lag_mean'], ' s')}, "
        f"máximo {_num(s['lag_max'], ' s')}",
    ]


def open_section(ev: Evaluation) -> list[str]:
    lines = ["", "## Alertas abiertas al final", ""]
    if not ev.open_alerts:
        return lines + ["Ninguna."]
    for alert in ev.open_alerts:
        p = alert["payload"]
        lines.append(
            f"- {p['alert_id']} {p['cause']} ({p['severity']}) de "
            f"{fmt_t(alert['sim_time'])}: {p['summary']}"
        )
    return lines


def render_markdown(ev: Evaluation) -> str:
    parts = [
        header(ev),
        labels_section(ev),
        responses_section(ev),
        false_section(ev),
        agents_section(ev),
        waits_section(ev),
        no_wait_section(ev),
        open_section(ev),
    ]
    return "\n".join(line for part in parts for line in part) + "\n"


def to_json(ev: Evaluation) -> dict[str, Any]:
    return {
        "scenario": ev.data.scenario,
        "run_id": ev.data.folder.name,
        "overall": ev.overall,
        "summary": summary_line(ev),
        "labels": [
            {
                "id": r.label.id,
                "type": r.label.type.value,
                "verdict": r.verdict,
                "chains": r.chains,
                "first_detection": r.first_detection.event["sim_time"]
                if r.first_detection
                else None,
                "first_alert": r.first_alert["payload"]["alert_id"] if r.first_alert else None,
                "wrong": [i.detection_id for i in r.wrong],
            }
            for r in ev.results
        ],
        "false_alarms": len(ev.stray_detections) + len(ev.stray_alerts),
        "fallbacks": ev.fallbacks,
        "timeouts": ev.timeouts,
        "unanswered": [i.detection_id for i in ev.unanswered],
        "open_alerts": [a["payload"]["alert_id"] for a in ev.open_alerts],
        "agents": ev.agents,
        "waits": ev.wait_list,
    }


def write_evaluation(folder: Path) -> Evaluation:
    ev = evaluate(folder)
    (folder / "eval.md").write_text(render_markdown(ev), encoding="utf-8")
    (folder / "eval.json").write_text(
        json.dumps(to_json(ev), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return ev


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evalúa una ejecución contra sus etiquetas")
    parser.add_argument("folder", type=Path, help="runs/<escenario>/<run_id>")
    args = parser.parse_args(argv)
    ev = write_evaluation(args.folder)
    print(summary_line(ev))
    print(f"→ {args.folder / 'eval.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
