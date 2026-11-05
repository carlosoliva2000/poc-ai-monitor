"""E5 · prueba real mínima de un perfil de pago, antes de lanzar ninguna matriz.

    LLM_RUN_CAP_USD=0.25 uv run --project ai-module-py --with-editable ./cloud-adapter \\
        python tools/experiments/e5_probe.py claude-haiku-5-5 [claude-haiku-5-5-a0 ...]

Hace la secuencia más corta que ejercita lo que usa el monitor, con el prompt de sistema y las
tools reales: (1) una petición con tools, (2) la respuesta con el resultado de la tool y los
bloques de razonamiento devueltos tal cual (lee de la caché el prefijo), (3) otra petición con
menos tools (la última iteración del motor), que debe aceptarse sin error. Imprime latencia,
tokens y coste de cada llamada (nunca la clave) y anota el gasto en el libro de cuentas.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ai_module.agent.assets import Assets
from ai_module.agent.llm import LlmResponse, load_adapter
from ai_module.agent.profiles import load_profile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cost  # noqa: E402

USER = (
    "Probe of the monitoring pipeline (not a real detection). Call get_my_alerts once to see "
    "the open alerts and then say in one short sentence what you found."
)
TOOL_RESULT = {"alerts": [], "note": "no alert has been published yet"}


def show(label: str, r: LlmResponse, price: dict[str, float]) -> float:
    usd = cost.call_cost(
        price,
        r.prompt_tokens,
        r.cached_tokens or 0,
        r.cache_write_tokens or 0,
        r.completion_tokens,
    )
    print(
        f"  {label}: {r.latency_s:.1f} s · prompt {r.prompt_tokens} "
        f"(read {r.cached_tokens}, written {r.cache_write_tokens}) · output {r.completion_tokens} "
        f"(reasoning {r.reasoning_tokens}) · {r.finish_reason} · "
        f"tools {[c.name for c in r.tool_calls]} · retries {r.retries} · {usd:.5f} USD"
    )
    if r.reasoning:
        print(f"      reasoning summary: {r.reasoning[:160]!r}")
    if r.content:
        print(f"      text: {r.content[:160]!r}")
    return usd


async def probe(name: str) -> float:
    profile = load_profile(name)
    assets = Assets(profile=profile)
    config = assets.agent("monitor")
    llm = load_adapter(
        assets.llm.adapter or "",
        model=assets.llm.model,
        api_key_file=assets.llm.api_key_file,
        pricing=assets.llm.pricing,
    )
    await llm.check()  # type: ignore[attr-defined]
    assert assets.llm.pricing
    sampling = config.sampling()
    tools = assets.tool_schemas(config.active_tools)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": assets.system_prompt(config)},
        {"role": "user", "content": USER},
    ]
    print(f"{name}: thinking={config.thinking} tool_choice={config.tool_choice}")
    total = 0.0
    first = await llm.complete(messages, tools, sampling, timeout_s=config.llm_timeout_s)
    total += show("1 request     ", first, assets.llm.pricing)
    if first.tool_calls:
        messages.append(first.assistant_message())
        for call in first.tool_calls:
            result = json.dumps(TOOL_RESULT)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        second = await llm.complete(messages, tools, sampling, timeout_s=config.llm_timeout_s)
        total += show("2 tool result ", second, assets.llm.pricing)
        messages.append(second.assistant_message())
        if second.tool_calls:
            for call in second.tool_calls:
                result = json.dumps(TOOL_RESULT)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        else:
            messages.append({"role": "user", "content": "Reminder: answer with a tool call."})
        final_names = set(config.final_tools)
        fewer = [t for t in tools if t["function"]["name"] in final_names]
        third = await llm.complete(messages, fewer, sampling, timeout_s=config.llm_timeout_s)
        total += show("3 fewer tools ", third, assets.llm.pricing)
        # 4: se restablecen las tools con un razonamiento en el historial (el cambio de tools de
        # la petición anterior a esta es lo que invalida los bloques si no se descartan)
        thinking_in_history = any(
            b.get("type") == "thinking"
            for b in (third.raw_blocks or []) + (second.raw_blocks or [])
        )
        messages.append(third.assistant_message())
        for call in third.tool_calls:
            result = json.dumps({"ok": True, "note": "probe: nothing was published"})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        if not third.tool_calls:
            messages.append({"role": "user", "content": "Reminder: answer with a tool call."})
        fourth = await llm.complete(messages, tools, sampling, timeout_s=config.llm_timeout_s)
        total += show("4 tools back  ", fourth, assets.llm.pricing)
        print(f"      thinking blocks were in the replayed history: {thinking_in_history}")
    else:
        print("  (the model answered without calling a tool: replay not exercised)")
    ledger = cost.load_ledger()
    ledger["entries"].append(
        {"kind": "probe", "experiment": "e5-probe", "profile": name, "cost_usd": round(total, 5)}
    )
    cost.save_ledger(ledger)
    print(f"  total {total:.5f} USD · ledger {cost.spent_usd(ledger):.4f} USD")
    return total


async def main(names: list[str]) -> None:
    for name in names:
        await probe(name)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
