"""E5 · medidas de estilo de los textos de cada serie, sin LLM (complementan `text_metrics.py`).

    uv run --project ai-module-py python tools/experiments/e5_style.py \\
        --out experiments/e5-estilo.md

Por serie y repetición (`demo` y `faults`), sobre los textos que extrae `text_metrics.py`:

- **longitud** por campo (caracteres y frases) y si los textos **chocan con los límites** de las
  plantillas (resumen de menos de 160 caracteres; respuestas cortadas por `max_tokens`);
- **concreción**: cifras, ids y tiempos por frase;
- **cifras sin respaldo** frente a cifras (más detalle = más ocasiones de afirmar sin respaldo);
- **recomendaciones**: puntos con una acción sobre algo concreto, con su porqué (causa, dato o
  fin en el mismo punto) y con las dos cosas;
- **frases que el operador entiende sin conocer el sistema**: se mide lo contrario, la parte de
  frases con nombres internos, enums, `true`/`false` sueltos o tramos copiados de los prompts;
- **dudas**: frases con una duda (may, might, possibly…) y las que la dicen sin ningún dato;
- **repetición**: alertas cuyo resumen y explicación comparten la mitad o más de sus palabras.

Son medidas léxicas en inglés: orientan, no juzgan. La rúbrica la aplica una persona.
"""

import argparse
import importlib.util
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"e5s_{name}", HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"e5s_{name}"] = module
    spec.loader.exec_module(module)
    return module


tm = load("text_metrics")
tables = load("e5_tables")

SUMMARY_LIMIT = 160
WHY_RE = re.compile(
    r"\b(?:because|since|as it|as the|due to|so that|so the|in case|given|which (?:means|would|"
    r"could|may)|to (?:rule out|confirm|verify|avoid|prevent|check|keep|make sure|ensure|"
    r"reduce|regain|restore|protect)|in order to|otherwise|if (?:it|the|this|they))\b",
    re.IGNORECASE,
)
HEDGE_RE = re.compile(
    r"\b(?:may|might|possibly|possible|could|perhaps|likely|unlikely|suggests?|appears?|seems?|"
    r"potentially|probably|presumably|uncertain)\b",
    re.IGNORECASE,
)
DATA_RE = re.compile(r"\d|\b(?:gps|rad|met|lnk|det|ai)-\d", re.IGNORECASE)
WORD_RE = re.compile(r"[a-z]{4,}")
LEAKS = ("internal_names", "enum_names", "bare_bools", "copied_phrases")
ANNEX = tm.ANNEX_TITLES
MAIN_REPORT = ("report.Summary", "report.What was seen", "report.Recommendations")


def alert_texts(items: list[Any], field: str) -> list[Any]:
    return [m for m in items if m.kind == f"alert.{field}"]


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def words(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def metrics_of(items: list[Any]) -> dict[str, float | None]:
    """Medidas de una repetición (lista de `Measured` de un escenario o de los dos)."""
    out: dict[str, float | None] = {}
    for field in ("summary", "explanation", "recommendation"):
        texts = alert_texts(items, field)
        out[f"alert_{field}_chars"] = mean([m.chars for m in texts])
        out[f"alert_{field}_sentences"] = mean([len(tm.sentences(m.text)) for m in texts])
    summaries = alert_texts(items, "summary")
    out["summary_over_limit"] = sum(1 for m in summaries if m.chars >= SUMMARY_LIMIT)
    out["summary_max_chars"] = max((m.chars for m in summaries), default=None)
    closes = [m for m in items if m.kind.startswith("end.")]
    out["close_chars"] = mean([m.chars for m in closes])
    for kind, key in (("report.Summary", "report_summary"), ("report.What was seen", "report_seen"),
                      ("report.Recommendations", "report_recs")):  # fmt: skip
        out[f"{key}_chars"] = mean([m.chars for m in items if m.kind == kind])
    # concreción: cifras, ids y tiempos por frase, en la explicación, el cierre y el informe
    for label, group in (
        ("alert_explanation", alert_texts(items, "explanation")),
        ("close", closes),
        ("report_seen", [m for m in items if m.kind == "report.What was seen"]),
    ):
        sentences = sum(len(tm.sentences(m.text)) for m in group)
        concrete = sum(m.figures + m.ids + m.times for m in group)
        out[f"{label}_concrete_per_sentence"] = ratio(concrete, sentences)
    # cifras con y sin respaldo, en todos los textos del monitor y del informe (sin el anexo)
    body = [m for m in items if m.kind.startswith(("alert.", "end.", *MAIN_REPORT))]
    unsupported = sum(len(m.findings.get("unsupported_figures", [])) for m in body)
    figures = sum(m.figures for m in body)
    out["unsupported_figures"] = unsupported
    out["unsupported_share"] = ratio(unsupported, figures)
    # recomendaciones
    points = [
        p
        for m in items
        if m.kind in tm.RECOMMENDATION_KINDS and not m.kind.endswith(ANNEX)
        for p in tm.recommendation_points(m.text)
    ]
    acting = [p for p in points if tm.ACTION_RE.search(p) and tm.OBJECT_RE.search(p)]
    with_why = [p for p in points if WHY_RE.search(p) or DATA_RE.search(p)]
    both = [p for p in acting if WHY_RE.search(p) or DATA_RE.search(p)]
    out["rec_points"] = len(points)
    out["rec_with_action"] = ratio(len(acting), len(points))
    out["rec_with_why"] = ratio(len(with_why), len(points))
    out["rec_with_action_and_why"] = ratio(len(both), len(points))
    # frases opacas para quien no conoce el sistema
    total_sentences = sum(len(tm.sentences(m.text)) for m in body)
    leaked = sum(sum(len(m.findings.get(k, [])) for k in LEAKS) for m in body)
    out["opaque_sentences_share"] = ratio(leaked, total_sentences)
    # dudas
    sentences_all = [s for m in body for s in tm.sentences(m.text)]
    hedged = [s for s in sentences_all if HEDGE_RE.search(s)]
    out["hedged_share"] = ratio(len(hedged), len(sentences_all))
    out["hedged_without_data_share"] = ratio(
        sum(1 for s in hedged if not DATA_RE.search(s)), len(sentences_all)
    )
    # repetición entre resumen y explicación de la misma alerta
    explanations = {(m.scenario, m.ref): m for m in alert_texts(items, "explanation")}
    pairs = [(m, explanations.get((m.scenario, m.ref))) for m in summaries]
    similar = 0
    counted = 0
    for s, e in pairs:
        if e is None:
            continue
        counted += 1
        a, b = words(s.text), words(e.text)
        similar += 1 if a and len(a & b) / len(a) >= 0.5 else 0
    out["summary_repeated_in_explanation"] = ratio(similar, counted)
    out["texts"] = len(items)
    return out


ROWS = [
    ("texts", "Textos medidos", 0),
    ("alert_summary_chars", "Resumen de la alerta: caracteres (media)", 0),
    ("summary_max_chars", "Resumen: máximo de caracteres (límite 160)", 0),
    ("summary_over_limit", "Resúmenes de 160 caracteres o más", 1),
    ("alert_explanation_chars", "Explicación: caracteres (media)", 0),
    ("alert_explanation_sentences", "Explicación: frases (media)", 1),
    ("alert_recommendation_chars", "Recomendación: caracteres (media)", 0),
    ("alert_recommendation_sentences", "Recomendación: frases (media)", 1),
    ("close_chars", "Motivo de cierre: caracteres (media)", 0),
    ("report_summary_chars", "Informe, resumen: caracteres", 0),
    ("report_seen_chars", "Informe, «qué se vio»: caracteres", 0),
    ("report_recs_chars", "Informe, recomendaciones: caracteres", 0),
    (
        "alert_explanation_concrete_per_sentence",
        "Concreción de la explicación (datos por frase)",
        2,
    ),
    ("close_concrete_per_sentence", "Concreción del cierre (datos por frase)", 2),
    ("report_seen_concrete_per_sentence", "Concreción de «qué se vio» (datos por frase)", 2),
    ("unsupported_figures", "Cifras sin respaldo (número)", 1),
    ("unsupported_share", "Cifras sin respaldo (parte de las cifras)", 3),
    ("rec_points", "Recomendaciones: puntos", 1),
    ("rec_with_action", "Puntos con una acción sobre algo concreto", 2),
    ("rec_with_why", "Puntos con su porqué (causa, dato o fin)", 2),
    ("rec_with_action_and_why", "Puntos con acción y porqué", 2),
    ("opaque_sentences_share", "Frases con nombres internos o copiadas (parte)", 3),
    ("hedged_share", "Frases con una duda (parte)", 2),
    ("hedged_without_data_share", "Frases con una duda y sin ningún dato (parte)", 3),
    ("summary_repeated_in_explanation", "Alertas con el resumen repetido en la explicación", 2),
]


# Contadores de `text_metrics.py` (misma definición que en la Fase 14), sumados por repetición
PHASE14_ROWS = [
    ("total_leaks", "Fugas (nombres internos, enums, true/false, frases copiadas)", 1),
    ("total_errors", "Errores (ids, viento, distancias, desviaciones)", 1),
    ("generic_recommendation", "Recomendaciones genéricas", 1),
    ("no_action_recommendation", "Recomendaciones sin acción", 1),
    ("now_window_mix", "Mezcla ahora/ventana", 1),
    ("agree_without_fix", "Coinciden sin fix", 1),
    ("false_radar_unavailable", "Radar falso (dice que no informa y informaba)", 1),
    ("foreign_source_in_close", "Fuentes ajenas en el cierre", 1),
    ("close_without_cause_source", "Cierre sin dato de la causa", 1),
    ("monitor_talk_in_recommendations", "Jerga del monitor en las recomendaciones", 1),
    ("unsupported_figures", "Cifras sin respaldo (contador de la Fase 14)", 1),
    ("recovery_time_mismatch", "Hora de recuperación que no cuadra", 1),
]


def collect(experiment: str, profile: str, corpus: set[Any], scenarios: list[str]) -> list[Any]:
    """Una lista de métricas por repetición."""
    folder = tables.EXPERIMENTS / experiment
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    reps = sorted({e["rep"] for e in manifest["runs"] if e["profile"] == profile})
    source = tm.texts.Source(profile, folder, profile)
    out = []
    for rep in reps:
        items, _ = tm.measure_source(source, scenarios, rep, corpus)
        values = metrics_of(items)
        summary = tm.summarize(items)  # los contadores de `text_metrics.py` (Fase 14)
        values.update({f"tm_{key}": summary[key] for key, _, _ in PHASE14_ROWS})
        out.append(values)
    return out


def cell(values: list[float | None], decimals: int) -> str:
    known = [v for v in values if v is not None]
    if not known:
        return "–"
    text = f"{statistics.mean(known):.{decimals}f}"
    if len(known) > 1 and min(known) != max(known):
        text += f" ({min(known):.{decimals}f}–{max(known):.{decimals}f})"
    return text


def render(series: dict[str, list[dict[str, float | None]]]) -> str:
    names = list(series)
    lines = [
        "# E5 · medidas de estilo",
        "",
        __doc__.split("\n\n", 1)[1].split("\n\nSon medidas")[0],
        "",
        "Media entre repeticiones y, entre paréntesis, mínimo y máximo (`demo` y `faults` juntos "
        "en cada repetición). `actual` y Haiku: 3 repeticiones; Sonnet: 1.",
        "",
        "| | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for key, title, decimals in ROWS:
        row = [cell([r.get(key) for r in series[n]], decimals) for n in names]
        lines.append(f"| {title} | " + " | ".join(row) + " |")
    lines += ["", "## Contadores de corrección de los textos (definición de la Fase 14)", ""]
    lines += ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key, title, decimals in PHASE14_ROWS:
        row = [cell([r.get(f"tm_{key}") for r in series[n]], decimals) for n in names]
        lines.append(f"| {title} | " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=tables.EXPERIMENTS / "e5-estilo.md")
    parser.add_argument("--scenarios", default="demo,faults")
    args = parser.parse_args(argv)
    corpus = tm.static_corpus()
    scenarios = args.scenarios.split(",")
    series: dict[str, list[dict[str, float | None]]] = {}
    for name, experiment, profile in tables.SERIES:
        if (tables.EXPERIMENTS / experiment / "manifest.json").exists():
            series[name] = collect(experiment, profile, corpus, scenarios)
    args.out.write_text(render(series), encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(series, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{args.out} ({len(series)} series)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
