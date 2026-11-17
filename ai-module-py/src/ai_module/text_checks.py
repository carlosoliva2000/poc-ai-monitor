"""Comprobaciones de texto, sin LLM y deterministas (E6).

Las usan `tools/experiments/text_metrics.py` (para medir los textos de una matriz) y el
enriquecimiento del híbrido (`enrich.py`, para no publicar un texto que no pase): nombres internos
(tools, skills, campos de los hechos y de `checks`, `true`/`false` sueltos, nombres de enum),
cifras con unidad que no estaban entre las recibidas, horas e ids que no estaban.
"""

import re
import unicodedata

ID_RE = re.compile(r"\b(?:gps|rad|met|lnk|bat|mis|det|ai|chk|act|tcl|ops|sim|plr)-\d{3,6}\b")
DASHES = dict.fromkeys(
    map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"), "-"
)
ENUMS = [
    "WIND",
    "HIJACK",
    "GPS_SPOOFING",
    "SENSOR_FAULT",
    "GPS_JAMMING",
    "ROUTE_DEVIATION",
    "SOURCE_DISCREPANCY",
    "SOURCE_SILENT",
    "GPS_DEGRADED",
]
TOOLS = [
    "get_events",
    "get_mission_plan",
    "get_track_metrics",
    "get_my_alerts",
    "get_flight_summary",
    "load_skill",
    "publish_alert",
    "acknowledge_detection",
    "close_alert",
]
SKILLS = ("route-deviation", "source-discrepancy", "report-format")
MODULE_FIELDS = [
    "alert_id",
    "detection_id",
    "detection_ids",
    "evidence_event_ids",
    "as_of_sim_time",
    "sim_time",
    "tool_choice",
]


UNIT_FIGURE_RE = re.compile(
    r"(?<![\w.+:-])(\d+(?:\.\d+)?)\s*(?:%|°|(?:minutes?|min|m/s|km/h|km|meters?|metres?|seconds?|ms|hz|dbm|db|m|s)"
    r"(?![\w/]))",
    re.I,
)
ANY_NUMBER_RE = re.compile(r"(?<![\w.+:-])\d+(?:\.\d+)?")
APPROX_RE = re.compile(r"(?:about|approximately|around|roughly|~|circa)\s*$", re.I)


def prompt_numbers(text: str) -> set[float]:
    """Todas las cifras de un texto (sin ids ni horas T+mm:ss, que llevan guion o dos puntos)."""
    return {float(m.group(0)) for m in ANY_NUMBER_RE.finditer(norm(text))}


def unsupported_figures(text: str, known: set[float]) -> list[str]:
    """Cifras con unidad del texto que no están entre las cifras recibidas (`known`). Un entero
    precedido de «about», «around»… cuenta como respaldado si redondea una cifra recibida."""
    plain = norm(text)
    found: list[str] = []
    for m in UNIT_FIGURE_RE.finditer(plain):
        value = float(m.group(1))
        if any(abs(value - k) <= 0.05 for k in known):
            continue
        approx = APPROX_RE.search(plain[max(0, m.start() - 14) : m.start()])
        if approx and value.is_integer() and any(round(k) == value for k in known):
            continue
        found.append(m.group(0).strip())
    return found


def norm(text: str) -> str:
    """Unicode comparable: NFKC, guiones y espacios especiales a ASCII."""
    text = unicodedata.normalize("NFKC", text).translate(DASHES)
    return re.sub(r"\s", " ", text)


def internal_field_names() -> tuple[set[str], set[str]]:
    """(campos con guion bajo, nombres con punto) de los hechos y de los `checks`, sacados de los
    modelos del contrato."""
    from poc_contracts import payloads, tools  # noqa: PLC0415

    underscored: set[str] = set(MODULE_FIELDS)
    dotted: set[str] = set()
    models = {
        "": tools.TrackMetrics,
        "wind": tools.WindStat,
        "gps_radar": tools.GpsRadarFact,
        "now": tools.NowFacts,
    }
    for prefix, model in models.items():
        for name in model.model_fields:
            if "_" in name:
                underscored.add(name)
            if prefix:
                dotted.add(f"{prefix}.{name}")
    underscored |= set(payloads.AlertChecks.model_fields)
    underscored |= {"now"} - {"now"}  # `now` es una palabra corriente: no se cuenta
    return underscored, dotted


UNDERSCORED, DOTTED = internal_field_names()
NAME_RE = re.compile(
    r"(?<![\w.])("
    + "|".join(
        re.escape(n)
        for n in sorted([*TOOLS, *SKILLS, *UNDERSCORED, *DOTTED], key=len, reverse=True)
    )
    + r")(?![\w])"
)
ENUM_RE = re.compile(r"\b(" + "|".join(ENUMS) + r")\b")
BOOL_RE = re.compile(
    r"(?:[=:]\s*|\bis\s+|\bare\s+|`)(true|false)\b(?!\s+(?:alarm|positive|reading))"
)


def find_names(text: str) -> tuple[list[str], list[str], list[str]]:
    plain = norm(text)
    names = [m.group(1) for m in NAME_RE.finditer(plain)]
    enums = [m.group(1) for m in ENUM_RE.finditer(plain)]
    bools = [m.group(1) for m in BOOL_RE.finditer(plain)]
    return names, enums, bools


# --- Enriquecimiento del híbrido (E6) ---------------------------------------------------------

TIME_RE = re.compile(r"T\+\d{1,2}:\d{2}")
CAPS_NAME_RE = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b")
"""Nombres en mayúsculas con guion bajo (causas y reglas: `GPS_SPOOFING`, `LINK_ANOMALY`)."""
MAX_ENRICH_CHARS = 400


def enrichment_problems(text: str, *, prompt: str, seen_ids: set[str]) -> list[str]:
    """Por qué el texto de un `AlertEnriched` no se publica (vacío: se publica). Mensajes en
    inglés: van a la traza. `prompt` es todo lo que recibió el LLM; una cifra, una hora o un id
    solo valen si estaban ahí (o entre las evidencias consultadas, `seen_ids`)."""
    plain = norm(text).strip()
    problems: list[str] = []
    if not plain:
        return ["empty text"]
    if len(plain) > MAX_ENRICH_CHARS:
        problems.append(f"too long: {len(plain)} characters (maximum {MAX_ENRICH_CHARS})")
    names, enums, bools = find_names(plain)
    caps = sorted(set(CAPS_NAME_RE.findall(plain)) - set(enums))
    if names:
        problems.append(f"internal names: {', '.join(sorted(set(names)))}")
    if enums or caps:
        problems.append(f"names in capitals: {', '.join(sorted({*enums, *caps}))}")
    if bools:
        problems.append(f"bare booleans: {', '.join(bools)}")
    known = prompt_numbers(prompt)
    figures = unsupported_figures(plain, known)
    if figures:
        problems.append(f"figures not in the facts: {', '.join(figures)}")
    shown = norm(prompt)
    times = [t for t in TIME_RE.findall(plain) if t not in shown]
    if times:
        problems.append(f"times not in the facts: {', '.join(times)}")
    ids = [i for i in ID_RE.findall(plain) if i not in seen_ids and i not in shown]
    if ids:
        problems.append(f"event ids not seen: {', '.join(ids)}")
    return problems
