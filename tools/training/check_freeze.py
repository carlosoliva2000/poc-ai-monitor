"""E7b, paso 5: congelación de las tablas aprendidas y de todo lo que calcula sus entradas.

    uv run --project ai-module-py python tools/training/check_freeze.py --write   # congela
    uv run --project ai-module-py python tools/training/check_freeze.py           # comprueba

`--write` escribe `ai-module-py/src/ai_module/situation/tables_freeze.json` con el sha256 de cada
fichero, uno combinado y la fecha; sin él, compara los ficheros de hoy con los congelados y sale con
1 si alguno cambió (se comprueba antes de evaluar a ciegas en la E8). No se vuelve a congelar encima
sin `--force`: un cambio después cuenta como «a posteriori».
"""

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITUATION = "ai-module-py/src/ai_module/situation"
FREEZE = REPO / SITUATION / "tables_freeze.json"
DATASET = "e7b-v3"
FILES = [
    # las tablas y la regla
    f"{SITUATION}/tables_learned.yaml",
    f"{SITUATION}/situation_rule.yaml",
    f"{SITUATION}/situation_rule.py",
    # lo que calcula sus entradas y las ejecuta
    f"{SITUATION}/features.py",
    f"{SITUATION}/assets.yaml",
    "ai-module-py/src/ai_module/decision/table.py",
    # de dónde salen y qué se quitó
    f"tools/training/manifests/{DATASET}.yaml",
    f"tools/training/candidates/{DATASET}.yaml",
    f"tools/training/review/{DATASET}/rejected.yaml",
]


def digests() -> dict[str, str]:
    return {f: hashlib.sha256((REPO / f).read_bytes()).hexdigest() for f in FILES}


def combined(files: dict[str, str]) -> str:
    text = "".join(f"{h}  {name}\n" for name, h in sorted(files.items()))
    return hashlib.sha256(text.encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--force", action="store_true", help="volver a congelar (a posteriori)")
    args = parser.parse_args(argv)
    files = digests()
    if args.write:
        if FREEZE.exists() and not args.force:
            print("already frozen: use --force to freeze again (counts as a posteriori)")
            return 1
        FREEZE.write_text(
            json.dumps({"frozen_at": date.today().isoformat(), "dataset": DATASET,
                        "margin_k": 0.5, "combined_sha256": combined(files), "files": files},
                       indent=2) + "\n",
            encoding="utf-8",
        )  # fmt: skip
        print(f"frozen: {combined(files)[:16]} ({len(files)} files)")
        return 0
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    changed = [f for f in FILES if frozen["files"].get(f) != files[f]]
    for f in changed:
        print(f"CHANGED {f}")
    print("ok" if not changed else "changed since the freeze")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
