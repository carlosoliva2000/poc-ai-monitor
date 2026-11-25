"""C/N0 y AGC del receptor con los emisores (E7a, paso 5): `demo` con el emisor de engaño y el
escenario `jamming` con un emisor de interferencia. Escribe `experiments/e7a/gnss_examples.png` y
`.md`.

    uv run --project platform python tools/e7a_gnss_example.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

from platform_app.generator.build import generate  # noqa: E402
from platform_app.generator.scenario_io import load_scenario  # noqa: E402
from poc_contracts.scenario import ScenarioConfig  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "e7a"
def demo_with_spoofer() -> ScenarioConfig:
    """`demo` (acto 1 con 18 m/s) y el emisor de engaño con posición."""
    raw = yaml.safe_load((ROOT / "scenarios" / "demo.yaml").read_text(encoding="utf-8"))
    raw["drone"].update({"acceptance_radius_m": 5.0, "max_turn_rate_dps": 100.0})
    raw["wind"]["episodes"][0]["speed_mps"] = 18.0
    raw["spoofing"]["emitter"] = {"x": 1400.0, "y": 1900.0, "power_db": 12.0}
    return ScenarioConfig.model_validate(raw)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spoof = [(0, 160, "sin emisor"), (175, 220, "engaño activo"), (240, 330, "después")]
    jam = [(0, 100, "sin emisor"), (130, 170, "interferencia activa"), (270, 400, "después")]
    cases = [
        ("demo (engaño, emisor en 1400, 1900)", demo_with_spoofer(), spoof),
        ("jamming (interferencia, emisor en 900, 1500)", load_scenario("jamming"), jam),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 6.5), sharex="col")
    rows = ["| Caso | Tramo | C/N0 (dB-Hz) | AGC (dB) |", "|---|---|---|---|"]
    for c, (label, cfg, windows) in enumerate(cases):
        run = generate(cfg)
        gnss = [e for e in run.events if e.type == "GnssStatus"]
        t = [e.sim_time for e in gnss]
        axes[0][c].plot(t, [e.payload["cn0_dbhz"] for e in gnss], color="#2a78d6", lw=1.0)
        axes[1][c].plot(t, [e.payload["agc_db"] for e in gnss], color="#eb6834", lw=1.0)
        active = [(s.t, bool(s.emitters_active)) for s in run.truth.trajectory]
        for ax in (axes[0][c], axes[1][c]):
            for (t0, on), (t1, _) in zip(active, active[1:], strict=False):
                if on:
                    ax.axvspan(t0, t1, color="#b9b8b2", alpha=0.35, lw=0)
        axes[0][c].set_title(label)
        axes[0][c].set_ylabel("C/N0 (dB-Hz)")
        axes[1][c].set_ylabel("AGC (dB)")
        axes[1][c].set_xlabel("t (s); en gris, con emisor activo")
        for a, b, name in windows:
            sel = [e.payload for e in gnss if a <= e.sim_time < b]
            cn0 = sum(p["cn0_dbhz"] for p in sel) / len(sel)
            agc = sum(p["agc_db"] for p in sel) / len(sel)
            rows.append(f"| {label.split(' ')[0]} | T+{a}–{b} ({name}) | {cn0:.1f} | {agc:.1f} |")
    fig.tight_layout()
    fig.savefig(OUT / "gnss_examples.png", dpi=110)
    (OUT / "gnss_examples.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
