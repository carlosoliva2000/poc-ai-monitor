"""Compara el guiado de hoy con el de multirrotor (E7a, paso 2) en `nominal`, `wind` con un viento
por encima de la velocidad máxima del dron y `demo`. Escribe `experiments/e7a/guidance_compare.png`
y `.md`.

    uv run --project platform python tools/e7a_guidance_compare.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

from platform_app.generator.build import generate  # noqa: E402
from platform_app.geometry import distance_to_route  # noqa: E402
from poc_contracts.scenario import ScenarioConfig  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "e7a"
CASES = [("nominal", None), ("wind", 18.0), ("demo", 18.0)]  # (escenario, viento del episodio)


def config(name: str, v2: bool, wind: float | None) -> ScenarioConfig:
    raw = yaml.safe_load((ROOT / "scenarios" / f"{name}.yaml").read_text(encoding="utf-8"))
    if v2:
        raw["simulator"] = {"multirotor_guidance": True}
        raw["drone"].update({"acceptance_radius_m": 5.0, "max_turn_rate_dps": 90.0})
    if wind is not None:
        raw["wind"]["episodes"][0]["speed_mps"] = wind
    return ScenarioConfig.model_validate(raw)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(CASES), 3, figsize=(16, 4.2 * len(CASES)))
    head = (
        "| Caso | Guiado | Duración (s) | Desviación máx. (m) | Segundos desviado | Sin causa (s) |"
    )
    rows = [head, "|---|---|---|---|---|---|"]
    for r, (name, wind) in enumerate(CASES):
        label = name if wind is None else f"{name} (viento {wind:.0f} m/s)"
        for v2, color, tag in ((False, "#eb6834", "hoy"), (True, "#2a78d6", "multirrotor")):
            run = generate(config(name, v2, wind))
            route = [(w.x, w.y) for w in run.plan.waypoints]
            tr = run.truth.trajectory
            dev = [distance_to_route((s.x, s.y), route) for s in tr]
            axes[r][0].plot([s.x for s in tr], [s.y for s in tr], color=color, lw=1.4, label=tag)
            axes[r][1].plot([s.t for s in tr], dev, color=color, lw=1.2, label=tag)
            axes[r][2].plot([s.t for s in tr], [s.speed_mps for s in tr], color=color, lw=1.0)
            dsv = sum(x.facets["drone.situation"] == "deviated" for x in run.states)
            unx = sum(x.facets["drone.cause"] == "unexplained" for x in run.states)
            rows.append(
                f"| {label} | {tag} | {run.truth.duration_s:.0f} | {max(dev):.1f} | {dsv} | {unx} |"
            )
        axes[r][0].plot([p[0] for p in route], [p[1] for p in route], "k--", lw=0.8, label="ruta")
        axes[r][0].set_aspect("equal")
        axes[r][0].set_title(f"{label}: trayectoria real")
        axes[r][1].set_title("distancia real a la ruta (m)")
        axes[r][2].set_title("velocidad sobre el suelo (m/s)")
        axes[r][0].legend()
    fig.tight_layout()
    fig.savefig(OUT / "guidance_compare.png", dpi=110)
    (OUT / "guidance_compare.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
