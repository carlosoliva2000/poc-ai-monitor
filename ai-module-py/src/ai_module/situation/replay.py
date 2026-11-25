"""Monitor de situación sobre un `events.jsonl`, sin plataforma (pruebas y revisión).

uv run --project ai-module-py python -m ai_module.situation.replay \\
    runs/demo/events.jsonl [learned|handwritten]
"""

import gzip
import json
import sys
from pathlib import Path
from typing import Any

from ..outbox import format_t
from .facets import LEARNED
from .monitor import SituationMonitor

WORLD_DOMAINS = ("air", "env")


def is_world(event: dict[str, Any]) -> bool:
    """Eventos del dron, del radar, de la estación y del enlace (dominios `air` y `env`)."""
    return event["topic"].split(".")[3] in WORLD_DOMAINS


def read_events(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def replay(path: Path, tables: str = LEARNED) -> list[tuple[float, dict[str, Any]]]:
    """Los `IncidentUpdated` (instante, payload) que publicaría el monitor con este fichero."""
    monitor = SituationMonitor(tables=tables)
    out: list[tuple[float, dict[str, Any]]] = []
    for event in read_events(path):
        if is_world(event):
            out.extend(monitor.push(event))
    out.extend(monitor.flush())
    return out


def describe(update: dict[str, Any]) -> str:
    """Una línea legible de una transición: instante, cambio, nombre, estado y evidencias."""
    conds = []
    for item in update["evidence"]:
        parts = [
            f"{c['feature']} {c['value']} {c['op']} {c['threshold']}" for c in item["conditions"]
        ]
        detail = f" ({'; '.join(parts)})" if parts else ""
        conds.append(f"{item['facet']}={item['state']} [{item['rule_id']}]{detail}")
    return (
        f"{format_t(update['as_of_sim_time'])}  {update['change']:<8} {update['incident_id']} "
        f"{update['name']:<22} {update['state']:<10} {update['severity']:<6} "
        f"{update['confidence']}\n      " + "\n      ".join(conds)
    )


def main() -> None:
    path, *rest = sys.argv[1:]
    for _, update in replay(Path(path), rest[0] if rest else LEARNED):
        print(describe(update))


if __name__ == "__main__":
    main()
