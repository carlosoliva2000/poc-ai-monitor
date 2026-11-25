"""Genera los datos de prueba del monitor de situación para `nominal` con dos órdenes del
instructor: viento del norte de 19 m/s hasta nuevo aviso a T+110 y cancelación a T+150 (lo que
hace el instructor en el vídeo del 19/11/2026). No toca `runs/`.

    uv run --project platform python tools/video/gen_nominal_cmd.py

Escribe `ai-module-py/tests/fixtures/nominal_cmd/events.jsonl.gz` (determinista: misma semilla
que `nominal`).
"""

import gzip
from pathlib import Path

from platform_app.generator.build import generate
from platform_app.generator.scenario_io import load_scenario
from poc_contracts.commands import ScheduledCommand

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ai-module-py" / "tests" / "fixtures" / "nominal_cmd" / "events.jsonl.gz"


def main() -> None:
    cfg = load_scenario("nominal")
    commands = [
        ScheduledCommand(
            at_s=110.0,
            command="set_wind",
            params={"from_deg": 0.0, "speed_mps": 19.0, "ramp_s": 10.0, "duration_s": None},
        ),
        ScheduledCommand(at_s=150.0, command="cancel_wind", params=None),
    ]
    run = generate(cfg.model_copy(update={"commands": commands, "name": "nominal-cmd"}))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(event.model_dump_json() + "\n" for event in run.events)
    # mtime=0: el .gz sale igual byte a byte en cada generación
    with gzip.GzipFile(OUT, "wb", mtime=0) as handle:
        handle.write(lines.encode("utf-8"))
    print(f"{len(run.events)} events -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
