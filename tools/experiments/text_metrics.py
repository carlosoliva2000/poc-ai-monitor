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

    def merge(self, other: "Facts") -> None:
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
    now = metrics.get("now") or {}  # bloque de la Fase 14.1, paso 2
    if now.get("gps_radar_distance_m") is not None:
        facts.distance.add(float(now["gps_radar_distance_m"]))
    for key in ("gps_deviation_from_plan_m", "radar_deviation_from_plan_m"):
        if now.get(key) is not None:
            facts.deviation.add(float(now[key]))
    for key in ("wind_speed_mps", "wind_gust_mps"):
        if now.get(key) is not None:
            facts.wind_speed.add(float(now[key]))
    if now.get("wind_from_deg") is not None:
        facts.wind_from.add(float(now["wind_from_deg"]))


def add_events(facts: Facts, result: dict[str, Any]) -> None:
    for event in result.get("events", []):
        if event.get("type") == "WindReported":
            facts.wind_speed |= {float(event["speed_mps"]), float(event["gust_mps"])}
            facts.wind_from.add(float(event["from_deg"]))


def add_prompt_numbers(facts: Facts, text: str) -> None:
    """Cifras en metros que ya vienen en un prompt (mensaje del detector, alertas inyectadas…)."""
    for m in re.finditer(NUM + r"\s*m\b(?!/)", text):
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
    + r"\s*m\b(?!/)"
)
DISAGREED_M = 25.0  # `gps_radar.disagreed`: distancia máxima GPS–radar de la ventana ≥ 25 m
DISAGREE_RE = re.compile(r"disagree\w*\s+(?:by\s+|of\s+)?" + NUM + r"\s*m\b(?!/)")
NEGATION_RE = re.compile(r"(?:\bnot|\bno longer|n't|\bnever)\s+(?:\w+\s+)?$")
NOT_WITH_DRIFT_RE = re.compile(
    r"(?:does not|doesn't|did not|do not|not)\s+(?:push|align|blow|point|go|explain|match)"
    r"[^.;]{0,40}drift|opposite[^.;]{0,30}drift|against[^.;]{0,20}drift"
)
DEV_GAP = r"[^.;,()=]"  # una desviación y su cifra van juntas: sin comas, paréntesis ni «=»
DEV_RE = re.compile(
    NUM + r"\s*m\b(?!/)\s+(?:away\s+)?(?:from|off)\s+(?:the\s+)?(?:planned\s+)?(?:route|plan)"
    r"|(?:deviation|deviates|deviating)" + DEV_GAP + r"{0,40}?" + NUM + r"\s*m\b(?!/)"
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
        sections, seen = texts.model_report_sections(report.read_text(encoding="utf-8"))
        for title, body in sections.items():
            # la valoración y las recomendaciones técnicas son la autoevaluación del monitor, para
            # quien evalúa el ejercicio (en el formato anterior iba en medio del informe): se
            # miden aparte y no entran en los totales del informe de misión
            kind = "annex" if title in ANNEX_TITLES else "report"
            out.append(
                measure_text(
                    scenario, f"{kind}.{title}", "report", body, facts, existing, corpus, prose
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
        **{c: total[c] for c in COUNTERS},
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
    header = ["source", "texts", *COUNTERS, "leaks", "errors", "chars", "figures", "ids", "times"]
    out += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for name, measured in results.items():
        s = summarize(measured)
        row = [name, s["texts"], *(s[c] for c in COUNTERS)]
        row += [
            s["total_leaks"],
            s["total_errors"],
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
