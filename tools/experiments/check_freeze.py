"""Congelación de la tabla de decisión de la E6 y de todo lo que calcula sus entradas.

    uv run --project ai-module-py python tools/experiments/check_freeze.py --write   # congela
    uv run --project ai-module-py python tools/experiments/check_freeze.py           # comprueba

`--write` escribe `experiments/e6/table_freeze.json` con el sha256 de cada archivo, uno combinado
y la fecha; sin él, compara los archivos de hoy con los congelados y sale con 1 si alguno cambió
(se comprueba antes del barrido del paso 2b y antes de ejecutar el conjunto reservado). No se
puede volver a congelar encima: un cambio después cuenta como «a posteriori».
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FREEZE = REPO / "experiments" / "e6" / "table_freeze.json"
FILES = [
    # la tabla y su código
    "ai-module-py/src/ai_module/config/decision_table.yaml",
    "ai-module-py/src/ai_module/decision/table.py",
    "ai-module-py/src/ai_module/decision/features.py",
    "ai-module-py/src/ai_module/decision/decider.py",
    "ai-module-py/src/ai_module/decision/templates.py",
    # de lo que dependen las entradas en el módulo
    "ai-module-py/src/ai_module/agent/guardrails.py",
    "ai-module-py/src/ai_module/monitor_state.py",
    "ai-module-py/src/ai_module/monitor.py",
    "ai-module-py/src/ai_module/agent/tools.py",
    "ai-module-py/src/ai_module/config/detector.yaml",
    # las tools de la plataforma que calculan los hechos
    "platform/src/platform_app/tools/metrics.py",
    "platform/src/platform_app/tools/events.py",
    "platform/src/platform_app/tools/context.py",
    "platform/src/platform_app/geometry.py",
    "contracts/python/src/poc_contracts/times.py",
]


def digests() -> dict[str, str]:
    return {f: hashlib.sha256((REPO / f).read_bytes()).hexdigest() for f in FILES}


def combined(files: dict[str, str]) -> str:
    text = "".join(f"{h}  {name}\n" for name, h in sorted(files.items()))
    return hashlib.sha256(text.encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze or check the E6 decision table")
    parser.add_argument("--write", action="store_true", help="freeze (only if not frozen yet)")
    parser.add_argument("--freeze-file", type=Path, default=FREEZE)
    args = parser.parse_args(argv)
    now = digests()
    if args.write:
        if args.freeze_file.exists():
            print(f"already frozen: {args.freeze_file} (a later change is «a posteriori»)")
            return 1
        args.freeze_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "frozen_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "combined_sha256": combined(now),
            "files": now,
        }
        args.freeze_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"frozen: {args.freeze_file} · {data['combined_sha256'][:16]}")
        return 0
    frozen = json.loads(args.freeze_file.read_text(encoding="utf-8"))
    changed = [f for f, h in frozen["files"].items() if now.get(f) != h]
    missing = [f for f in FILES if f not in frozen["files"]]
    if changed or missing:
        for f in changed:
            print(f"CHANGED  {f}")
        for f in missing:
            print(f"NOT IN THE FREEZE  {f}")
        return 1
    print(f"ok: {len(FILES)} files as frozen at {frozen['frozen_at']} · "
          f"{frozen['combined_sha256'][:16]}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
