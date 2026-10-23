"""Cliente del LLM: SDK oficial `openai` (Chat Completions) contra vLLM, sin frameworks de agentes.

Cada petición lleva siempre explícitos `temperature`, `top_p`, `max_tokens` y `tool_choice`, y en
`extra_body` los parámetros que no son de OpenAI (`top_k`, `repetition_penalty`). Una llamada a
tool se detecta por `message.tool_calls` no vacío, **nunca** por `finish_reason` (que solo se
guarda como anotación).
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import AsyncOpenAI

# Nombre con el que se devuelve el razonamiento al modelo en el mensaje del asistente. vLLM lo
# entrega como `reasoning`; la plantilla de Qwen3 lee `reasoning_content` (ver `llm_check`).
REASONING_INPUT_FIELD = "reasoning_content"

Messages = list[dict[str, Any]]
DeltaCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    """Texto JSON tal como lo escribió el modelo (puede no ser JSON válido)."""


@dataclass
class LlmResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    reasoning: str = ""
    """Texto del razonamiento de esta llamada (vacío si el modelo no razona)."""
    reasoning_tokens: int | None = None
    """Tokens de razonamiento si vLLM los da en `usage`, si no `None`."""

    def assistant_message(self) -> dict[str, Any]:
        """El mensaje del asistente para devolver al modelo en la siguiente petición."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.reasoning:
            message[REASONING_INPUT_FIELD] = self.reasoning
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in self.tool_calls
            ]
        return message


class LlmClient(Protocol):
    model: str

    async def complete(
        self,
        messages: Messages,
        tools: list[dict[str, Any]],
        sampling: dict[str, Any],
        *,
        stream: bool = False,
        on_delta: DeltaCallback | None = None,
        timeout_s: float | None = None,
    ) -> LlmResponse: ...


class OpenAiLlm:
    """`LlmClient` real. `timeout_s` de cada petición manda sobre el del cliente."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 60.0) -> None:
        self.model = model
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0
        )

    async def complete(
        self,
        messages: Messages,
        tools: list[dict[str, Any]],
        sampling: dict[str, Any],
        *,
        stream: bool = False,
        on_delta: DeltaCallback | None = None,
        timeout_s: float | None = None,
    ) -> LlmResponse:
        params: dict[str, Any] = {"model": self.model, "messages": messages, **sampling}
        if tools:
            params["tools"] = tools
        else:
            params.pop("tool_choice", None)  # sin tools, vLLM rechaza tool_choice
        if timeout_s is not None:
            params["timeout"] = timeout_s
        start = time.monotonic()
        if not stream:
            completion = await self._client.chat.completions.create(**params)
            choice = completion.choices[0]
            message = choice.message
            calls = [
                ToolCall(c.id, c.function.name, c.function.arguments)  # type: ignore[union-attr]
                for c in (message.tool_calls or [])
            ]
            usage = completion.usage
            return LlmResponse(
                reasoning=reasoning_of(message),
                reasoning_tokens=reasoning_tokens_of(usage),
                content=message.content or "",
                tool_calls=calls,
                finish_reason=choice.finish_reason,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_s=time.monotonic() - start,
            )
        return await self._stream(params, on_delta, start)

    async def _stream(
        self, params: dict[str, Any], on_delta: DeltaCallback | None, start: float
    ) -> LlmResponse:
        """Streaming: el texto se entrega a `on_delta` según llega; las tool calls se acumulan por
        `index` (el nombre y los argumentos llegan troceados)."""
        stream = await self._client.chat.completions.create(
            stream=True, stream_options={"include_usage": True}, **params
        )
        content = reasoning = ""
        reasoning_tokens: int | None = None
        calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        prompt_tokens = completion_tokens = 0
        async for chunk in stream:
            if chunk.usage is not None:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
                reasoning_tokens = reasoning_tokens_of(chunk.usage)
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            delta = choice.delta
            reasoning += reasoning_of(delta)  # no se entrega a `on_delta`: la web no lo ve
            if delta.content:
                content += delta.content
                if on_delta is not None:
                    await on_delta(delta.content)
            for part in delta.tool_calls or []:
                call = calls.setdefault(part.index, {"id": "", "name": "", "arguments": ""})
                call["id"] += part.id or ""
                if part.function:
                    call["name"] += part.function.name or ""
                    call["arguments"] += part.function.arguments or ""
        return LlmResponse(
            content=content,
            tool_calls=[
                ToolCall(c["id"], c["name"], c["arguments"]) for _, c in sorted(calls.items())
            ],
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_s=time.monotonic() - start,
            reasoning=reasoning,
            reasoning_tokens=reasoning_tokens,
        )


def reasoning_of(message: Any) -> str:
    """Razonamiento de un mensaje o delta: vLLM lo entrega como `reasoning` (versiones
    anteriores, `reasoning_content`)."""
    return getattr(message, "reasoning", None) or getattr(message, "reasoning_content", None) or ""


def reasoning_tokens_of(usage: Any) -> int | None:
    details = getattr(usage, "completion_tokens_details", None)
    value = getattr(details, "reasoning_tokens", None)
    return value if isinstance(value, int) else None
