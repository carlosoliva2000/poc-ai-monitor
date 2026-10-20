"""Genera `runs/<escenario>/`: `uv run python -m platform_app.generator [nombre …] [--all]`."""

import argparse

from .build import generate, write_run
from .scenario_io import list_scenarios, load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="escenarios (nombre del YAML sin extensión)")
    parser.add_argument("--all", action="store_true", help="todos los de scenarios/")
    args = parser.parse_args()
    names = list_scenarios() if args.all else args.names
    if not names:
        parser.error("indica uno o más escenarios, o --all")
    for name in names:
        run = generate(load_scenario(name))
        out = write_run(run)
        print(f"{name}: {run.truth.duration_s:.1f} s, {len(run.events)} eventos -> {out}")


if __name__ == "__main__":
    main()
