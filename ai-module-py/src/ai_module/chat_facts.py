"""Hechos de la trayectoria para el sistema de un chat sin tools, **con su interpretación**.

El chat no tiene que deducir si un valor es «notable» o va «a favor»: cada hecho que exige una
comparación o un juicio lleva al lado el sí o el no, calculado con las mismas reglas que usa el
guardrail del monitor para los `checks` de las alertas (`metric_facts`), y las cifras se
mantienen para que pueda darlas. Sin nombres de campos.
"""

from typing import Any

from .agent.guardrails import link_is_anomalous, metric_facts
from .outbox import format_t


def _n(value: float | None, decimals: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{decimals}f}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


_TREND = {"increasing": "increasing", "decreasing": "decreasing", "stable": "stable"}


def _deviation(label: str, stats: dict[str, Any] | None) -> str | None:
    if stats is None:
        return f"- {label}: no data in the window."
    trend = _TREND.get(stats.get("trend") or "", "no clear trend")
    mean, top = _n(stats.get("mean")), _n(stats.get("max"))
    return f"- {label}: mean {mean} m, maximum {top} m, trend {trend}."


def describe_metrics(metrics: dict[str, Any] | None, note: str) -> str:
    """Texto para el prompt de un chat a partir del último resultado de `get_track_metrics`."""
    if metrics is None:
        return "The monitor has not yet looked up the trajectory metrics."
    facts = metric_facts(metrics)
    wind = metrics.get("wind")
    gps_radar = metrics.get("gps_radar")
    distance = metrics.get("gps_radar_distance_m")
    step = metrics.get("gps_max_step_m")
    lines = [f"{note}:"]

    # viento
    if wind is None:
        lines.append("- There is no wind data in that window (or it is completely calm).")
    else:
        lines.append(
            f"- The wind is notable: {_yes_no(facts['wind_notable'])} (mean "
            f"{_n(wind.get('mean_speed_mps'))} m/s, gust {_n(wind.get('max_gust_mps'))} m/s)."
        )
        gap = wind.get("drift_vs_wind_deg")
        if gap is None:
            lines.append(
                "- The drift goes with the wind: no (the drone is not moving off the route)."
            )
        elif facts["wind_with_drift"]:
            lines.append(
                "- The drift goes with the wind: yes (the wind pushes in the same direction in "
                f"which the drone moves off the route; difference of {_n(gap)}° between the two "
                "directions)."
            )
        else:
            lines.append(
                "- The drift goes with the wind: no (the wind does not push in the direction in "
                f"which the drone moves off the route; difference of {_n(gap)}° between the two "
                "directions)."
            )

    # GPS contra radar
    if gps_radar is None or distance is None:
        lines.append(
            "- GPS and radar disagree: cannot be known (one of the two sources is missing)."
        )
    else:
        lines.append(
            f"- GPS and radar disagree: {_yes_no(facts['gps_radar_disagreed'])} (mean distance "
            f"of {_n(distance.get('mean'))} m, maximum of {_n(distance.get('max'))} m)."
        )

    # salto del GPS (recuperación tras un engaño o una pérdida)
    if step is None:
        lines.append("- Sudden GPS jump: cannot be known (too few samples).")
    else:
        lines.append(
            "- Sudden GPS jump (typical of the recovery after a spoofing or a loss): "
            f"{_yes_no(facts['gps_jump'])} (largest increase of the deviation between two "
            f"consecutive samples: {_n(step)} m)."
        )

    # cifras sueltas
    for label, key in (
        ("GPS deviation from the planned route", "gps_deviation_from_plan_m"),
        ("Radar deviation from the planned route", "radar_deviation_from_plan_m"),
    ):
        lines.append(_deviation(label, metrics.get(key)) or "")
    return "\n".join(line for line in lines if line)


def describe_link(events: list[dict[str, Any]] | None, note: str) -> str:
    """El enlace de mando que miró el monitor, con el sí o el no de «anómalo» (las mismas reglas
    que el guardrail) y las cifras que lo sostienen. Vacío si el monitor aún no lo ha mirado."""
    if not events:
        return ""
    anomalous = link_is_anomalous(events)
    controllers = list(dict.fromkeys(str(e.get("controller_id")) for e in events))
    rssi = [e["rssi_dbm"] for e in events if "rssi_dbm" in e]
    latency = [e["latency_ms"] for e in events if "latency_ms" in e]
    parts = []
    if len(controllers) > 1:
        change = next(e for e in events if str(e.get("controller_id")) != controllers[0])
        parts.append(
            f"the controller changes from {controllers[0]} to {controllers[1]} at "
            f"{format_t(change['sim_time'])}"
        )
    else:
        parts.append(f"a single controller, {controllers[0]}")
    if rssi:
        parts.append(f"signal between {_n(min(rssi), 0)} and {_n(max(rssi), 0)} dBm")
    if latency:
        parts.append(f"latency between {_n(min(latency), 0)} and {_n(max(latency), 0)} ms")
    parts.append(note)
    return f"- The command link is anomalous: {_yes_no(anomalous)} ({'; '.join(parts)})."
