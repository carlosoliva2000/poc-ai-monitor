"""E7b, paso 2c: la regla determinista de la situación del dron frente a la aprendida.

    uv run --project ai-module-py --group train python tools/training/situation_eval.py [V3] [GEN]

- Elige el margen (`MARGIN_K`, veces el error esperado de la posición) **en validación**.
- Compara, en validación, prueba y generalización: la regla, el árbol de e7b-v3 (solo geometría),
  un árbol de referencia con las señales de causa y el bosque de e7b-v3.
- Con el dron de 28 m/s mira cuánto del fallo viene de las esquinas (el dron las abre más y los
  25/15 m son fijos): reparto de los errores por cercanía a un waypoint, desviaciones sin anomalía
  inyectada y reintentos descartados por `unexplained` por velocidad.
Escribe `<v3>/report/situation.md` y `situation.json`.
"""

# ruff: noqa: E501

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import train as trainer
import yaml
from allowed import SITUATION_WITH_CAUSE_SIGNALS, columns
from compare_v1_v2 import cell
from features import DEFAULT_DATASET, load
from models import confusion_by_variant, scores
from tree_to_table import candidates_path, table_predict

from ai_module.decision.table import load_tables
from ai_module.situation.policy import HERE
from ai_module.situation.replay import is_world, read_events
from ai_module.situation.situation_rule import rule_inputs
from poc_contracts.states import FACETS

FACET = "drone.situation"
CLASSES = list(FACETS[FACET])
J = list(FACETS).index(FACET)
STATE_FACETS = ("gps.integrity", "gps.availability", "environment.wind", "drone.mode")
K_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
CORNER_M = 150.0  # «cerca de una esquina»: a menos de esta distancia de un waypoint
RULE = load_tables(HERE / "situation_rule.yaml")["drone_situation_rule"]


def learned_states(tables, data, names):  # noqa: ANN001, ANN201
    """Estado que dan las tablas aprendidas de las facetas que usa la regla, en todas las filas."""
    out = {}
    for facet in STATE_FACETS:
        codes = table_predict(tables, facet, data["x"], names)
        out[facet] = np.array(FACETS[facet])[codes]
    return out


def run_rule(data, states, names, k):  # noqa: ANN001, ANN201
    """La regla segundo a segundo, con la situación anterior como entrada (por variante)."""
    col = {n: names.index(n) for n in ("gps_dev_m", "radar_dev_m", "gps_sigma_m", "radar_sigma_m")}
    x, variant = data["x"], data["variant"]
    pred = np.zeros(len(x), dtype=np.int16)
    previous, last = "on_route", -1
    for i in range(len(x)):
        if variant[i] != last:
            previous, last = "on_route", int(variant[i])
        row = x[i]
        values = {n: (None if np.isnan(row[c]) else float(row[c])) for n, c in col.items()}
        facets = {f: str(states[f][i]) for f in STATE_FACETS}
        previous = str(RULE.evaluate(rule_inputs(values, facets, previous, k)).then["state"])
        pred[i] = CLASSES.index(previous)
    return pred


def conf(data, pred):  # noqa: ANN001, ANN201
    keep = data["y"][:, J] >= 0
    return confusion_by_variant(
        data["y"][keep, J].astype(np.int32), pred[keep], data["variant"][keep], len(CLASSES)
    )


def per_class(by_variant) -> str:  # noqa: ANN001
    s = scores(sum(by_variant.values()))
    return " / ".join(f"{c} {f:.3f}" for c, f in zip(CLASSES, s["f1"], strict=True))


def reference_tree(train, val, names):  # noqa: ANN001, ANN201
    """Árbol con la geometría y las señales de causa (profundidad ≤ 6, poda por episodios)."""
    cols = [names.index(n) for n in SITUATION_WITH_CAUSE_SIGNALS]
    keep = train["y"][:, J] >= 0
    x, y, g, t = (
        train["x"][keep],
        train["y"][keep, J].astype(np.int32),
        train["variant"][keep],
        train["t"][keep],
    )
    kv = val["y"][:, J] >= 0
    found = []
    for depth in (4, 5, 6):
        for alpha in (0.0, 5e-4, 2e-3):
            tree = trainer.fit_tree(x, y, depth, alpha, CLASSES, names, cols)
            tree.prune_unsupported(x, y, g, t)
            vy, vg = val["y"][kv, J].astype(np.int32), val["variant"][kv]
            found.append((trainer.macro_f1(tree, val["x"][kv], vy, vg), tree, depth, alpha))
    top = max(f for f, *_ in found)
    return min(
        (c for c in found if c[0] >= top - trainer.TOLERANCE), key=lambda c: len(c[1].leaves())
    )


def waypoints_and_positions(folder: Path):  # noqa: ANN201
    """Los waypoints (sin la base) y la última posición conocida en cada segundo (estima o radar)."""
    route, pos, last, sec = [], {}, None, 0
    for e in read_events(folder / "events.jsonl.gz"):
        if not is_world(e):
            continue
        p = e["payload"]
        if e["type"] == "MissionPlanned":
            route = [(w["x"], w["y"]) for w in p["waypoints"][1:-1]]
        elif e["type"] == "AutopilotStatus":
            last = (p["est_x"], p["est_y"])
        elif e["type"] == "TrackUpdated":
            last = (p["x"], p["y"])
        sec_now = int(e["sim_time"])
        while sec <= sec_now:
            pos[sec] = last
            sec += 1
    return route, pos


def corner_analysis(dataset: Path, data, pred, index, airspeed):  # noqa: ANN001, ANN201
    """Por grupo de velocidad: reparto de los errores y de las desviaciones por cercanía a esquinas."""
    out = {}
    j_keep = data["y"][:, J]
    for name, pick in (("8 m/s", lambda a: a < 15), ("28 m/s", lambda a: a >= 15)):
        err = near_err = false_dev = near_false = dev_total = dev_free = dev_free_near = 0
        for v in np.unique(data["variant"]):
            if not pick(airspeed[int(v)]):
                continue
            meta = index[int(v)]
            route, pos = waypoints_and_positions(dataset / "variants" / meta["name"])
            windows = [a["window"] for a in meta["anomalies"] if a["window"]]
            rows = np.nonzero(data["variant"] == v)[0]
            for r in rows:
                t = int(data["t"][r])
                lab, pr = int(j_keep[r]), int(pred[r])
                p = pos.get(t)
                near = bool(
                    p
                    and route
                    and min(np.hypot(p[0] - w[0], p[1] - w[1]) for w in route) < CORNER_M
                )
                if lab == 1:
                    dev_total += 1
                    if not any(
                        a - 60 <= t <= b + 60 for a, b in windows
                    ):  # fuera de toda anomalía inyectada
                        dev_free += 1
                        dev_free_near += near
                if pr != lab:
                    err += 1
                    near_err += near
                    if pr == 1 and lab == 0:
                        false_dev += 1
                        near_false += near
        out[name] = {
            "errors": err, "errors_near_corner": near_err, "false_deviated": false_dev,
            "false_deviated_near_corner": near_false, "label_deviated": dev_total,
            "label_deviated_outside_anomalies": dev_free, "of_which_near_corner": dev_free_near,
        }  # fmt: skip
    return out


def main() -> int:
    exp = DEFAULT_DATASET.parent
    v3 = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else exp / "e7b-v3"
    gen = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else exp / "e7b-gen-v3"
    trees = pickle.loads((v3 / "models" / "trees.pkl").read_bytes())  # noqa: S301
    forest = pickle.loads((v3 / "models" / "forests" / f"{FACET}.pkl").read_bytes())  # noqa: S301
    tables = load_tables(candidates_path(v3))
    data = {
        "validation": load(v3, "validation"),
        "test": load(v3, "test"),
        "gen": load(gen, "test"),
    }
    train = load(v3, "train")
    names = [str(f) for f in data["validation"]["features"]]
    states = {s: learned_states(tables, d, names) for s, d in data.items()}

    # 1. margen elegido en validación
    grid = {
        k: scores(
            sum(
                conf(
                    data["validation"], run_rule(data["validation"], states["validation"], names, k)
                ).values()
            )
        )["macro_f1"]
        for k in K_GRID
    }
    k = max(K_GRID, key=lambda c: (round(grid[c], 4), -c))
    # 2. modelos de referencia
    tree = trees[FACET]
    ref_f1, ref_tree, ref_depth, ref_alpha = reference_tree(train, data["validation"], names)
    cols = columns(FACET, names)
    index_gen = json.loads((gen / "index.json").read_text(encoding="utf-8"))
    airspeed = {
        i: yaml.safe_load((gen / "variants" / m["name"] / "assets.yaml").read_text("utf-8"))[
            "drone"
        ]["max_airspeed_mps"]
        for i, m in enumerate(index_gen)
    }

    lines = ["# E7b · drone.situation: regla determinista frente a la aprendida (e7b-v3)", "",
             "La regla (`situation/situation_rule.yaml`) decide con la distancia a la referencia del modo, con un margen "
             "según el error esperado de la posición y con la causa activa que dan las tablas aprendidas de las otras facetas. "
             "Margen elegido **en validación** (F1 macro):", "",
             "| Margen (× error esperado) | " + " | ".join(f"{c:g}" for c in K_GRID) + " |",
             "|---|" + "---|" * len(K_GRID),
             "| F1 macro validación | " + " | ".join(f"{grid[c]:.3f}" for c in K_GRID) + f" |\n\nElegido: **{k:g}**.", ""]  # fmt: skip
    summary = {"margin_grid": grid, "margin": k}
    results = {}
    for split, d in data.items():
        pred_rule = run_rule(d, states[split], names, k)
        rows = {
            "Regla determinista": conf(d, pred_rule),
            "Árbol aprendido (solo geometría)": conf(d, tree.predict(d["x"])),
            "Árbol aprendido + señales de causa": conf(d, ref_tree.predict(d["x"])),
            "Bosque (solo geometría)": conf(d, forest.predict(d["x"][:, cols])),
        }
        results[split] = (pred_rule, rows)
        title = {
            "validation": "Validación",
            "test": "Prueba de v3",
            "gen": "Generalización (e7b-gen-v3)",
        }[split]
        lines += [
            f"## {title}",
            "",
            "| Modelo | F1 macro [IC 95 %] | F1 por clase |",
            "|---|---|---|",
        ]
        for name, c in rows.items():
            lines.append(f"| {name} | {cell(c)} | {per_class(c)} |")
        summary[split] = {n: scores(sum(c.values()))["macro_f1"] for n, c in rows.items()}
        summary.setdefault("cells", {})[split] = {n: cell(c) for n, c in rows.items()}
        lines.append("")
        if split == "gen":
            sub = [
                "**Por velocidad máxima del dron:**",
                "",
                "| Grupo | Regla | Árbol (geometría) | Árbol + causa | Bosque |",
                "|---|---|---|---|---|",
            ]
            for gname, pick in (("8 m/s", lambda a: a < 15), ("28 m/s", lambda a: a >= 15)):
                cells = [
                    cell({v: m for v, m in c.items() if pick(airspeed[v])}) for c in rows.values()
                ]
                sub.append(f"| {gname} | " + " | ".join(cells) + " |")
            lines += sub + [""]
    lines += [
        f"Árbol de referencia con señales de causa: profundidad {ref_depth}, `ccp_alpha` {ref_alpha}, {len(ref_tree.leaves())} hojas (validación {ref_f1:.3f}).",
        "",
    ]

    # 3. esquinas con el dron de 28 m/s
    corners = corner_analysis(gen, data["gen"], results["gen"][0], index_gen, airspeed)
    summary["corners_rule"] = corners
    attempts = {"8 m/s": [0, 0], "28 m/s": [0, 0]}
    for i, m in enumerate(index_gen):
        g = "8 m/s" if airspeed[i] < 15 else "28 m/s"
        attempts[g][0] += len(m["discarded"])
        attempts[g][1] += len(m["discarded"]) + 1
    lines += [f"## ¿Cuánto del fallo con 28 m/s viene de las esquinas? (regla, generalización; «cerca» = a menos de {CORNER_M:g} m de un waypoint)", "",
              "| Grupo | Errores | de ellos, cerca de una esquina | Falsas «desviado» | de ellas, cerca | Segundos «desviado» (etiqueta) | sin anomalía inyectada (±60 s) | de ellos, cerca de una esquina | Intentos descartados por `unexplained` |",
              "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for g, c in corners.items():
        lines.append(f"| {g} | {c['errors']} | {c['errors_near_corner']} | {c['false_deviated']} | {c['false_deviated_near_corner']} | "
                     f"{c['label_deviated']} | {c['label_deviated_outside_anomalies']} | {c['of_which_near_corner']} | "
                     f"{attempts[g][0]} de {attempts[g][1]} ({100 * attempts[g][0] / attempts[g][1]:.0f} %) |")  # fmt: skip
    out = v3 / "report" / "situation.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (v3 / "report" / "situation.json").write_text(
        json.dumps(summary, indent=1, default=float), "utf-8"
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
