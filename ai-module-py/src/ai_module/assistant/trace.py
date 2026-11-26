"""Traza del asistente: una línea JSON por texto (entrada, salida, veredicto, latencia).

Va a `runs/_assistant/<run_id>/assistant.jsonl` (solo el `run_id`: el proceso del alumno no conoce
el nombre del escenario). Sin ruta, no escribe nada (pruebas y herramientas fuera de línea).
"""

import json
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []

    def write(self, record: dict[str, Any]) -> None:
        self.records.append(record)
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
