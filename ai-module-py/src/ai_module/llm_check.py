"""Comprobación previa del servidor LLM.

    uv run --project ai-module-py python -m ai_module.llm_check [--latency CARPETA…]

Comprueba contra el vLLM real lo que el módulo da por hecho: tool calls con y sin streaming,
`stream_options.include_usage`, `timeout` de `AsyncOpenAI`, parámetros de `extra_body` y
`max_tokens`; y, con `--latency CARPETA…`, resume la latencia de las invocaciones del monitor
guardadas en las trazas de esas ejecuciones (para fijar `max_invocation_s` y `llm_timeout_s`).
"""

import argparse
import asyncio
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

import openai
from openai import AsyncOpenAI

from .agent.assets import Assets

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Devuelve el tiempo de una ciudad.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}
MESSAGES = [{"role": "user", "content": "¿Qué tiempo hace en Madrid? Usa la herramienta."}]


async def check_all(base_url: str, api_key: str, model: str) -> list[tuple[str, bool, str]]:
    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=0)
    base: dict[str, Any] = {"model": model, "messages": MESSAGES, "temperature": 0, "top_p": 1.0}
    results: list[tuple[str, bool, str]] = []

    async def attempt(name: str, check: Any) -> None:
        try:
            ok, detail = await check()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        results.append((name, ok, detail))

    async def tool_call_no_stream() -> tuple[bool, str]:
        r = await client.chat.completions.create(
            tools=[TOOL], tool_choice="auto", max_tokens=200, **base
        )
        choice = r.choices[0]
        calls = choice.message.tool_calls or []
        return bool(calls), f"tool_calls={len(calls)}, finish_reason={choice.finish_reason!r}"

    async def tool_call_stream() -> tuple[bool, str]:
        stream = await client.chat.completions.create(
            tools=[TOOL], tool_choice="auto", max_tokens=200, stream=True,
            stream_options={"include_usage": True}, **base,
        )  # fmt: skip
        calls: dict[int, dict[str, str]] = {}
        usage = None
        finish = None
        async for chunk in stream:
            usage = chunk.usage or usage
            if not chunk.choices:
                continue
            finish = chunk.choices[0].finish_reason or finish
            for part in chunk.choices[0].delta.tool_calls or []:
                call = calls.setdefault(part.index, {"name": "", "arguments": ""})
                call["name"] += (part.function.name or "") if part.function else ""
                call["arguments"] += (part.function.arguments or "") if part.function else ""
        parsed = [json.loads(c["arguments"]) for c in calls.values()]
        has_usage = "sí" if usage else "no"
        detail = f"tool_calls={len(calls)} args={parsed} usage={has_usage} finish={finish!r}"
        return bool(calls) and usage is not None and bool(parsed), detail

    async def usage_in_stream() -> tuple[bool, str]:
        stream = await client.chat.completions.create(
            max_tokens=20, stream=True, stream_options={"include_usage": True}, **base
        )
        usage = None
        async for chunk in stream:
            usage = chunk.usage or usage
        return (
            usage is not None,
            f"usage={usage and (usage.prompt_tokens, usage.completion_tokens)}",
        )

    async def timeout() -> tuple[bool, str]:
        try:
            await client.chat.completions.create(max_tokens=50, timeout=0.001, **base)
        except openai.APITimeoutError as exc:
            return True, f"{type(exc).__name__} con timeout=0.001 por petición"
        return False, "no hubo timeout"

    async def extra_body() -> tuple[bool, str]:
        out = []
        for extra in ({"top_k": -1, "repetition_penalty": 1.05}, {"top_k": 0}, {"top_k": 20}):
            r = await client.chat.completions.create(max_tokens=10, extra_body=extra, **base)
            out.append(f"{extra} -> {r.choices[0].message.content!r}")
        return True, "; ".join(out)

    async def tool_choice_required() -> tuple[bool, str]:
        plain = [{"role": "user", "content": "Hola, ¿qué tal?"}]
        r = await client.chat.completions.create(
            tools=[TOOL], tool_choice="required", max_tokens=200,
            **{**base, "messages": plain},
        )  # fmt: skip
        choice = r.choices[0]
        calls = choice.message.tool_calls or []
        detail = (
            f"sin pedirlo, tool_calls={len(calls)}, content={choice.message.content!r}, "
            f"finish_reason={choice.finish_reason!r}"
        )
        return bool(calls), detail

    async def max_tokens() -> tuple[bool, str]:
        r = await client.chat.completions.create(max_tokens=5, **base)
        n = r.usage.completion_tokens if r.usage else -1
        return (
            n <= 5,
            f"max_tokens=5 -> completion_tokens={n}, finish_reason={r.choices[0].finish_reason!r}",
        )

    async def max_completion_tokens() -> tuple[bool, str]:
        r = await client.chat.completions.create(max_completion_tokens=5, **base)
        n = r.usage.completion_tokens if r.usage else -1
        return n <= 5, f"max_completion_tokens=5 -> completion_tokens={n}"

    async def temperature_zero_is_deterministic() -> tuple[bool, str]:
        texts = []
        for _ in range(3):
            r = await client.chat.completions.create(
                max_tokens=60, extra_body={"top_k": -1, "repetition_penalty": 1.0}, **base
            )
            texts.append(r.choices[0].message.content)
        return len(set(texts)) == 1, f"{len(set(texts))} respuestas distintas de 3"

    await attempt("tool calls sin streaming (`message.tool_calls`)", tool_call_no_stream)
    await attempt(
        "tool calls con streaming (deltas por `index`) y `include_usage`", tool_call_stream
    )
    await attempt("`stream_options.include_usage` en texto", usage_in_stream)
    await attempt("`timeout` por petición de `AsyncOpenAI`", timeout)
    await attempt("`extra_body` con `top_k` -1 / 0 / 20 y `repetition_penalty`", extra_body)
    await attempt("`tool_choice: required` (llamada garantizada)", tool_choice_required)
    await attempt("`max_tokens`", max_tokens)
    await attempt("`max_completion_tokens`", max_completion_tokens)
    await attempt(
        "temperature 0 con `top_k -1`: respuestas idénticas", temperature_zero_is_deterministic
    )
    return results


def latency_summary(folders: list[Path]) -> str:
    """Latencia de las invocaciones del monitor con LLM de esas ejecuciones."""
    rows: list[tuple[str, float, int, int, int]] = []
    for folder in folders:
        path = folder / "llm_trace.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["agent"] != "monitor" or record.get("deterministic"):
                continue
            calls = record["calls"]
            rows.append(
                (
                    f"{folder.parent.name}/{record['invocation_id']}",
                    record["duration_s"],
                    len(calls),
                    max((c["prompt_tokens"] for c in calls), default=0),
                    sum(c["completion_tokens"] for c in calls),
                )
            )
    if not rows:
        return "Sin invocaciones del monitor en esas trazas."
    durations = sorted(r[1] for r in rows)

    def pct(q: float) -> float:
        return durations[min(len(durations) - 1, math.ceil(q * len(durations)) - 1)]

    lines = [
        "| Invocación | Duración | Llamadas | Prompt máx. | Tokens generados |",
        "|---|---|---|---|---|",
        *(f"| {n} | {d:.1f} s | {c} | {p} | {g} |" for n, d, c, p, g in rows),
        "",
        f"n={len(rows)} · media {statistics.fmean(durations):.1f} s · p50 {pct(0.5):.1f} s · "
        f"p95 {pct(0.95):.1f} s · máx. {durations[-1]:.1f} s",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latency", nargs="*", type=Path, help="carpetas runs/<esc>/<run_id>")
    args = parser.parse_args(argv)
    if args.latency:
        print(latency_summary(args.latency))
        return 0
    assets = Assets()
    llm = assets.llm
    print(f"openai {openai.__version__} · {llm.base_url} · {llm.model}")
    results = asyncio.run(check_all(llm.base_url, llm.api_key, llm.model))
    for name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name}: {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
