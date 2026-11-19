"""Compara el simulador de hoy con el de multirrotor (E7a): el guiado solo (paso 2) y con todo
encendido (estimador, receptor GPS, radar y estación, pasos 3 y 4), en `nominal`, `wind` y `demo`
con un viento por encima de la velocidad máxima del dron. Escribe `experiments/e7a/` con la figura
y la tabla (con la desviación máxima por acto de `demo`).

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
GUIDANCE = {"multirotor_guidance": True}
ALL = {
    **GUIDANCE,
    "onboard_estimator": True,
    "gps_receiver": True,
    "radar_geometry": True,
    "ground_station": True,
}
VARIANTS = [  # (nombre, interruptores, color)
    ("hoy", None, "#eb6834"),
    ("multirrotor (paso 2)", GUIDANCE, "#2a78d6"),
    ("v2 completo (pasos 2-4)", ALL, "#1baf7a"),
]
ACTS = [("viento", 95.0, 168.0), ("engaño", 168.0, 335.0), ("secuestro", 335.0, 1e9)]


def config(name: str, switches: dict | None, wind: float | None) -> ScenarioConfig:
    raw = yaml.safe_load((ROOT / "scenarios" / f"{name}.yaml").read_text(encoding="utf-8"))
    # los YAML ya llevan el simulador v2 encendido: se fuerza cada variante
    raw["simulator"] = switches or {}
    if switches:
        raw["drone"].update({"acceptance_radius_m": 5.0, "max_turn_rate_dps": 100.0})
    else:  # el guiado de hoy: radio de 25 m y giro de 40 °/s
        raw["drone"].update({"acceptance_radius_m": 25.0, "max_turn_rate_dps": 40.0})
    if raw.get("hijack") and not (switches or {}).get("link_physics"):
        # el enlace de antes (sin física) lleva la pista del secuestro
        raw["hijack"]["link_hint"] = {
            "controller_id": "UNK-4F2A",
            "rssi_dbm": -79.0,
            "latency_ms": 120.0,
        }
    if wind is not None:
        raw["wind"]["episodes"][0]["speed_mps"] = wind
    return ScenarioConfig.model_validate(raw)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(CASES), 3, figsize=(16, 4.2 * len(CASES)))
    head = "| Caso | Simulador | Duración (s) | Desviación máx. (m) | Segundos desviado |"
    head += " Sin causa (s) |"
    rows = [head, "|---|---|---|---|---|---|"]
    acts = [
        "| Simulador | Viento (T+95–168) | Engaño (T+168–335) | Secuestro (T+335–fin) |",
        "|---|---|---|---|",
    ]
    for r, (name, wind) in enumerate(CASES):
        label = name if wind is None else f"{name} (viento {wind:.0f} m/s)"
        for tag, switches, color in VARIANTS:
            run = generate(config(name, switches, wind))
            route = [(w.x, w.y) for w in run.plan.waypoints]
            tr = run.truth.trajectory
            dev = [distance_to_route((s.x, s.y), route) for s in tr]
            axes[r][0].plot([s.x for s in tr], [s.y for s in tr], color=color, lw=1.3, label=tag)
            axes[r][1].plot([s.t for s in tr], dev, color=color, lw=1.1, label=tag)
            axes[r][2].plot([s.t for s in tr], [s.speed_mps for s in tr], color=color, lw=1.0)
            dsv = sum(x.facets["drone.situation"] == "deviated" for x in run.states)
            unx = sum(x.facets["drone.cause"] == "unexplained" for x in run.states)
            rows.append(
                f"| {label} | {tag} | {run.truth.duration_s:.0f} | {max(dev):.1f} | {dsv} | {unx} |"
            )
            if name == "demo":
                per_act = [
                    max(d for s, d in zip(tr, dev, strict=True) if a <= s.t < b) for _, a, b in ACTS
                ]
                acts.append(f"| {tag} | " + " | ".join(f"{m:.0f} m" for m in per_act) + " |")
        axes[r][0].plot([p[0] for p in route], [p[1] for p in route], "k--", lw=0.8, label="ruta")
        axes[r][0].set_aspect("equal")
        axes[r][0].set_title(f"{label}: trayectoria real")
        axes[r][1].set_title("distancia real a la ruta (m)")
        axes[r][2].set_title("velocidad sobre el suelo (m/s)")
        axes[r][0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "guidance_compare.png", dpi=110)
    text = "\n".join(rows) + "\n\n**Desviación máxima por acto de `demo` (acto 1 con 18 m/s):**\n\n"
    text += "\n".join(acts) + "\n"
    (OUT / "guidance_compare.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
