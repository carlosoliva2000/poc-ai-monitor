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
    return "n/d" if value is None else f"{value:.{decimals}f}".replace(".", ",")


def _yes_no(value: bool) -> str:
    return "sí" if value else "no"


_TREND = {"increasing": "creciente", "decreasing": "decreciente", "stable": "estable"}


def _deviation(label: str, stats: dict[str, Any] | None) -> str | None:
    if stats is None:
        return f"- {label}: sin datos en la ventana."
    trend = _TREND.get(stats.get("trend") or "", "sin tendencia clara")
    mean, top = _n(stats.get("mean")), _n(stats.get("max"))
    return f"- {label}: media {mean} m, máxima {top} m, tendencia {trend}."


def describe_metrics(metrics: dict[str, Any] | None, note: str) -> str:
    """Texto para el prompt de un chat a partir del último resultado de `get_track_metrics`."""
    if metrics is None:
        return "El monitor todavía no ha consultado las métricas de la trayectoria."
    facts = metric_facts(metrics)
    wind = metrics.get("wind")
    gps_radar = metrics.get("gps_radar")
    distance = metrics.get("gps_radar_distance_m")
    step = metrics.get("gps_max_step_m")
    lines = [f"{note}:"]

    # viento
    if wind is None:
        lines.append("- No hay datos de viento en esa ventana (o es calma total).")
    else:
        lines.append(
            f"- El viento es notable: {_yes_no(facts['wind_notable'])} (media "
            f"{_n(wind.get('mean_speed_mps'))} m/s, racha {_n(wind.get('max_gust_mps'))} m/s)."
        )
        gap = wind.get("drift_vs_wind_deg")
        if gap is None:
            lines.append("- La deriva va a favor del viento: no (el dron no se aleja de la ruta).")
        elif facts["wind_with_drift"]:
            lines.append(
                "- La deriva va a favor del viento: sí (el viento empuja en el mismo sentido en "
                f"que el dron se aleja de la ruta; diferencia de {_n(gap)}° entre las dos "
                "direcciones)."
            )
        else:
            lines.append(
                "- La deriva va a favor del viento: no (el viento no empuja en el sentido en que "
                f"el dron se aleja de la ruta; diferencia de {_n(gap)}° entre las dos direcciones)."
            )

    # GPS contra radar
    if gps_radar is None or distance is None:
        lines.append("- GPS y radar discrepan: no se puede saber (falta una de las dos fuentes).")
    else:
        lines.append(
            f"- GPS y radar discrepan: {_yes_no(facts['gps_radar_disagreed'])} (distancia media "
            f"de {_n(distance.get('mean'))} m, máxima de {_n(distance.get('max'))} m)."
        )

    # salto del GPS (recuperación tras un engaño o una pérdida)
    if step is None:
        lines.append("- Salto brusco del GPS: no se puede saber (pocas muestras).")
    else:
        lines.append(
            f"- Salto brusco del GPS (típico de la recuperación tras un engaño o una pérdida): "
            f"{_yes_no(facts['gps_jump'])} (mayor aumento de la desviación entre dos muestras "
            f"seguidas: {_n(step)} m)."
        )

    # cifras sueltas
    for label, key in (
        ("Desviación del GPS respecto a la ruta planificada", "gps_deviation_from_plan_m"),
        ("Desviación del radar respecto a la ruta planificada", "radar_deviation_from_plan_m"),
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
            f"el controlador pasa de {controllers[0]} a {controllers[1]} desde "
            f"{format_t(change['sim_time'])}"
        )
    else:
        parts.append(f"un solo controlador, {controllers[0]}")
    if rssi:
        parts.append(f"señal entre {_n(min(rssi), 0)} y {_n(max(rssi), 0)} dBm")
    if latency:
        parts.append(f"latencia entre {_n(min(latency), 0)} y {_n(max(latency), 0)} ms")
    parts.append(note)
    return f"- El enlace de mando es anómalo: {_yes_no(anomalous)} ({'; '.join(parts)})."
