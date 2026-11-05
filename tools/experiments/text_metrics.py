"""Medida de los textos de una matriz, sin LLM: lo que escriben el monitor, los chats y el informe.

    uv run --project ai-module-py python tools/experiments/text_metrics.py \\
        --out experiments/e14-base-textos-medida.md \\
        actual=experiments/e12-cierre:actual gpt-oss=experiments/e13-gpt-oss-20b-low

Misma sintaxis de fuentes que `texts.py` (`nombre=carpeta[:perfil]`) y su mismo extractor de
informes. Por texto mide:

- nombres internos filtrados: tools, skills, campos de hechos y de `checks`, `true`/`false`
  sueltos y nombres de enum (causas y reglas);
- frases copiadas: tramos de 6 palabras seguidas o más iguales a las de los prompts y skills
  (de las dos carpetas de assets) o a los rechazos de los guardrails y al estado de la traza;
- ids citados que no existen en la ejecución (normalizando Unicode);
- cifras y direcciones que no cuadran con los hechos de la invocación: velocidad y racha del
  viento (±0,5 m/s), de dónde viene el viento (±15°; ±25° con puntos cardinales, y se distingue la
  confusión de/hacia: ±180°), distancia GPS–radar y desviación (±1 m);
- concreción: longitud y número de cifras, ids y tiempos.

Los hechos de un texto del monitor son los de su invocación; los de un chat o del informe, los de
todas las invocaciones del monitor hasta ese instante más los números de su propio prompt.
"""

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("texts", REPO / "tools" / "experiments" / "texts.py")
assert _spec and _spec.loader
texts = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("texts", texts)
_spec.loader.exec_module(texts)

SCENARIOS = ("nominal", "wind", "spoofing", "hijack", "faults", "demo")
ASSET_DIRS = ("agent-assets", "agent-assets-v13")
NGRAM = 6  # palabras seguidas iguales para contar una frase como copiada
SPEED_TOL = 0.5  # m/s
BEARING_TOL = 15.0  # grados
COMPASS_TOL = 25.0  # grados, cuando el texto da solo un punto cardinal
DIST_TOL = 1.0  # m

ANNEX_TITLES = ("Monitor assessment", "Technical recommendations")
RECOMMENDATION_KINDS = ("alert.recommendation", "report.Recommendations")
COUNTERS = (
    "internal_names",
    "enum_names",
    "bare_bools",
    "copied_phrases",
    "bad_ids",
    "wind_speed",
    "wind_dir_reversed",
    "wind_dir",
    "gps_radar_distance",
    "deviation",
    "wind_drift",
)
# Contadores de estilo (Fase 14.2): se miden aparte, no entran en las fugas ni en los errores.
STYLE_COUNTERS = (
    "generic_recommendation",
    "no_action_recommendation",
    "now_window_mix",
    "foreign_source_in_close",
    "summary_missing_type",
    "monitor_talk_in_recommendations",
    "agree_without_fix",
    "close_without_cause_source",
    "unsupported_figures",
    "recovery_time_mismatch",
)
COMPASS = {
    name: i * 22.5
    for i, name in enumerate(
        [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ],
    )
}
ID_RE = re.compile(r"\b(?:gps|rad|met|lnk|bat|mis|det|ai|chk|act|tcl|ops|sim|plr)-\d{3,6}\b")
DASHES = dict.fromkeys(
    map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"), "-"
)
NUM = r"(\d+(?:\.\d+)?)"
# Unidad de longitud: «m», «meter(s)» y «metre(s)» (el 32B escribe «9.9 meters»), no «m/s».
METRES = r"\s*(?:m|meters?|metres?)\b(?!/)"
GAP = r"(?:[^.;]|(?<=\d)\.(?=\d))"  # texto hasta el fin de la frase, con decimales
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


# --- Recomendaciones genéricas y sin acción (Fase 14.2) ----------------------------------------
# Heurísticas léxicas en inglés, sobre cada recomendación de una alerta y cada punto numerado de
# «Recommendations» del informe. Un punto puede ser a la vez genérico y sin acción.

GENERIC_FORMULAS = (
    r"ensure (?:the )?(?:secure|safe) communication",
    r"verify the (?:[\w-]+ ){0,3}(?:authenticity|integrity)",
    r"ensure (?:that )?(?:there is )?no unauthori[sz]ed access",
    r"ensure (?:the )?(?:integrity|security) of",
    r"(?:follow|adhere to|implement) (?:standard |established |appropriate )?"
    r"(?:security|safety) (?:protocols|procedures|measures)",
    r"take appropriate (?:action|measures|steps)",
    r"(?:strengthen|enhance|improve) (?:the )?(?:security|cybersecurity)",
    r"ensure (?:the )?(?:system|network|communications?) (?:is|are) secure",
)
GENERIC_RE = re.compile("|".join(GENERIC_FORMULAS), re.IGNORECASE)
# Verbos de acción concretos (no «investigate», «verify», «ensure», «review», «consider»…).
ACTION_VERBS = (
    r"use|rely|switch|keep|hold|maintain|hover|return|land|abort|take|regain|recover|"
    r"re-?establish|restore|check|inspect|replace|re-?calibrate|calibrate|restart|reboot|"
    r"re-?route|reduce|slow|descend|climb|divert|contact|notify|alert|inform|report|escalate|"
    r"resume|continue|navigate|fly|monitor|watch|track|compare|cross-?check|confirm|do not|"
    r"avoid|wait|let"
)
ACTION_OBJECTS = (
    r"drone|radar|link|route|gps|controller|control|base|waypoint|position|flight|mission|"
    r"receiver|sensor|antenna|operator|ground station|wind|deviation|signal|track"
)
ACTION_RE = re.compile(r"\b(?:" + ACTION_VERBS + r")\b", re.IGNORECASE)
OBJECT_RE = re.compile(r"\b(?:" + ACTION_OBJECTS + r")", re.IGNORECASE)
POINT_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+", re.MULTILINE)


def recommendation_points(text: str) -> list[str]:
    """Los puntos de una lista numerada o con viñetas; si no la hay, el texto entero."""
    parts = [p.strip() for p in POINT_RE.split(text) if p.strip()]
    return parts if POINT_RE.search(text) and parts else [text.strip()]


def recommendation_style(text: str) -> dict[str, list[str]]:
    """`generic_recommendation`: puntos con una fórmula vacía de seguridad.
    `no_action_recommendation`: puntos sin un verbo de acción concreto y un objeto (el dron, el
    radar, el enlace, la ruta, el GPS…) en el mismo punto."""
    generic, no_action = [], []
    for point in map(norm, recommendation_points(text)):  # se separa antes de normalizar
        if GENERIC_RE.search(point):
            generic.append(point)
        if not (ACTION_RE.search(point) and OBJECT_RE.search(point)):
            no_action.append(point)
    return {"generic_recommendation": generic, "no_action_recommendation": no_action}


# --- «Ahora» frente a la ventana y fuentes ajenas en el cierre (Fase 14.2) -----------------------
# Heurísticas léxicas en inglés (frases con marcador de presente o de pasado y una cifra), con las
# mismas tolerancias que el resto (distancias ±1 m, viento ±0,5 m/s). Cuentan frases, no cifras.

PRESENT_RE = re.compile(r"\b(?:now|currently|at the moment|at present|right now|at this moment)\b")
PAST_RE = re.compile(
    r"\b(?:was|were|had|reached|peaked|earlier|previously|during|before|between)\b"
)
# causa de la alerta -> fuentes que no tienen que ver con ella (el viento en un secuestro…)
FOREIGN_TERMS = {
    "HIJACK": ("wind",),
    "GPS_SPOOFING": ("wind",),
    "SENSOR_FAULT": ("wind",),
}
WIND_TERM_RE = re.compile(r"\b(?:wind|gusts?|weather)\b", re.IGNORECASE)


def figure_mentions(low: str) -> list[tuple[str, float]]:
    """(magnitud, valor) de las cifras de distancia GPS–radar, desviación y viento de una frase."""
    out: list[tuple[str, float]] = []
    if "gps" in low and "radar" in low:
        for m in DIST_RE.finditer(low):
            if not re.search(r"=|deviation|jump|step|route|plan", m.group(0)):
                out.append(("distance", float(m.group(1))))
    for m in DEV_RE.finditer(low):
        start = next(m.start(k) for k in (1, 2) if m.group(k) is not None)
        if not THRESHOLD_RE.search(low[:start]):
            out.append(("deviation", float(next(g for g in m.groups() if g is not None))))
    if "wind" in low or "gust" in low:
        for pattern in SPEED_PATTERNS:
            out.extend(("wind_speed", float(m.group(1))) for m in pattern.finditer(low))
    return out


def now_window_mix(text: str, facts: "Facts") -> list[str]:
    """Frases que mezclan «ahora» y la ventana: en presente («now», «currently»…) con una cifra
    que solo está en la ventana, en pasado («was», «reached»…) con una que solo está en `now`, o
    «disagree by N m» con N de `now` (coinciden ahora: no discrepan)."""
    sets = {
        "distance": (facts.now_distance, facts.window_distance),
        "deviation": (facts.now_deviation, facts.window_deviation),
        "wind_speed": (facts.now_wind_speed, facts.window_wind_speed),
    }
    found: list[str] = []
    for sentence in sentences(text):
        low = sentence.lower()
        present, past = bool(PRESENT_RE.search(low)), bool(PAST_RE.search(low))
        for kind, value in figure_mentions(low):
            now, window = sets[kind]
            only_window = near(value, window, DIST_TOL) and not near(value, now, DIST_TOL)
            only_now = near(value, now, DIST_TOL) and not near(value, window, DIST_TOL)
            if kind == "wind_speed":
                only_window = near(value, window, SPEED_TOL) and not near(value, now, SPEED_TOL)
                only_now = near(value, now, SPEED_TOL) and not near(value, window, SPEED_TOL)
            if (present and not past and only_window) or (past and not present and only_now):
                found.append(f"{kind} {value:g} :: {sentence}")
        if "gps" in low and "radar" in low:
            for m in DISAGREE_RE.finditer(low):
                if NEGATION_RE.search(low[max(0, m.start() - 25) : m.start()]):
                    continue
                value = float(m.group(1))
                if near(value, facts.now_distance, DIST_TOL) and not near(
                    value, facts.window_distance, DIST_TOL
                ):
                    found.append(f"disagree by {value:g} (now) :: {sentence}")
    return found


def foreign_source_in_close(text: str, cause: str | None, sources: set[str]) -> list[str]:
    """Frases de un cierre que hablan de una fuente ajena a la causa de la alerta (el viento en un
    secuestro, en un engaño del GPS o en el fallo de un sensor que no es la meteo), también para
    decir que no importa."""
    terms = FOREIGN_TERMS.get(cause or "", ())
    if "wind" not in terms or "meteo" in sources:
        return []
    return [s for s in sentences(text) if WIND_TERM_RE.search(s)]


# --- La hora de la recuperación del informe no es la del cierre (Fase 14.3) ---------------------
# Heurística léxica en inglés sobre el Summary: una cláusula con «recover…» y una hora T+mm:ss que
# es la del cierre de la anomalía y no la de su entrada en recuperación («entered recovery by
# T+03:54» cuando entró a T+03:42). Se mira cada anomalía que pasó por `recovering`.

RECOVERY_TIME_RE = re.compile(r"recover\w*[^.;]{0,50}?(T\+\d\d:\d\d)", re.I)


def format_t(sim_time: float) -> str:
    total = int(sim_time)
    return f"T+{total // 60:02d}:{total % 60:02d}"


def recovery_time_mismatch(text: str, recoveries: list[tuple[float, float | None]]) -> list[str]:
    """Horas del resumen dadas como entrada en recuperación que son la del cierre. `recoveries`:
    `(entrada en recuperación, cierre)` de cada anomalía que pasó por `recovering`."""
    found: list[str] = []
    for m in RECOVERY_TIME_RE.finditer(norm(text)):
        stated = m.group(1)
        for entered, closed in recoveries:
            if closed is not None and stated == format_t(closed) != format_t(entered):
                found.append(m.group(0))
                break
    return found


# --- Cifras sin respaldo en las recomendaciones del informe (Fase 14.3) --------------------------
# Una recomendación solo puede usar cifras que estén en lo que el agente de informe recibió (los
# hechos del vuelo y el conocimiento operativo). Cuenta cifras con unidad (m, m/s, s, %, °…) que no
# están en el prompt de la llamada del informe de misión: umbrales, plazos o límites inventados. No
# ve acciones inventadas sin cifra («actualiza el firmware»): eso es de la rúbrica.

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


# --- El cierre dice qué volvió a la normalidad de la causa (Fase 14.3) ---------------------------
# Heurística léxica en inglés sobre el motivo de un `AlertClosed`: un secuestro se cierra con el
# enlace (controlador, latencia, señal); una causa del GPS, con GPS y radar; un fallo de sensor, con
# que el sensor vuelve a informar. El viento y la causa desconocida no se miden.

LINK_TERMS_RE = re.compile(r"\b(?:link|controller|latency|rssi|signal strength|gcs-\d+)\b", re.I)
GPS_CAUSES = ("GPS_SPOOFING", "GPS_JAMMING")
BACK_TERMS_RE = re.compile(
    r"\b(?:report(?:s|ing|ed)?|resum\w+|back|available|operational|working|recover\w+|restor\w+"
    r"|return\w*|normal)\b",
    re.I,
)


def close_without_cause_source(text: str, cause: str | None) -> list[str]:
    """El cierre (una entrada con el texto) si no menciona el dato de la causa de la alerta:
    `HIJACK` sin el enlace o el controlador; una causa del GPS sin GPS y radar; `SENSOR_FAULT` sin
    que el sensor vuelve a informar."""
    plain = norm(text)
    low = plain.lower()
    if cause == "HIJACK":
        missing = not LINK_TERMS_RE.search(plain)
    elif cause in GPS_CAUSES:
        missing = "gps" not in low or "radar" not in low
    elif cause == "SENSOR_FAULT":
        missing = not BACK_TERMS_RE.search(plain)
    else:
        missing = False
    return [text] if missing else []


# --- GPS y radar «coinciden» con el GPS sin fix (Fase 14.3) ------------------------------------
# Sin fix, la posición del GPS es una estimación a estima: no hay comparación con el radar y un
# texto no puede decir que coinciden. Heurística léxica en inglés sobre los textos del monitor
# (alertas y cierres) escritos mientras la última posición del GPS no tenía fix.

AGREE_RE = re.compile(
    r"\bgps and radar\b(?:\s+[\w-]+){0,3}?\s+(?:agree|agrees|match|matches|coincide|coincides"
    r"|are consistent)\b"
)


def agree_without_fix(text: str, gps_nofix: bool) -> list[str]:
    """Frases que dan por coincidentes GPS y radar (sin negación ni pasado) cuando el GPS no tenía
    fix en ese instante. Vacío si tenía fix."""
    if not gps_nofix:
        return []
    found: list[str] = []
    for sentence in sentences(text):
        low = sentence.lower()
        if PAST_RE.search(low):
            continue
        for m in AGREE_RE.finditer(low):
            negated = re.search(r"\b(?:not|never|no longer)\b|n't", m.group(0))
            if not negated and not NEGATION_RE.search(low[max(0, m.start() - 25) : m.start()]):
                found.append(sentence)
                break
    return found


def gps_without_fix_at(events: list[dict[str, Any]], at: float) -> bool:
    """La última posición del GPS publicada hasta `at` no tiene fix (navega a estima)."""
    last = None
    for e in events:
        if e.get("type") == "PositionUpdated" and e.get("source") == "d1-gps":
            if e["sim_time"] <= at:
                last = e
            else:
                break
    return last is not None and last["payload"].get("fix") == "none"


# --- Informe de misión: tipo de cada anomalía y jerga del monitor (Fase 14.2) ---------------------
# Heurísticas léxicas en inglés. Una anomalía es una cadena de alertas: basta con que el Summary
# nombre alguna de sus causas.

CAUSE_WORDS = {
    "WIND": r"wind",
    "HIJACK": r"hijack",
    "GPS_SPOOFING": r"spoof",
    "SENSOR_FAULT": r"sensor|fault|silen|radar|receiver",
    "GPS_JAMMING": r"jam|gps loss|loss of (?:the )?gps|lost|interfer|signal loss",
    "UNKNOWN": r"unknown|undiagnosed|no diagnosis",
}
MONITOR_TALK_RE = re.compile(
    r"\b(?:guardrails?|fall-?backs?|rejections?|rejected|wall-?clock|diagnosis delay|"
    r"the monitor|monitoring system|detector|model aids?|prompts?|thresholds?)\b",
    re.IGNORECASE,
)


def summary_missing_type(text: str, chains: list[set[str]]) -> list[str]:
    """Una entrada por anomalía cuyo tipo (ninguna de las causas de su cadena) no nombra el
    resumen del informe."""
    low = norm(text).lower()
    return [
        "/".join(sorted(causes))
        for causes in chains
        if not any(re.search(CAUSE_WORDS.get(c, c.lower()), low) for c in causes)
    ]


def monitor_talk(text: str) -> list[str]:
    """Puntos de las recomendaciones que hablan del sistema de monitorización (retrasos, rechazos,
    guardrails, ayudas…) y no del dron: eso va en el anexo."""
    return [p for p in map(norm, recommendation_points(text)) if MONITOR_TALK_RE.search(p)]


# --- Normalización y nombres internos ----------------------------------------------------------


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


# --- Frases copiadas ---------------------------------------------------------------------------


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_.°]+", norm(text).lower().replace("`", " "))


def ngrams(tokens: list[str], n: int = NGRAM) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def static_corpus(repo: Path = REPO) -> set[tuple[str, ...]]:
    """N-gramas de todos los prompts y skills de las carpetas de assets (la actual y la v13)."""
    grams: set[tuple[str, ...]] = set()
    for directory in ASSET_DIRS:
        root = repo / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            grams |= ngrams(words(path.read_text(encoding="utf-8")))
    return grams


def copied_spans(text: str, corpus: set[tuple[str, ...]]) -> list[str]:
    """Tramos del texto (de ≥ NGRAM palabras) que están literalmente en el corpus."""
    tokens = words(text)
    hit = [tuple(tokens[i : i + NGRAM]) in corpus for i in range(len(tokens) - NGRAM + 1)]
    spans, start = [], None
    for i, flag in enumerate(hit + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            spans.append(" ".join(tokens[start : i - 1 + NGRAM]))
            start = None
    return spans


# --- Hechos ------------------------------------------------------------------------------------


@dataclass
class Facts:
    """Valores válidos para cada categoría de cifra."""

    wind_speed: set[float] = field(default_factory=set)
    wind_from: set[float] = field(default_factory=set)
    distance: set[float] = field(default_factory=set)
    deviation: set[float] = field(default_factory=set)
    with_drift: set[bool] = field(default_factory=set)
    """Valores de `wind.with_drift` de las consultas (el viento va a favor de la deriva o no)."""
    now_distance: set[float] = field(default_factory=set)
    now_deviation: set[float] = field(default_factory=set)
    now_wind_speed: set[float] = field(default_factory=set)
    """Los valores del bloque `now` (v0.13), aparte de los agregados de la ventana de abajo."""
    window_distance: set[float] = field(default_factory=set)
    window_deviation: set[float] = field(default_factory=set)
    window_wind_speed: set[float] = field(default_factory=set)
    gps_nofix: bool = False
    """La última posición del GPS de la invocación no tenía fix (se saca de la línea temporal)."""

    def merge(self, other: "Facts") -> None:
        self.now_distance |= other.now_distance
        self.now_deviation |= other.now_deviation
        self.now_wind_speed |= other.now_wind_speed
        self.window_distance |= other.window_distance
        self.window_deviation |= other.window_deviation
        self.window_wind_speed |= other.window_wind_speed
        self.wind_speed |= other.wind_speed
        self.wind_from |= other.wind_from
        self.distance |= other.distance
        self.deviation |= other.deviation
        self.with_drift |= other.with_drift


def add_metrics(facts: Facts, metrics: dict[str, Any]) -> None:
    wind = metrics.get("wind") or {}
    for key in ("mean_speed_mps", "max_gust_mps"):
        if wind.get(key) is not None:
            facts.wind_speed.add(float(wind[key]))
    if wind.get("from_deg") is not None:
        facts.wind_from.add(float(wind["from_deg"]))
    if isinstance(wind.get("with_drift"), bool):
        facts.with_drift.add(wind["with_drift"])
    for key in ("gps_radar_distance_m",):
        for stat in ("mean", "max"):
            value = (metrics.get(key) or {}).get(stat)
            if value is not None:
                facts.distance.add(float(value))
    for key in ("gps_deviation_from_plan_m", "radar_deviation_from_plan_m"):
        for stat in ("mean", "max"):
            value = (metrics.get(key) or {}).get(stat)
            if value is not None:
                facts.deviation.add(float(value))
    if metrics.get("gps_max_step_m") is not None:
        facts.deviation.add(float(metrics["gps_max_step_m"]))
    # agregados de la ventana, aparte (para distinguir «ahora» de «la ventana», Fase 14.2)
    facts.window_distance |= {
        float((metrics.get("gps_radar_distance_m") or {})[stat])
        for stat in ("mean", "max")
        if (metrics.get("gps_radar_distance_m") or {}).get(stat) is not None
    }
    facts.window_deviation |= {
        float((metrics.get(key) or {})[stat])
        for key in ("gps_deviation_from_plan_m", "radar_deviation_from_plan_m")
        for stat in ("mean", "max")
        if (metrics.get(key) or {}).get(stat) is not None
    }
    facts.window_wind_speed |= {
        float(wind[key]) for key in ("mean_speed_mps", "max_gust_mps") if wind.get(key) is not None
    }
    now = metrics.get("now") or {}  # bloque de la Fase 14.1, paso 2
    if now.get("gps_radar_distance_m") is not None:
        facts.distance.add(float(now["gps_radar_distance_m"]))
        facts.now_distance.add(float(now["gps_radar_distance_m"]))
    for key in ("gps_deviation_from_plan_m", "radar_deviation_from_plan_m"):
        if now.get(key) is not None:
            facts.deviation.add(float(now[key]))
            facts.now_deviation.add(float(now[key]))
    for key in ("wind_speed_mps", "wind_gust_mps"):
        if now.get(key) is not None:
            facts.wind_speed.add(float(now[key]))
            facts.now_wind_speed.add(float(now[key]))
    if now.get("wind_from_deg") is not None:
        facts.wind_from.add(float(now["wind_from_deg"]))


def add_events(facts: Facts, result: dict[str, Any]) -> None:
    for event in result.get("events", []):
        if event.get("type") == "WindReported":
            facts.wind_speed |= {float(event["speed_mps"]), float(event["gust_mps"])}
            facts.wind_from.add(float(event["from_deg"]))


def add_prompt_numbers(facts: Facts, text: str) -> None:
    """Cifras en metros que ya vienen en un prompt (mensaje del detector, alertas inyectadas…)."""
    for m in re.finditer(NUM + METRES, text):
        value = float(m.group(1))
        facts.distance.add(value)
        facts.deviation.add(value)
    for m in re.finditer(NUM + r"\s*m/s", text):
        facts.wind_speed.add(float(m.group(1)))


def tool_results(record: dict[str, Any]):
    for call in record.get("calls", []):
        for tool in call.get("tool_calls") or []:
            yield tool["name"], tool.get("result")


def record_facts(record: dict[str, Any], with_prompts: bool) -> Facts:
    facts = Facts()
    for name, result in tool_results(record):
        if not isinstance(result, dict):
            continue
        if name == "get_track_metrics" and "ok" not in result:
            add_metrics(facts, result)
        elif name == "get_events":
            add_events(facts, result)
    if with_prompts:
        for message in record.get("messages", []):
            if message.get("role") in ("system", "user") and isinstance(
                message.get("content"), str
            ):
                add_prompt_numbers(facts, message["content"])
    else:
        users = [m for m in record.get("messages", []) if m.get("role") == "user"]
        if users and isinstance(users[0].get("content"), str):
            add_prompt_numbers(facts, users[0]["content"])
    return facts


def prompt_prose(record: dict[str, Any]) -> list[str]:
    """Texto que el modelo vio y que puede copiar: el prompt del sistema ya está en el corpus
    estático; aquí van los rechazos de los guardrails y la línea de estado."""
    out: list[str] = []
    for rejection in record.get("guardrail_rejections", []):
        out += [str(e) for e in rejection.get("errors", [])]
    for message in record.get("messages", []):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            for line in message["content"].splitlines():
                if line.startswith("- Recent GPS alert"):
                    out.append(line)
    for call in record.get("calls", []):
        for tool in call.get("tool_calls") or []:
            result = tool.get("result")
            if isinstance(result, dict) and result.get("ok") is False:
                out += [str(e) for e in result.get("errors", [])]
    return out


# --- Cifras y direcciones ----------------------------------------------------------------------


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def near(value: float, valid: set[float], tol: float) -> bool:
    return any(abs(value - v) <= tol for v in valid)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z(*`\"'])|\n+", norm(text)) if s.strip()]


SPEED_PATTERNS = (
    re.compile(r"wind" + GAP + r"{0,40}?" + NUM + r"\s*m/s"),
    re.compile(r"gusts?" + GAP + r"{0,25}?" + NUM + r"\s*m/s"),
    re.compile(NUM + r"\s*m/s\s*(?:of\s+)?(?:wind|gusts?)"),
)
DIR_RE = re.compile(
    r"\b(from|toward|towards|pushing(?:\s+it)?(?:\s+to|\s+towards)?|blowing(?:\s+to|\s+towards)?)"
    r"\s+(?:the\s+)?(?:([NSEW]{1,3})\b\s*)?\(?" + NUM + r"?\s*°?"
)
DIST_RE = re.compile(
    r"(?:distance|disagree\w*|differ\w*|apart|separat\w*|gap|offset)"
    + GAP
    + r"{0,40}?"
    + NUM
    + METRES
)
DISAGREED_M = 25.0  # `gps_radar.disagreed`: distancia máxima GPS–radar de la ventana ≥ 25 m
DISAGREE_RE = re.compile(
    r"disagree\w*\s+(?:by\s+|of\s+|\((?:distance|gap)(?:\s+of)?\s+)?" + NUM + METRES
)  # «disagree by 9.9 m», «disagree of 9.9 m» y «disagree (distance 9.9 m)»
NEGATION_RE = re.compile(r"(?:\bnot|\bno longer|n't|\bnever)\s+(?:\w+\s+)?$")
NOT_WITH_DRIFT_RE = re.compile(
    r"(?:does not|doesn't|did not|do not|not)\s+(?:push|align|blow|point|go|explain|match)"
    r"[^.;]{0,40}drift|opposite[^.;]{0,30}drift|against[^.;]{0,20}drift"
)
DEV_GAP = r"[^.;,()=]"  # una desviación y su cifra van juntas: sin comas, paréntesis ni «=»
DEV_RE = re.compile(
    NUM + METRES + r"\s+(?:away\s+)?(?:from|off)\s+(?:the\s+)?(?:planned\s+)?(?:route|plan)"
    r"|(?:deviation|deviates|deviating)" + DEV_GAP + r"{0,40}?" + NUM + METRES
)
THRESHOLD_RE = re.compile(
    r"(?:below|under|above|over|less than|more than|within|up to|at most|at least)\s+$"
)


def check_numbers(text: str, facts: Facts) -> dict[str, list[str]]:
    """Frases con una cifra o dirección que no cuadra con los hechos."""
    found: dict[str, list[str]] = {c: [] for c in COUNTERS[5:]}
    for sentence in sentences(text):
        low = sentence.lower()
        if "wind" in low or "gust" in low:
            for pattern in SPEED_PATTERNS:
                for m in pattern.finditer(low):
                    if facts.wind_speed and not near(
                        float(m.group(1)), facts.wind_speed, SPEED_TOL
                    ):
                        found["wind_speed"].append(f"{m.group(0)} :: {sentence}")
            for m in DIR_RE.finditer(sentence):
                kind = "from" if m.group(1) == "from" else "to"
                if m.group(3) is not None and "°" in m.group(0):
                    claimed, tol = float(m.group(3)), BEARING_TOL
                elif m.group(2) in COMPASS:
                    claimed, tol = COMPASS[m.group(2)], COMPASS_TOL
                else:
                    continue
                if not facts.wind_from:
                    continue
                truth = {(f + (0 if kind == "from" else 180)) % 360 for f in facts.wind_from}
                reverse = {(f + (180 if kind == "from" else 0)) % 360 for f in facts.wind_from}
                if near_angle(claimed, truth, tol):
                    continue
                key = "wind_dir_reversed" if near_angle(claimed, reverse, tol) else "wind_dir"
                found[key].append(f"{m.group(0).strip()} :: {sentence}")
        below_threshold: set[str] = set()
        if "gps" in low and "radar" in low:
            for m in DISAGREE_RE.finditer(low):
                if NEGATION_RE.search(low[max(0, m.start() - 25) : m.start()]):
                    continue
                if float(m.group(1)) < DISAGREED_M:
                    below_threshold.add(m.group(1))
                    found["gps_radar_distance"].append(f"{m.group(0)} :: {sentence}")
        if (
            "wind" in low
            and "drift" in low
            and facts.with_drift == {True}
            and NOT_WITH_DRIFT_RE.search(low)
        ):
            found["wind_drift"].append(sentence)
        if "gps" in low and "radar" in low and facts.distance:
            for m in DIST_RE.finditer(low):
                if re.search(r"=|deviation|jump|step|route|plan", m.group(0)):
                    continue  # la cifra es de otra magnitud (desviación, salto del GPS…)
                if m.group(1) in below_threshold:
                    continue  # ya contada como «discrepan» por debajo del umbral
                if not near(float(m.group(1)), facts.distance, DIST_TOL):
                    found["gps_radar_distance"].append(f"{m.group(0)} :: {sentence}")
        if facts.deviation:
            for m in DEV_RE.finditer(low):
                start = next(m.start(k) for k in (1, 2) if m.group(k) is not None)
                if THRESHOLD_RE.search(low[:start]):
                    continue  # «below 6 m» es un umbral, no una desviación medida
                value = float(next(g for g in m.groups() if g is not None))
                if not near(value, facts.deviation, DIST_TOL):
                    found["deviation"].append(f"{m.group(0)} :: {sentence}")
    return found


def near_angle(value: float, valid: set[float], tol: float) -> bool:
    return any(angle_diff(value, v) <= tol for v in valid)


# --- Medida de un texto ------------------------------------------------------------------------


@dataclass
class Measured:
    scenario: str
    kind: str
    ref: str
    text: str
    findings: dict[str, list[str]]
    chars: int
    figures: int
    ids: int
    times: int

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.findings.items()}


def measure_text(
    scenario: str,
    kind: str,
    ref: str,
    text: str,
    facts: Facts,
    existing_ids: set[str],
    corpus: set[tuple[str, ...]],
    prose: list[str],
    cause: str | None = None,
    sources: set[str] | None = None,
    chains: list[set[str]] | None = None,
    is_close: bool = False,
    known_figures: set[float] | None = None,
    recoveries: list[tuple[float, float | None]] | None = None,
) -> Measured:
    names, enums, bools = find_names(text)
    grams = set(corpus)
    for line in prose:
        grams |= ngrams(words(line))
    cited = ID_RE.findall(norm(text))
    findings: dict[str, list[str]] = {
        "internal_names": names,
        "enum_names": enums,
        "bare_bools": bools,
        "copied_phrases": copied_spans(text, grams),
        "bad_ids": [i for i in cited if i not in existing_ids],
        **check_numbers(text, facts),
    }
    if kind in RECOMMENDATION_KINDS:
        findings.update(recommendation_style(text))
    if kind == "report.Summary" and chains is not None:
        findings["summary_missing_type"] = summary_missing_type(text, chains)
    if kind == "report.Summary" and recoveries is not None:
        findings["recovery_time_mismatch"] = recovery_time_mismatch(text, recoveries)
    if kind == "report.Recommendations":
        findings["monitor_talk_in_recommendations"] = monitor_talk(text)
        if known_figures is not None:
            findings["unsupported_figures"] = unsupported_figures(text, known_figures)
    if kind.startswith(("alert.", "end.")):
        findings["now_window_mix"] = now_window_mix(text, facts)
        findings["agree_without_fix"] = agree_without_fix(text, facts.gps_nofix)
    if kind == "end.reason" and cause is not None:
        findings["foreign_source_in_close"] = foreign_source_in_close(text, cause, sources or set())
    if is_close and cause is not None:
        findings["close_without_cause_source"] = close_without_cause_source(text, cause)
    plain = norm(text)
    return Measured(
        scenario,
        kind,
        ref,
        text,
        findings,
        chars=len(text),
        figures=len(re.findall(r"(?<![\w-])\d+(?:\.\d+)?", plain)),
        ids=len(cited),
        times=len(re.findall(r"T\+\d\d:\d\d", plain)),
    )


# --- Una ejecución -----------------------------------------------------------------------------


def monitor_record_for(records: list[dict[str, Any]], event_id: str) -> dict[str, Any] | None:
    for record in records:
        if any(p.get("event_id") == event_id for p in record.get("published", [])):
            return record
    return None


def measure_run(
    source: "texts.Source", scenario: str, folder: Path, corpus: set[tuple[str, ...]]
) -> list[Measured]:
    events = texts.read_events(folder / "timeline.jsonl")
    existing = {ID_RE_NORM(e["event_id"]) for e in events}
    trace_path = folder / "llm_trace.jsonl"
    records = (
        [json.loads(line) for line in trace_path.read_text("utf-8").splitlines() if line.strip()]
        if trace_path.exists()
        else []
    )
    monitor = [r for r in records if r.get("agent") == "monitor"]
    out: list[Measured] = []
    det_source = {
        e["payload"]["detection_id"]: e["payload"].get("source")
        for e in events
        if e.get("type") == "DetectionRaised"
    }
    alert_cause: dict[str, str] = {}
    alert_sources: dict[str, set[str]] = {}
    chain_times: dict[str, dict[str, float | None]] = {}  # raíz -> recuperación y cierre
    chain_causes: dict[str, set[str]] = {}  # raíz de la cadena -> causas de sus alertas
    root_of: dict[str, str] = {}
    for e in events:
        if e.get("type") == "AnomalyDetected":
            p = e["payload"]
            alert_cause[p["alert_id"]] = p.get("cause", "")
            alert_sources[p["alert_id"]] = {
                det_source[d] for d in p.get("detection_ids", []) if det_source.get(d)
            }
            if p.get("supersedes") in alert_sources:  # una cadena es un episodio
                alert_sources[p["alert_id"]] |= alert_sources[p["supersedes"]]
            root = root_of.get(p.get("supersedes") or "", p["alert_id"])
            root_of[p["alert_id"]] = root
            chain_causes.setdefault(root, set()).add(p.get("cause", ""))
            times = chain_times.setdefault(root, {"entered": None, "closed": None})
            if p.get("phase") == "recovering" and times["entered"] is None:
                times["entered"] = e["sim_time"]
        elif e.get("type") == "AlertClosed":
            root = root_of.get(e["payload"].get("alert_id") or "")
            if root is not None:
                chain_times[root]["closed"] = e["sim_time"]

    def run_facts(until: float | None, own: dict[str, Any] | None) -> tuple[Facts, list[str]]:
        facts = Facts()
        prose: list[str] = []
        for record in monitor:
            if until is None or record["as_of"] <= until:
                facts.merge(record_facts(record, with_prompts=True))
                prose += prompt_prose(record)
        if own is not None:
            facts.merge(record_facts(own, with_prompts=True))
        return facts, prose

    for event in events:
        payload, kind = event.get("payload", {}), event.get("type")
        if kind in ("AnomalyDetected", "AlertClosed", "DetectionAcknowledged"):
            record = monitor_record_for(monitor, event["event_id"])
            if record is None or record.get("fallback") and payload.get("fallback"):
                continue  # un fallback lo escribe el módulo, no el modelo
            facts = record_facts(record, with_prompts=False)
            facts.gps_nofix = gps_without_fix_at(events, record["as_of"])
            prose = prompt_prose(record)
            names = (
                ("summary", "explanation", "recommendation")
                if kind == "AnomalyDetected"
                else ("reason",)
            )
            for name in names:
                if payload.get(name):
                    label = "alert" if kind == "AnomalyDetected" else "end"
                    out.append(
                        measure_text(
                            scenario,
                            f"{label}.{name}",
                            event["event_id"],
                            str(payload[name]),
                            facts,
                            existing,
                            corpus,
                            prose,
                            alert_cause.get(payload.get("alert_id") or ""),
                            alert_sources.get(payload.get("alert_id") or "", set()),
                            is_close=kind == "AlertClosed",
                        )
                    )
        elif kind == "AgentReply":
            facts, prose = run_facts(
                event["sim_time"], monitor_record_for(records, event["event_id"])
            )
            conv = payload.get("conversation_id", "chat")
            out.append(
                measure_text(
                    scenario,
                    f"chat.{conv}",
                    event["event_id"],
                    str(payload["text"]),
                    facts,
                    existing,
                    corpus,
                    prose,
                )
            )
    report = folder / "informe.md"
    if report.exists():
        facts, prose = run_facts(None, None)
        for rec in records:
            if rec.get("agent") == "report":
                facts.merge(record_facts(rec, with_prompts=True))
        first_report = next((r for r in records if r.get("agent") == "report"), None)
        known = (
            prompt_numbers(
                "\n".join(
                    m["content"]
                    for m in first_report.get("messages", [])
                    if m.get("role") in ("system", "user") and isinstance(m.get("content"), str)
                )
            )
            if first_report is not None
            else None
        )
        sections, seen = texts.model_report_sections(report.read_text(encoding="utf-8"))
        for title, body in sections.items():
            # la valoración y las recomendaciones técnicas son la autoevaluación del monitor, para
            # quien evalúa el ejercicio (en el formato anterior iba en medio del informe): se
            # miden aparte y no entran en los totales del informe de misión
            kind = "annex" if title in ANNEX_TITLES else "report"
            out.append(
                measure_text(
                    scenario,
                    f"{kind}.{title}",
                    "report",
                    body,
                    facts,
                    existing,
                    corpus,
                    prose,
                    chains=list(chain_causes.values()),
                    known_figures=known,
                    recoveries=[
                        (t["entered"], t["closed"])
                        for t in chain_times.values()
                        if t["entered"] is not None
                    ],
                )
            )
        for label, (_, body) in sorted(seen.items()):
            out.append(
                measure_text(
                    scenario, "report.What was seen", label, body, facts, existing, corpus, prose
                )
            )
    return out


def ID_RE_NORM(event_id: str) -> str:
    return norm(event_id)


# --- Severidad, confianza y sustituciones por etiqueta -----------------------------------------


def chain_rows(
    source: "texts.Source", scenarios: list[str], rep: int
) -> list[tuple[str, str, str]]:
    """(escenario, etiqueta, cadena) de cada anomalía: severidad y confianza de cada alerta y
    cuántas sustituciones (`supersedes`) hay. Lo que `eval.md` no juzga."""
    rows: list[tuple[str, str, str]] = []
    for scenario in scenarios:
        folder = texts.run_folder(source, scenario, rep)
        if folder is None:
            continue
        run = texts.load_run(source, folder)
        for label in sorted(run.alerts, key=lambda x: (x == texts.NO_LABEL, x)):
            alerts = sorted(run.alerts[label], key=lambda e: (e["sim_time"], e["seq"]))
            steps = " → ".join(
                f"{a['payload']['cause']} {a['payload']['severity']} {a['payload']['confidence']:g}"
                f"{' [recovering]' if a['payload'].get('phase') == 'recovering' else ''}"
                f"{' (fb)' if a['payload'].get('fallback') else ''}"
                for a in alerts
            )
            rows.append((scenario, label, f"{steps} · {len(alerts) - 1} supersedes"))
    return rows


# --- Matriz y salida ---------------------------------------------------------------------------


def measure_source(
    source: "texts.Source", scenarios: list[str], rep: int, corpus: set[tuple[str, ...]]
) -> tuple[list[Measured], list[str]]:
    out: list[Measured] = []
    missing: list[str] = []
    for scenario in scenarios:
        folder = texts.run_folder(source, scenario, rep)
        if folder is None:
            missing.append(f"{source.name} · {scenario} · r{rep}")
            continue
        out += measure_run(source, scenario, folder, corpus)
    return out, missing


def summarize(measured: list[Measured], with_annex: bool = False) -> dict[str, Any]:
    """Totales de los textos medidos. Sin `with_annex`, la autoevaluación del monitor (anexo del
    informe) no cuenta: se resume aparte en `by_kind`."""
    if not with_annex:
        measured = [m for m in measured if not m.kind.startswith("annex.")]
    total = Counter()
    for m in measured:
        total.update(m.counts())
    n = len(measured) or 1
    return {
        "texts": len(measured),
        **{c: total[c] for c in (*COUNTERS, *STYLE_COUNTERS)},
        "total_errors": sum(total[c] for c in COUNTERS[4:]),
        "total_leaks": sum(total[c] for c in COUNTERS[:4]),
        "chars_mean": round(sum(m.chars for m in measured) / n, 1),
        "figures_mean": round(sum(m.figures for m in measured) / n, 2),
        "ids_mean": round(sum(m.ids for m in measured) / n, 2),
        "times_mean": round(sum(m.times for m in measured) / n, 2),
    }


def by_kind(measured: list[Measured]) -> dict[str, dict[str, Any]]:
    kinds: dict[str, list[Measured]] = {}
    for m in measured:
        kinds.setdefault(m.kind.split(".")[0], []).append(m)
    return {k: summarize(v, with_annex=True) for k, v in sorted(kinds.items())}


def render(
    results: dict[str, list[Measured]],
    missing: list[str],
    chains: dict[str, list[tuple[str, str, str]]] | None = None,
) -> str:
    out = ["# Text measure", ""]
    out += [
        "No LLM: counts per matrix. *Leaks* = internal names, enum names, bare true/false and "
        "copied phrases (6+ words). *Errors* = ids that do not exist, wind speed, wind direction "
        "(reversed = from/to mixed up) and distance or deviation figures that do not match the "
        "facts of the invocation. Tolerances: wind ±0.5 m/s, bearing ±15° (±25° with a compass "
        "point), distances ±1 m.",
        "",
    ]
    for gap in missing:
        out += [f"- missing: {gap}", ""]
    header = [
        "source", "texts", *COUNTERS, "leaks", "errors", *STYLE_COUNTERS,
        "chars", "figures", "ids", "times",
    ]  # fmt: skip
    out += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for name, measured in results.items():
        s = summarize(measured)
        row = [name, s["texts"], *(s[c] for c in COUNTERS)]
        row += [
            s["total_leaks"],
            s["total_errors"],
            *(s[c] for c in STYLE_COUNTERS),
            s["chars_mean"],
            s["figures_mean"],
            s["ids_mean"],
            s["times_mean"],
        ]
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    out += ["", "(chars, figures, ids and times are means per text.)", ""]
    out += [
        "## By agent",
        "",
        "| source | agent | texts | leaks | errors | chars |",
        "|---|---|---|---|---|---|",
    ]
    for name, measured in results.items():
        for kind, s in by_kind(measured).items():
            out.append(
                f"| {name} | {kind} | {s['texts']} | {s['total_leaks']} | {s['total_errors']} "
                f"| {s['chars_mean']} |"
            )
    if chains:
        out += ["", "## Severity, confidence and supersedes per label", ""]
        out += ["| scenario · label | " + " | ".join(chains) + " |", "|---|" + "---|" * len(chains)]
        keys = sorted({(sc, lb) for rows in chains.values() for sc, lb, _ in rows})
        for sc, lb in keys:
            cells = [
                next((c for s_, l_, c in rows if (s_, l_) == (sc, lb)), "—")
                for rows in chains.values()
            ]
            out.append(f"| {sc} · {lb} | " + " | ".join(cells) + " |")
    out += ["", "## Findings", ""]
    for name, measured in results.items():
        out += [f"### {name}", ""]
        for m in measured:
            for counter, items in m.findings.items():
                for item in items:
                    out.append(f"- `{m.scenario}` · {m.kind} · {m.ref} · **{counter}**: {item}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_json(results: dict[str, list[Measured]]) -> dict[str, Any]:
    return {
        name: {
            "summary": summarize(measured),
            "by_agent": by_kind(measured),
            "texts": [
                {
                    "scenario": m.scenario,
                    "kind": m.kind,
                    "ref": m.ref,
                    "chars": m.chars,
                    "figures": m.figures,
                    "ids": m.ids,
                    "times": m.times,
                    "findings": {k: v for k, v in m.findings.items() if v},
                }
                for m in measured
            ],
        }
        for name, measured in results.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sources", nargs="+", help="nombre=carpeta[:perfil]")
    parser.add_argument(
        "--out", type=Path, required=True, help="fichero .md; al lado sale el .json"
    )
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--rep", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        sources = [texts.parse_source(s) for s in args.sources]
        corpus = static_corpus()
        results: dict[str, list[Measured]] = {}
        chains: dict[str, list[tuple[str, str, str]]] = {}
        missing: list[str] = []
        for source in sources:
            chains[source.name] = chain_rows(source, args.scenarios.split(","), args.rep)
            results[source.name], gaps = measure_source(
                source, args.scenarios.split(","), args.rep, corpus
            )
            missing += gaps
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.out.write_text(render(results, missing, chains), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(to_json(results), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{args.out} ({len(results)} sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
