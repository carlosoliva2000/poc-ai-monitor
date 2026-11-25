"""E7b, paso 4: un fichero de revisión por tabla (`tools/training/review/<faceta>.yaml`).

Cada fila se escribe en texto legible, con su soporte (instantes, variantes y rachas de
entrenamiento), su probabilidad (pureza) y cómo acierta en validación. Lo único que se puede tocar
es, en cada fila, **`reject`** (la fila se quita y su región pasa a la fila por defecto) y, en cada
umbral, **`round_to`** (el valor redondeado que sustituye al que escribió el árbol). Nada más.
`apply_review.py` (paso 5) lo aplica con constancia de cada cambio.
"""

from pathlib import Path

import numpy as np
import yaml
from tree_to_table import Row, table_name

REVIEW_DIR = Path(__file__).resolve().parent / "review"


def readable(row: Row) -> str:
    """Las condiciones de la fila en texto, con 4 cifras (la tabla conserva el umbral entero)."""
    if row.leaf < 0:
        return "never reached: the rows above cover everything (leaves the cause undetermined)"
    if row.default:
        return "everything the rows above do not match"
    parts = []
    for feature, cond in row.conds.items():
        if cond.lo >= cond.hi:
            parts.append(f"{feature} is missing")
        elif cond.feel() == "not(null)":
            parts.append(f"{feature} is present")
        else:
            if cond.lo == -np.inf:
                text = f"<= {cond.hi:.4g}"
            elif cond.hi == np.inf:
                text = f"> {cond.lo:.4g}"
            else:
                text = f"in ({cond.lo:.4g}, {cond.hi:.4g}]"
            parts.append(f"{feature} {text}" + (" (or missing)" if cond.nan_ok else ""))
    return " and ".join(parts)


def thresholds(row: Row) -> list[dict]:
    out = []
    for feature, cond in row.conds.items():
        if np.isfinite(cond.lo):
            out.append(
                {"feature": feature, "op": ">", "value": float(f"{cond.lo:.6g}"), "round_to": None}
            )
        if np.isfinite(cond.hi):
            out.append(
                {"feature": feature, "op": "<=", "value": float(f"{cond.hi:.6g}"), "round_to": None}
            )
    return out


def write_review(
    facet: str, rows: list[Row], validation: dict[str, tuple[int, int]], out_dir: Path = REVIEW_DIR
) -> Path:
    """`validation`: id de fila → (instantes de validación que caen en ella, los de su clase)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "facet": facet,
        "table": table_name(facet),
        "how_to_review": (
            "Per row you can only change `reject` (true removes the row; its region goes to the "
            "default row) and, in each threshold, `round_to` (the rounded value that replaces it). "
            "The default row cannot be rejected."
        ),
        "rows": [],
    }
    for row in rows:
        hits, right = validation.get(row.rule_id, (0, 0))
        body["rows"].append({
            "id": row.rule_id,
            "state": row.state,
            "when": readable(row),
            "training": {
                "probability": row.probability, "instants": row.instants,
                "variants": row.variants, "episodes": row.episodes,
            },
            "validation": {"instants": hits, "right": right,
                           "precision": round(right / hits, 4) if hits else None},  # fmt: skip
            "confidence": row.confidence,
            "reject": False,
            "thresholds": [] if row.default or row.leaf < 0 else thresholds(row),
        })  # fmt: skip
    path = out_dir / f"{facet}.yaml"
    path.write_text(yaml.safe_dump(body, sort_keys=False, width=100, allow_unicode=True), "utf-8")
    return path
