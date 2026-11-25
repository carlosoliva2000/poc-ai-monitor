"""E7b, paso 1: gráficas de variantes de ejemplo (regenera sus ficheros de verdad desde el YAML).

uv run --project platform python tools/training/examples.py v0001 v0002 …
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "experiments" / "e7b" / "e7b-v1"
sys.path.insert(0, str(REPO / "platform" / "src"))
# las gráficas leen el YAML del escenario por nombre: que lo encuentren junto a su salida
os.environ["POC_SCENARIOS_DIR"] = str(DATASET / "examples" / "scenarios")

from platform_app.generator.build import generate, write_run  # noqa: E402
from platform_app.plot_scenario import plot_scenario  # noqa: E402
from poc_contracts.scenario import ScenarioConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    out = DATASET / "examples"
    (out / "scenarios").mkdir(parents=True, exist_ok=True)
    for name in args.names:
        source = DATASET / "variants" / name / "scenario.yaml"
        raw = yaml.safe_load(source.read_text("utf-8"))
        (out / "scenarios" / f"{name}.yaml").write_text(source.read_text("utf-8"), "utf-8")
        write_run(generate(ScenarioConfig.model_validate(raw)), out / name)
        for path in plot_scenario(name, runs_dir=out):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
