"""E7b: la línea base de las tablas escritas a mano (`situation/tables.yaml`) sobre las variantes.

Pasa los eventos de cada variante por el `SituationMonitor` del vídeo (el mismo código que en
directo) y recoge, en cada segundo, el estado que decide cada una de sus cuatro tablas de faceta.
Los umbrales de esas tablas se midieron sobre `demo` y `nominal`.
"""

import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from features import CODES, variant_assets

from ai_module.situation.facets import HAND_FACET_TABLES, HANDWRITTEN
from ai_module.situation.monitor import SituationMonitor
from ai_module.situation.replay import is_world, read_events

HAND_FACETS = tuple(HAND_FACET_TABLES)  # gps.integrity, link.availability, environment.wind, …


def _variant(folder: Path) -> dict[int, dict[str, str]]:
    monitor = SituationMonitor(tables=HANDWRITTEN)
    monitor.features.assets = variant_assets(folder)
    out: dict[int, dict[str, str]] = {}
    for event in read_events(folder / "events.jsonl.gz"):
        if not is_world(event):
            continue
        for row in monitor.features.push(event):
            monitor.step(row)
            out[int(row.t)] = {f: monitor.last.states[f] for f in HAND_FACETS}
    for row in monitor.features.flush():
        monitor.step(row)
        out[int(row.t)] = {f: monitor.last.states[f] for f in HAND_FACETS}
    return out


def predict_split(dataset: Path, data: dict[str, np.ndarray], workers: int = 4) -> np.ndarray:
    """Matriz (filas, facetas de la tabla a mano) con el código de la clase decidida (-1 = `?`
    o sin decisión), alineada con las filas de `data`."""
    index = json.loads((dataset / "index.json").read_text(encoding="utf-8"))
    variants = [int(v) for v in np.unique(data["variant"])]
    folders = [dataset / "variants" / index[v]["name"] for v in variants]
    with Pool(workers) as pool:
        per_variant = pool.map(_variant, folders, chunksize=4)
    pred = np.full((len(data["x"]), len(HAND_FACETS)), -1, dtype=np.int16)
    for v, states in zip(variants, per_variant, strict=True):
        rows = np.nonzero(data["variant"] == v)[0]
        for r in rows:
            decided = states.get(int(data["t"][r]))
            if decided:
                for j, facet in enumerate(HAND_FACETS):
                    pred[r, j] = CODES[facet].get(decided[facet], -1)
    return pred
