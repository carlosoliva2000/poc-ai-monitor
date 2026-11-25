"""E7b, paso 1: recuento de instantes y de episodios por faceta y estado en cada partición.

    uv run --project platform python tools/training/counts.py [--dataset D]

Los instantes con etiqueta `n/a` o `?` no cuentan (van enmascarados al entrenar y evaluar). Un
episodio es una racha seguida de un mismo estado en una variante. Escribe `counts.json` y
`counts.md` en la carpeta del conjunto y avisa de los estados anómalos por debajo del mínimo del
manifiesto.
"""

import argparse
import gzip
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform" / "src"))

from poc_contracts.states import FACETS, NOT_APPLICABLE, NOT_OBSERVABLE  # noqa: E402

SPLITS = ("train", "validation", "test")
NORMAL = {"normal", "good", "reliable", "connected", "sufficient", "calm", "mission", "on_route"}


def read_states(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line)["facets"] for line in handle]


def count_variant(rows: list[dict[str, str]]) -> dict[str, dict[str, list[int]]]:
    """`{faceta: {estado: [instantes, episodios]}}` de una variante."""
    out: dict[str, dict[str, list[int]]] = {f: {} for f in FACETS}
    for facet in FACETS:
        previous = None
        for row in rows:
            state = row[facet]
            if state in (NOT_APPLICABLE, NOT_OBSERVABLE):
                previous = None
                continue
            cell = out[facet].setdefault(state, [0, 0])
            cell[0] += 1
            cell[1] += state != previous
            previous = state
    return out


def count_dataset(dataset: Path) -> dict[str, dict[str, dict[str, list[int]]]]:
    index = json.loads((dataset / "index.json").read_text(encoding="utf-8"))
    total: dict = {s: {f: {} for f in FACETS} for s in SPLITS}
    for meta in index:
        rows = read_states(dataset / "variants" / meta["name"] / "states.jsonl.gz")
        for facet, states in count_variant(rows).items():
            for state, (instants, episodes) in states.items():
                cell = total[meta["split"]][facet].setdefault(state, [0, 0])
                cell[0] += instants
                cell[1] += episodes
    return total


def render(total: dict, minimum: dict[str, int]) -> tuple[str, list[str]]:
    lines = ["# Recuento por faceta y estado (instantes / episodios)", ""]
    lines += ["| Faceta | Estado | " + " | ".join(SPLITS) + " |", "|---|---|---|---|---|"]
    low: list[str] = []
    for facet, states in FACETS.items():
        for state in states:
            cells = []
            for split in SPLITS:
                n, e = total[split][facet].get(state, [0, 0])
                cells.append(f"{n} / {e}")
                anomalous = state not in NORMAL and state != "unexplained"
                if anomalous and e < minimum[split]:
                    low.append(
                        f"{facet}={state} en {split}: {e} episodios (mínimo {minimum[split]})"
                    )
            lines.append(f"| {facet} | {state} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n", low


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=REPO / "experiments" / "e7b" / "e7b-v1")
    args = parser.parse_args()
    manifest = yaml.safe_load((args.dataset / "manifest.yaml").read_text(encoding="utf-8"))
    total = count_dataset(args.dataset)
    text, low = render(total, manifest["min_episodes"])
    (args.dataset / "counts.json").write_text(json.dumps(total, indent=1) + "\n", encoding="utf-8")
    (args.dataset / "counts.md").write_text(text, encoding="utf-8")
    print(text)
    print("\n".join(["Por debajo del mínimo:", *low]) if low else "Todos los mínimos se cumplen.")
    return 0 if not low else 1


if __name__ == "__main__":
    raise SystemExit(main())
