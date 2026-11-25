"""Pruebas del árbol propio, la poda por episodios y las métricas con bootstrap:

uv run --project ai-module-py --group train pytest tools/training/tests/test_models.py
"""

import models
import numpy as np
from sklearn.tree import DecisionTreeClassifier

from ai_module.situation.features import FEATURES


def _data(n: int = 3000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 4)).astype(np.float32)
    y = ((x[:, 0] > 0.3) + 2 * (x[:, 1] < -0.5)).astype(np.int32)
    x[rng.random(n) < 0.15, 0] = np.nan  # valores que faltan
    return x, y


def test_our_tree_predicts_exactly_like_scikit_learn_including_missing_values() -> None:
    x, y = _data()
    clf = DecisionTreeClassifier(max_depth=5, min_samples_leaf=10, random_state=0).fit(x, y)
    tree = models.from_sklearn(clf, ["a", "b", "c", "d"], ["f0", "f1", "f2", "f3"])
    xt, _ = _data(2000, seed=1)
    assert (tree.predict(xt) == clf.predict(xt)).all()
    only_missing = np.full((50, 4), np.nan, dtype=np.float32)  # todo NaN: solo manda su lado
    assert (tree.predict(only_missing) == clf.predict(only_missing)).all()


def test_a_missing_value_goes_where_the_training_data_sent_it() -> None:
    x = np.array([[1.0], [2.0], [3.0], [4.0], [np.nan], [np.nan]], dtype=np.float32)
    y = np.array([0, 0, 1, 1, 1, 1])
    clf = DecisionTreeClassifier(max_depth=1, random_state=0).fit(x, y)
    tree = models.from_sklearn(clf, ["a", "b"], ["f"])
    assert not tree.missing_left[0]  # los NaN eran de la clase 1: van con 3 y 4 (a la derecha)
    assert tree.predict(np.array([[np.nan]], dtype=np.float32))[0] == 1


def _supported(groups_a: int, groups_b: int) -> tuple[np.ndarray, ...]:
    """Una clase 1 sostenida por `groups_a` variantes y otra región (clase 2) por `groups_b`."""
    rows, y, g = [], [], []
    for v in range(20):  # fondo: clase 0 en 20 variantes
        rows += [[0.0]] * 30
        y += [0] * 30
        g += [v] * 30
    for k, (value, label, n_groups) in enumerate(((1.0, 1, groups_a), (2.0, 2, groups_b))):
        for v in range(n_groups):
            rows += [[value]] * 10
            y += [label] * 10
            g += [100 * (k + 1) + v] * 10
    x = np.array(rows, dtype=np.float32)
    t = np.concatenate([np.arange(30)] * 20 + [np.arange(10)] * (groups_a + groups_b))
    return x, np.array(y), np.array(g), t.astype(np.float32)


def test_leaves_with_fewer_than_five_variants_are_collapsed() -> None:
    x, y, g, t = _supported(groups_a=8, groups_b=2)
    clf = DecisionTreeClassifier(max_depth=4, random_state=0).fit(x, y)
    tree = models.from_sklearn(clf, ["n", "a", "b"], ["f"])
    assert len(tree.leaves()) == 3
    collapsed = tree.prune_unsupported(x, y, g, t)
    assert collapsed >= 1
    assert all(tree.support[leaf] >= models.MIN_VARIANTS for leaf in tree.leaves() if leaf != 0)
    assert 2 not in tree.predict(np.array([[2.0]], dtype=np.float32))  # la clase de 2 variantes


def test_the_audit_counts_instants_variants_and_episodes_per_leaf() -> None:
    x, y, g, t = _supported(groups_a=6, groups_b=6)
    clf = DecisionTreeClassifier(max_depth=4, random_state=0).fit(x, y)
    tree = models.from_sklearn(clf, ["n", "a", "b"], ["f"])
    tree.audit(x, y, g, t)
    leaf = int(tree.apply(np.array([[1.0]], dtype=np.float32))[0])
    assert tree.counts[leaf, 1] == 60 and tree.support[leaf] == 6 and tree.episodes[leaf] == 6
    assert tree.purity(leaf) == 1.0


def test_scores_and_bootstrap_by_variant() -> None:
    y_true = np.array([0, 0, 1, 1, 0, 1, 1, 0])
    groups = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    perfect = models.confusion_by_variant(y_true, y_true, groups, 2)
    assert models.scores(sum(perfect.values()))["macro_f1"] == 1.0
    wrong = models.confusion_by_variant(y_true, 1 - y_true, groups, 2)
    assert models.scores(sum(wrong.values()))["macro_f1"] == 0.0
    masked = models.confusion_by_variant(np.array([-1, 0, 1]), np.array([0, 0, 1]), np.zeros(3), 2)
    assert sum(masked.values()).sum() == 2  # `n/a` y `?` no cuentan
    ci = models.bootstrap(perfect, n_boot=50)
    assert ci["macro_f1"].tolist() == [1.0, 1.0]
    unsure = dict(zip(range(6), [perfect[0], wrong[0]] * 3, strict=True))
    lo, hi = models.bootstrap(unsure, n_boot=200)["macro_f1"]
    assert lo < 0.5 < hi


def test_no_feature_is_the_time_the_variant_or_the_scenario() -> None:
    forbidden = {"t", "time", "variant", "name", "scenario", "seed", "index", "leg"}
    assert not forbidden & set(FEATURES)
    assert len(FEATURES) == len(set(FEATURES))


def test_a_tree_trained_on_a_subset_of_columns_predicts_with_the_full_matrix() -> None:
    x, y = _data()
    cols = [3, 1]  # solo dos de las cuatro columnas, en otro orden
    clf = DecisionTreeClassifier(max_depth=3, random_state=0).fit(x[:, cols], y)
    tree = models.from_sklearn(clf, ["a", "b", "c", "d"], ["f0", "f1", "f2", "f3"], cols)
    assert (tree.predict(x) == clf.predict(x[:, cols])).all()
    assert {tree.features[i] for i in tree.feature if i >= 0} <= {"f3", "f1"}
    one = DecisionTreeClassifier(max_depth=2, random_state=0).fit(x[:, [2]], y)  # una sola columna
    assert (
        models.from_sklearn(one, list("abcd"), ["f0", "f1", "f2", "f3"], [2]).predict(x)
        == one.predict(x[:, [2]])
    ).all()
