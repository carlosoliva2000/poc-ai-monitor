"""E7b, paso 5: aplica la revisión de las tablas candidatas y escribe la tabla revisada.

    uv run --project ai-module-py --group train python tools/training/apply_review.py [DATASET]

Lee `review/<dataset>/<faceta>.yaml` (solo `reject` y `reason`; `round_to` no se admite: no se ha
usado), aplica **cada rechazo por separado** midiendo su efecto en **validación** y lo deshace si
la F1 macro de esa faceta baja más de `TOLERANCE`. Una fila rechazada deja su región a la fila por
defecto (las filas son excluyentes: no puede haber solapes ni huecos nuevos). Escribe:

- `ai-module-py/src/ai_module/situation/tables_learned.yaml`: las tablas revisadas (13 facetas;
  `drone.situation` es la regla determinista de `situation_rule.yaml`);
- `review/<dataset>/rejected.yaml`: las filas rechazadas **completas** (condiciones, estado,
  probabilidad, soporte y aciertos) con su motivo y la fecha, para poder restaurarlas;
- `review/<dataset>/candidate-unreviewed.yaml`: copia de la tabla candidata sin revisar;
- `<dataset>/report/review.json`: el efecto de cada rechazo.
"""

# ruff: noqa: E501

import copy
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import yaml
from features import DEFAULT_DATASET, load
from models import confusion_by_variant, scores
from review_files import REVIEW_DIR
from tree_to_table import candidates_path, table_name, table_predict

from ai_module.decision.table import load_tables
from poc_contracts.states import FACETS

REPO = Path(__file__).resolve().parents[2]
FROZEN_TABLES = REPO / "ai-module-py" / "src" / "ai_module" / "situation" / "tables_learned.yaml"
TOLERANCE = (
    0.005  # si una fila rechazada hace bajar la F1 macro de validación más que esto, se deshace
)


def evaluate(raw_tables: dict, facet: str, data: dict, names: list[str]) -> tuple[dict, np.ndarray]:
    """Matriz de confusión por variante de una faceta con la tabla `raw_tables[facet]`."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        yaml.safe_dump({"version": 1, "tables": raw_tables}, handle, sort_keys=False)
    tables = load_tables(Path(handle.name))
    j = list(FACETS).index(facet)
    keep = data["y"][:, j] >= 0
    x, y, g = data["x"][keep], data["y"][keep, j].astype(np.int32), data["variant"][keep]
    pred = table_predict(tables, facet, x, names)
    return confusion_by_variant(y, pred, g, len(FACETS[facet])), pred


def main() -> int:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    review_dir = REVIEW_DIR / dataset.name
    candidate = candidates_path(dataset)
    raw = yaml.safe_load(candidate.read_text(encoding="utf-8"))["tables"]
    val = load(dataset, "validation")
    names = [str(f) for f in val["features"]]
    final = copy.deepcopy(raw)
    rejected, effects = [], []
    for review_file in sorted(review_dir.glob("*.yaml")):
        review = yaml.safe_load(review_file.read_text(encoding="utf-8"))
        if not isinstance(review, dict) or "rows" not in review:
            continue
        facet, name = review["facet"], review["table"]
        for row in review["rows"]:
            if any(t.get("round_to") is not None for t in row.get("thresholds", [])):
                raise SystemExit(f"{row['id']}: `round_to` is not supported in this review")
            if not row.get("reject"):
                continue
            rules = final[name]["rules"]
            target = next(r for r in rules if r["id"] == row["id"])
            if not target["when"]:
                raise SystemExit(f"{row['id']} is the default row: it cannot be rejected")
            before_conf, before_pred = evaluate(final, facet, val, names)
            trial = copy.deepcopy(final)
            trial[name]["rules"] = [r for r in trial[name]["rules"] if r["id"] != row["id"]]
            after_conf, after_pred = evaluate(trial, facet, val, names)
            b, a = scores(sum(before_conf.values())), scores(sum(after_conf.values()))
            moved = int((before_pred != after_pred).sum())
            effect = {
                "row": row["id"], "facet": facet, "reason": row.get("reason", ""),
                "macro_f1_before": b["macro_f1"], "macro_f1_after": a["macro_f1"],
                "delta": a["macro_f1"] - b["macro_f1"],
                "f1_before": np.round(b["f1"], 4).tolist(), "f1_after": np.round(a["f1"], 4).tolist(),
                "classes": list(FACETS[facet]), "validation_instants_changed": moved,
                "applied": a["macro_f1"] >= b["macro_f1"] - TOLERANCE,
            }  # fmt: skip
            effects.append(effect)
            if effect["applied"]:
                final = trial
                rejected.append(
                    {
                        "id": row["id"],
                        "facet": facet,
                        "table": name,
                        "reason": row.get("reason", ""),
                        "when": target["when"],
                        "then": target["then"],
                        "note": target.get("note", ""),
                        "readable": row["when"],
                        "validation": row["validation"],
                        "effect_in_validation": {
                            "macro_f1_before": round(b["macro_f1"], 4),
                            "macro_f1_after": round(a["macro_f1"], 4),
                            "instants_changed": moved,
                        },  # fmt: skip
                    }
                )
    today = date.today().isoformat()
    header = (
        "# Tablas aprendidas de la E7b, revisadas y congeladas (e7b-v3). Salen de\n"
        f"# `tools/training/candidates/{dataset.name}.yaml` quitando las filas de\n"
        f"# `tools/training/review/{dataset.name}/rejected.yaml` (`tools/training/apply_review.py`).\n"
        "# No se editan a mano: `tables_freeze.json` guarda su hash. `drone.situation` no está aquí:\n"
        "# es la regla determinista de `situation_rule.yaml`. Formato de `tables.yaml` (política FIRST);\n"
        "# `state`, `probability`, `confidence` (confirmed ≥ 0,9, probable ≥ 0,6, possible), `instants`,\n"
        "# `variants` y `episodes` de cada fila son los de su hoja en el entrenamiento.\n"
    )
    names_out = {k: v for k, v in final.items() if k != table_name("drone.situation")}
    FROZEN_TABLES.write_text(
        header + yaml.safe_dump({"version": 1, "tables": names_out}, sort_keys=False, width=100),
        encoding="utf-8",
    )
    (review_dir / "rejected.yaml").write_text(
        "# Filas rechazadas en la revisión de e7b-v3 (completas, para poder restaurarlas: volver a\n"
        f"# ponerlas en su tabla de `{FROZEN_TABLES.name}` y recalcular `tables_freeze.json`).\n"
        + yaml.safe_dump(
            {"dataset": dataset.name, "date": today, "tolerance_macro_f1": TOLERANCE,
             "rows": rejected}, sort_keys=False, width=100, allow_unicode=True),
        encoding="utf-8",
    )  # fmt: skip
    shutil.copy(candidate, review_dir / "candidate-unreviewed.yaml")
    (dataset / "report" / "review.json").write_text(
        json.dumps(effects, indent=1, default=float), "utf-8"
    )
    for e in effects:
        print(f"{e['row']} ({e['facet']}): F1 macro validación {e['macro_f1_before']:.4f} → "
              f"{e['macro_f1_after']:.4f} ({e['delta']:+.4f}); {e['validation_instants_changed']} "
              f"instantes cambian; {'aplicado' if e['applied'] else 'DESHECHO'}")  # fmt: skip
    print(FROZEN_TABLES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
