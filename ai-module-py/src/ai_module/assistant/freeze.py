"""Congelación de los prompts del asistente (antes de la E8).

`agent-assets/prompts_freeze.json` guarda el sha256 de cada prompt, de los esquemas de tools, del
glosario y de la configuración (`assistant.yaml`). Los procesos del asistente comprueban al arrancar
que nada ha cambiado y, si cambió algo, no arrancan: la evaluación a ciegas compara textos de
exactamente estos prompts. Para refrescar tras un cambio **decidido**:

    uv run --project ai-module-py python tools/assistant/freeze_prompts.py
"""

import hashlib
import json
from pathlib import Path

from .config import ASSETS_DIR

FREEZE_FILE = "prompts_freeze.json"


class FreezeError(Exception):
    """Algún fichero congelado ha cambiado."""


def frozen_files(assets: Path = ASSETS_DIR) -> list[Path]:
    """Los ficheros que entran en la congelación (rutas relativas a `assets`)."""
    names = [*sorted((assets / "prompts").glob("*.md")), *sorted(assets.glob("*_tools.json"))]
    names += [assets / "glossary.yaml", assets / "assistant.yaml"]
    return [p.relative_to(assets) for p in names]


def digests(assets: Path = ASSETS_DIR) -> dict[str, str]:
    return {
        str(rel): hashlib.sha256((assets / rel).read_bytes()).hexdigest()
        for rel in frozen_files(assets)
    }


def write(assets: Path = ASSETS_DIR) -> dict[str, str]:
    data = digests(assets)
    (assets / FREEZE_FILE).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def verify(assets: Path = ASSETS_DIR) -> str:
    """Comprueba la congelación. Devuelve un resumen (huella corta); `FreezeError` si cambió algo.
    Sin fichero de congelación no hay nada que comprobar y lo dice."""
    path = assets / FREEZE_FILE
    if not path.exists():
        return "prompts not frozen (no prompts_freeze.json)"
    frozen = json.loads(path.read_text(encoding="utf-8"))
    current = digests(assets)
    changed = sorted(k for k in current if frozen.get(k) != current[k])
    removed = sorted(set(frozen) - set(current))
    if changed or removed:
        raise FreezeError(
            "the frozen prompts changed: "
            + ", ".join([*changed, *(f"{r} (removed)" for r in removed)])
            + ". If it is intended: uv run --project ai-module-py python "
            "tools/assistant/freeze_prompts.py"
        )
    return "prompts frozen, sha " + hashlib.sha256(json.dumps(frozen).encode()).hexdigest()[:12]
