"""E7b, paso 4: informe de las tablas candidatas por faceta, en la partición de prueba.

    uv run --project ai-module-py --group train python tools/training/report_tables.py

Escribe `<dataset>/report/e7b-tablas.md` (y `.json`) y los ficheros de revisión de
`tools/training/review/`. Las métricas salen de **la tabla** (no del árbol): primero se comprueba
que la tabla da lo mismo que el árbol en validación y que no tiene solapes ni huecos. Por fila:
soporte en entrenamiento (instantes, variantes y rachas distintas) y cómo acierta en validación y
en prueba. Por faceta: aciertos por clase y F1 macro con intervalo por bootstrap de variantes,
matriz de confusión, calibración, cortes de confianza (elegidos **en validación**), retraso de
detección por episodio, filas y profundidad, y la comparación con el modelo de muchos árboles y con
la tabla a mano. Al final, `demo` y `nominal` con el monitor de las tablas aprendidas.
"""

# ruff: noqa: E501  (líneas largas de las tablas en Markdown del informe)

import json
import pickle
import sys
from pathlib import Path

import numpy as np
from features import DEFAULT_DATASET, load
from hand_tables import HAND_FACETS, predict_split
from models import Tree, bootstrap, confusion_by_variant, scores
from replay_learned import replay as replay_learned
from review_files import REVIEW_DIR, readable, write_review
from tree_to_table import (
    NORMAL,
    candidates_path,
    leaf_rows,
    overlapping,
    table_predict,
    table_rows_hit,
    uncovered,
    write_candidates,
)

from ai_module.decision.table import load_tables
from ai_module.outbox import format_t
from ai_module.situation.replay import replay as replay_hand
from poc_contracts.states import FACETS

REPO = DEFAULT_DATASET.parents[2]
KEY_FACETS = {
    "gps.integrity": ["spoofed"], "link.availability": ["lost"],
    "environment.wind": ["beyond_limit"], "drone.situation": ["deviated"],
    "drone.cause": ["foreign_control", "spoofed_position", "dead_reckoning", "wind"],
}  # fmt: skip
BINS = (0.0, 0.5, 0.6, 0.9, 0.99, 1.0001)


def facet_split(data: dict, j: int) -> tuple[np.ndarray, ...]:
    keep = data["y"][:, j] >= 0
    return (
        data["x"][keep],
        data["y"][keep, j].astype(np.int32),
        data["variant"][keep],
        data["t"][keep],
    )


def detection_delays(y, pred, groups, t, state: int, k: int) -> dict:  # noqa: ANN001
    """Por cada racha de `state` en la etiqueta, los segundos hasta que la tabla da `state` `k`
    instantes seguidos dentro de esa racha (la etiqueta empieza con el suceso)."""
    n = len(y)
    is_state = y == state
    start = (
        is_state
        & ~np.r_[
            False, is_state[:-1] & (groups[1:] == groups[:-1]) & (np.diff(t, prepend=-9) <= 1.5)[1:]
        ]
    )  # noqa: E501
    delays, missed = [], 0
    for s in np.nonzero(start)[0]:
        e = s
        while (
            e + 1 < n and is_state[e + 1] and groups[e + 1] == groups[s] and t[e + 1] - t[e] <= 1.5
        ):
            e += 1
        run = (pred[s : e + 1] == state).astype(int)
        ok = np.convolve(run, np.ones(k, dtype=int), mode="valid") >= k
        if ok.any():
            delays.append(float(t[s + int(np.argmax(ok)) + k - 1] - t[s]))
        else:
            missed += 1
    arr = np.array(delays) if delays else np.array([np.nan])
    return {"episodes": len(delays) + missed, "detected": len(delays), "median_s": float(np.nanmedian(arr)),
            "p90_s": float(np.nanpercentile(arr, 90)), "max_s": float(np.nanmax(arr))}  # fmt: skip


def calibration(rows: list[tuple[float, int, int]]) -> list[dict]:
    """`rows`: (probabilidad de la fila, instantes que caen en ella, cuántos son de su clase)."""
    out = []
    for lo, hi in zip(BINS[:-1], BINS[1:], strict=True):
        sel = [(p, h, r) for p, h, r in rows if lo <= p < hi and h > 0]
        hits = sum(h for _, h, _ in sel)
        out.append({"bin": f"[{lo:g}, {min(hi, 1):g}]", "rows": len(sel), "instants": hits,
                    "predicted": sum(p * h for p, h, _ in sel) / hits if hits else None,
                    "observed": sum(r for _, _, r in sel) / hits if hits else None})  # fmt: skip
    return out


CUT_GRID = (0.99, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)


MIN_BAND = 300  # instantes mínimos para fiarse de la precisión de una banda


def choose_cuts(rows: list[tuple[float, int, int]]) -> tuple[float, float]:
    """Cortes de «confirmado» y «probable», elegidos con los instantes de validación: se baja por la
    rejilla banda a banda mientras cada banda acierta al menos el 90 % (confirmado) y, por debajo,
    al menos el 60 % (probable). Una banda con menos de `MIN_BAND` instantes no decide."""
    edges = (2.0, *CUT_GRID)

    def precision(lo: float, hi: float) -> float | None:
        hits = sum(h for p, h, _ in rows if lo <= p < hi)
        right = sum(r for p, h, r in rows if lo <= p < hi)
        return right / hits if hits >= MIN_BAND else None

    cuts: list[float] = []
    for target in (0.9, 0.6):
        cut = cuts[-1] if cuts else 1.0
        for hi, lo in zip(edges[:-1], edges[1:], strict=True):
            if lo >= cut:
                continue
            if (
                prec := precision(lo, hi if not cuts else min(hi, cuts[-1]))
            ) is not None and prec < target:
                break
            cut = lo
        cuts.append(cut)
    return cuts[0], cuts[1]


def per_row(tables, facet, x, y, features, codes):  # noqa: ANN001
    hit = table_rows_hit(tables, facet, x, features)
    rules = tables[facet.replace(".", "_")].rules
    out = {}
    for i, rule in enumerate(rules):
        sel = hit == i
        out[rule.rule_id] = (int(sel.sum()), int((y[sel] == codes[str(rule.then["state"])]).sum()))
    return out


def fmt_ci(s: dict, ci: dict, key="macro_f1") -> str:  # noqa: ANN001
    lo, hi = ci[key]
    return f"{s[key]:.3f} [{lo:.3f}, {hi:.3f}]"


def main() -> int:
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET
    trees: dict[str, Tree] = pickle.loads((dataset / "models" / "trees.pkl").read_bytes())  # noqa: S301
    step2 = json.loads((dataset / "report" / "step2.json").read_text(encoding="utf-8"))
    path = write_candidates(trees, candidates_path(dataset))
    tables = load_tables(path)
    data = {s: load(dataset, s) for s in ("validation", "test")}
    features = list(trees[next(iter(trees))].features)
    hand = {s: predict_split(dataset, data[s]) for s in ("validation", "test")}
    md = [f"# E7b · Tablas candidatas por faceta ({dataset.name}, partición de prueba)", "",
          "Las métricas salen **de la tabla** que ejecutaría el monitor. IC 95 % por bootstrap de "
          "variantes (episodios), 400 remuestreos. «Mín. variantes» y «mín. rachas» son por fila, en "
          "entrenamiento.", ""]  # fmt: skip
    summary: dict = {}
    pooled_val: list[tuple[float, int, int]] = []
    pooled_test: list[tuple[float, int, int]] = []
    sections: list[str] = []
    for facet, tree in trees.items():
        j = list(FACETS).index(facet)
        classes = list(FACETS[facet])
        codes = {s: i for i, s in enumerate(classes)}
        rows = leaf_rows(tree, facet)
        xv, yv, gv, _ = facet_split(data["validation"], j)
        xt, yt, gt, tt = facet_split(data["test"], j)
        pv = table_predict(tables, facet, xv, features)
        mismatches = int((pv != tree.predict(xv)).sum())
        overlaps, gaps = overlapping(rows), uncovered(rows, features)
        pt = table_predict(tables, facet, xt, features)
        conf = confusion_by_variant(yt, pt, gt, len(classes))
        total = sum(conf.values())
        sc, ci = scores(total), bootstrap(conf)
        row_val = per_row(tables, facet, xv, yv, features, codes)
        row_test = per_row(tables, facet, xt, yt, features, codes)
        review_dir = REVIEW_DIR if dataset.name == "e7b-v1" else REVIEW_DIR / dataset.name
        review = write_review(facet, rows, row_val, review_dir)
        probs = [(r.probability, *row_val[r.rule_id]) for r in rows if r.state not in NORMAL]
        probs_t = [(r.probability, *row_test[r.rule_id]) for r in rows if r.state not in NORMAL]
        pooled_val += probs
        pooled_test += probs_t
        summary[facet] = {"rows": len(rows), "depth": tree.depth(), "table_equals_tree": mismatches == 0,
                          "mismatches_validation": mismatches, "overlaps": overlaps, "gaps": gaps,
                          "macro_f1": sc["macro_f1"], "macro_f1_ci": ci["macro_f1"].tolist()}  # fmt: skip
        s2 = step2["facets"][facet]
        sec = [f"## {facet}", "",
               f"- **{len(rows)} filas, profundidad {tree.depth()}.** Tabla = árbol en validación: "
               f"{'sí' if mismatches == 0 else f'NO ({mismatches} instantes distintos)'}. "
               f"Solapes: {overlaps or 'ninguno'}. Huecos: {'sí' if gaps else 'no'}.",
               f"- F1 macro en prueba: **{fmt_ci(sc, ci)}**; exactitud {fmt_ci(sc, ci, 'accuracy')}.",
               "- Referencias (F1 macro en prueba): bosque de 100 árboles "
               f"{s2['forest_test']['macro_f1']:.3f} [{s2['forest_test']['macro_f1_ci'][0]:.3f}, "
               f"{s2['forest_test']['macro_f1_ci'][1]:.3f}]"]  # fmt: skip
        if facet in HAND_FACETS:
            k = HAND_FACETS.index(facet)
            hc = confusion_by_variant(
                yt, hand["test"][:, k][data["test"]["y"][:, j] >= 0], gt, len(classes)
            )
            hs, hci = scores(sum(hc.values())), bootstrap(hc)
            sec[-1] += f"; tabla a mano del vídeo {fmt_ci(hs, hci)}"
            # diferencia emparejada (mismas variantes remuestreadas) árbol − tabla a mano
            keys = sorted(conf)
            rng = np.random.default_rng(1)
            diffs = []
            for _ in range(400):
                pick = rng.integers(0, len(keys), len(keys))
                a = scores(sum(conf[keys[i]] for i in pick))["macro_f1"]
                b = scores(sum(hc[keys[i]] for i in pick))["macro_f1"]
                diffs.append(a - b)
            lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
            sec.append(f"- Diferencia emparejada tabla aprendida − tabla a mano: "
                       f"{sc['macro_f1'] - hs['macro_f1']:+.3f} [{lo:+.3f}, {hi:+.3f}].")  # fmt: skip
            summary[facet]["hand_macro_f1"] = hs["macro_f1"]
        sec += ["", "**Por clase (prueba):**", "", "| Clase | Instantes | F1 [IC 95 %] | Exhaustividad | Precisión |",
                "|---|---|---|---|---|"]  # fmt: skip
        for i, name in enumerate(classes):
            if sc["support"][i]:
                sec.append(f"| {name} | {int(sc['support'][i])} | {sc['f1'][i]:.3f} "
                           f"[{ci['f1'][0][i]:.3f}, {ci['f1'][1][i]:.3f}] | {sc['recall'][i]:.3f} | "
                           f"{sc['precision'][i]:.3f} |")  # fmt: skip
        sec += ["", "**Matriz de confusión (filas: etiqueta; columnas: tabla; última columna: sin decisión):**", "",
                "| | " + " | ".join(classes) + " | — |", "|---|" + "---|" * (len(classes) + 1)]  # fmt: skip
        for i, name in enumerate(classes):
            sec.append(f"| {name} | " + " | ".join(str(int(v)) for v in total[i]) + " |")
        if facet in KEY_FACETS:
            sec += ["", "**Retraso de detección por episodio (prueba)** — segundos desde que empieza el "
                    "suceso hasta que la tabla da ese estado `k` instantes seguidos:", "",
                    "| Estado | k | Episodios | Detectados | Mediana | p90 | Máx. |", "|---|---|---|---|---|---|---|"]  # fmt: skip
            for state in KEY_FACETS[facet]:
                for k in (1, 3):
                    d = detection_delays(yt, pt, gt, tt, codes[state], k)
                    sec.append(f"| {state} | {k} | {d['episodes']} | {d['detected']} | {d['median_s']:.0f} s | "
                               f"{d['p90_s']:.0f} s | {d['max_s']:.0f} s |")  # fmt: skip
        sec += ["", "**Filas** (soporte en entrenamiento; aciertos en validación y prueba):", "",
                "| Fila | Estado | Condiciones | Prob. | Instantes | Variantes | Rachas | Val. (n / acierta) | Prueba (n / acierta) |",
                "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for r in rows:
            vn, vr = row_val[r.rule_id]
            tn, tr = row_test[r.rule_id]
            sec.append(f"| {r.rule_id} | {r.state} | {readable(r)} | {r.probability:.3f} | {r.instants} | "
                       f"{r.variants} | {r.episodes} | {vn} / " + (f"{vr / vn:.2f}" if vn else "–") + f" | {tn} / " + (f"{tr / tn:.2f}" if tn else "–") + " |")  # fmt: skip
        sec += ["", f"Fichero de revisión: `{review.relative_to(REPO)}`", ""]
        sections.append("\n".join(sec))

    # Calibración y cortes de confianza (agrupando las filas de estados anómalos de todas las facetas).
    cut_confirmed, cut_probable = choose_cuts(pooled_val)
    cal = ["## Calibración y cortes de confianza", "",
           "Probabilidad de la fila (fracción de entrenamiento de su clase) frente a la frecuencia real "
           "en **prueba**, en las filas de estados anómalos de todas las facetas:", "",
           "| Probabilidad | Filas | Instantes | Prevista | Observada |", "|---|---|---|---|---|"]  # fmt: skip
    for b in calibration(pooled_test):
        cal.append(f"| {b['bin']} | {b['rows']} | {b['instants']} | "
                   + (f"{b['predicted']:.3f} | {b['observed']:.3f} |" if b["instants"] else "– | – |"))  # fmt: skip
    cal += ["", f"Cortes propuestos, elegidos en validación (primera probabilidad a partir de la cual se acierta "
            f"≥ 90 % y ≥ 60 %): **confirmado ≥ {cut_confirmed:.3f}**, **probable ≥ {cut_probable:.3f}**, "
            "posible por debajo (la especificación partía de 0,9 y 0,6). Precisión observada en prueba:", "",
            "| Banda | Instantes | Aciertos |", "|---|---|---|"]  # fmt: skip
    for name, lo, hi in (("confirmado", cut_confirmed, 2.0), ("probable", cut_probable, cut_confirmed),
                         ("posible", 0.0, cut_probable), ("confirmado con 0,9", 0.9, 2.0),
                         ("probable con 0,6–0,9", 0.6, 0.9)):  # fmt: skip
        hits = sum(h for p, h, _ in pooled_test if lo <= p < hi)
        right = sum(r for p, h, r in pooled_test if lo <= p < hi)
        cal.append(f"| {name} ({lo:g}–{min(hi, 1):g}) | {hits} | " + (f"{right / hits:.3f} |" if hits else "– |"))  # fmt: skip
    summary["cuts"] = {"confirmed": cut_confirmed, "probable": cut_probable}

    # demo y nominal con las tablas aprendidas.
    rep = ["", "## `demo` y `nominal` con las tablas aprendidas", "",
           "Facetas GPS, enlace, viento y situación aprendidas; tabla del tipo de incidente, seguidor y "
           "política, los del vídeo. Transiciones (sin las revisiones de evidencias):", ""]  # fmt: skip
    for name in ("demo", "nominal"):
        events = REPO / "runs" / name / "events.jsonl"
        video = [(p["as_of_sim_time"], p["change"], p["kind"], p["state"]) for _, p in replay_hand(events)
                 if p["change"] != "evidence"]  # fmt: skip
        learned = replay_learned(events, tables, rule=dataset.name.startswith("e7b-v3"))
        rep += [f"**{name}**", "", "| Vídeo (tablas a mano) | Tablas aprendidas |", "|---|---|"]
        for i in range(max(len(video), len(learned))):

            def one(lst, i=i):  # noqa: ANN001, ANN202
                return (
                    f"{format_t(lst[i][0])} {lst[i][1]} {lst[i][2]} ({lst[i][3]})"
                    if i < len(lst)
                    else ""
                )

            rep.append(f"| {one(video)} | {one(learned)} |")
        if not video and not learned:
            rep.append("| ningún incidente | ningún incidente |")
        rep.append("")
        summary[f"replay_{name}"] = {"video": video, "learned": learned}
    out = dataset / "report" / "e7b-tablas.md"
    out.write_text("\n".join(md + sections + ["\n".join(cal)] + rep) + "\n", encoding="utf-8")
    (dataset / "report" / "e7b-tablas.json").write_text(
        json.dumps(summary, indent=1, default=float), "utf-8"
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
