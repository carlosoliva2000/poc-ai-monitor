"""Lo que recibe el LLM: la revisión del incidente en inglés llano y los hechos de ahora.

Todo número, hora y nombre que el modelo puede usar sale de aquí; `checks.py` comprueba después que
el texto no trae nada que no estuviera en esta entrada. El glosario (`agent-assets/glossary.yaml`)
traduce facetas, estados y entradas de las tablas, así que el modelo no ve nombres internos.
"""

import math
import re
from dataclasses import dataclass, field
from functools import cache
from typing import Any

import yaml

from poc_contracts.enums import IncidentKind

from ..outbox import format_t
from ..situation.policy import load_policy
from .config import ASSETS_DIR
from .store import Store

COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW",
           "NW", "NNW")  # fmt: skip
KIND_RE = re.compile(r"\b(" + "|".join(k.value for k in IncidentKind) + r")\b")
CHANGE_PHRASE = {
    "opened": "the incident opened",
    "state": "the incident changed state",
    "renamed": "the incident got a more specific name",
    "closed": "the incident closed",
}


@cache
def glossary() -> dict[str, Any]:
    return dict(yaml.safe_load((ASSETS_DIR / "glossary.yaml").read_text(encoding="utf-8")))


@cache
def _policy():  # type: ignore[no-untyped-def]
    return load_policy()


def number(value: float) -> str:
    """Un número sin ceros de más: 7.2, 32, -0.7."""
    text = f"{round(value, 2):.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def compass(deg: float) -> str:
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def wind_text(speed: float, from_deg: float) -> str:
    """«7.2 m/s from N (350°), pushing S (170°)»: de dónde viene y hacia dónde empuja."""
    to_deg = (from_deg + 180) % 360
    return (
        f"{speed:.1f} m/s from {compass(from_deg)} ({from_deg:.0f}°), "
        f"pushing {compass(to_deg)} ({to_deg:.0f}°)"
    )


def distance_to_route(point: tuple[float, float], route: list[tuple[float, float]]) -> float | None:
    """Distancia mínima del punto a la polilínea de la ruta planificada."""
    if len(route) < 2:
        return None
    best = math.inf
    px, py = point
    for (ax, ay), (bx, by) in zip(route, route[1:], strict=False):
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def value_word(value: Any) -> str:
    return str(glossary()["values"].get(str(value), value))


def condition_text(cond: dict[str, Any]) -> str:
    """Una condición de la tabla en palabras: «signal strength against its nominal +7.2 dB»."""
    feature = cond["feature"]
    info = glossary()["features"].get(feature, {"label": feature})
    label = info["label"][0].upper() + info["label"][1:]
    value = cond.get("value")
    if value is None:
        return f"{label}: no data"
    if info.get("kind") == "flag" or isinstance(value, bool):
        return f"{label}: {'yes' if value else 'no'}"
    if isinstance(value, str):  # p. ej. el estado anterior de la situación del dron
        return f"{label}: {value_word(value)}"
    unit = info.get("unit", "")
    # el umbral de la fila no se enseña: son cortes de las tablas y confunden al modelo
    return f"{label}: {number(value)}{unit}"


def evidence_lines(update: dict[str, Any], for_chat: bool = False) -> list[str]:
    """Las evidencias del incidente en palabras. `for_chat` quita también las entradas técnicas
    (σ del sensor y velocidades de crucero), que el operador no lee."""
    lines = []
    for item in update["evidence"]:
        facet = glossary()["facets"].get(item["facet"], item["facet"])
        parts = [
            condition_text(c)
            for c in item["conditions"]
            if not glossary()["features"].get(c["feature"], {}).get("hidden")
            and not (for_chat and glossary()["features"].get(c["feature"], {}).get("technical"))
        ]
        detail = f". {'; '.join(parts)}" if parts else ""
        lines.append(f"- {facet}: {value_word(item['state'])}{detail}")
    return lines


def context_lines(update: dict[str, Any]) -> list[str]:
    """El contexto del incidente; los tipos de incidente salen con su nombre, no su código."""
    policy = _policy()
    lines = []
    for item in update["context"]:
        info = glossary()["features"].get(item["feature"], {"label": item["feature"]})
        value = item["value"]
        if isinstance(value, str):
            value = KIND_RE.sub(lambda m: policy.name(IncidentKind(m.group(1))), value)
            value = value.replace("(possible)", "(a weak hint that may be wrong)").replace(
                "(probable)", "(probable)"
            )
            lines.append(f"- {info['label'].capitalize()}: {value_word(value)}")
        else:
            lines.append(f"- {info['label'].capitalize()}: {number(value)}{info.get('unit', '')}")
    return lines


def ago(store: Store, kind: str) -> str:
    """Hace cuánto llegó la última lectura de ese tipo, en palabras («just now», «5 s ago»)."""
    seconds = store.now - store.last[kind][0]
    return "just now" if seconds < 1 else f"{seconds:.0f} s ago"


def link_facts(store: Store) -> list[str]:
    """El enlace según su último `LinkStatus` (cada 5 s), **con su antigüedad**: la evidencia del
    incidente puede ser más nueva (lee la telemetría del dron), y sin la hora el modelo veía
    «conectado» y «sin señal» a la vez. Si la telemetría ha llegado después de un enlace perdido,
    se dice."""
    link = store.reading("LinkStatus", 12)
    if link is None:
        return []
    when = ago(store, "LinkStatus")
    if link["rssi_dbm"] is None:
        line = f"- Command link at the last link report ({when}): no signal, all packets lost"
        telemetry = [
            store.last[k][0]
            for k in ("PositionUpdated", "GnssStatus", "AutopilotStatus")
            if k in store.last
        ]
        if telemetry and max(telemetry) > store.last["LinkStatus"][0]:
            line += "; drone telemetry has arrived since, so the link is coming back"
        return [line]
    return [
        f"- Command link at the last link report ({when}): signal {link['rssi_dbm']:.0f} dBm, "
        f"packet loss {link['packet_loss_pct']:.0f} %"
    ]


def now_facts(store: Store) -> list[str]:
    """Hechos de ahora, calculados con lo último que llegó del bus (cifras redondeadas)."""
    lines: list[str] = []
    gps = store.reading("PositionUpdated", 5)
    radar = store.reading("TrackUpdated", 6)
    has_fix = gps is not None and gps["fix"] != "none" and gps["x"] is not None
    if has_fix and radar is not None:
        gap = math.hypot(gps["x"] - radar["x"], gps["y"] - radar["y"])
        lines.append(f"- Distance between the GPS position and the radar track: {gap:.0f} m")
    if radar is not None:
        dev = distance_to_route((radar["x"], radar["y"]), store.route)
        if dev is not None:
            lines.append(f"- Radar distance to the planned route: {dev:.0f} m")
    if has_fix:
        dev = distance_to_route((gps["x"], gps["y"]), store.route)
        if dev is not None:
            lines.append(f"- GPS distance to the planned route: {dev:.0f} m")
    elif gps is not None:
        lines.append("- The GPS has no fix")
    gnss = store.reading("GnssStatus", 5)
    if gnss is not None:
        cn0 = gnss["cn0_dbhz"] - store.cn0_nominal_dbhz
        agc = gnss["agc_db"] - store.agc_nominal_db
        lines.append(f"- GPS signal strength (C/N0) against its nominal: {cn0:+.1f} dB")
        lines.append(f"- GPS receiver gain (AGC) against its nominal: {agc:+.1f} dB")
    wind = store.reading("WindReported", 30)
    if wind is not None:
        lines.append(f"- Weather station wind: {wind_text(wind['speed_mps'], wind['from_deg'])}")
    apl = store.reading("AutopilotStatus", 5)
    if apl is not None:
        lines.append(f"- Estimated wind on board: {apl['wind_est_speed_mps']:.1f} m/s")
        lines.append(f"- Autopilot mode: {value_word(apl['mode'])}")
    lines += link_facts(store)
    bat = store.reading("BatteryStatus", 30)
    if bat is not None:
        lines.append(f"- Battery: {bat['battery_pct']:.0f} %")
    telemetry = [store.last[k][0] for k in ("PositionUpdated", "GnssStatus", "AutopilotStatus")
                 if k in store.last]  # fmt: skip
    if telemetry:
        silent = store.now - max(telemetry)
        if silent >= 5:
            lines.append(f"- No drone telemetry for {silent:.0f} s")
    return lines


@dataclass
class PromptInput:
    """La entrada del LLM y lo que el texto de salida puede citar."""

    text: str
    current: str  # lo que vale «ahora»: evidencias, contexto y hechos de ahora
    opening: str  # solo de la apertura
    allowed_kinds: set[IncidentKind] = field(default_factory=set)
    event_ids: list[str] = field(default_factory=list)  # los de la revisión (campos, no texto)
    times: list[float] = field(default_factory=list)
    checks_text: str = (
        ""  # el «qué comprobar» del incidente: su vocabulario (p. ej. «dead reckoning») vale
    )


def build_input(update: dict[str, Any], store: Store) -> PromptInput:
    """La revisión del incidente, ya traducida, con los hechos de ahora y los de la apertura."""
    as_of = update["as_of_sim_time"]
    kind = IncidentKind(update["kind"])
    head = [
        f"Incident: {update['name']}",
        f"State: {update['state'].replace('recovering', 'recovering (the cause has gone)')}",
        f"What just happened: {CHANGE_PHRASE.get(update['change'], update['change'])}",
        f"Severity: {update['severity']}. Confidence: {update['confidence']}",
        f"Opened at {format_t(update['opened_at'])}. This revision is from {format_t(as_of)}",
    ]
    evidence = evidence_lines(update)
    context = context_lines(update)
    facts = now_facts(store)
    parts = ["\n".join(head)]
    current_parts: list[str] = []
    for title, lines in (
        ("Evidence now (what the monitor's rules read)", evidence),
        ("Context", context),
        ("Facts now", facts),
    ):
        if lines:
            block = f"{title}:\n" + "\n".join(lines)
            parts.append(block)
            current_parts.append(block)
    opening_text = ""
    first = store.opening(update["incident_id"])
    if first is not None and first["revision"] != update["revision"]:
        opening_lines = evidence_lines(first)
        if opening_lines:
            opening_text = f"At opening ({format_t(first['as_of_sim_time'])}):\n" + "\n".join(
                opening_lines
            )
            parts.append(opening_text)
    if update["checks"]:
        parts.append("What to check:\n" + "\n".join(f"- {c}" for c in update["checks"]))
    allowed = {kind} | {IncidentKind(m) for m in KIND_RE.findall(" ".join(
        str(c["value"]) for c in update["context"] if isinstance(c["value"], str)))}  # fmt: skip
    return PromptInput(
        text="\n\n".join(parts),
        current="\n".join(current_parts) + "\n" + "\n".join(update["checks"]) + "\n" + head[3],
        opening=opening_text,
        allowed_kinds=allowed,
        event_ids=list(update["evidence_event_ids"]),
        checks_text=" ".join(update["checks"]),
        times=[as_of, update["opened_at"]]
        + ([first["as_of_sim_time"]] if first is not None else []),
    )
