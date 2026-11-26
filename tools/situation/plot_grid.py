"""Curvas de la calibración de k y m (E7c): falsos por hora, parpadeo y retraso de apertura por k.

    uv run --project platform python tools/situation/plot_grid.py \\
        experiments/e7c/e7b-v3-validation-grid.json

Solo lee el JSON que escribe `calibrate.py grid`; escribe el PNG al lado.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

KINDS = ("GPS_SPOOFING", "LINK_LOSS", "HIJACK", "WIND", "GPS_NO_FIX", "BATTERY_CRITICAL")
LIMITS = {"false_weighted_per_h": 0.5, "false_attack_per_h": 0.1, "flicker_pct": 5.0}
TITLES = {
    "false_weighted_per_h": "Falsos ponderados por hora (ataque ×3)",
    "false_attack_per_h": "Falsos de ataque por hora (HIJACK, GPS_SPOOFING)",
    "flicker_pct": "Parpadeo (% de los incidentes de verdad)",
}


def main(path: Path) -> Path:
    data = json.loads(path.read_text(encoding="utf-8"))
    cells = data["cells"]
    ks = sorted({int(key.split("-")[0]) for key in cells})
    ms = sorted({int(key.split("-")[1]) for key in cells})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for ax, metric in zip(axes.flat[:3], LIMITS, strict=True):
        for m in ms:
            ax.plot(ks, [cells[f"{k}-{m}"][metric] for k in ks], marker="o", label=f"m = {m}")
        ax.axhline(LIMITS[metric], color="crimson", linestyle="--", linewidth=1, label="tope")
        ax.set_title(TITLES[metric])
        ax.set_xlabel("k (instantes para abrir)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    ax = axes.flat[3]
    m = 10 if 10 in ms else ms[0]
    for kind in KINDS:
        delays = [cells[f"{k}-{m}"]["per_kind"].get(kind, {}).get("delay_open_median") for k in ks]
        ax.plot(ks, [d if d is not None else float("nan") for d in delays], marker="o", label=kind)
    ax.set_title(f"Retraso de apertura, mediana (s), con m = {m}")
    ax.set_xlabel("k (instantes para abrir)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.suptitle(f"{data['dataset']} · {data['split']} · {data['variants']} variantes")
    out = path.with_suffix(".png")
    fig.savefig(out, dpi=130)
    return out


if __name__ == "__main__":
    print(main(Path(sys.argv[1])))
