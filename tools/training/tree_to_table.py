"""E7b, paso 3: del árbol a la tabla de reglas (formato de `situation/tables.yaml`, política FIRST).

    uv run --project ai-module-py --group train python tools/training/tree_to_table.py

Cada hoja del árbol es una fila: el camino de la raíz a la hoja se resume en **una condición por
característica** (un intervalo FEEL `(a..b]`, `> a` o `<= b`, más `null` si los valores que faltan
llegan a esa hoja). Las salidas son el estado, la probabilidad de la hoja (fracción de los instantes
de entrenamiento de la hoja que son de su clase), cuántos instantes la sostienen y de cuántas
variantes y rachas distintas. La hoja con más instantes de la clase normal queda de fila por
defecto, sin condiciones, al final. Las filas son excluyentes, así que el orden da igual.
"""

import math
import pickle
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from features import DEFAULT_DATASET
from models import Tree

from ai_module.decision.table import _COMPARISON, _RANGE, DecisionTables, load_tables
from poc_contracts.states import FACETS

REPO = Path(__file__).resolve().parents[2]
CANDIDATES = REPO / "tools" / "training" / "candidates" / "e7b-v1.yaml"
NORMAL = {"normal", "good", "reliable", "connected", "sufficient", "calm", "mission", "on_route"}
PREFIX = {
    "gps.availability": "GA", "gps.quality": "GQ", "gps.integrity": "GI",
    "radar.availability": "RA",
    "link.availability": "LA", "link.quality": "LQ", "meteo.availability": "MA",
    "battery.availability": "BA", "battery.level": "BL", "battery.endurance": "BE",
    "environment.wind": "EW", "drone.mode": "DM", "drone.situation": "DS", "drone.cause": "DC",
}  # fmt: skip
OUTPUTS = ["state", "probability", "confidence", "instants", "variants", "episodes"]
CUT_CONFIRMED, CUT_PROBABLE = 0.9, 0.6  # cortes de confianza (validados en el informe)
INF = math.inf


FALLBACK_STATE = "unexplained"


def confidence(probability: float) -> str:
    """Banda de confianza de una fila por la probabilidad de su hoja."""
    if probability >= CUT_CONFIRMED:
        return "confirmed"
    return "probable" if probability >= CUT_PROBABLE else "possible"


def table_name(facet: str) -> str:
    return facet.replace(".", "_")


def number(x: float) -> str:
    """El número en notación posicional (FEEL no admite exponente), sin perder cifras."""
    return np.format_float_positional(x, unique=True, trim="-")


@dataclass
class Cond:
    """Una característica en un camino: `lo < x <= hi`; `nan_ok`: llegan también los NaN."""

    lo: float = -INF
    hi: float = INF
    nan_ok: bool = True

    def feel(self) -> str:
        if self.lo >= self.hi:  # ningún valor: solo los NaN (scikit-learn parte «NaN o no» con inf)
            return "null"
        if self.lo == -INF and self.hi == INF:
            return "-" if self.nan_ok else "not(null)"  # cualquier valor / cualquier valor no nulo
        elif self.lo == -INF:
            test = f"<= {number(self.hi)}"
        elif self.hi == INF:
            test = f"> {number(self.lo)}"
        else:
            test = f"({number(self.lo)}..{number(self.hi)}]"
        return ", ".join(part for part in (test, "null" if self.nan_ok else "") if part) or "-"

    def empty(self) -> bool:
        return self.lo >= self.hi and not self.nan_ok


@dataclass
class Row:
    rule_id: str
    conds: dict[str, Cond]
    state: str
    probability: float
    instants: int
    variants: int
    episodes: int
    leaf: int
    confidence: str = ""
    default: bool = False
    note: str = ""
    features_order: list[str] = field(default_factory=list)


def leaf_rows(tree: Tree, facet: str) -> list[Row]:
    rows: list[Row] = []

    def walk(node: int, conds: dict[str, Cond]) -> None:
        if tree.is_leaf(node):
            label = int(tree.label[node])
            rows.append(Row(
                "", {k: Cond(c.lo, c.hi, c.nan_ok) for k, c in conds.items()},
                tree.classes[label], round(tree.purity(node), 4),
                int(tree.counts[node, label]), int(tree.support[node]),
                int(tree.episodes[node]), node,
            ))  # fmt: skip
            return
        name = tree.features[tree.feature[node]]
        thr = float(tree.threshold[node])
        went_left_nan = bool(tree.missing_left[node])
        for side, child in (("left", tree.left[node]), ("right", tree.right[node])):
            c = conds.get(name, Cond())
            new = Cond(c.lo, c.hi, c.nan_ok and (went_left_nan == (side == "left")))
            if side == "left":
                new.hi = min(c.hi, thr)
            else:
                new.lo = max(c.lo, thr)
            if not new.empty():
                walk(int(child), {**conds, name: new})

    walk(0, {})
    for r in rows:
        r.confidence = confidence(r.probability)
    normal = [r for r in rows if r.state in NORMAL]
    if normal:
        # La fila por defecto: la hoja con más instantes de su clase normal.
        default = max(normal, key=lambda r: r.instants)
        default.default = True
        ordered = sorted(
            (r for r in rows if not r.default), key=lambda r: (r.state in NORMAL, -r.instants)
        )
        ordered.append(default)
    else:
        # Sin clase normal (la causa): todas las hojas llevan sus condiciones y la fila por defecto
        # es un «sin determinar» al que no llega ninguna muestra (el árbol cubre todo el espacio).
        # Así la hoja mayor no se convierte en la respuesta de lo que no encaja.
        ordered = sorted(rows, key=lambda r: -r.instants)
        fallback = FALLBACK_STATE if FALLBACK_STATE in FACETS[facet] else ordered[-1].state
        ordered.append(Row("", {}, fallback, 0.0, 0, 0, 0, -1, "possible", default=True))
    for i, r in enumerate(ordered, 1):
        r.rule_id = f"{PREFIX[facet]}-{i:02d}"
        tail = " (default row: everything the rows above do not match)" if r.default else ""
        tail = " (fallback: no row of the tree reaches it)" if r.leaf < 0 else tail
        r.note = (
            f"{r.variants} variants, {r.episodes} episodes, {r.instants} training instants{tail}"
        )
    return ordered


# --- Escritura del YAML ------------------------------------------------------------------------


def table_dict(tree: Tree, facet: str) -> dict:
    rows = leaf_rows(tree, facet)
    used = [
        f for f in tree.features if any(f in r.conds and r.conds[f].feel() != "-" for r in rows)
    ]
    return {
        "description": f"Learned from simulator data (CART tree, {len(rows)} rows): {facet}.",
        "hit_policy": "FIRST",
        "inputs": used,
        "outputs": OUTPUTS,
        "rules": [
            {
                "id": r.rule_id,
                "note": r.note,
                "when": {} if r.default else {f: r.conds[f].feel() for f in used if f in r.conds},
                "then": {
                    "state": r.state, "probability": r.probability, "confidence": r.confidence,
                    "instants": r.instants, "variants": r.variants, "episodes": r.episodes,
                },
            }
            for r in rows
        ],
    }  # fmt: skip


def candidates_path(dataset: Path) -> Path:
    return REPO / "tools" / "training" / "candidates" / f"{dataset.name}.yaml"


def write_candidates(trees: dict[str, Tree], path: Path = CANDIDATES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"version": 1, "tables": {table_name(f): table_dict(t, f) for f, t in trees.items()}}
    header = (
        "# Tablas candidatas de la E7b: un árbol CART por faceta convertido en reglas (política\n"
        "# FIRST). Salen de `tools/training/tree_to_table.py`; no se editan a mano.\n"
        "# Cada fila dice cuántas variantes distintas la sostienen.\n"
    )
    path.write_text(header + yaml.safe_dump(body, sort_keys=False, width=100), encoding="utf-8")
    return path


# --- Cobertura ---------------------------------------------------------------------------------


def _meet(a: Cond, b: Cond) -> bool:
    """Si dos condiciones sobre la misma característica comparten algún valor (o los NaN)."""
    return max(a.lo, b.lo) < min(a.hi, b.hi) or (a.nan_ok and b.nan_ok)


def overlapping(rows: list[Row]) -> list[tuple[str, str]]:
    """Pares de filas con condiciones que se cruzan (dos filas del mismo árbol no pueden). La
    fila por defecto no entra: es el resto."""
    named = [r for r in rows if not r.default]
    bad = []
    for i, a in enumerate(named):
        for b in named[i + 1 :]:
            if all(
                _meet(a.conds.get(f, Cond()), b.conds.get(f, Cond())) for f in {*a.conds, *b.conds}
            ):
                bad.append((a.rule_id, b.rule_id))
    return bad


def uncovered(rows: list[Row], features: list[str]) -> bool:
    """Si queda algún hueco: algún punto del espacio que no cae en ninguna fila. Con todas las
    cajas (la de la fila por defecto con sus condiciones reales) se resta cada caja del universo."""
    pending = [{f: Cond() for f in features}]
    for r in rows:
        if r.leaf < 0:  # el «sin determinar» no cubre nada: es lo que queda si algo se escapara
            continue
        nxt = []
        for box in pending:
            nxt += _subtract(box, {f: r.conds.get(f, Cond()) for f in features})
        pending = nxt
    return any(_nonempty(box) for box in pending)


def _nonempty(box: dict[str, Cond]) -> bool:
    return all(c.lo < c.hi or c.nan_ok for c in box.values())


def _subtract(box: dict[str, Cond], cut: dict[str, Cond]) -> list[dict[str, Cond]]:
    """`box` menos `cut`, como una lista de cajas disjuntas."""
    if not all(_meet(box[f], cut[f]) for f in box):
        return [box]
    pieces = []
    rest = dict(box)
    for f in box:
        b, c = rest[f], cut[f]
        for part in (  # lo que de `b` queda fuera de `c`, por abajo, por arriba y los NaN
            Cond(b.lo, min(b.hi, c.lo), False) if c.lo > b.lo else None,
            Cond(max(b.lo, c.hi), b.hi, False) if c.hi < b.hi else None,
            Cond(INF, INF, True) if b.nan_ok and not c.nan_ok else None,
        ):
            if part is not None and _nonempty({f: part}):
                pieces.append({**rest, f: part})
        rest[f] = Cond(max(b.lo, c.lo), min(b.hi, c.hi), b.nan_ok and c.nan_ok)
    return pieces


# --- Evaluación vectorizada de una tabla escrita ------------------------------------------------


def _test_mask(test: str, v: np.ndarray) -> np.ndarray:
    """Un unary test (el subconjunto que escribe este módulo) sobre un vector con NaN."""
    test = test.strip()
    if test == "-":
        return np.ones(len(v), dtype=bool)
    if test == "null":
        return np.isnan(v)
    if test == "not(null)":
        return ~np.isnan(v)
    with np.errstate(invalid="ignore"):
        if m := _COMPARISON.match(test):
            op, lim = m.group(1), float(m.group(2))
            return {"<": v < lim, "<=": v <= lim, ">": v > lim, ">=": v >= lim}[op]
        if m := _RANGE.match(test):
            lo, hi = float(m.group(2)), float(m.group(3))
            above = v >= lo if m.group(1) == "[" else v > lo
            below = v <= hi if m.group(4) == "]" else v < hi
            return above & below
    raise ValueError(f"unsupported test {test!r}")


def table_rows_hit(
    tables: DecisionTables, facet: str, x: np.ndarray, features: list[str]
) -> np.ndarray:
    """Índice de la primera fila que encaja en cada muestra (política FIRST)."""
    table = tables[table_name(facet)]
    col = {name: x[:, features.index(name)].astype(np.float64) for name in table.inputs}
    hit = np.full(len(x), -1, dtype=np.int32)
    for i, rule in enumerate(table.rules):
        mask = np.ones(len(x), dtype=bool)
        for name, cell in rule.when.items():
            parts = re.split(r",(?![^(\[]*[\])])", str(cell))  # comas de primer nivel
            mask &= np.any([_test_mask(p, col[name]) for p in parts], axis=0)
        hit[(hit < 0) & mask] = i
    return hit


def table_predict(
    tables: DecisionTables, facet: str, x: np.ndarray, features: list[str]
) -> np.ndarray:
    table = tables[table_name(facet)]
    codes = {s: i for i, s in enumerate(FACETS[facet])}
    per_rule = np.array([codes[str(r.then["state"])] for r in table.rules])
    return per_rule[table_rows_hit(tables, facet, x, features)]


def main() -> int:
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    trees: dict[str, Tree] = pickle.loads((dataset / "models" / "trees.pkl").read_bytes())  # noqa: S301
    path = write_candidates(trees, candidates_path(dataset))
    load_tables(path)  # el evaluador de la E6 la lee y la valida
    for facet, tree in trees.items():
        rows = leaf_rows(tree, facet)
        features = tree.features
        print(
            f"{facet}: {len(rows)} filas, solapes {overlapping(rows)}, "
            f"huecos {uncovered(rows, features)}"
        )
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
