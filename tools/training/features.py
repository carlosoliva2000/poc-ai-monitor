"""E7b, paso 2: matrices de características y etiquetas por partición.

    uv run --project ai-module-py --group train python tools/training/features.py [--dataset D]

Por cada variante pasa sus eventos del mundo (dominios `air` y `env`) **uno a uno** por el
`FeatureExtractor` del monitor (`ai_module.situation.features`, el mismo código que en directo, con
los `assets.yaml` de la variante) y une cada fila con el estado de `states.jsonl` del mismo segundo.
Entran solo las características; las etiquetas salen de `states.jsonl`; `n/a` y `?` quedan
enmascarados (-1). El nombre de la variante solo se guarda para agrupar por episodios (nunca es una
entrada). Escribe `features/<partición>.npz`.
"""

import argparse
import gzip
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "contracts" / "python" / "src"))

from ai_module.situation.features import (  # noqa: E402
    FEATURES,
    Assets,
    FeatureExtractor,
    load_assets,
)
from ai_module.situation.replay import is_world, read_events  # noqa: E402
from poc_contracts.states import FACETS, NOT_APPLICABLE, NOT_OBSERVABLE  # noqa: E402

DEFAULT_DATASET = REPO / "experiments" / "e7b" / "e7b-v1"
SPLITS = ("train", "validation", "test")
FACET_NAMES = tuple(FACETS)
CODES = {f: {s: i for i, s in enumerate(states)} for f, states in FACETS.items()}


def variant_assets(folder: Path) -> Assets:
    """Los activos de la variante (`assets.yaml`, completo: dron, periodos, σ y receptor)."""
    return load_assets(folder / "assets.yaml")


def read_states(path: Path) -> dict[int, dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = (json.loads(line) for line in handle)
        return {int(r["t"]): r["facets"] for r in rows}


def variant_matrix(folder: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(X, y, t)` de una variante: una fila por segundo con su etiqueta en cada faceta."""
    fx = FeatureExtractor(variant_assets(folder))
    rows = []
    for event in read_events(folder / "events.jsonl.gz"):
        if is_world(event):
            rows += fx.push(event)
    rows += fx.flush()
    states = read_states(folder / "states.jsonl.gz")
    rows = [r for r in rows if int(r.t) in states]
    x = np.array([[np.nan if r.values[f] is None else r.values[f] for f in FEATURES] for r in rows])
    y = np.full((len(rows), len(FACET_NAMES)), -1, dtype=np.int8)
    for i, r in enumerate(rows):
        facets = states[int(r.t)]
        for j, name in enumerate(FACET_NAMES):
            state = facets[name]
            if state not in (NOT_APPLICABLE, NOT_OBSERVABLE):
                y[i, j] = CODES[name][state]
    return x.astype(np.float32), y, np.array([r.t for r in rows], dtype=np.float32)


def _job(args: tuple[Path, str]) -> tuple[str, np.ndarray, np.ndarray, np.ndarray]:
    folder, name = args
    return (name, *variant_matrix(folder))


def build(dataset: Path, workers: int = 4) -> dict[str, Path]:
    index = json.loads((dataset / "index.json").read_text(encoding="utf-8"))
    out = dataset / "features"
    out.mkdir(exist_ok=True)
    order = {m["name"]: i for i, m in enumerate(index)}
    jobs = [(dataset / "variants" / m["name"], m["name"]) for m in index]
    with Pool(workers) as pool:
        results = pool.map(_job, jobs, chunksize=8)
    paths: dict[str, Path] = {}
    for split in SPLITS:
        names = {m["name"] for m in index if m["split"] == split}
        chosen = [r for r in results if r[0] in names]
        if not chosen:  # una partición vacía (la prueba de generalización solo tiene `test`)
            continue
        np.savez_compressed(
            out / f"{split}.npz",
            x=np.concatenate([r[1] for r in chosen]),
            y=np.concatenate([r[2] for r in chosen]),
            t=np.concatenate([r[3] for r in chosen]),
            variant=np.concatenate([np.full(len(r[1]), order[r[0]], np.int32) for r in chosen]),
            features=np.array(FEATURES),
            facets=np.array(FACET_NAMES),
        )
        paths[split] = out / f"{split}.npz"
    return paths


def load(dataset: Path, split: str) -> dict[str, np.ndarray]:
    with np.load(dataset / "features" / f"{split}.npz") as data:
        return {k: data[k] for k in data.files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    t0 = time.perf_counter()
    for split, path in build(args.dataset, args.workers).items():
        data = load(args.dataset, split)
        print(f"{split}: {len(data['x'])} filas × {data['x'].shape[1]} características -> {path}")
    print(f"{time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
