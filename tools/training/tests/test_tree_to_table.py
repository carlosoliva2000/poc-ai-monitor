"""Pruebas de la conversión árbol → tabla de reglas y de su comprobación de cobertura:

uv run --project ai-module-py --group train pytest tools/training/tests/test_tree_to_table.py
"""

from pathlib import Path

import models
import numpy as np
import tree_to_table as t2t
from sklearn.tree import DecisionTreeClassifier

from ai_module.decision.table import load_tables

FEATURES = ["a", "b", "c"]
FACET = "gps.integrity"  # reliable / spoofed
RNG = np.random.default_rng(3)


def _fit() -> tuple[models.Tree, np.ndarray, np.ndarray]:
    n = 6000
    x = RNG.normal(size=(n, 3)).astype(np.float32)
    x[:, 2] *= 1e-4  # una característica de escala pequeña: umbrales con muchos decimales
    y = ((x[:, 0] > 0.4) & (x[:, 1] < 0.5) | (x[:, 2] > 1.2e-4)).astype(np.int32)
    x[RNG.random(n) < 0.1, 0] = np.nan
    x[RNG.random(n) < 0.05, 2] = np.nan
    groups = np.repeat(np.arange(n // 30), 30)
    t = np.tile(np.arange(30, dtype=np.float32), n // 30)
    clf = DecisionTreeClassifier(max_depth=4, min_samples_leaf=20, random_state=0).fit(x, y)
    tree = models.from_sklearn(clf, ["reliable", "spoofed"], FEATURES)
    tree.audit(x, y, groups, t)
    return tree, x, y


def test_the_table_gives_the_same_states_as_the_tree(tmp_path: Path) -> None:
    tree, x, _ = _fit()
    path = t2t.write_candidates({FACET: tree}, tmp_path / "t.yaml")
    tables = load_tables(path)  # el evaluador de la E6 la acepta
    pred = t2t.table_predict(tables, FACET, x, FEATURES)
    assert (pred == tree.predict(x)).all()
    # y el motor de la E6, fila a fila, da lo mismo que la evaluación vectorizada
    table = tables[t2t.table_name(FACET)]
    for i in range(0, len(x), 97):
        inputs = {
            name: (None if np.isnan(v) else float(v))
            for name, v in zip(FEATURES, x[i], strict=True)
        }
        state = str(table.evaluate({k: inputs[k] for k in table.inputs}).then["state"])
        assert state == tree.classes[tree.predict(x[i : i + 1])[0]]


def test_the_default_row_is_last_and_has_no_conditions(tmp_path: Path) -> None:
    tree, _, _ = _fit()
    rows = t2t.leaf_rows(tree, FACET)
    assert rows[-1].default and sum(r.default for r in rows) == 1
    assert rows[-1].state == "reliable"  # la hoja normal con más instantes
    table = load_tables(t2t.write_candidates({FACET: tree}, tmp_path / "t.yaml"))["gps_integrity"]
    assert table.rules[-1].when == {} and table.outputs == t2t.OUTPUTS
    assert {r.rule_id for r in table.rules} == {r.rule_id for r in rows}


def test_thresholds_are_written_without_exponent_and_keep_every_digit() -> None:
    assert t2t.number(1.2345e-5) == "0.000012345"
    assert float(t2t.number(0.30000001192092896)) == 0.30000001192092896
    assert t2t.Cond(-t2t.INF, 2.5, True).feel() == "<= 2.5, null"
    assert t2t.Cond(1.0, 2.0, False).feel() == "(1..2]"
    assert t2t.Cond(1.0, t2t.INF, True).feel() == "> 1, null"
    assert t2t.Cond(-t2t.INF, t2t.INF, False).feel() == "not(null)"  # cualquier valor presente
    assert t2t.Cond(t2t.INF, 0.5, True).feel() == "null"  # solo los valores que faltan


def test_a_tree_gives_rows_without_overlaps_or_gaps() -> None:
    tree, _, _ = _fit()
    rows = t2t.leaf_rows(tree, FACET)
    assert t2t.overlapping(rows) == []
    assert not t2t.uncovered(rows, FEATURES)


def test_coverage_check_finds_overlaps_and_gaps() -> None:
    tree, _, _ = _fit()
    rows = t2t.leaf_rows(tree, FACET)
    assert t2t.uncovered(rows[:1] + rows[-1:], FEATURES)  # faltan filas: hay hueco
    named = [r for r in rows if not r.default]
    named[1].conds = {k: t2t.Cond(c.lo - 1.0, c.hi + 1.0, True) for k, c in named[0].conds.items()}
    assert t2t.overlapping(rows)  # una fila ensanchada se cruza con otra


def test_the_support_of_each_row_is_written() -> None:
    tree, _, _ = _fit()
    for row in t2t.leaf_rows(tree, FACET):
        assert row.variants >= 0 and row.instants == tree.counts[row.leaf, tree.label[row.leaf]]
        assert 0.0 <= row.probability <= 1.0


def test_a_split_between_missing_and_present_values_keeps_both_rows_apart(tmp_path: Path) -> None:
    """scikit-learn parte «NaN o no» con umbral `inf`: una hoja es «algún valor» y la otra «ningún
    valor»; si la primera se escribiera como `-` (también NaN), las dos filas se cruzarían."""
    tree = models.Tree(
        feature=np.array([0, -1, -1], dtype=np.int32),
        threshold=np.array([np.inf, 0.0, 0.0]),
        left=np.array([1, -1, -1], dtype=np.int32),
        right=np.array([2, -1, -1], dtype=np.int32),
        missing_left=np.array([False, False, False]),
        label=np.array([0, 0, 1], dtype=np.int32),
        classes=["reliable", "spoofed"],
        features=["a"],
    )
    x = np.array([[1.0], [-5.0], [np.nan]] * 40, dtype=np.float32)
    y = np.array([0, 0, 1] * 40, dtype=np.int32)
    tree.audit(x, y, np.repeat(np.arange(8), 15), np.tile(np.arange(15, dtype=np.float32), 8))
    rows = t2t.leaf_rows(tree, FACET)
    assert t2t.overlapping(rows) == [] and not t2t.uncovered(rows, ["a"])
    tables = load_tables(t2t.write_candidates({FACET: tree}, tmp_path / "t.yaml"))
    assert (t2t.table_predict(tables, FACET, x, ["a"]) == tree.predict(x)).all()
    assert [r.conds["a"].feel() for r in rows if not r.default] == ["null"]


def test_the_cause_has_no_default_class_and_low_confidence_rows_are_marked(tmp_path: Path) -> None:
    """Sin clase normal (`drone.cause`) la fila por defecto no es la hoja mayor (que acabaría siendo
    «control ajeno» para todo lo que no encaja) sino un «sin determinar» al que no llega nada; y
    cada fila lleva su banda de confianza para que la política resuelva lo dudoso."""
    n = 6000
    x = RNG.normal(size=(n, 2)).astype(np.float32)
    y = np.where(x[:, 0] > 0.5, 0, np.where(x[:, 1] > 0, 1, 2)).astype(np.int32)  # 3 causas
    flip = RNG.random(n) < 0.35  # ruido de etiqueta: hojas con probabilidad baja
    y[flip] = RNG.integers(0, 3, flip.sum())
    clf = DecisionTreeClassifier(max_depth=3, min_samples_leaf=40, random_state=0).fit(x, y)
    classes = ["foreign_control", "spoofed_position", "dead_reckoning", "wind", "unexplained"]
    tree = models.from_sklearn(clf, classes, ["a", "b"])
    groups = np.repeat(np.arange(n // 30), 30)
    tree.audit(x, y, groups, np.tile(np.arange(30, dtype=np.float32), n // 30))
    rows = t2t.leaf_rows(tree, "drone.cause")
    assert rows[-1].default and rows[-1].leaf < 0 and rows[-1].state == "unexplained"
    assert all(r.conds for r in rows[:-1]) and not any(r.default for r in rows[:-1])
    assert t2t.overlapping(rows) == [] and not t2t.uncovered(rows, ["a", "b"])
    assert {r.confidence for r in rows[:-1]} <= {"confirmed", "probable", "possible"}
    assert t2t.confidence(0.9) == "confirmed" and t2t.confidence(0.6) == "probable"
    assert t2t.confidence(0.59) == "possible"
    tables = load_tables(t2t.write_candidates({"drone.cause": tree}, tmp_path / "c.yaml"))
    assert (t2t.table_predict(tables, "drone.cause", x, ["a", "b"]) == tree.predict(x)).all()
    assert "confidence" in tables["drone_cause"].outputs
