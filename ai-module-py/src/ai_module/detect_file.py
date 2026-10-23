"""Ejecuta el detector sobre uno o varios `events.jsonl` y muestra las detecciones.

uv run --project ai-module-py python -m ai_module.detect_file runs/fallos/events.jsonl
"""

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from poc_contracts.envelope import EventDraft

from .detection_format import DetectionFormatter
from .detector import Detector


def read_events(path: Path) -> Iterable[EventDraft]:
    """Lee un `events.jsonl`: un `EventDraft` por línea."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield EventDraft.model_validate_json(line)


def detect(path: Path) -> list[EventDraft]:
    """Todas las detecciones que produce el detector con los eventos del fichero."""
    detector = Detector()
    detections: list[EventDraft] = []
    for event in read_events(path):
        detections += detector.feed(event)
    return detections


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rule-based detector over event files")
    parser.add_argument("files", nargs="+", type=Path, help="uno o varios events.jsonl")
    parser.add_argument("--json", action="store_true", help="print the full events")
    args = parser.parse_args(argv)
    for path in args.files:
        if len(args.files) > 1 and not args.json:
            print(f"== {path}")
        formatter = DetectionFormatter()
        for event in detect(path):
            print(event.model_dump_json() if args.json else formatter.format(event))
    return 0


if __name__ == "__main__":
    sys.exit(main())
