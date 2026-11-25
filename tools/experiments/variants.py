"""E6, paso 2b: variantes de escenarios a partir de una rejilla
(`experiments/e6-variantes/grid.yaml`).

    uv run --project platform python tools/experiments/variants.py [--grid G] [--out D]

Por cada combinación de la rejilla crea el YAML del escenario (`<out>/scenarios/<nombre>.yaml`,
sobre el escenario `base`: misma ruta y física, solo cambian las perturbaciones), lo genera en
memoria y lo escribe con `write_run` en `<out>/runs/<nombre>/` (nunca en `runs/`). Mide el tiempo
del generador por variante y deja el índice en `<out>/variants.json` (familia, parámetros,
etiquetas y tiempo). Determinista: la misma rejilla da los mismos ficheros.
"""

import argparse
import copy
import itertools
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform" / "src"))

from platform_app.generator.build import generate, write_run  # noqa: E402
from platform_app.paths import SCENARIOS_DIR  # noqa: E402
from poc_contracts.scenario import ScenarioConfig  # noqa: E402

DEFAULT_GRID = REPO / "experiments" / "e6-variantes" / "grid.yaml"

Variant = tuple[str, str, dict[str, Any], dict[str, Any]]
"""(nombre, familia, parámetros para el índice, cambios sobre la base)."""


def _wind(spec: dict[str, Any]) -> list[Variant]:
    out = []
    for from_deg, (sk, strength), (lk, leg) in itertools.product(
        spec["from_deg"], spec["strength"].items(), spec["leg"].items()
    ):
        episode = {**leg, "ramp_s": spec["ramp_s"], **strength, "from_deg": float(from_deg)}
        name = f"wind-from{from_deg:03d}-{sk}-{lk}"
        out.append((name, "wind", {"from_deg": from_deg, "strength": sk, "leg": lk},
                    {"wind_episodes": [episode]}))  # fmt: skip
    return out


def _spoofing(spec: dict[str, Any]) -> list[Variant]:
    out = []
    for direction, (rk, rate), start in itertools.product(
        spec["direction_deg"], spec["rate"].items(), spec["start_s"]
    ):
        spoof = {
            "start_s": start,
            "end_s": start + rate["duration_s"],
            "drift_rate_mps": rate["drift_rate_mps"],
            "direction_deg": float(direction),
        }
        name = f"spoofing-d{direction:03d}-{rk}-t{int(start):03d}"
        out.append((name, "spoofing", {"direction_deg": direction, "rate": rk, "start_s": start},
                    {"spoofing": spoof}))  # fmt: skip
    return out


def _hijack(spec: dict[str, Any]) -> list[Variant]:
    out = []
    for (tk, target), (mk, mute) in itertools.product(
        spec["target"].items(), spec["radar_mute"].items()
    ):
        hijack = {"start_s": spec["start_s"], "end_s": spec["end_s"], "target": target}
        faults = [] if mute is None else [{"source": "radar", "mode": "mute", **mute}]
        out.append((f"hijack-{tk}-radar-{mk}", "hijack", {"target": tk, "radar": mk},
                    {"hijack": hijack, "faults": faults}))  # fmt: skip
    return out


def _faults(spec: dict[str, Any]) -> list[Variant]:
    out = []
    for source, window in spec["mute"].items():
        fault = {"source": source, "mode": "mute", **window}
        out.append((f"fault-mute-{source}", "faults", {"mode": "mute", "source": source},
                    {"faults": [fault]}))  # fmt: skip
    for key, window in spec["loss"].items():
        fault = {"source": "gps", "mode": "loss", **window}
        out.append((f"fault-loss-{key}", "faults", {"mode": "loss", "duration": key},
                    {"faults": [fault]}))  # fmt: skip
    return out


def _degradation(spec: dict[str, Any]) -> list[Variant]:
    out = []
    window = spec["window"]
    for source in ("gps", "link"):
        for (mk, target), ramp in itertools.product(spec[source].items(), spec["ramp_s"]):
            episode = {**window, "ramp_s": ramp, **target}
            name = f"deg-{source}-{mk}-ramp{int(ramp):02d}"
            out.append((name, "degradation", {"source": source, "magnitude": mk, "ramp_s": ramp},
                        {f"{source}_episodes": [episode]}))  # fmt: skip
    for key, params in spec["unlabeled"].items():
        params = dict(params)
        source = params.pop("source")
        episode = {**window, **params, "labeled": False}
        out.append((f"deg-unlabeled-{key}", "unlabeled", {"source": source, "kind": key},
                    {f"{source}_episodes": [episode]}))  # fmt: skip
    return out


def _clean(spec: dict[str, Any]) -> list[Variant]:
    return [(f"clean-seed{s}", "clean", {"seed": s}, {"seed": s}) for s in spec["seeds"]]


def _combination(spec: dict[str, Any]) -> list[Variant]:
    out = []
    for key, parts in spec.items():
        changes = {("wind_episodes" if k == "wind" else k): v for k, v in parts.items()}
        if "wind_episodes" in changes:
            changes["wind_episodes"] = [changes["wind_episodes"]]
        out.append((f"combo-{key}", "combination", {"parts": sorted(parts)}, changes))
    return out


BUILDERS = {
    "wind": _wind,
    "spoofing": _spoofing,
    "hijack": _hijack,
    "faults": _faults,
    "degradation": _degradation,
    "clean": _clean,
    "combination": _combination,
}


def apply(base: dict[str, Any], name: str, family: str, changes: dict[str, Any]) -> dict[str, Any]:
    """El escenario `base` con los cambios de una variante (diccionario listo para el YAML)."""
    raw = copy.deepcopy(base)
    raw["name"] = name
    raw["description"] = f"E6 variant ({family}) of {base['name']}: {name}."
    for key, value in changes.items():
        if key == "wind_episodes":
            raw["wind"]["episodes"] = value
        elif key in ("gps_episodes", "link_episodes"):
            raw["sensors"][key.split("_")[0]]["episodes"] = value
        else:
            raw[key] = value
    return raw


def build_variants(grid: dict[str, Any]) -> list[tuple[str, str, dict[str, Any], dict]]:
    base = yaml.safe_load((SCENARIOS_DIR / f"{grid['base']}.yaml").read_text(encoding="utf-8"))
    variants = []
    for family, spec in grid["families"].items():
        for name, fam, params, changes in BUILDERS[family](spec):
            variants.append((name, fam, params, apply(base, name, fam, changes)))
    names = [v[0] for v in variants]
    if len(names) != len(set(names)):
        raise ValueError("duplicated variant names")
    return variants


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=DEFAULT_GRID)
    parser.add_argument("--out", type=Path, default=None, help="por defecto, la carpeta de grid")
    args = parser.parse_args(argv)
    grid = yaml.safe_load(args.grid.read_text(encoding="utf-8"))
    out = args.out or args.grid.parent
    scenarios_dir, runs_dir = out / "scenarios", out / "runs"
    for folder in (scenarios_dir, runs_dir):  # siempre desde cero: la salida es de la rejilla
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    index = []
    for name, family, params, raw in build_variants(grid):
        text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
        (scenarios_dir / f"{name}.yaml").write_text(text, encoding="utf-8")
        config = ScenarioConfig.model_validate(raw)
        t0 = time.perf_counter()
        run = generate(config)
        gen_s = time.perf_counter() - t0
        write_run(run, runs_dir / name)
        index.append({
            "name": name,
            "family": family,
            "params": params,
            "generator_s": round(gen_s, 4),
            "duration_s": run.truth.duration_s,
            "labels": [
                {"id": lb.id, "type": lb.type.value, "source": lb.source and lb.source.value,
                 "start_s": lb.start_s, "end_s": lb.end_s}
                for lb in run.labels.labels
            ],
            "unlabeled": [] if run.unlabeled is None
            else [{"id": u.id, "source": u.source.value} for u in run.unlabeled.episodes],
        })  # fmt: skip
    (out / "variants.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    times = [v["generator_s"] for v in index]
    print(f"{len(index)} variantes en {out} · generador: media {sum(times) / len(times):.3f} s, "
          f"máx {max(times):.3f} s, total {sum(times):.1f} s")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
