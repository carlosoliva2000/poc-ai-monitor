"""Cliente del vLLM local: SDK `openai`, Chat Completions (regla 6 del proyecto).

`temperature` y `top_p` van siempre explícitos; el resto del muestreo, en `extra_body`. Una llamada
a tool se detecta con `message.tool_calls` no vacío, nunca con `finish_reason`. El tiempo máximo
lo pone `asyncio.wait_for` (cancela la petición: vLLM aborta al cerrarse la conexión).
"""

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from openai import AsyncOpenAI

from .config import LlmConfig, RoleConfig


class LlmError(Exception):
    """El LLM no ha contestado (red, tiempo o respuesta vacía)."""


@dataclass(frozen=True)
class LlmResult:
    text: str
    tool_name: str | None
    tool_args: dict[str, Any] | None
    latency_s: float
    tokens_in: int = 0
    tokens_out: int = 0


class LlmPort(Protocol):
    async def complete(
        self, role: RoleConfig, system: str, user: str, tools: list[dict[str, Any]] | None = None
    ) -> LlmResult: ...


class VllmClient:
    def __init__(self, config: LlmConfig) -> None:
        self.config = config
        self.client = AsyncOpenAI(base_url=config.base_url, api_key=config.api_key, max_retries=0)

    async def check_model(self) -> None:
        """Comprueba que vLLM sirve el modelo configurado (si no, el proceso para con un error)."""
        try:
            models = await asyncio.wait_for(self.client.models.list(), timeout=5)
        except Exception as exc:
            raise LlmError(f"vLLM does not answer at {self.config.base_url}: {exc}") from exc
        served = [m.id for m in models.data]
        if self.config.model not in served:
            raise LlmError(f"vLLM serves {served}, not {self.config.model}")

    async def complete(
        self, role: RoleConfig, system: str, user: str, tools: list[dict[str, Any]] | None = None
    ) -> LlmResult:
        extra: dict[str, Any] = {
            "top_k": self.config.top_k,
            "repetition_penalty": self.config.repetition_penalty,
        }
        if not self.config.reasoning:
            extra["chat_template_kwargs"] = {"enable_thinking": False}
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": role.temperature,
            "top_p": role.top_p,
            "max_tokens": role.max_tokens,
            "extra_body": extra,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = (
                "required"  # la respuesta es siempre una llamada; nunca por nombre
            )
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**kwargs), timeout=role.timeout_s
            )
        except TimeoutError as exc:
            raise LlmError(f"timeout after {role.timeout_s:.0f} s") from exc
        except Exception as exc:  # error de red o del servidor
            raise LlmError(str(exc)) from exc
        latency = time.monotonic() - started
        message = response.choices[0].message
        name: str | None = None
        args: dict[str, Any] | None = None
        if message.tool_calls:  # nunca por finish_reason
            call = message.tool_calls[0]
            name = call.function.name
            try:
                args = json.loads(call.function.arguments)
            except ValueError as exc:
                raise LlmError(f"tool arguments are not JSON: {exc}") from exc
        usage = response.usage
        return LlmResult(
            text=(message.content or "").strip(),
            tool_name=name,
            tool_args=args,
            latency_s=latency,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
        )
