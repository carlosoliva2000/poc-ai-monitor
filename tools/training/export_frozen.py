"""E7b, paso 5: el JSON de reglas de las tablas congeladas para la web.

    uv run --project ai-module-py python tools/training/export_frozen.py

Escribe `web/lib/situation-tables-frozen.json` con `build_frozen()` de `export_tables` (las tablas
de `tables_learned.yaml` y la regla de `situation_rule.yaml`); un test comprueba que no se
desincroniza. La web aún no lo lee: lo enchufa la E7c.
"""

import json
from pathlib import Path

from ai_module.situation.export_tables import build_frozen

OUT = Path(__file__).resolve().parents[2] / "web" / "lib" / "situation-tables-frozen.json"


def main() -> int:
    OUT.write_text(
        json.dumps(build_frozen(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
