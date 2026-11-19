"""Escribe `web/lib/situation-tables.json` desde `tables.yaml` del monitor de situación (lo que
enseña la ventana «Rules» de la web). Hay que volver a ejecutarlo si cambia `tables.yaml`; un test
del módulo de IA falla si el fichero no está sincronizado.

    uv run --project ai-module-py python tools/video/export_tables.py
"""

import json
from pathlib import Path

from ai_module.situation.export_tables import build

OUT = Path(__file__).resolve().parents[2] / "web" / "lib" / "situation-tables.json"


def main() -> None:
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"tables -> {OUT.relative_to(OUT.parents[2])}")


if __name__ == "__main__":
    main()
