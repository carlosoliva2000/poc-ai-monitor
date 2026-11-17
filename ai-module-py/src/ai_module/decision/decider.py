"""El monitor sin LLM (E6): de un aviso del detector a una respuesta, con la tabla de decisión.

`decide` pide las tools de datos (las mismas que el modelo, por el mismo camino), calcula las
entradas (`features.py`), evalúa las tablas `cause`, `severity` y `confidence`
(`config/decision_table.yaml`) y resuelve el **ciclo de vida** en código, porque DMN no tiene
estado:

- `attach: gps_alert`: la alerta del GPS reciente; si sigue abierta, se sustituye (o se reconoce si
  no cambia nada); si ya está cerrada, alerta nueva sin `supersedes` (lo que pide el guardrail);
- `attach: hijack_alert`: la alerta del secuestro cuya recuperación es el aviso;
- `attach: same_cause`: la alerta abierta a la que ya pertenece la detección o, si no tiene, la
  abierta de la misma causa y fuente («un problema, una alerta»);
- `attach: none`: alerta propia (una fuente callada).

Si la alerta de destino tiene la misma causa, severidad y fase, la respuesta es un reconocimiento;
si no, una alerta con `supersedes`. El último cierre de una alerta la cierra.

No publica nada: devuelve la llamada (`publish_alert`, `acknowledge_detection` o `close_alert`)
que el monitor ejecuta por las mismas rutas que las del modelo, guardrails incluidos.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from ..agent.guardrails import InvocationFacts, ModuleJump, expected_checks
from ..monitor_state import MonitorState
from .features import Facts, ToolCall, gather, inputs_for, support_for
from .table import DecisionTables
from .templates import alert_texts, close_reason

SAME_AS_GPS_ALERT = "SAME_AS_GPS_ALERT"
MAX_EVIDENCE = 6
CLOSURE_WINDOW_S = 20.0  # como el aviso de cierre del modelo (`monitor.CLOSURE_WINDOW_S`)

Action = Literal["publish_alert", "acknowledge_detection", "close_alert"]


@dataclass
class Choice:
    """La respuesta de la tabla a un aviso, con lo necesario para la traza."""

    action: Action
    args: dict[str, Any]
    rows: dict[str, str] = field(default_factory=dict)
    """Fila que encajó en cada tabla (`cause`, `severity`, `confidence`)."""
    inputs: dict[str, Any] = field(default_factory=dict)
    facts: Facts = field(default_factory=Facts)
    invocation_facts: InvocationFacts = field(default_factory=InvocationFacts)

    def trace(self, detection_id: str) -> dict[str, Any]:
        return {
            "detection_id": detection_id,
            "action": self.action,
            "rows": self.rows,
            "inputs": self.inputs,
            "outputs": {
                k: self.args.get(k)
                for k in ("cause", "severity", "confidence", "phase", "supersedes", "alert_id")
                if k in self.args
            },
        }


def _evidence(trigger: list[str], cause: str, facts: Facts, inputs: dict[str, Any]) -> list[str]:
    """Entre 2 y 6 ids vistos, de al menos dos fuentes si se puede: los del aviso y los que
    sostienen la causa."""
    m = facts.metrics or {}
    picks: list[str] = list(trigger)
    if cause in ("HIJACK",) or inputs["rule"] == "LINK_ANOMALY":
        link = facts.link or []
        changed = [e["event_id"] for i, e in enumerate(link)
                   if i and e.get("controller_id") != link[i - 1].get("controller_id")]  # fmt: skip
        picks += changed or [e["event_id"] for e in link[-2:]]
    if cause == "WIND" and (m.get("wind") or {}).get("last_event_id"):
        picks.append(m["wind"]["last_event_id"])
    if cause in ("GPS_SPOOFING", "GPS_JAMMING") and facts.gps:
        picks.append(facts.gps[-1]["event_id"])
    picks += m.get("last_event_ids", [])
    picks += m.get("first_event_ids", [])
    return list(dict.fromkeys(picks))[:MAX_EVIDENCE]


async def decide(
    tables: DecisionTables,
    call: ToolCall,
    *,
    kind: str,
    detection: dict[str, Any],
    state: MonitorState,
    as_of: float,
    link_recovery: bool = False,
    last_open_of: str | None = None,
    module_jump: ModuleJump | None = None,
    mission_controller: str | None = None,
    link_back_change: tuple[float, str] | None = None,
) -> Choice:
    detection_id = detection["detection_id"]
    record = state.detections[detection_id]
    rule = record.rule

    if kind == "cleared" and not link_recovery:  # el último cierre de una alerta: se cierra
        since = max(as_of - CLOSURE_WINDOW_S, record.since, 0.0)
        facts = Facts()
        facts.metrics = await call("get_track_metrics", {"since": since, "until": as_of})
        return Choice(
            "close_alert",
            {"alert_id": last_open_of, "reason": close_reason({**detection, "rule": rule}, facts)},
            facts=facts,
        )

    facts = await gather(call, rule, record.since, as_of, link_recovery=link_recovery)
    facts.module_step = module_jump.step if module_jump is not None else None
    inputs = inputs_for(
        facts,
        rule=rule,
        kind=kind,
        source=record.source,
        detection_id=detection_id,
        link_recovery=link_recovery,
        state=state,
        as_of=as_of,
        mission_controller=mission_controller,
    )
    cause_row = tables["cause"].evaluate(inputs)
    cause = str(cause_row.then["cause"])
    phase = str(cause_row.then["phase"])
    attach = str(cause_row.then["attach"])

    recent = state.recent_gps_alert(as_of)
    target = None
    episode_cause = None
    if attach == "gps_alert" and recent is not None:
        episode_cause = recent.cause
        if cause == SAME_AS_GPS_ALERT:
            cause = recent.cause
        target = recent if recent.status.value == "open" else None
    elif attach == "hijack_alert":
        target = state.link_recovery_alert(detection_id)
    elif attach == "same_cause":
        current = state.alert_of(detection_id)
        if current is not None and current.status.value == "open":
            target = current
        else:
            target = next(
                (
                    a
                    for a in state.open_alerts()
                    if a.cause == cause and not state.foreign_sensor_fault(a, detection_id)
                ),
                None,
            )
    if cause == SAME_AS_GPS_ALERT:  # sin alerta del GPS reciente no debería pasar
        cause = "UNKNOWN"

    severity_row = tables["severity"].evaluate({**inputs, "cause": cause, "phase": phase})
    severity = str(severity_row.then["severity"])
    n_support, n_contra = support_for(cause, phase, inputs, facts, mission_controller)
    confidence_row = tables["confidence"].evaluate(
        {"cause": cause, "n_support": n_support, "n_contra": n_contra}
    )
    confidence = float(confidence_row.then["confidence"])
    rows = {"cause": cause_row.rule_id, "severity": severity_row.rule_id,
            "confidence": confidence_row.rule_id}  # fmt: skip
    trace_inputs = {**inputs, "n_support": n_support, "n_contra": n_contra}
    inv_facts = InvocationFacts(metrics=facts.metrics, link_events=facts.link,
                                module_jump=module_jump)  # fmt: skip

    if target is not None and (target.cause, target.severity, target.phase) == (
        cause,
        severity,
        phase,
    ):
        return Choice(
            "acknowledge_detection",
            {
                "detection_ids": [detection_id],
                "alert_id": target.alert_id,
                "reason": f"Same episode as {target.alert_id}: nothing changes.",
            },
            rows,
            trace_inputs,
            facts,
            inv_facts,
        )

    summary, explanation, recommendation = alert_texts(
        cause=cause,
        phase=phase,
        severity=severity,
        rule=rule,
        inputs=inputs,
        facts=facts,
        detection=detection,
        as_of=as_of,
        episode_cause=episode_cause or (target.cause if target is not None else None),
        mission_controller=mission_controller,
        link_back=link_back_change,
    )
    args = {
        "detection_ids": [detection_id],
        "checks": expected_checks(inv_facts, state, as_of),
        "cause": cause,
        "severity": severity,
        "phase": phase,
        "confidence": confidence,
        "evidence_event_ids": _evidence(
            list(detection.get("trigger_event_ids", [])), cause, facts, inputs
        ),
        "summary": summary,
        "explanation": explanation,
        "recommendation": recommendation,
        "supersedes": target.alert_id if target is not None else None,
    }
    return Choice("publish_alert", args, rows, trace_inputs, facts, inv_facts)
