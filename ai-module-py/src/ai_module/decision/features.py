"""Entradas de la tabla de decisión (E6): los hechos que calcula el código, con nombre.

Todo lo que exige una cuenta (distancias, ángulos, ventanas, el salto del GPS, si el enlace es
anómalo) se calcula aquí o en las tools de la plataforma, nunca en una celda de la tabla. Se usan
las mismas reglas que los guardrails (`metric_facts`, `link_is_anomalous`) para que la tabla y el
guardrail no puedan discrepar. Las tools se piden con las ventanas que dicen las skills.

Hechos nuevos de la E6, calculados aquí y **no** en `get_track_metrics` (así el LLM no ve nada
distinto): la diferencia entre la desviación del radar y la del GPS ahora (`radar_minus_gps_now_m`,
con la tendencia del radar: «el radar está fuera y se aleja») y la peor calidad reciente del
radar (`radar_quality_min`).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..agent.guardrails import RECOVERY_STEP_M, link_is_anomalous, metric_facts
from ..monitor_state import POSITION_RULES, MonitorState

ToolCall = Callable[[str, dict[str, Any]], Awaitable[Any]]

WINDOW_BEFORE_S = {
    "ROUTE_DEVIATION": 30.0,  # route-deviation, paso 1
    "SOURCE_DISCREPANCY": 40.0,  # source-discrepancy, paso 1
    "GPS_DEGRADED": 20.0,  # source-discrepancy, paso 4
    "LINK_ANOMALY": 30.0,  # link-anomaly, paso 2
    "SOURCE_SILENT": 30.0,
}
RECOVERY_WINDOW_S = 30.0
"""La recuperación del secuestro mira los últimos 30 s (lo que dice el aviso al modelo)."""
GPS_LOSS_HDOP = 20.0
"""Fix malo según la skill `source-discrepancy` (paso 4): `fix none`, 0 satélites o `hdop` ≥ 20."""
GPS_CAUSES = ("GPS_SPOOFING", "GPS_JAMMING", "SENSOR_FAULT")


@dataclass
class Facts:
    """Lo que devolvieron las tools para un aviso (sin recortar) y lo que se citó."""

    metrics: dict[str, Any] | None = None
    link: list[dict[str, Any]] | None = None
    gps: list[dict[str, Any]] | None = None
    radar: list[dict[str, Any]] | None = None
    module_step: float | None = None
    """Salto del GPS que calcula el módulo con la ventana fija (`Monitor._module_jump`)."""
    seen_ids: set[str] = field(default_factory=set)


async def gather(
    call: ToolCall,
    rule: str,
    since: float,
    as_of: float,
    *,
    link_recovery: bool = False,
) -> Facts:
    """Pide las tools de datos que necesita la tabla para un aviso, con las ventanas de las
    skills. Siempre las cuatro: no hay que elegir (lo que el modelo sí hacía)."""
    before = RECOVERY_WINDOW_S if link_recovery else WINDOW_BEFORE_S.get(rule, 30.0)
    start = (as_of - before) if link_recovery else (since - before)
    facts = Facts()
    facts.metrics = await call("get_track_metrics", {"since": max(0.0, start), "until": as_of})
    facts.link = (await call("get_events", {"source": "link", "last_n": 6})).get("events", [])
    facts.gps = (await call("get_events", {"source": "gps", "last_n": 5})).get("events", [])
    facts.radar = (await call("get_events", {"source": "radar", "last_n": 5})).get("events", [])
    m = facts.metrics or {}
    facts.seen_ids.update(m.get("first_event_ids", []) + m.get("last_event_ids", []))
    if (m.get("wind") or {}).get("last_event_id"):
        facts.seen_ids.add(m["wind"]["last_event_id"])
    for events in (facts.link, facts.gps, facts.radar):
        facts.seen_ids.update(e["event_id"] for e in events or [])
    return facts


def _angle(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def gps_fix_bad(events: list[dict[str, Any]] | None) -> bool:
    return any(
        e.get("fix") == "none" or e.get("sats") == 0 or float(e.get("hdop") or 0) >= GPS_LOSS_HDOP
        for e in events or []
    )


def controller_changed(events: list[dict[str, Any]] | None, mission: str | None) -> bool:
    """Otro controlador en los últimos eventos del enlace (o uno distinto del de la misión)."""
    ids = {e.get("controller_id") for e in events or []}
    return len(ids) > 1 or (mission is not None and bool(ids) and ids != {mission})


def step_of(facts: Facts) -> float | None:
    """El salto con el que se decide la recuperación: el del módulo si lo hay, si no el de la
    ventana (la misma regla que `guardrails.gps_step`)."""
    if facts.module_step is not None:
        return facts.module_step
    return (facts.metrics or {}).get("gps_max_step_m")


def inputs_for(
    facts: Facts,
    *,
    rule: str,
    kind: str,
    source: str | None,
    detection_id: str,
    link_recovery: bool,
    state: MonitorState,
    as_of: float,
    mission_controller: str | None = None,
) -> dict[str, Any]:
    """Las entradas de las tablas `cause` y `severity` (la confianza se completa después, cuando
    ya se sabe la causa: `support_for`)."""
    m = facts.metrics or {}
    now = m.get("now") or {}
    computed = metric_facts(m)
    recent = state.recent_gps_alert(as_of)
    open_gps = next((a for a in state.open_alerts() if state.is_gps_alert(a)), None)
    degraded_open = any(d.open and d.rule == "GPS_DEGRADED" for d in state.detections.values())
    gps_dev = m.get("gps_deviation_from_plan_m") or {}
    radar_dev = m.get("radar_deviation_from_plan_m") or {}
    radar_now = now.get("radar_deviation_from_plan_m")
    gps_now = now.get("gps_deviation_from_plan_m")
    course = (m.get("course_deg") or {}).get("gps")
    bearing = m.get("bearing_to_next_waypoint_deg")
    qualities = [float(e["quality"]) for e in facts.radar or [] if e.get("quality") is not None]
    radar_silent = not m.get("radar_available") and radar_now is None
    other_position = any(
        d.open and d.detection_id != detection_id and d.rule in POSITION_RULES
        for d in state.detections.values()
    )
    return {
        "rule": rule,
        "kind": kind,
        "link_recovery": link_recovery,
        "fault_source": _fault_source(rule, source),
        "gps_alert_recent": recent is not None,
        "gps_step_m": step_of(facts),
        "gps_radar_disagreed": computed["gps_radar_disagreed"],
        "gps_radar_agree_now": now.get("gps_radar_agree"),
        "position_conflict": rule == "SOURCE_DISCREPANCY" or computed["gps_radar_disagreed"],
        "gps_loss_open": open_gps is not None
        and open_gps.cause in ("GPS_JAMMING", "SENSOR_FAULT")
        and degraded_open,
        "open_gps_alert_cause": open_gps.cause if open_gps is not None else "none",
        "gps_fix_bad": gps_fix_bad(facts.gps),
        "gps_dev_mean_m": gps_dev.get("mean"),
        "radar_minus_gps_now_m": (
            None if radar_now is None or gps_now is None else round(radar_now - gps_now, 1)
        ),
        "radar_trend": radar_dev.get("trend") or "none",
        "radar_silent": radar_silent,
        "radar_quality_min": min(qualities) if qualities else None,
        "wind_notable": computed["wind_notable"],
        "wind_with_drift": computed["wind_with_drift"],
        "link_controller_changed": controller_changed(facts.link, mission_controller),
        "link_anomalous": link_is_anomalous(facts.link or []),
        "course_vs_waypoint_deg": (
            None if course is None or bearing is None else round(_angle(course, bearing), 1)
        ),
        "gps_dev_trend": gps_dev.get("trend") or "none",
        "deviation_now_m": radar_now if radar_now is not None else gps_now,
        "route_trend": now.get("route_trend") or "none",
        "other_position_detection_open": other_position,
    }


def _fault_source(rule: str, source: str | None) -> str:
    """De qué es un fallo de sensor: la fuente callada, el GPS, el enlace o la posición."""
    if rule == "SOURCE_SILENT" and source:
        return source
    if rule == "GPS_DEGRADED":
        return "gps"
    if rule == "LINK_ANOMALY":
        return "link"
    return "position"


def support_for(
    cause: str,
    phase: str,
    inputs: dict[str, Any],
    facts: Facts,
    mission_controller: str | None = None,
) -> tuple[int, int]:
    """Cuántas fuentes independientes apoyan la causa y cuántas la contradicen (criterio de
    `monitor_output.md`: GPS, radar, estación meteorológica y enlace). **Es un criterio propuesto
    para la E6, no derivado de datos.**"""
    agree_now = inputs["gps_radar_agree_now"]
    disagreed = inputs["gps_radar_disagreed"]
    step = inputs["gps_step_m"]
    jumped = step is not None and step >= RECOVERY_STEP_M
    support = contra = 0
    if phase == "recovering":
        if cause == "HIJACK":
            support += link_back(facts, mission_controller)  # el enlace ha vuelto
        else:
            support += jumped  # el GPS ha saltado a la posición real
        support += agree_now is True  # GPS y radar coinciden ahora
        contra += agree_now is False
        return support, contra
    if cause == "WIND":
        support += inputs["wind_notable"] and inputs["wind_with_drift"]  # la estación
        support += not disagreed  # GPS y radar ven la misma deriva
        contra += disagreed
        contra += inputs["link_anomalous"]
    elif cause == "GPS_SPOOFING":
        support += (inputs["radar_minus_gps_now_m"] or 0) > 0  # el radar ve al dron fuera
        support += not inputs["gps_fix_bad"]  # el GPS parece perfecto
        contra += inputs["gps_fix_bad"]
    elif cause == "HIJACK":
        support += inputs["link_controller_changed"] or inputs["link_anomalous"]  # el enlace
        support += inputs["gps_dev_trend"] == "increasing" or (
            (inputs["course_vs_waypoint_deg"] or 0) > 45
        )  # la trayectoria
        contra += disagreed  # si GPS y radar discrepan, la posición no es fiable
    elif cause == "GPS_JAMMING":
        support += inputs["gps_fix_bad"]  # el propio GPS
        support += disagreed  # el radar ve la deriva
    elif cause == "SENSOR_FAULT":
        if inputs["rule"] == "SOURCE_SILENT":
            support += 1  # el silencio
            support += _others_report(facts, inputs["fault_source"])  # las demás siguen
        else:
            support += 1  # el detector
            contra += inputs["rule"] in ("SOURCE_DISCREPANCY", "ROUTE_DEVIATION") and (
                (inputs["gps_dev_mean_m"] or 0) < 15
            )  # GPS en el plan con el radar fuera es el patrón del engaño
    return int(support), int(contra)


def link_back(facts: Facts, mission_controller: str | None) -> bool:
    """El último `LinkStatus` es del controlador de la misión."""
    link = facts.link or []
    return (
        bool(link)
        and mission_controller is not None
        and (link[-1].get("controller_id") == mission_controller)
    )


def _others_report(facts: Facts, silent: str) -> bool:
    """Las demás fuentes de posición y el enlace siguen informando."""
    reporting = {
        "gps": bool(facts.gps),
        "radar": bool(facts.radar),
        "link": bool(facts.link),
    }
    return all(v for k, v in reporting.items() if k != silent)


__all__ = [
    "GPS_CAUSES",
    "Facts",
    "ToolCall",
    "controller_changed",
    "gather",
    "gps_fix_bad",
    "inputs_for",
    "link_back",
    "step_of",
    "support_for",
]
