"""E7b, paso 2: resumen en Markdown de `report/step2.json` (métricas de prueba con IC 95 % por
bootstrap de variantes, árbol frente a bosque y tabla a mano).

    uv run --project ai-module-py --group train python tools/training/report_step2.py
"""

import json
import pickle
import sys
from pathlib import Path

from features import DEFAULT_DATASET

SPLIT_KEYS = (("tree", "Árbol"), ("forest", "Bosque"), ("hand", "Tabla a mano"))


def cell(entry: dict, key: str) -> str:
    if key not in entry:
        return "—"
    s = entry[key]
    lo, hi = s["macro_f1_ci"]
    return f"{s['macro_f1']:.3f} [{lo:.3f}, {hi:.3f}]"


def main() -> int:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    report = json.loads((dataset / "report" / "step2.json").read_text(encoding="utf-8"))
    trees = pickle.loads((dataset / "models" / "trees.pkl").read_bytes())  # noqa: S301
    lines = [
        "# Paso 2 · árboles por faceta: F1 macro en la partición de prueba",
        "",
        "Intervalo de confianza del 95 % por bootstrap de variantes (400 remuestreos). "
        "`Hojas` y `prof.`: del árbol elegido en validación. `Mín. variantes` y `Mín. rachas`: "
        "el mínimo por hoja de cuántas variantes y cuántas rachas seguidas de su clase la "
        "sostienen en el entrenamiento (la poda exige al menos 5 variantes).",
        "",
        "| Faceta | Hojas | Prof. | Mín. variantes | Mín. rachas | Árbol | Bosque | Tabla a mano |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for facet, e in report["facets"].items():
        if "tree_test" not in e:
            lines.append(f"| {facet} | — | — | — | — | (sin entrenar: {e.get('skipped')}) | | |")
            continue
        tree = trees[facet]
        leaves = tree.leaves()
        support = min(int(tree.support[leaf]) for leaf in leaves)
        episodes = min(int(tree.episodes[leaf]) for leaf in leaves)
        lines.append(
            f"| {facet} | {e['n_leaves']} | {e['depth']} | {support} | {episodes} | "
            f"{cell(e, 'tree_test')} | {cell(e, 'forest_test')} | {cell(e, 'hand_test')} |"
        )
    lines += ["", "## Validación (con la que se eligió cada árbol)", "",
              "| Faceta | Árbol | Bosque | Tabla a mano |", "|---|---|---|---|"]  # fmt: skip
    for facet, e in report["facets"].items():
        if "tree_validation" in e:
            lines.append(
                f"| {facet} | {cell(e, 'tree_validation')} | {cell(e, 'forest_validation')} | "
                f"{cell(e, 'hand_validation')} |"
            )
    head = "| Faceta | Clase | Soporte (instantes) | F1 | IC 95 % | Exhaustividad | Precisión |"
    lines += [
        "",
        "## F1 por clase en prueba (árbol, con IC 95 %)",
        "",
        head,
        "|---|---|---|---|---|---|---|",
    ]
    for facet, e in report["facets"].items():
        if "tree_test" not in e:
            continue
        s = e["tree_test"]
        for i, name in enumerate(e["classes"]):
            if s["support"][i]:
                lo, hi = s["f1_ci"][i]
                lines.append(
                    f"| {facet} | {name} | {int(s['support'][i])} | {s['f1'][i]:.3f} | "
                    f"[{lo:.3f}, {hi:.3f}] | {s['recall'][i]:.3f} | {s['precision'][i]:.3f} |"
                )
    lines += ["", "## Rejilla de árboles (profundidad × `ccp_alpha`)", ""]
    for facet, e in report["facets"].items():
        if "candidates" in e:
            lines.append(f"**{facet}** (elegido: profundidad {e['chosen']['depth']}, "
                         f"`ccp_alpha` {e['chosen']['alpha']})\n")  # fmt: skip
            head = (
                "| Prof. | `ccp_alpha` | Hojas antes de podar | Colapsos | Hojas | F1 macro val. |"
            )
            lines += [head, "|---|---|---|---|---|---|"]
            for c in e["candidates"]:
                row = [c["depth"], c["alpha"], c["leaves_before"], c["collapsed"], c["leaves"]]
                lines.append(
                    "| " + " | ".join(str(v) for v in row) + f" | {c['val_macro_f1']:.3f} |"
                )
            lines.append("")
    out = dataset / "report" / "step2.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
