"""Textos de las alertas de la tabla de decisión (E6): plantillas con los hechos de la fila.

Para el responsable del dron, en inglés y en palabras llanas: sin nombres de campos, tools ni
`true`/`false`, sin las mayúsculas de causas y reglas. Cada texto cuenta solo los hechos que
importan para su causa (la consulta del 16/11 vio que volcarlo todo despistaba: el viento en una
alerta de secuestro). Si falta un dato, la frase que lo necesita no se escribe.
"""

from typing import Any

from ..outbox import format_t
from .features import Facts

SOURCE_NAMES = {
    "gps": "GPS",
    "radar": "radar",
    "meteo": "weather station",
    "link": "command link",
    "battery": "battery",
}
LOSS_OF = {
    "radar": "Without the radar, the GPS position cannot be checked.",
    "gps": "Without the GPS, the position is known only through the radar.",
    "meteo": "Without the weather station, the wind cannot be confirmed.",
    "battery": "Without the battery reports, the remaining endurance is unknown.",
    "link": "Without the command link, the control of the drone is at risk.",
}
RECOMMEND_LOSS = {
    "radar": "Treat the GPS position with care until the radar reports again.",
    "gps": "Use the radar as the position reference until the GPS reports again.",
    "meteo": "Keep in mind that a drift cannot be confirmed as wind while the station is silent.",
    "battery": "Check the battery by other means and plan the return with margin.",
    "link": "Check the command link and be ready to apply the lost-link procedure.",
}
TREND_WORDS = {
    "approaching": "getting closer to the route",
    "moving_away": "moving away from the route",
    "steady": "holding its distance to the route",
}


def _n(value: float | None, decimals: int = 1) -> str | None:
    return None if value is None else f"{value:.{decimals}f}"


def _join(parts: list[str | None]) -> str:
    return " ".join(p for p in parts if p)


def _clip(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _now(facts: Facts) -> dict[str, Any]:
    return (facts.metrics or {}).get("now") or {}


def _where_now(facts: Facts) -> str | None:
    """«The drone is 77.7 m from the route now (radar) and moving away; GPS and radar agree.»"""
    now = _now(facts)
    dev = now.get("radar_deviation_from_plan_m")
    by = "radar"
    if dev is None:
        dev, by = now.get("gps_deviation_from_plan_m"), "GPS"
    if dev is None:
        return None
    trend = TREND_WORDS.get(str(now.get("route_trend")))
    agree = now.get("gps_radar_agree")
    tail = {True: "GPS and radar agree", False: "GPS and radar disagree"}.get(agree)
    text = f"Now the drone is {_n(dev)} m from the route ({by})"
    text += f" and {trend}" if trend else ""
    return text + (f"; {tail}." if tail else ".")


def _wind(facts: Facts) -> str | None:
    w = (facts.metrics or {}).get("wind")
    if not w:
        return None
    text = _now(facts).get("wind")
    blows = f", {text}" if text else ""
    return (
        f"The weather station reports {_n(w.get('mean_speed_mps'))} m/s with gusts of "
        f"{_n(w.get('max_gust_mps'))} m/s{blows} ({w.get('last_event_id')})."
    )


def _gps_quality(facts: Facts) -> str | None:
    if not facts.gps:
        return None
    g = facts.gps[-1]
    if g.get("fix") == "none":
        return f"The GPS has no fix ({g.get('sats')} satellites, {g.get('event_id')})."
    return (
        f"The GPS has a good fix ({g.get('sats')} satellites, hdop {g.get('hdop')}, "
        f"{g.get('event_id')})."
    )


def _link(facts: Facts) -> str | None:
    if not facts.link:
        return None
    controllers = list(dict.fromkeys(str(e.get("controller_id")) for e in facts.link))
    last = facts.link[-1]
    who = " then ".join(controllers)
    return (
        f"Command link: controller {who}, latency {_n(last.get('latency_ms'), 0)} ms, signal "
        f"{_n(last.get('rssi_dbm'), 0)} dBm ({last.get('event_id')})."
    )


def alert_texts(
    *,
    cause: str,
    phase: str,
    severity: str,
    rule: str,
    inputs: dict[str, Any],
    facts: Facts,
    detection: dict[str, Any],
    as_of: float,
    episode_cause: str | None = None,
    mission_controller: str | None = None,
    link_back: tuple[float, str] | None = None,
) -> tuple[str, str, str]:
    """`(summary, explanation, recommendation)` de una alerta de la tabla."""
    m = facts.metrics or {}
    now = _now(facts)
    t = format_t(as_of)
    seen = (
        f"At {t} the detector warned: {detection.get('message')}."
        if detection.get("message")
        else None
    )
    dist_now = _n(now.get("gps_radar_distance_m"))
    dist_max = _n((m.get("gps_radar_distance_m") or {}).get("max"))
    dev_now = inputs.get("deviation_now_m")

    if phase == "recovering" and cause == "HIJACK":
        back = (
            f"The command link returned to {mission_controller} at {format_t(link_back[0])} "
            f"({link_back[1]})."
            if link_back
            else f"The command link is back with {mission_controller}."
        )
        summary = (
            f"The command link is back with {mission_controller}; the drone is still "
            f"{_n(dev_now, 0)} m from the route."
            if dev_now is not None
            else f"The command link is back with {mission_controller}."
        )
        explanation = _join([back, _where_now(facts)])
        recommendation = (
            "Check where the drone is and that it gets back to the route; the control is back "
            "with the mission controller."
        )
    elif phase == "recovering":
        what = "spoofing" if episode_cause == "GPS_SPOOFING" else "loss of the GPS"
        step = _n(inputs.get("gps_step_m"), 0)
        summary = f"The GPS is back after the {what}: it jumped {step} m to the real position."
        explanation = _join(
            [
                f"At {t} the GPS position jumped {step} m in one second: the GPS is giving the "
                "real position again.",
                _where_now(facts),
            ]
        )
        recommendation = (
            "Check that the drone gets back to the route; the GPS position is valid again."
            if severity == "medium"
            else "Watching is enough: the drone is close to the route and the GPS is valid again."
        )
    elif cause == "WIND":
        summary = (
            f"The wind is pushing the drone {_n(dev_now, 0)} m off the route; GPS and radar agree."
        )
        explanation = _join([seen, _wind(facts), "It pushes the same way as the drift.",
                             _where_now(facts)])  # fmt: skip
        recommendation = (
            "No intervention: the drone corrects by itself; watch that the deviation does not grow."
            if severity == "low"
            else "Watch the drone closely: the deviation is large or growing; be ready to act if "
            "it keeps moving away."
        )
    elif cause == "GPS_SPOOFING":
        summary = (
            f"The GPS says the drone is on the route, but the radar sees it {_n(dev_now, 0)} m "
            "off: likely GPS spoofing."
        )
        explanation = _join(
            [
                seen,
                f"GPS and radar were up to {dist_max} m apart.",
                _gps_quality(facts),
                f"The GPS stays {_n(inputs.get('gps_dev_mean_m'))} m from the route on average "
                "while the radar sees the drone moving away from it.",
            ]
        )
        recommendation = (
            "Do not trust the GPS position: use the radar as the reference for where the drone "
            "is, and warn whoever has to know."
        )
    elif cause == "GPS_JAMMING":
        drifting = inputs.get("gps_radar_disagreed")
        summary = (
            f"The GPS has lost the fix and the drone is drifting: GPS and radar are {dist_max} m "
            "apart."
            if drifting
            else "The GPS has lost the fix: the drone navigates by dead reckoning."
        )
        explanation = _join([seen, _gps_quality(facts), _where_now(facts)])
        recommendation = (
            "Use the radar as the position reference; hold position or return to base according "
            "to the procedure."
        )
    elif cause == "HIJACK":
        changed = inputs.get("link_controller_changed")
        others = [str(e.get("controller_id")) for e in facts.link or []]
        other = next((c for c in reversed(others) if c != mission_controller), None)
        summary = (
            f"The command link has been taken by another controller ({other})."
            if changed and other
            else "The drone leaves the route with a normal link: possible hijacking."
        )
        explanation = _join([seen, _link(facts), _where_now(facts)])
        recommendation = (
            "Recover control of the command link and warn whoever has to know; watch where the "
            "drone goes."
        )
    elif cause == "SENSOR_FAULT":
        source = inputs.get("fault_source")
        if rule == "SOURCE_SILENT":
            name = SOURCE_NAMES.get(str(source), str(source))
            summary = (
                f"The {name} has stopped reporting ({_n(detection.get('value'), 0)} s without "
                "data)."
            )
            explanation = _join([seen, LOSS_OF.get(str(source)), "The other sources keep "
                                 "reporting."])  # fmt: skip
            recommendation = RECOMMEND_LOSS.get(str(source), "Check the sensor.")
        elif rule == "GPS_DEGRADED":
            summary = "The GPS quality has degraded but it keeps a fix."
            explanation = _join([seen, _gps_quality(facts), _where_now(facts)])
            recommendation = "Treat the GPS position with care and compare it with the radar."
        elif rule == "LINK_ANOMALY":
            summary = "The command link has degraded; the controller is still the mission's."
            explanation = _join([seen, _link(facts)])
            recommendation = "Watch the command link and be ready for the lost-link procedure."
        else:
            summary = (
                f"GPS and radar disagree by up to {dist_max} m without the pattern of a "
                "spoofing: one of the two sensors may be failing."
            )
            explanation = _join([seen, _gps_quality(facts), _where_now(facts)])
            recommendation = (
                "Check which of the two sensors is failing before trusting the position."
            )
    else:  # UNKNOWN
        if inputs.get("radar_silent"):
            summary = "GPS and radar disagree but the radar is not reporting: it cannot be checked."
        else:
            summary = (
                f"The drone is {_n(dev_now, 0)} m off the route and the cause is not clear."
                if dev_now is not None
                else "Something does not add up and the cause is not clear."
            )
        wind = (facts.metrics or {}).get("wind")
        checked = [
            "No wind data in the window."
            if not wind
            else "The wind does not explain the drift.",  # fmt: skip
            "The command link is normal." if not inputs.get("link_anomalous") else None,
            f"GPS and radar agree ({dist_now} m apart now)."
            if now.get("gps_radar_agree")
            else None,
        ]
        explanation = _join([seen, *checked])
        recommendation = "Review the command link, the GPS fix and the radar before deciding."
    return _clip(summary), explanation, recommendation


UNITS = {
    "ROUTE_DEVIATION": " m",
    "SOURCE_DISCREPANCY": " m",
    "SOURCE_SILENT": " s",
    "GPS_DEGRADED": " of hdop",
    "LINK_ANOMALY": " ms of latency",
}


def close_reason(detection: dict[str, Any], facts: Facts) -> str:
    """Motivo del cierre: cuánto duró la detección y cómo está el dron ahora."""
    duration = _n(detection.get("duration_s"), 0)
    peak = _n(detection.get("max_value"))
    unit = UNITS.get(str(detection.get("rule")), "")
    first = f"The warning cleared after {duration} s (maximum {peak}{unit})." if duration else None
    return _join([first, _where_now(facts)]) or "All its warnings have cleared."
