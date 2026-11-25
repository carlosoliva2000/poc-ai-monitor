"""E7b, paso 2b: las entradas permitidas de cada faceta con su justificación, marcando cuáles usa
de verdad la tabla elegida.

    uv run --project ai-module-py --group train python tools/training/report_inputs.py [DATASET]
"""

# ruff: noqa: E501

import pickle
import sys
from pathlib import Path

from allowed import ALLOWED
from features import DEFAULT_DATASET


def main() -> int:
    v2 = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET.parent / "e7b-v2"
    trees = pickle.loads((v2 / "models" / "trees.pkl").read_bytes())  # noqa: S301
    lines = ["# Entradas permitidas por faceta (e7b-v2)", "",
             "Cada árbol solo puede usar su lista. «Usada» = aparece en alguna fila de la tabla elegida.", ""]  # fmt: skip
    for facet, entries in ALLOWED.items():
        used = set()
        if facet in trees:
            tree = trees[facet]
            used = {
                tree.features[tree.feature[n]] for n in _internal(tree)
            }  # solo el árbol alcanzable
        lines += [
            f"## {facet}",
            "",
            "| Característica | Usada | Por qué informa de esta faceta |",
            "|---|---|---|",
        ]
        for name, why in entries:
            lines.append(f"| `{name}` | {'sí' if name in used else ''} | {why} |")
        lines.append("")
    out = v2 / "report" / "inputs.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


def _internal(tree) -> list[int]:  # noqa: ANN001
    out, stack = [], [0]
    while stack:
        n = stack.pop()
        if not tree.is_leaf(n):
            out.append(n)
            stack += [int(tree.left[n]), int(tree.right[n])]
    return out


if __name__ == "__main__":
    sys.exit(main())
