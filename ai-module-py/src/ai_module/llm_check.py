"""Comprobación previa del servidor LLM.

    uv run --project ai-module-py python -m ai_module.llm_check [--profile PERFIL]
    uv run --project ai-module-py python -m ai_module.llm_check --latency CARPETA…

Comprueba contra el vLLM real lo que el módulo da por hecho: tool calls con y sin streaming,
`stream_options.include_usage`, `timeout` de `AsyncOpenAI`, parámetros de `extra_body` y
`max_tokens`; y, con `--latency CARPETA…`, resume la latencia de las invocaciones del monitor
guardadas en las trazas de esas ejecuciones (para fijar `max_invocation_s` y `llm_timeout_s`).

Con `--profile PERFIL` usa el modelo del perfil y, si su servidor tiene parser de razonamiento,
añade las pruebas de razonamiento: se pide y se apaga por petición, `required` con razonamiento,
streaming, y **si la plantilla recibe el razonamiento que se le devuelve** en el mensaje del
asistente (comparando `usage.prompt_tokens` sin el campo y con `reasoning` o `reasoning_content`).
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
from .agent.llm import REASONING_INPUT_FIELD, reasoning_of, reasoning_tokens_of
from .agent.profiles import DEFAULT_PROFILES, load_profile

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


REASONING_SAMPLING: dict[str, Any] = {
    "temperature": 0.6, "top_p": 0.95, "extra_body": {"top_k": 20},
}  # fmt: skip
WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Returns the weather of a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}
# Un razonamiento largo y reconocible: si la plantilla lo pinta, el prompt crece en unos
# cientos de tokens.
FAKE_REASONING = " ".join(
    f"Step {i}: the user asked for the weather in Madrid, so I must call get_weather."
    for i in range(30)
)


async def check_reasoning(client: AsyncOpenAI, model: str) -> list[tuple[str, bool, str]]:
    """Pruebas de razonamiento (servidor con `--reasoning-parser`)."""
    results: list[tuple[str, bool, str]] = []

    def kwargs(enable: bool, **extra: Any) -> dict[str, Any]:
        sampling = {**REASONING_SAMPLING, "extra_body": {
            "top_k": 20, "chat_template_kwargs": {"enable_thinking": enable},
        }}  # fmt: skip
        return {"model": model, **sampling, **extra}

    async def attempt(name: str, check: Any) -> None:
        try:
            ok, detail = await check()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        results.append((name, ok, detail))

    question = [{"role": "user", "content": "What is 17 times 23? Answer briefly."}]
    weather = [{"role": "user", "content": "What is the weather in Madrid? Use the tool."}]

    async def thinking_on() -> tuple[bool, str]:
        r = await client.chat.completions.create(messages=question, max_tokens=1500, **kwargs(True))
        message = r.choices[0].message
        reasoning = reasoning_of(message)
        tokens = reasoning_tokens_of(r.usage)
        detail = (
            f"reasoning={len(reasoning)} chars, content={(message.content or '')[:40]!r}, "
            f"completion_tokens={r.usage.completion_tokens if r.usage else '?'}, "
            f"usage reasoning_tokens={tokens if tokens is not None else 'not reported'}"
        )
        return bool(reasoning.strip()) and "<think>" not in (message.content or ""), detail

    async def thinking_off() -> tuple[bool, str]:
        r = await client.chat.completions.create(messages=question, max_tokens=300, **kwargs(False))
        message = r.choices[0].message
        reasoning = reasoning_of(message)
        return (
            not reasoning.strip(),
            f"reasoning={len(reasoning)} chars, content={message.content!r}",
        )

    async def required_with_reasoning() -> tuple[bool, str]:
        r = await client.chat.completions.create(
            messages=weather,
            tools=[WEATHER],
            tool_choice="required",
            max_tokens=1500,
            **kwargs(True),
        )
        message = r.choices[0].message
        calls = message.tool_calls or []
        reasoning = reasoning_of(message)
        return bool(calls) and bool(reasoning.strip()), (
            f"tool_calls={len(calls)}, reasoning={len(reasoning)} chars"
        )

    async def stream_reasoning() -> tuple[bool, str]:
        stream = await client.chat.completions.create(
            messages=question, max_tokens=1500, stream=True,
            stream_options={"include_usage": True}, **kwargs(True),
        )  # fmt: skip
        reasoning = content = ""
        async for chunk in stream:
            if chunk.choices:
                reasoning += reasoning_of(chunk.choices[0].delta)
                content += chunk.choices[0].delta.content or ""
        return bool(
            reasoning.strip()
        ), f"delta.reasoning={len(reasoning)} chars, content={len(content)} chars"

    def conversation(field: str | None, *, reminder: bool) -> list[dict[str, Any]]:
        assistant: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "Madrid"}'},
                }
            ],
        }
        if field:
            assistant[field] = FAKE_REASONING
        messages = [
            *weather,
            assistant,
            {"role": "tool", "tool_call_id": "call-1", "content": '{"temp_c": 21}'},
        ]
        if reminder:  # el recordatorio del motor es un mensaje de usuario
            messages.append({"role": "user", "content": "Reminder: answer with the result."})
        return messages

    async def prompt_tokens(field: str | None, reminder: bool) -> int:
        r = await client.chat.completions.create(
            messages=conversation(field, reminder=reminder), tools=[WEATHER], max_tokens=1,
            **kwargs(True),
        )  # fmt: skip
        return r.usage.prompt_tokens if r.usage else -1

    async def template_receives_reasoning() -> tuple[bool, str]:
        base = await prompt_tokens(None, False)
        grown: dict[str, int] = {}
        for field in ("reasoning", "reasoning_content"):
            grown[field] = await prompt_tokens(field, False) - base
        # unas 30 frases de ~16 tokens: si la plantilla lo pinta, crece ≥ 200 tokens
        works = [f for f, extra in grown.items() if extra >= 200]
        detail = (
            f"prompt_tokens without the field={base}; extra with `reasoning`={grown['reasoning']}, "
            f"with `reasoning_content`={grown['reasoning_content']}; "
            f"used by the engine: `{REASONING_INPUT_FIELD}`"
        )
        return REASONING_INPUT_FIELD in works, detail

    async def reasoning_after_reminder() -> tuple[bool, str]:
        """Informativo: tras un mensaje de usuario la plantilla deja de pintar el razonamiento."""
        base = await prompt_tokens(None, True)
        extra = await prompt_tokens(REASONING_INPUT_FIELD, True) - base
        return True, (
            f"with a final user message (the engine's reminder), the field adds {extra} tokens "
            f"({'it is NOT shown to the model' if extra < 50 else 'it is still shown'})"
        )

    await attempt("razonamiento pedido (`enable_thinking: true`)", thinking_on)
    await attempt("razonamiento apagado (`enable_thinking: false`)", thinking_off)
    await attempt("`tool_choice: required` con razonamiento", required_with_reasoning)
    await attempt("streaming entrega `delta.reasoning`", stream_reasoning)
    await attempt(
        f"la plantilla recibe el razonamiento devuelto (`{REASONING_INPUT_FIELD}`)",
        template_receives_reasoning,
    )
    await attempt("el recordatorio (mensaje de usuario) corta la cadena", reasoning_after_reminder)
    return results


async def check_all(
    base_url: str, api_key: str, model: str, reasoning: bool = False
) -> list[tuple[str, bool, str]]:
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
    if reasoning:
        results += await check_reasoning(client, model)
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
    parser.add_argument("--profile", help="perfil de model-profiles/ (modelo y razonamiento)")
    parser.add_argument("--latency", nargs="*", type=Path, help="carpetas runs/<esc>/<run_id>")
    args = parser.parse_args(argv)
    if args.latency:
        print(latency_summary(args.latency))
        return 0
    profile = load_profile(args.profile, DEFAULT_PROFILES) if args.profile else None
    assets = Assets(profile=profile)
    llm = assets.llm
    reasoning = bool(profile and profile.server.get("reasoning_parser"))
    name = f" · perfil {profile.name}" if profile else ""
    print(f"openai {openai.__version__} · {llm.base_url} · {llm.model}{name}")
    results = asyncio.run(check_all(llm.base_url, llm.api_key, llm.model, reasoning))
    for name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name}: {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
