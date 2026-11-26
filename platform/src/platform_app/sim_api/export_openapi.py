"""Exporta el OpenAPI de `/api/v1` a `contracts/api/sim-api-v1.json` (versionado en el repo).

    uv run --project platform python -m platform_app.sim_api.export_openapi [--out FICHERO]

Salida determinista; una prueba comprueba que el fichero del repo está al día.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from ..bus import Bus
from ..paths import REPO_ROOT, SCENARIOS_DIR
from ..player import Player
from .feed import Feed
from .routes import create_sim_api

DEFAULT_OUT = REPO_ROOT / "contracts" / "api" / "sim-api-v1.json"


def build_openapi() -> dict[str, Any]:
    bus = Bus()
    return create_sim_api(Player(bus), Feed(bus), SCENARIOS_DIR).openapi()


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(build_openapi()), encoding="utf-8")
    print(f"OpenAPI written to {args.out}")


if __name__ == "__main__":
    main()
