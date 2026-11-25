"""E7b, paso 5: métricas finales de las tablas revisadas y congeladas.

    uv run --project ai-module-py --group train python tools/training/final_report.py

Para las 13 facetas aprendidas (tabla candidata sin revisar frente a la revisada) y la regla
determinista de `drone.situation` (con las facetas ya revisadas), en validación, en la prueba de
e7b-v3 y en la generalización (e7b-gen-v3): F1 macro con IC 95 % por bootstrap de variantes. Mide
el efecto de cada rechazo (por faceta y en las demás: `drone.mode` alimenta a la regla de la
situación) y pasa `demo` y `nominal` por el monitor con las tablas congeladas. Escribe
`<v3>/report/e7b-final.md`.
"""

# ruff: noqa: E501

import json
import sys
from pathlib import Path

import numpy as np
import situation_eval as se
from apply_review import FROZEN_TABLES
from compare_v1_v2 import cell
from features import DEFAULT_DATASET, load
from models import confusion_by_variant, scores
from replay_learned import replay as replay_learned
from tree_to_table import candidates_path, table_predict

from ai_module.decision.table import load_tables
from ai_module.outbox import format_t
from ai_module.situation.replay import replay as replay_hand
from poc_contracts.states import FACETS

REPO = DEFAULT_DATASET.parents[2]


def facet_conf(tables, facet, data, names):  # noqa: ANN001, ANN201
    j = list(FACETS).index(facet)
    keep = data["y"][:, j] >= 0
    x, y, g = data["x"][keep], data["y"][keep, j].astype(np.int32), data["variant"][keep]
    return confusion_by_variant(y, table_predict(tables, facet, x, names), g, len(FACETS[facet]))


def _one(lst, i):  # noqa: ANN001, ANN202
    return f"{format_t(lst[i][0])} {lst[i][1]} {lst[i][2]}" if i < len(lst) else ""


def main() -> int:
    exp = DEFAULT_DATASET.parent
    v3 = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else exp / "e7b-v3"
    gen = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else exp / "e7b-gen-v3"
    unreviewed = load_tables(candidates_path(v3))
    reviewed = load_tables(FROZEN_TABLES)
    data = {
        "Validación": load(v3, "validation"),
        "Prueba de v3": load(v3, "test"),
        "Generalización": load(gen, "test"),
    }
    names = [str(f) for f in data["Validación"]["features"]]
    margin = json.loads((v3 / "report" / "situation.json").read_text(encoding="utf-8"))["margin"]
    effects = json.loads((v3 / "report" / "review.json").read_text(encoding="utf-8"))
    lines = ["# E7b · Tablas revisadas (e7b-v3): métricas finales", "",
             "Revisión: no se redondea ningún umbral; se rechazan LQ-03, BE-06 y DM-10 (probabilidad < 0,1). "
             "`drone.situation` es la regla determinista. F1 macro con IC 95 % por bootstrap de variantes.", "",
             "## Efecto de cada rechazo en validación (la faceta de la fila)", "",
             "| Fila | Faceta | F1 macro antes | después | Instantes que cambian | F1 por clase antes → después |", "|---|---|---|---|---|---|"]  # fmt: skip
    for e in effects:
        per = ", ".join(
            f"{c} {b:.3f}→{a:.3f}"
            for c, b, a in zip(e["classes"], e["f1_before"], e["f1_after"], strict=True)
        )
        lines.append(
            f"| {e['row']} | {e['facet']} | {e['macro_f1_before']:.4f} | {e['macro_f1_after']:.4f} ({e['delta']:+.4f}) | {e['validation_instants_changed']} | {per} |"
        )
    summary: dict = {}
    for split, d in data.items():
        lines += [
            "",
            f"## {split}",
            "",
            "| Faceta | Sin revisar | **Revisada** | Δ |",
            "|---|---|---|---|",
        ]
        for facet in FACETS:
            if facet == "drone.situation":
                continue
            a = facet_conf(unreviewed, facet, d, names)
            b = facet_conf(reviewed, facet, d, names)
            fa, fb = scores(sum(a.values()))["macro_f1"], scores(sum(b.values()))["macro_f1"]
            lines.append(f"| {facet} | {cell(a)} | **{cell(b)}** | {fb - fa:+.3f} |")
            summary.setdefault(split, {})[facet] = fb
        # la regla de la situación, con las facetas de cada versión
        res = {}
        for label, tables in (("sin revisar", unreviewed), ("revisada", reviewed)):
            states = se.learned_states(tables, d, names)
            pred = se.run_rule(d, states, names, margin)
            res[label] = se.conf(d, pred)
        fa, fb = (scores(sum(res[k].values()))["macro_f1"] for k in ("sin revisar", "revisada"))
        lines.append(
            f"| drone.situation (regla, margen {margin:g}) | {cell(res['sin revisar'])} | **{cell(res['revisada'])}** | {fb - fa:+.3f} |"
        )
        summary.setdefault(split, {})["drone.situation"] = fb
    # demo y nominal con las tablas congeladas
    lines += ["", "## `demo` y `nominal` con las tablas congeladas", "",
              "Facetas GPS, enlace, viento y situación (regla) congeladas; tabla del tipo de incidente, seguidor y política: los del vídeo.", ""]  # fmt: skip
    for name in ("demo", "nominal"):
        events = REPO / "runs" / name / "events.jsonl"
        video = [
            (p["as_of_sim_time"], p["change"], p["kind"])
            for _, p in replay_hand(events)
            if p["change"] != "evidence"
        ]
        frozen = [
            (t, c, k) for t, c, k, _ in replay_learned(events, reviewed, rule=True, margin_k=margin)
        ]
        lines += [f"**{name}**", "", "| Vídeo (tablas a mano) | Tablas congeladas |", "|---|---|"]
        for i in range(max(len(video), len(frozen))):
            lines.append(f"| {_one(video, i)} | {_one(frozen, i)} |")
        if not video and not frozen:
            lines.append("| ningún incidente | ningún incidente |")
        lines.append("")
    out = v3 / "report" / "e7b-final.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (v3 / "report" / "e7b-final.json").write_text(
        json.dumps(summary, indent=1, default=float), "utf-8"
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
