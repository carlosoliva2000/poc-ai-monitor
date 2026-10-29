"""Guardrails de las tools que publican (`contracts/eventos.md` §7). Funciones puras.

Un rechazo no es una excepción: devuelve la lista de errores (en inglés), que vuelve al modelo
como resultado de la tool y cuenta como iteración.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from poc_contracts.enums import AlertStatus
from poc_contracts.envelope import EventDraft
from poc_contracts.tools import AcknowledgeDetectionArgs, CloseAlertArgs, PublishAlertArgs

from ..monitor_state import MonitorState

INDEXED_DOMAINS = ("air", "env", "ai", "ops")
LINK_RSSI_JUMP_DB = 10.0  # un enlace es anómalo si el RSSI varía más de esto en los eventos vistos
LINK_LATENCY_RATIO = 2.5  # o si la latencia máxima supera esta vez la mínima
RECOVERY_STEP_M = 30.0  # la recuperación del GPS salta al menos esto de golpe
RECOVERY_CAUSES = ("GPS_SPOOFING", "GPS_JAMMING", "SENSOR_FAULT")
RECOVERY_SEVERITY = "medium"  # severidad que el guardrail impone a la alerta de recuperación
SILENT_CAUSE = "SENSOR_FAULT"  # causa de la alerta propia de una fuente callada


class EventIndex:
    """`event_id -> sim_time` de los eventos de los dominios `air`, `env`, `ai` y `ops` que ha
    recibido el módulo por el WebSocket. No incluye el dominio `sim`: un id suyo no vale como
    evidencia, igual que no lo devuelve ninguna tool. No consulta `/api/timeline`."""

    def __init__(self) -> None:
        self._times: dict[str, float] = {}

    def add(self, event: EventDraft) -> None:
        domain = event.topic.split(".")[3] if event.topic.count(".") == 6 else None
        if (
            domain in INDEXED_DOMAINS and not event.ephemeral
        ):  # los efímeros no están en el timeline
            self._times[event.event_id] = event.sim_time

    def get(self, event_id: str) -> float | None:
        return self._times.get(event_id)

    def clear(self) -> None:
        self._times.clear()


@dataclass
class InvocationFacts:
    """Lo que han devuelto las tools en la invocación en curso, sin recortar (aunque el
    interruptor `computed_facts` quite campos al modelo): con ello se contrastan los `checks`."""

    metrics: dict[str, Any] | None = None
    """El último resultado de `get_track_metrics`."""
    link_events: list[dict[str, Any]] | None = None
    """Los eventos del último `get_events` con `source: link` (`None`: no se miró)."""


def link_is_anomalous(events: list[dict[str, Any]]) -> bool:
    """Enlace anómalo en esos eventos: más de un `controller_id`, un salto de RSSI de más de
    10 dB o una latencia máxima de más de 2,5 veces la mínima. (En vuelo normal el RSSI varía
    hasta 6 dB y la latencia hasta 1,7 veces.)"""
    if len(events) < 2:
        return False
    if len({e.get("controller_id") for e in events}) > 1:
        return True
    rssi = [float(e["rssi_dbm"]) for e in events if "rssi_dbm" in e]
    latency = [float(e["latency_ms"]) for e in events if "latency_ms" in e]
    if rssi and max(rssi) - min(rssi) > LINK_RSSI_JUMP_DB:
        return True
    return bool(latency) and min(latency) > 0 and max(latency) / min(latency) > LINK_LATENCY_RATIO


def metric_facts(metrics: dict[str, Any] | None) -> dict[str, bool]:
    """Los hechos de un `get_track_metrics` que exigen una comparación, con las reglas de la
    plataforma (`notable`, `with_drift`, `disagreed`) y el salto de la recuperación. Los usan el
    guardrail y el texto que se inyecta a los chats, para que digan lo mismo."""
    metrics = metrics or {}
    wind = metrics.get("wind") or {}
    gps_radar = metrics.get("gps_radar") or {}
    step = metrics.get("gps_max_step_m")
    return {
        "wind_notable": bool(wind.get("notable")),
        "wind_with_drift": bool(wind.get("with_drift")),
        "gps_radar_disagreed": bool(gps_radar.get("disagreed")),
        "gps_jump": step is not None and step >= RECOVERY_STEP_M,
    }


def expected_checks(facts: InvocationFacts, state: MonitorState, as_of: float) -> dict[str, Any]:
    """Los valores que deben tener los `checks` según las tools de la invocación y el estado."""
    computed = metric_facts(facts.metrics)
    checked = facts.link_events is not None
    return {
        "gps_alert_recent": state.gps_alert_recent(as_of),
        "gps_radar_disagreed": computed["gps_radar_disagreed"],
        "wind_notable": computed["wind_notable"],
        "wind_with_drift": computed["wind_with_drift"],
        "link_checked": checked,
        "link_anomalous": link_is_anomalous(facts.link_events or []) if checked else None,
    }


def is_new_source_silent(detection_ids: list[str], state: MonitorState) -> bool:
    """Alguna de esas detecciones es un `SOURCE_SILENT` que aún no está en ninguna alerta."""
    return any(
        (d := state.detections.get(i)) is not None
        and d.rule == "SOURCE_SILENT"
        and state.alert_of(i) is None
        for i in detection_ids
    )


def _json(value: bool | None) -> str:
    return "null" if value is None else str(value).lower()


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def _source_of(name: str, facts: InvocationFacts, state: MonitorState) -> str:
    """De dónde sale el valor esperado de un check (para el mensaje de rechazo)."""
    if name == "gps_alert_recent":
        return "the state (open alerts: " + state.describe_open_alerts() + ")"
    if name.startswith("link"):
        return (
            "the link events you requested"
            if facts.link_events
            else "you have not looked at the link"
        )
    if facts.metrics is None:
        return "you have not called get_track_metrics"
    return "get_track_metrics"


def check_coherence(
    args: Any,
    facts: InvocationFacts,
    state: MonitorState,
    as_of: float,
    *,
    require_checks: bool,
) -> list[str]:
    """Guardrail de coherencia de `publish_alert`: (a) cada valor de `checks` coincide con las
    tools de la invocación y el estado; (b) la causa es coherente con ellos. Cada rechazo dice
    en una frase qué falta."""
    expected = expected_checks(facts, state, as_of)
    errors: list[str] = []
    if args.checks is None:
        if require_checks:
            errors.append("`checks` is missing: fill in the checks before choosing the cause")
    else:
        given = args.checks.model_dump()
        for name, want in expected.items():
            if given[name] != want:
                errors.append(
                    f"checks.{name} = {_json(given[name])} does not match "
                    f"{_source_of(name, facts, state)} ({_json(want)})"
                )
    metrics = facts.metrics or {}
    wind = metrics.get("wind") or {}
    cause = args.cause.value
    if cause == "WIND":
        if facts.metrics is None:
            errors.append("WIND requires calling get_track_metrics first (wind of the window)")
        elif not expected["wind_notable"]:
            errors.append(
                f"WIND requires notable wind: mean {_num(wind.get('mean_speed_mps'))} and gust "
                f"{_num(wind.get('max_gust_mps'))} are not; look at the link (step 5)"
            )
        elif not expected["wind_with_drift"]:
            errors.append(
                "WIND requires the drift to go with the wind: they differ by "
                f"{_num(wind.get('drift_vs_wind_deg'))}° (maximum 45°); look at the link (step 5)"
            )
    if cause == "HIJACK" and not expected["link_checked"]:
        errors.append("HIJACK requires having looked at the link: call get_events with source link")
    on_route_deviation = any(
        (d := state.detections.get(i)) is not None and d.rule == "ROUTE_DEVIATION"
        for i in args.detection_ids
    )
    if on_route_deviation:
        step = metrics.get("gps_max_step_m")
        disagreed = expected["gps_radar_disagreed"] or (
            step is not None and step >= RECOVERY_STEP_M
        )
        recent = state.recent_gps_alert(as_of)
        if recent is not None and disagreed:
            # recuperación del GPS: la única causa aceptada es la de esa alerta, y la alerta
            # nueva sustituye a la anterior si esta sigue abierta
            still_open = recent.status == AlertStatus.OPEN
            want_supersedes = recent.alert_id if still_open else None
            if still_open and recent.severity == RECOVERY_SEVERITY:
                errors.append(
                    f"This is the recovery from the {recent.cause} of {recent.alert_id}, which is "
                    f"already {RECOVERY_SEVERITY}: nothing changes, use acknowledge_detection with "
                    f"alert_id {recent.alert_id}"
                )
            elif (
                cause != recent.cause
                or args.supersedes != want_supersedes
                or args.severity.value != RECOVERY_SEVERITY
            ):
                how = (
                    f"supersedes {recent.alert_id}"
                    if still_open
                    else f"no supersedes ({recent.alert_id} is already closed)"
                )
                errors.append(
                    f"This is the recovery from the {recent.cause} of {recent.alert_id}: publish "
                    f"cause {recent.cause}, severity {RECOVERY_SEVERITY} and {how}"
                )
        elif cause in RECOVERY_CAUSES:
            errors.append(
                f"a route deviation with cause {cause} is the GPS recovery and requires a GPS "
                "alert that is open or from 60 s ago or less "
                f"({'there is one' if recent is not None else 'there is none'}) and that GPS and "
                "radar disagreed "
                f"(gps_radar.disagreed={str(expected['gps_radar_disagreed']).lower()}) "
                f"or a GPS jump of 30 m or more (gps_max_step_m={_num(step)})"
            )
    return errors


@dataclass
class Verdict:
    """Resultado de validar una llamada: los argumentos ya validados o los errores."""

    args: Any = None
    errors: list[str] = field(default_factory=list)
    unseen_evidence: list[str] = field(default_factory=list)
    """Evidencias que existen pero el modelo no ha visto en esta invocación (se cuentan)."""

    @property
    def ok(self) -> bool:
        return not self.errors


FIELD_HINTS = {
    "evidence_event_ids": "put there, not in the explanation, 2 to 6 ids you have seen, such as "
    "met-0010 or gps-000106",
    "checks": "fill it in with the six checks before choosing the cause",
    "detection_ids": "give the det-… of the warnings you are handling",
    "cause": "one of WIND, HIJACK, GPS_SPOOFING, SENSOR_FAULT, GPS_JAMMING or UNKNOWN",
    "severity": "low, medium or high",
    "confidence": "a number between 0 and 1",
    "summary": "one sentence of fewer than 160 characters",
    "explanation": "the reasoning, with figures, sources and T+mm:ss times",
    "recommendation": "what you recommend to the person in charge of the drone (you cannot act)",
    "reason": "one sentence with data",
    "alert_id": "the alert_id of an open alert",
    "checks.link_anomalous": "true, false, or null if you have not looked at the link",
}


def _describe(exc: ValidationError) -> list[str]:
    """Errores de validación en inglés y accionables: qué falta o sobra y cómo arreglarlo."""
    out = []
    for e in exc.errors():
        name = ".".join(str(p) for p in e["loc"]) or "arguments"
        hint = FIELD_HINTS.get(name, "")
        kind = e["type"]
        if kind == "missing":
            out.append(f"`{name}` is missing" + (f": {hint}" if hint else ""))
        elif kind in ("string_too_long", "too_long"):
            out.append(f"`{name}` is too long" + (f": {hint}" if hint else ""))
        elif kind == "too_short":
            out.append(f"`{name}` is empty" + (f": {hint}" if hint else ""))
        elif kind in ("greater_than_equal", "less_than_equal"):
            out.append(f"`{name}` is out of range" + (f": {hint}" if hint else ""))
        elif kind in ("enum", "literal_error"):
            out.append(f"`{name}` is not an allowed value" + (f": use {hint}" if hint else ""))
        elif kind == "extra_forbidden":
            out.append(f"`{name}` is not needed: remove it (it is not an argument of this tool)")
        else:
            out.append(f"`{name}` is not valid ({e['msg']})" + (f": {hint}" if hint else ""))
    return out


def _parse(model: type[BaseModel], raw: dict[str, Any]) -> tuple[Any, list[str]]:
    try:
        return model.model_validate(raw), []
    except ValidationError as exc:
        return None, _describe(exc)


def check_publish_alert(
    raw: dict[str, Any],
    *,
    as_of: float,
    state: MonitorState,
    index: EventIndex,
    seen_ids: set[str],
    facts: InvocationFacts | None = None,
    coherence: bool = False,
    require_checks: bool = True,
    pending: set[str] | None = None,
    unanswered: set[str] | None = None,
    source_silent_own_alert: bool = False,
    no_duplicate_cause: bool = False,
) -> Verdict:
    args, errors = _parse(PublishAlertArgs, raw)
    if args is None:
        return Verdict(errors=errors)
    if args.detection_ids is None:
        return Verdict(errors=[_missing_detection_ids(pending)])
    unseen: list[str] = []
    no_change: str | None = None
    for event_id in args.evidence_event_ids:
        sim_time = index.get(event_id)
        if sim_time is None:
            errors.append(f"evidence {event_id!r} does not exist: cite only ids you have seen")
        elif sim_time > as_of + 1e-9:
            errors.append(f"evidence {event_id!r} is later than the current time")
        elif event_id not in seen_ids:
            unseen.append(event_id)
    for detection_id in args.detection_ids:
        if detection_id not in state.detections:
            errors.append(
                f"detection {detection_id!r} does not exist: use a det-… from the warnings"
            )
        elif pending is not None and detection_id not in pending:
            errors.append(
                f"detection {detection_id} is not one you are handling now "
                f"({', '.join(sorted(pending))}): use only those; what came earlier in the chain "
                "is inherited with `supersedes`"
            )
    no_new = unanswered is not None and not unanswered.intersection(args.detection_ids)
    if pending is not None and not errors and no_new:
        errors.append(
            "those detections already have a response: include one of those that do not have "
            f"one yet ({', '.join(sorted(unanswered or set())) or 'none'})"
        )
    if args.supersedes is not None:
        target = state.alerts.get(args.supersedes)
        if target is None or target.status != AlertStatus.OPEN:
            errors.append(f"supersedes: {args.supersedes!r} is not an open alert")
        elif (
            source_silent_own_alert
            and target.cause != SILENT_CAUSE
            and is_new_source_silent(args.detection_ids, state)
        ):
            errors.append(
                f"a SOURCE_SILENT warning is a different fault from {target.alert_id} "
                f"({target.cause}) and gets its own alert: publish_alert with cause "
                f"{SILENT_CAUSE} and without supersedes"
            )
        elif args.cause.value == target.cause and args.severity.value == target.severity:
            # una alerta que sustituye a otra tiene que cambiar algo; si no, es un reconocimiento.
            # Se comprueba al final: en la recuperación del GPS la regla específica (publicar con
            # severity medium) debe pasar por delante, o este mensaje mandaría reconocer.
            no_change = (
                f"Nothing changes with respect to {target.alert_id} (same cause and severity): "
                f"use acknowledge_detection with alert_id {target.alert_id}"
            )
    else:
        for detection_id in args.detection_ids:
            alert = state.alert_of(detection_id)
            if alert is not None and alert.status == AlertStatus.OPEN:
                errors.append(
                    f"detection {detection_id} is already in the open alert {alert.alert_id}: "
                    "use acknowledge_detection if nothing changes, or publish_alert with "
                    f"supersedes={alert.alert_id!r} if the cause or the severity changes"
                )
        if (
            no_duplicate_cause
            and not errors
            and not is_new_source_silent(args.detection_ids, state)
        ):
            # solo cuentan las abiertas (la cabeza de cada cadena); un SOURCE_SILENT nuevo queda
            # exento: la regla `source_silent_own_alert` le exige una alerta propia
            same = next((a for a in state.open_alerts() if a.cause == args.cause.value), None)
            if same is not None:
                errors.append(
                    f"{same.alert_id} ({same.cause}) is open: use supersedes {same.alert_id} if "
                    "the cause or severity changes, or acknowledge_detection"
                )
    if coherence and not errors:
        errors += check_coherence(
            args, facts or InvocationFacts(), state, as_of, require_checks=require_checks
        )
    if no_change and not errors:
        errors.append(no_change)
    return Verdict(args=args, errors=errors, unseen_evidence=unseen)


def _missing_detection_ids(pending: set[str] | None) -> str:
    listed = f" ({', '.join(sorted(pending))})" if pending else ""
    return f"`detection_ids` is missing: there are several pending detections{listed}; say which"


def check_acknowledge(
    raw: dict[str, Any],
    *,
    state: MonitorState,
    unanswered: set[str],
    pending: set[str],
    source_silent_own_alert: bool = False,
) -> Verdict:
    """`unanswered`: detecciones del lote que aún no tienen respuesta; `pending`: todas las del
    lote."""
    args, errors = _parse(AcknowledgeDetectionArgs, raw)
    if args is None:
        return Verdict(errors=errors)
    if args.detection_ids is None:
        return Verdict(errors=[_missing_detection_ids(pending)])
    if args.alert_id is not None:
        alert = state.alerts.get(args.alert_id)
        if alert is None or alert.status != AlertStatus.OPEN:
            errors.append(f"alert_id: {args.alert_id!r} is not an open alert")
    for detection_id in args.detection_ids:
        if detection_id not in pending:
            errors.append(
                f"detection {detection_id!r} is not one you must handle now "
                f"({', '.join(sorted(pending))})"
            )
        elif detection_id not in unanswered:
            errors.append(f"detection {detection_id!r} already has a response")
    if not errors and source_silent_own_alert and is_new_source_silent(args.detection_ids, state):
        errors.append(
            "a SOURCE_SILENT warning is always a different fault and gets its own alert: "
            f"publish_alert with cause {SILENT_CAUSE} and without supersedes"
        )
    return Verdict(args=args, errors=errors)


def check_close_alert(raw: dict[str, Any], *, state: MonitorState) -> Verdict:
    args, errors = _parse(CloseAlertArgs, raw)
    if args is None:
        return Verdict(errors=errors)
    if args.alert_id is None:
        return Verdict(errors=["`alert_id` is missing: say which alert you are closing"])
    alert = state.alerts.get(args.alert_id)
    if alert is None:
        errors.append(f"alert {args.alert_id!r} does not exist")
    elif alert.status == AlertStatus.SUPERSEDED:
        head = state.head(alert.alert_id)
        errors.append(
            f"alert {alert.alert_id} has been superseded by {head.alert_id if head else '?'}: "
            "close the current one"
        )
    elif alert.status == AlertStatus.CLOSED:
        errors.append(f"alert {alert.alert_id} is already closed")
    else:
        still_open = state.open_detections_of(alert.alert_id)
        if still_open:
            ids = ", ".join(d.detection_id for d in still_open)
            errors.append(
                f"{alert.alert_id} cannot be closed: it still has open detections ({ids})"
            )
    return Verdict(args=args, errors=errors)
