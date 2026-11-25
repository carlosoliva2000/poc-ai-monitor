"""E7b: el árbol de decisión como estructura propia (sale de scikit-learn y se poda por episodios)
y las métricas por episodio con intervalos de confianza por bootstrap.

El árbol que se ejecuta y se convierte en tabla es este (no el de scikit-learn): tiene los mismos
nodos, umbrales y lado de los valores que faltan, más lo que hace falta para auditarlo (cuántos
instantes de entrenamiento, de qué clase y de cuántas variantes distintas sostienen cada hoja).
"""

from dataclasses import dataclass, field

import numpy as np

MIN_VARIANTS = 5  # una hoja la tienen que sostener al menos 5 variantes (episodios) distintos
MIN_INSTANTS = 3  # y una variante cuenta si aporta al menos 3 instantes de la clase de la hoja


@dataclass
class Tree:
    """Nodos en arrays (como `sklearn.tree._tree.Tree`). `feature` = -1 en las hojas."""

    feature: np.ndarray
    threshold: np.ndarray
    left: np.ndarray
    right: np.ndarray
    missing_left: np.ndarray  # a qué hijo van los NaN en cada nodo
    label: np.ndarray  # clase de cada nodo si fuera hoja (la de mayor peso con el peso por clase)
    classes: list[str]
    features: list[str]
    counts: np.ndarray = field(default=None)  # type: ignore[assignment]  # (nodos, clases)
    support: np.ndarray = field(default=None)  # type: ignore[assignment]  # variantes por hoja
    episodes: np.ndarray = field(default=None)  # type: ignore[assignment]  # rachas por hoja

    @property
    def n_nodes(self) -> int:
        return len(self.feature)

    def is_leaf(self, node: int) -> bool:
        return self.feature[node] < 0

    def leaves(self) -> list[int]:
        """Hojas alcanzables desde la raíz, en orden de izquierda a derecha."""
        out, stack = [], [0]
        while stack:
            n = stack.pop()
            if self.is_leaf(n):
                out.append(n)
            else:
                stack += [self.right[n], self.left[n]]
        return out

    def depth(self) -> int:
        def walk(n: int) -> int:
            return 0 if self.is_leaf(n) else 1 + max(walk(self.left[n]), walk(self.right[n]))

        return walk(0)

    def apply(self, x: np.ndarray) -> np.ndarray:
        """La hoja a la que llega cada fila (los NaN van por `missing_left`)."""
        node = np.zeros(len(x), dtype=np.int32)
        while True:
            idx = np.nonzero(self.feature[node] >= 0)[0]
            if len(idx) == 0:
                return node
            at = node[idx]
            value = x[idx, self.feature[at]]
            go_left = np.where(np.isnan(value), self.missing_left[at], value <= self.threshold[at])
            node[idx] = np.where(go_left, self.left[at], self.right[at])

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.label[self.apply(x)]

    def purity(self, leaf: int) -> float:
        """Fracción de los instantes de entrenamiento de la hoja que son de su clase."""
        total = self.counts[leaf].sum()
        return float(self.counts[leaf, self.label[leaf]] / total) if total else 0.0

    # --- Auditoría y poda -------------------------------------------------------------------

    def parents(self) -> np.ndarray:
        parent = np.full(self.n_nodes, -1, dtype=np.int32)
        for n in range(self.n_nodes):
            if self.feature[n] >= 0:
                parent[self.left[n]] = parent[self.right[n]] = n
        return parent

    def audit(self, x: np.ndarray, y: np.ndarray, groups: np.ndarray, t: np.ndarray) -> None:
        """Rellena `counts` (instantes de entrenamiento por clase en cada hoja), `support`
        (variantes distintas que aportan `MIN_INSTANTS` instantes o más de la clase de la hoja) y
        `episodes` (rachas seguidas de esa clase en esa hoja). `x`, `y`, `groups` y `t` van
        ordenados por variante y tiempo, con `y` ya sin las filas enmascaradas."""
        leaf = self.apply(x)
        n_classes = len(self.classes)
        self.counts = np.zeros((self.n_nodes, n_classes), dtype=np.int64)
        np.add.at(self.counts, (leaf, y), 1)
        own = y == self.label[leaf]
        pairs, n = np.unique(np.stack([leaf[own], groups[own]]), axis=1, return_counts=True)
        self.support = np.bincount(pairs[0][n >= MIN_INSTANTS], minlength=self.n_nodes)
        prev_same = np.zeros(len(x), dtype=bool)  # la fila anterior es de la misma racha
        prev_same[1:] = (leaf[1:] == leaf[:-1]) & (groups[1:] == groups[:-1]) & own[:-1]
        prev_same[1:] &= (t[1:] - t[:-1]) <= 1.5
        starts = own & ~prev_same
        self.episodes = np.bincount(leaf[starts], minlength=self.n_nodes)

    def prune_unsupported(
        self, x: np.ndarray, y: np.ndarray, groups: np.ndarray, t: np.ndarray
    ) -> int:
        """Colapsa en su padre las hojas con menos de `MIN_VARIANTS` variantes distintas (el
        padre pasa a ser hoja, con su clase de mayor peso) hasta que no quede ninguna. Devuelve
        cuántos colapsos hizo."""
        collapsed = 0
        while True:
            self.audit(x, y, groups, t)
            weak = [n for n in self.leaves() if n != 0 and self.support[n] < MIN_VARIANTS]
            if not weak:
                return collapsed
            parent = self.parents()
            for node in weak:
                p = parent[node]
                if self.feature[p] >= 0:
                    self.feature[p] = -1
                    collapsed += 1
            if self.is_leaf(0):
                self.audit(x, y, groups, t)
                return collapsed


def from_sklearn(clf, classes: list[str], features: list[str], columns=None) -> Tree:  # noqa: ANN001
    """Copia un `DecisionTreeClassifier` entrenado. Las clases de `clf.classes_` son códigos de
    `classes`; el nodo dice la clase de mayor peso (con el peso por clase del entrenamiento).
    Si el árbol se entrenó con un subconjunto de columnas (`columns`: sus índices en `features`),
    los nodos se reescriben con los índices de la matriz completa."""
    t = clf.tree_
    # las hojas de scikit-learn llevan `feature = -2`: se pasan por 0 antes de mapear las columnas
    mapped = t.feature if columns is None else np.asarray(columns)[np.maximum(t.feature, 0)]
    value = t.value[:, 0, :]
    label = np.asarray(clf.classes_)[value.argmax(axis=1)].astype(np.int32)
    return Tree(
        feature=np.where(t.children_left < 0, -1, mapped).astype(np.int32),
        threshold=t.threshold.astype(np.float64),
        left=t.children_left.astype(np.int32),
        right=t.children_right.astype(np.int32),
        missing_left=t.missing_go_to_left.astype(bool),
        label=label,
        classes=classes,
        features=features,
    )


# --- Métricas por episodio ---------------------------------------------------------------------


def confusion_by_variant(
    y_true: np.ndarray, y_pred: np.ndarray, groups: np.ndarray, n_classes: int
) -> dict[int, np.ndarray]:
    """Matriz de confusión de cada variante. Las filas enmascaradas (`y_true` < 0) no cuentan; una
    predicción fuera de las clases (`y_pred` < 0, p. ej. `?` de una tabla) va a la columna extra."""
    keep = y_true >= 0
    yt, yp, g = y_true[keep], np.where(y_pred[keep] < 0, n_classes, y_pred[keep]), groups[keep]
    out: dict[int, np.ndarray] = {}
    for variant in np.unique(g):
        sel = g == variant
        m = np.zeros((n_classes, n_classes + 1), dtype=np.int64)
        np.add.at(m, (yt[sel], yp[sel]), 1)
        out[int(variant)] = m
    return out


def scores(conf: np.ndarray) -> dict[str, np.ndarray | float]:
    """Precisión, exhaustividad y F1 por clase y F1 macro (solo las clases con soporte)."""
    n = conf.shape[0]
    tp = np.diag(conf[:, :n]).astype(float)
    support = conf.sum(axis=1).astype(float)
    predicted = conf[:, :n].sum(axis=0).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        recall = np.where(support > 0, tp / support, np.nan)
        precision = np.where(predicted > 0, tp / predicted, 0.0)
        f1 = np.where(support > 0, 2 * precision * recall / (precision + recall), np.nan)
        f1 = np.where(np.isnan(f1) & (support > 0), 0.0, f1)
    return {
        "recall": recall, "precision": precision, "f1": f1, "macro_f1": float(np.nanmean(f1)),
        "accuracy": float(tp.sum() / support.sum()) if support.sum() else float("nan"),
        "support": support,
    }  # fmt: skip


def bootstrap(
    by_variant: dict[int, np.ndarray], n_boot: int = 400, seed: int = 0
) -> dict[str, np.ndarray]:
    """Intervalo de confianza del 95 % por bootstrap **de variantes** (episodios): se remuestrean
    las variantes con reemplazo y se recalculan el F1 macro, la exactitud y el F1 de cada clase."""
    keys = sorted(by_variant)
    stack = np.stack([by_variant[k] for k in keys])
    rng = np.random.default_rng(seed)
    macro, acc, per_class = [], [], []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        s = scores(stack[pick].sum(axis=0))
        macro.append(s["macro_f1"])
        acc.append(s["accuracy"])
        per_class.append(s["f1"])
    q = lambda a: np.nanpercentile(a, [2.5, 97.5], axis=0)  # noqa: E731
    return {"macro_f1": q(macro), "accuracy": q(acc), "f1": q(per_class)}
