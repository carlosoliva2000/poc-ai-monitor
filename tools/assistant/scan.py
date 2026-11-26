# ruff: noqa: E501
"""Recorre variantes de la E7b con el monitor y anota qué incidentes salen (para elegir cuáles
usar en la revisión de los textos del asistente).

    uv run --project ai-module-py python tools/assistant/scan.py e7b-v3 validation experiments/e7d/scan-v3-val.json
"""

import json
import sys
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "situation"))

from lib import variant_monitor  # noqa: E402

from ai_module.situation.replay import is_world, read_events  # noqa: E402

DATA = REPO / "experiments" / "e7b"


def scan(folder: Path) -> dict:
    monitor = variant_monitor(folder)
    updates = []
    for event in read_events(folder / "events.jsonl.gz"):
        if is_world(event):
            updates += [p for _, p in monitor.push(event)]
    updates += [p for _, p in monitor.flush()]
    meta = json.loads((folder / "meta.json").read_text())
    kinds = [f"{u['kind']}@{u['as_of_sim_time']:.0f}" for u in updates if u["change"] == "opened"]
    return {"name": folder.name, "family": meta["family"], "opened": kinds,
            "anomalies": [a["family"] for a in meta["anomalies"]]}  # fmt: skip


def main() -> None:
    dataset, split, out = sys.argv[1:4]
    index = json.loads((DATA / dataset / "index.json").read_text())
    names = [v["name"] for v in index if v["split"] == split]
    folders = [DATA / dataset / "variants" / n for n in names]
    with Pool(8) as pool:
        rows = pool.map(scan, folders, chunksize=4)
    Path(out).write_text(json.dumps(rows, indent=1))
    print(len(rows), "variants")


if __name__ == "__main__":
    main()
