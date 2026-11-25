"""E7b, paso 2: un árbol CART por faceta, un bosque de referencia y la tabla a mano, con métricas
de validación y de prueba (con intervalo de confianza por bootstrap de variantes).

    uv run --project ai-module-py --group train python tools/training/train.py [--dataset D]

Para cada faceta: entrenamiento con todos los instantes (con `CAP_TREE` se submuestrea, **solo en
entrenamiento**; validación y prueba van siempre enteras; con 40 000 por clase empeoraba
`gps.integrity` en validación, de 0,981 a 0,967), `class_weight="balanced"`, profundidad y
`ccp_alpha` de una rejilla, poda posterior de las hojas que no sostienen al menos 5 variantes (la
auditoría usa todo el entrenamiento, no el submuestreo) y elección en validación (F1 macro; entre
los que se quedan a menos de 0,01 del mejor, el de menos hojas). Guarda los árboles en
`<dataset>/models/trees.pkl` y las métricas en `<dataset>/report/step2.json`.
"""

import argparse
import json
import pickle
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from allowed import columns
from features import DEFAULT_DATASET, load
from hand_tables import HAND_FACETS, predict_split
from models import Tree, bootstrap, confusion_by_variant, from_sklearn, scores
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier

from poc_contracts.states import FACETS

CAP_TREE = None  # tope de instantes por clase del árbol (solo entrenamiento); None = todos
CAP_FOREST = 100_000
DEPTHS = (4, 5, 6)
ALPHAS = (0.0, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3)
MIN_LEAF = (
    100  # instantes por hoja (en el submuestreo); las hojas con menos de 5 variantes se podan
)
TOLERANCE = 0.01
SEED = 7011
COMPARE_FULL = ["gps.integrity", "drone.cause", "link.quality"]
DATA: dict[str, dict[str, np.ndarray]] = {}
FOREST_DIR = Path(".")


def facet_arrays(split: str, j: int) -> tuple[np.ndarray, ...]:
    d = DATA[split]
    keep = d["y"][:, j] >= 0
    return d["x"][keep], d["y"][keep, j].astype(np.int32), d["variant"][keep], d["t"][keep]


def subsample(y: np.ndarray, cap: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    picked = []
    for c in np.unique(y):
        idx = np.nonzero(y == c)[0]
        picked.append(idx if len(idx) <= cap else rng.choice(idx, cap, replace=False))
    return np.sort(np.concatenate(picked))


def fit_tree(x, y, depth: int, alpha: float, classes: list[str], features: list[str], cols) -> Tree:  # noqa: ANN001
    clf = DecisionTreeClassifier(
        max_depth=depth, min_samples_leaf=MIN_LEAF, ccp_alpha=alpha,
        class_weight="balanced", random_state=SEED,
    )  # fmt: skip
    return from_sklearn(clf.fit(x[:, cols], y), classes, features, cols)


def macro_f1(tree: Tree, x, y, groups) -> float:  # noqa: ANN001
    conf = confusion_by_variant(y, tree.predict(x), groups, len(tree.classes))
    return float(scores(sum(conf.values()))["macro_f1"])  # type: ignore[arg-type]


def work(j: int) -> dict:
    """Todo lo de una faceta: rejilla de árboles, elegido, bosque y sus matrices de confusión."""
    facet = list(FACETS)[j]
    classes = list(FACETS[facet])
    features = [str(f) for f in DATA["train"]["features"]]
    cols = columns(facet, features)  # solo las entradas permitidas de la faceta
    x, y, g, t = facet_arrays("train", j)
    xv, yv, gv, _ = facet_arrays("validation", j)
    xt, yt, gt, _ = facet_arrays("test", j)
    t0 = time.perf_counter()
    result: dict = {"facet": facet, "classes": classes, "train_rows": len(y)}
    if len(np.unique(y)) < 2:
        return {**result, "skipped": "una sola clase en entrenamiento"}
    sample = np.arange(len(y)) if CAP_TREE is None else subsample(y, CAP_TREE, SEED + j)
    candidates = []
    for depth in DEPTHS:
        for alpha in ALPHAS:
            tree = fit_tree(x[sample], y[sample], depth, alpha, classes, features, cols)
            leaves_before = len(tree.leaves())
            collapsed = tree.prune_unsupported(x, y, g, t)
            candidates.append({
                "depth": depth, "alpha": alpha, "tree": tree, "leaves_before": leaves_before,
                "collapsed": collapsed, "leaves": len(tree.leaves()),
                "val_macro_f1": macro_f1(tree, xv, yv, gv),
            })  # fmt: skip
    best = max(c["val_macro_f1"] for c in candidates)
    ok = [c for c in candidates if c["val_macro_f1"] >= best - TOLERANCE]
    chosen = min(ok, key=lambda c: (c["leaves"], c["depth"], -c["val_macro_f1"]))
    tree: Tree = chosen["tree"]
    result["candidates"] = [{k: v for k, v in c.items() if k != "tree"} for c in candidates]
    result["chosen"] = {k: v for k, v in chosen.items() if k != "tree"}
    result["tree"] = tree
    n = len(classes)
    result["conf"] = {
        "tree_validation": confusion_by_variant(yv, tree.predict(xv), gv, n),
        "tree_test": confusion_by_variant(yt, tree.predict(xt), gt, n),
    }
    forest = RandomForestClassifier(
        n_estimators=100, min_samples_leaf=20, max_features="sqrt",
        class_weight="balanced_subsample", n_jobs=1, random_state=SEED,
    )  # fmt: skip
    fs = subsample(y, CAP_FOREST, SEED + 100 + j)
    forest.fit(x[fs][:, cols], y[fs])  # el bosque, con las mismas entradas permitidas
    with (FOREST_DIR / f"{facet}.pkl").open("wb") as handle:  # no se devuelve: pesa mucho
        pickle.dump(forest, handle)
    for name, xs, ys, gs in (("validation", xv, yv, gv), ("test", xt, yt, gt)):
        result["conf"][f"forest_{name}"] = confusion_by_variant(
            ys, forest.predict(xs[:, cols]), gs, n
        )
    result["seconds"] = round(time.perf_counter() - t0, 1)
    return result


def compare_full(j: int, chosen: dict) -> dict:
    """El mismo árbol (profundidad y `ccp_alpha` elegidos) con todo el entrenamiento, sin
    submuestrear, para ver que el submuestreo no empeora la validación."""
    facet = list(FACETS)[j]
    classes = list(FACETS[facet])
    features = [str(f) for f in DATA["train"]["features"]]
    x, y, g, t = facet_arrays("train", j)
    xv, yv, gv, _ = facet_arrays("validation", j)
    tree = fit_tree(
        x, y, chosen["depth"], chosen["alpha"], classes, features, columns(facet, features)
    )
    tree.prune_unsupported(x, y, g, t)
    return {"facet": facet, "full_val_macro_f1": macro_f1(tree, xv, yv, gv),
            "full_leaves": len(tree.leaves())}  # fmt: skip


def summarize(by_variant: dict) -> dict:
    s = scores(sum(by_variant.values()))
    ci = bootstrap(by_variant)
    return {
        "macro_f1": s["macro_f1"], "macro_f1_ci": ci["macro_f1"].tolist(),
        "accuracy": s["accuracy"], "accuracy_ci": ci["accuracy"].tolist(),
        "f1": np.round(s["f1"], 4).tolist(), "f1_ci": np.round(ci["f1"], 4).T.tolist(),
        "recall": np.round(s["recall"], 4).tolist(),
        "precision": np.round(s["precision"], 4).tolist(),
        "support": s["support"].tolist(),
    }  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--compare-full", nargs="*", default=["gps.integrity", "drone.cause", "link.quality"]
    )
    args = parser.parse_args()
    for split in ("train", "validation", "test"):
        DATA[split] = load(args.dataset, split)
    out = args.dataset / "report"
    global FOREST_DIR
    FOREST_DIR = args.dataset / "models" / "forests"
    FOREST_DIR.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    with Pool(args.workers) as pool:
        results = pool.map(work, range(len(FACETS)), chunksize=1)
    print(f"árboles y bosques: {time.perf_counter() - t0:.0f} s", flush=True)

    # Tabla a mano (4 facetas) en validación y prueba.
    hand = {}
    for split in ("validation", "test"):
        pred = predict_split(args.dataset, DATA[split])
        for k, facet in enumerate(HAND_FACETS):
            j = list(FACETS).index(facet)
            d = DATA[split]
            hand[(facet, split)] = confusion_by_variant(
                d["y"][:, j], pred[:, k], d["variant"], len(FACETS[facet])
            )
    full = {}
    for facet in args.compare_full:
        j = list(FACETS).index(facet)
        res = next(r for r in results if r["facet"] == facet)
        full[facet] = compare_full(j, res["chosen"])

    report: dict = {"facets": {}, "full_vs_subsample": full}
    trees: dict[str, Tree] = {}
    for r in results:
        facet = r["facet"]
        entry = {k: v for k, v in r.items() if k not in ("tree", "conf")}
        if "tree" in r:
            trees[facet] = r["tree"]
            entry["depth"], entry["n_leaves"] = r["tree"].depth(), len(r["tree"].leaves())
            for key, conf in r["conf"].items():
                entry[key] = summarize(conf)
            if (facet, "test") in hand:
                entry["hand_validation"] = summarize(hand[(facet, "validation")])
                entry["hand_test"] = summarize(hand[(facet, "test")])
        report["facets"][facet] = entry
    with (args.dataset / "models" / "trees.pkl").open("wb") as handle:
        pickle.dump(trees, handle)
    (out / "step2.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    print(f"total {time.perf_counter() - t0:.0f} s -> {out / 'step2.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
