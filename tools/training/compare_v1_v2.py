"""E7b, paso 2b: las tablas de e7b-v2 frente a las de e7b-v1 y al bosque, en el conjunto de prueba
de v2 y en la **prueba de generalización** (drones y sensores fuera de los rangos de entrenamiento).

    uv run --project ai-module-py --group train python tools/training/compare_v1_v2.py [ANTERIOR NUEVO GEN]

La prueba de generalización (`e7b-gen`) no se usa para decidir nada: solo para medir. Las tablas de
v1 se evalúan con las mismas características (el extractor conserva sus columnas absolutas) y las de
v2 con su lista de entradas permitidas. El bosque es el de v2, con las mismas entradas que su
tabla. F1 macro con IC 95 % por bootstrap de variantes. Escribe `<v2>/report/generalization.md`.
"""

# ruff: noqa: E501  (líneas largas de las tablas en Markdown del informe)

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml
from allowed import columns
from features import DEFAULT_DATASET, load
from models import bootstrap, confusion_by_variant, scores
from tree_to_table import CANDIDATES, candidates_path, table_predict

from ai_module.decision.table import load_tables
from poc_contracts.states import FACETS

EXP = DEFAULT_DATASET.parent
SUBSETS = ("environment.wind", "drone.situation", "drone.cause", "drone.mode")


def predictions(facet, x, names, tables, forests):  # noqa: ANN001, ANN201
    """Las tres predicciones de una faceta: tabla v1, tabla v2 y bosque v2."""
    return {
        "v1": table_predict(tables["v1"], facet, x, names),
        "v2": table_predict(tables["v2"], facet, x, names),
        "forest": forests[facet].predict(x[:, columns(facet, names)]),
    }


def variant_airspeed(dataset: Path, variants: np.ndarray) -> dict[int, float]:
    index = json.loads((dataset / "index.json").read_text(encoding="utf-8"))
    out = {}
    for v in variants:
        a = yaml.safe_load(
            (dataset / "variants" / index[int(v)]["name"] / "assets.yaml").read_text(
                encoding="utf-8"
            )
        )
        out[int(v)] = a["drone"]["max_airspeed_mps"]
    return out


def cell(conf: dict) -> str:
    total = sum(conf.values())
    s, ci = scores(total), bootstrap(conf, n_boot=300)
    return f"{s['macro_f1']:.3f} [{ci['macro_f1'][0]:.3f}, {ci['macro_f1'][1]:.3f}]"


def main() -> int:
    args = [Path(a).resolve() for a in sys.argv[1:]]
    old, v2, gen = args if len(args) == 3 else (None, EXP / "e7b-v2", EXP / "e7b-gen")
    trees = pickle.loads((v2 / "models" / "trees.pkl").read_bytes())  # noqa: S301
    forests = {
        f: pickle.loads((v2 / "models" / "forests" / f"{f}.pkl").read_bytes()) for f in trees
    }  # noqa: S301
    old_name, new_name = (old.name if old else "e7b-v1"), v2.name
    situation = v2 / "report" / "situation.json"
    rule = json.loads(situation.read_text(encoding="utf-8"))["cells"] if situation.exists() else {}
    tables = {
        "v1": load_tables(candidates_path(old) if old else CANDIDATES),
        "v2": load_tables(candidates_path(v2)),
    }
    lines = ["# E7b · Tablas nuevas frente a las anteriores y al bosque", "",
             f"F1 macro con IC 95 % por bootstrap de variantes. **Prueba**: partición de prueba de "
             f"{new_name} (dentro de los rangos de entrenamiento). **Generalización**: {gen.name}, con "
             "`max_airspeed` de 8 y de 28 m/s, σ de los sensores, periodos y C/N0 y AGC nominales fuera de esos rangos "
             "(no se usa para decidir nada). Las tablas anteriores se evalúan con las mismas "
             "características; las de v2 y el bosque, con su lista de entradas permitidas.", ""]  # fmt: skip
    summary: dict = {}
    for title, dataset in ((f"Prueba de {new_name}", v2), (f"Generalización ({gen.name})", gen)):
        data = load(dataset, "test")
        names = [str(f) for f in data["features"]]
        lines += [
            f"## {title}",
            "",
            f"| Faceta | Tabla {old_name} | Tabla {new_name} | Bosque {new_name} | nueva − anterior |",
            "|---|---|---|---|---|",
        ]
        air = variant_airspeed(dataset, np.unique(data["variant"])) if dataset == gen else {}
        extra: list[str] = []
        for facet in trees:
            j = list(FACETS).index(facet)
            keep = data["y"][:, j] >= 0
            x, y, g = data["x"][keep], data["y"][keep, j].astype(np.int32), data["variant"][keep]
            pred = predictions(facet, x, names, tables, forests)
            confs = {k: confusion_by_variant(y, p, g, len(FACETS[facet])) for k, p in pred.items()}
            f1 = {k: scores(sum(c.values()))["macro_f1"] for k, c in confs.items()}
            lines.append(f"| {facet} | {cell(confs['v1'])} | {cell(confs['v2'])} | {cell(confs['forest'])} | "
                         f"{f1['v2'] - f1['v1']:+.3f} |")  # fmt: skip
            split = "test" if dataset == v2 else "gen"
            if facet == "drone.situation" and split in rule:  # la regla determinista, aparte
                cells = rule[split]
                lines.append(f"| drone.situation (regla determinista) | {cell(confs['v1'])} | {cells['Regla determinista']} | "
                             f"{cells['Bosque (solo geometría)']} | |")  # fmt: skip
            summary.setdefault(title, {})[facet] = f1
            if air and facet in SUBSETS:
                for name, pick in (("8 m/s", lambda a: a < 15), ("28 m/s", lambda a: a >= 15)):
                    sub = {
                        k: {v: m for v, m in c.items() if pick(air[v])} for k, c in confs.items()
                    }
                    extra.append(f"| {facet} | {name} | {cell(sub['v1'])} | {cell(sub['v2'])} | {cell(sub['forest'])} |")  # fmt: skip
        if extra:
            lines += ["", "**Por velocidad máxima del dron (solo la generalización):**", "",
                      f"| Faceta | `max_airspeed` | Tabla {old_name} | Tabla {new_name} | Bosque {new_name} |", "|---|---|---|---|---|", *extra]  # fmt: skip
        lines.append("")
    out = v2 / "report" / "generalization.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (v2 / "report" / "generalization.json").write_text(
        json.dumps(summary, indent=1, default=float), "utf-8"
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
