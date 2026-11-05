"""Coste de las ejecuciones con un cliente LLM de pago y libro de cuentas del presupuesto.

    uv run --project ai-module-py python tools/experiments/cost.py experiments/<id> [...]

El coste sale de los tokens que devuelve la API en cada llamada (`llm_trace.jsonl`) y de los
precios del perfil (`llm.pricing`, USD por millón de tokens). Una llamada que no llegó a devolver
`usage` (un tiempo agotado, un error) se cuenta con una **cota superior**: el prompt de la llamada
anterior a precio de entrada y `max_tokens` a precio de salida; se marca como estimada.

El libro (`experiments/e5-ledger.json`) suma lo gastado en todas las matrices y pruebas de la fase
y es lo que mira `run_matrix --budget-usd` antes de lanzar cada ejecución.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "experiments" / "e5-ledger.json"
# Coste por ejecución (USD) cuando aún no hay ninguna medida del mismo modelo y escenario: la cifra
# pesimista del presupuesto de la fase, con la serie B un 50 % por encima.
DEFAULT_ESTIMATE = {
    ("haiku", "demo"): 0.035,
    ("haiku", "faults"): 0.05,
    ("sonnet", "demo"): 0.45,
    ("sonnet", "faults"): 0.65,
}
SERIES_B_FACTOR = 1.5
MARGIN = 1.2


def call_cost(
    pricing: dict[str, float], prompt: int, cache_read: int, cache_write: int, output: int
) -> float:
    """Coste en USD de una llamada. `prompt` incluye lo leído y lo escrito en caché."""
    fresh = max(prompt - cache_read - cache_write, 0)
    return (
        fresh * pricing["input"]
        + cache_write * pricing["cache_write"]
        + cache_read * pricing["cache_read"]
        + output * pricing["output"]
    ) / 1_000_000


def trace_cost(trace: Path, pricing: dict[str, float]) -> dict[str, Any]:
    """Tokens y coste de un `llm_trace.jsonl`, por agente y en total."""
    total = {
        "calls": 0,
        "estimated_calls": 0,
        "prompt": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
        "reasoning": 0,
        "cost_usd": 0.0,
        "by_agent": {},
    }
    for line in trace.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        agent = total["by_agent"].setdefault(record["agent"], {"calls": 0, "cost_usd": 0.0})
        max_tokens = (record.get("sampling") or {}).get("max_tokens", 0)
        last_prompt = 0
        for call in record.get("calls", []):
            if call.get("prompt_tokens"):
                cost = call_cost(
                    pricing,
                    call["prompt_tokens"],
                    call.get("cached_tokens") or 0,
                    call.get("cache_write_tokens") or 0,
                    call["completion_tokens"],
                )
                total["prompt"] += call["prompt_tokens"]
                total["cache_read"] += call.get("cached_tokens") or 0
                total["cache_write"] += call.get("cache_write_tokens") or 0
                total["output"] += call["completion_tokens"]
                total["reasoning"] += call.get("reasoning_tokens") or 0
                last_prompt = call["prompt_tokens"]
            else:  # sin `usage`: cota superior
                cost = (last_prompt * pricing["input"] + max_tokens * pricing["output"]) / 1e6
                total["estimated_calls"] += 1
            total["calls"] += 1
            total["cost_usd"] += cost
            agent["calls"] += 1
            agent["cost_usd"] += cost
    return total


def load_ledger(path: Path = LEDGER) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"budget_usd": 3.0, "entries": []}


def save_ledger(ledger: dict[str, Any], path: Path = LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def spent_usd(ledger: dict[str, Any]) -> float:
    return sum(e["cost_usd"] for e in ledger["entries"])


def model_key(model: str) -> str:
    return "sonnet" if "sonnet" in model else "haiku"


def estimate_usd(ledger: dict[str, Any], model: str, scenario: str, series_b: bool) -> float:
    """Lo que puede costar la próxima ejecución: la mayor del mismo modelo y escenario ya medida,
    con margen, o la cifra pesimista del presupuesto si todavía no hay ninguna."""
    seen = [
        e["cost_usd"]
        for e in ledger["entries"]
        if e.get("kind") == "run" and e["model"] == model and e["scenario"] == scenario
    ]
    if seen:
        return max(seen) * MARGIN
    base = DEFAULT_ESTIMATE.get((model_key(model), scenario), 0.65)
    return base * (SERIES_B_FACTOR if series_b else 1.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folders", nargs="*", type=Path, help="carpetas de experimentos")
    args = parser.parse_args(argv)
    ledger = load_ledger()
    print(f"spent {spent_usd(ledger):.4f} USD of {ledger['budget_usd']:.2f}")
    for entry in ledger["entries"]:
        print(
            f"  {entry.get('experiment', '-'):<22} {entry.get('profile', '-'):<24} "
            f"{entry.get('scenario', '-'):<7} r{entry.get('rep', '-')} {entry['cost_usd']:.4f}"
            f"{' (estimated calls)' if entry.get('estimated_calls') else ''}"
        )
    for folder in args.folders:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        print(f"{folder.name}: {sum(r.get('cost_usd', 0) for r in manifest['runs']):.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
