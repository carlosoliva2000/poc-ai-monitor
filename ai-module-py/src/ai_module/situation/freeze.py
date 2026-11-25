"""Comprobación al arrancar de que lo que ejecuta el monitor es lo congelado.

`tables_freeze.json` guarda el sha256 de las tablas aprendidas, de la regla de la situación y de lo
que calcula sus entradas. Aquí se comprueban los ficheros que viajan con el paquete (los de
`ai-module-py/src/ai_module/`); los de `tools/training/` (manifiesto, candidata, filas rechazadas)
los comprueba `tools/training/check_freeze.py`, que es la comprobación completa. Si algo no coincide
el monitor no arranca: una evaluación contra tablas distintas de las congeladas no vale.
"""

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1]  # .../ai_module
FREEZE_FILE = Path(__file__).resolve().parent / "tables_freeze.json"
PACKAGE_PREFIX = "ai-module-py/src/ai_module/"


class FreezeError(RuntimeError):
    """Un fichero que ejecuta el monitor no es el congelado."""


@cache
def load_freeze() -> dict[str, Any]:
    return json.loads(FREEZE_FILE.read_text(encoding="utf-8"))


def changed_files() -> list[str]:
    """Los ficheros del paquete cuyo hash no coincide con el congelado (o que faltan)."""
    bad: list[str] = []
    for name, expected in load_freeze()["files"].items():
        if not name.startswith(PACKAGE_PREFIX):
            continue
        path = PACKAGE / name.removeprefix(PACKAGE_PREFIX)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            bad.append(name)
    return bad


def margin_k() -> float:
    """Margen de la regla de la situación con el que se evaluó (el congelado, no el de
    `situation_rule.MARGIN_K`: el fichero congelado dice 1,0 y la evaluación de la E7b usó 0,5)."""
    return float(load_freeze()["margin_k"])


def verify() -> None:
    """Para con un error si algo de lo que ejecuta el monitor ha cambiado desde la congelación."""
    bad = changed_files()
    if bad:
        raise FreezeError(
            "frozen tables changed since " + load_freeze()["frozen_at"] + ": " + ", ".join(bad)
        )
