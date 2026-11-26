"""Congela los prompts del asistente: escribe `agent-assets/prompts_freeze.json`.

uv run --project ai-module-py python tools/assistant/freeze_prompts.py [--check]
"""

import sys

from ai_module.assistant import freeze


def main() -> int:
    if "--check" in sys.argv:
        try:
            print(freeze.verify())
        except freeze.FreezeError as exc:
            print(f"CHANGED: {exc}")
            return 1
        return 0
    data = freeze.write()
    print(f"{len(data)} files frozen in agent-assets/{freeze.FREEZE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
