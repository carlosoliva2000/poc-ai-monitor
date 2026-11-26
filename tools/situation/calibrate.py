"""Calibración de k y m del seguidor y métricas por incidente (E7c, paso 2).

    uv run --project ai-module-py python tools/situation/calibrate.py grid \\
        --dataset e7b-v3 --split validation
    uv run --project ai-module-py python tools/situation/calibrate.py final \\
        --dataset e7b-v3 --split validation --k 3 --m 10
    uv run --project ai-module-py python tools/situation/calibrate.py final \\
        --dataset e7b-gen-v3 --split test --k 3 --m 10

`grid` pasa cada variante de la partición por el monitor con cada par (k, m) y puntúa los
incidentes contra los de la verdad (mismo catálogo y seguidor con k = m = 1). **La regla de
elección se escribió antes de mirar las curvas**: el menor k con los falsos ponderados ≤ 0,5/h,
los falsos de ataque (`HIJACK`, `GPS_SPOOFING`) ≤ 0,1/h y el parpadeo ≤ 5 %, y luego el menor m que
cumpla lo mismo; si ningún par cumple, no se elige y se enseña la curva. `final` puntúa un par
concreto (en la generalización solo se mide, no se decide nada).
"""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from lib import (
    REPO,
    Record,
    Variant,
    cached_trace,
    monitor_policy,
    records,
    score,
    truth_incidents,
)

from ai_module.situation.policy import load_policy

KS = (1, 2, 3, 5, 8)
MS = (5, 10, 20, 30)
MAX_WEIGHTED_FALSE_PER_H = 0.5
MAX_ATTACK_FALSE_PER_H = 0.1
MAX_FLICKER_PCT = 5.0
OUT = REPO / "experiments" / "e7c"


def _job(args: tuple[str, str, list[tuple[int, int]]]) -> tuple[str, float, list[Record], dict]:
    folder_s, cache_s, grid = args
    folder, cache = Path(folder_s), Path(cache_s)
    policy = load_policy()
    trace = cached_trace(folder, cache)
    end = trace[-1][0] if trace else 0.0
    truth = truth_incidents(folder, policy)
    monitor = {f"{k}-{m}": records(monitor_policy(policy, k, m), trace, end) for k, m in grid}
    return folder.name, end / 3600.0, truth, monitor


def run(dataset: str, split: str, grid: list[tuple[int, int]], workers: int) -> dict[str, Any]:
    base = REPO / "experiments" / "e7b" / dataset
    index = json.loads((base / "index.json").read_text(encoding="utf-8"))
    names = [v["name"] for v in index if v["split"] == split]
    cache = OUT / "cache" / dataset
    jobs = [(str(base / "variants" / n), str(cache), grid) for n in names]
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(_job, jobs, chunksize=2))
    cells: dict[str, Any] = {}
    for k, m in grid:
        variants = [Variant(n, h, truth, mon[f"{k}-{m}"]) for n, h, truth, mon in results]
        cells[f"{k}-{m}"] = score(variants)
    return {"dataset": dataset, "split": split, "variants": len(names), "cells": cells}


def chosen(cells: dict[str, Any]) -> tuple[int, int] | None:
    """La regla de elección escrita de antemano."""
    ok = [
        (int(key.split("-")[0]), int(key.split("-")[1]))
        for key, s in cells.items()
        if s["false_weighted_per_h"] <= MAX_WEIGHTED_FALSE_PER_H
        and s["false_attack_per_h"] <= MAX_ATTACK_FALSE_PER_H
        and s["flicker_pct"] <= MAX_FLICKER_PCT
    ]
    return min(ok) if ok else None


def table(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['dataset']} · {result['split']} ({result['variants']} variantes)\n",
        "| k | m | detectados | falsos pond./h | falsos ataque/h | falsos otros/h | parpadeo % |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, s in result["cells"].items():
        k, m = key.split("-")
        det = s["detected_incidents"]
        lines.append(
            f"| {k} | {m} | {det}/{s['truth_incidents']} | {s['false_weighted_per_h']:.2f} | "
            f"{s['false_attack_per_h']:.2f} | {s['false_other_per_h']:.2f} | "
            f"{s['flicker_pct']:.1f} |"
        )
    return "\n".join(lines) + "\n"


def per_kind_table(cell: dict[str, Any]) -> str:
    lines = [
        "| tipo (verdad) | de verdad | detectados | con su nombre | "
        "retraso apertura mediana / p90 (s) | retraso nombre (s) |",
        "|---|---|---|---|---|---|",
    ]
    for kind, r in cell["per_kind"].items():

        def fmt(v: float | None) -> str:
            return "—" if v is None else f"{v:.0f}"

        lines.append(
            f"| {kind} | {r['truth']} | {r['detected']} | {r['kind_ok']} | "
            f"{fmt(r['delay_open_median'])} / {fmt(r['delay_open_p90'])} | "
            f"{fmt(r['delay_kind_median'])} |"
        )
    lines.append(f"\nFalsos por tipo: {cell['false_by_kind']}\n")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("mode", choices=["grid", "final"])
    parser.add_argument("--dataset", default="e7b-v3")
    parser.add_argument("--split", default="validation")
    parser.add_argument("--k", type=int)
    parser.add_argument("--m", type=int)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"{args.dataset}-{args.split}"
    if args.mode == "grid":
        result = run(args.dataset, args.split, [(k, m) for k in KS for m in MS], args.workers)
        (OUT / f"{stem}-grid.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        (OUT / f"{stem}-grid.md").write_text(table(result), encoding="utf-8")
        print(table(result))
        pick = chosen(result["cells"])
        print(
            "elegido:",
            pick if pick else "NINGÚN par cumple los tres topes: hay que decidir con la curva",
        )
        return 0
    if args.k is None or args.m is None:
        parser.error("final necesita --k y --m")
    result = run(args.dataset, args.split, [(args.k, args.m)], args.workers)
    cell = result["cells"][f"{args.k}-{args.m}"]
    (OUT / f"{stem}-k{args.k}-m{args.m}.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8"
    )
    text = (
        f"# {stem} con k = {args.k}, m = {args.m}\n\n"
        f"Falsos ponderados {cell['false_weighted_per_h']:.2f}/h, "
        f"de ataque {cell['false_attack_per_h']:.2f}/h, "
        f"otros {cell['false_other_per_h']:.2f}/h; parpadeo {cell['flicker_pct']:.1f} %.\n\n"
        + per_kind_table(cell)
    )
    (OUT / f"{stem}-k{args.k}-m{args.m}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
