"""Cliente LLM de la API de mensajes de Anthropic (SDK oficial `anthropic`), detrás del mismo puerto
`LlmClient` que `OpenAiLlm`. El bucle de tools, las tools y los guardrails no cambian.

Lo que cambia respecto a Chat Completions (documentación oficial, comprobada el 05/11/2026):
- `temperature`, `top_p` y `top_k` con valores no por defecto dan error 400 en estos modelos, así
  que **no se envían** (excepción documentada a la regla de muestreo explícito); tampoco
  `repetition_penalty` ni `presence_penalty`, que no existen.
- El razonamiento cuenta dentro de `max_tokens`, se factura como salida y su texto nunca es el
  crudo: con `display: "summarized"` llega un resumen, que es lo que se guarda en la traza.
- Los bloques de razonamiento se devuelven sin modificar en el mensaje del asistente
  (`LlmResponse.raw_blocks`). Si el historial cambia (p. ej. la última iteración ofrece menos
  tools), `block_binding.prefix_mismatch_behavior = "drop_block"` hace que la API los descarte sin
  error. Con `between_tools` esa opción no existe: se quitan los bloques del historial.
- `tool_choice`: `required` → `any` (Haiku 5.5 lo admite; Sonnet 5.5 da 400 y va con `auto`).
- Caché de prompts con puntos explícitos: el final del sistema y el último bloque del último
  mensaje.
- Reintentos propios (el SDK, con `max_retries=0`): 429 con espera, 5xx, 529 y fallos de conexión,
  con retroceso. Un error que repetir no arregla (400, 401, 402, 403, 404, o el tope de gasto)
  lanza `FatalLlmError` y el cliente no vuelve a hacer peticiones.
"""

import asyncio
import json
import logging
import os
import stat
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anthropic

from ai_module.agent.llm import (
    DeltaCallback,
    FatalLlmError,
    LlmResponse,
    Messages,
    ModelMismatchError,
    ToolCall,
)

log = logging.getLogger(__name__)

DEFAULT_KEY_FILE = "~/.config/poc-ai-monitor/anthropic.key"
BINDING_BETA = "thinking-binding-controls-2026-08-01"
RETRY_DELAYS_S = (1.0, 2.0, 4.0, 8.0)
FINISH_REASONS = {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length"}
CACHE = {"type": "ephemeral"}
ENV_RUN_CAP = "LLM_RUN_CAP_USD"


def read_key(path: str | None) -> str:
    """Lee la clave de un fichero fuera del repositorio. No la guarda en ningún otro sitio."""
    file = Path(path or DEFAULT_KEY_FILE).expanduser()
    try:
        mode = stat.S_IMODE(file.stat().st_mode)
        key = file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ModelMismatchError(f"cannot read the API key file {file}: {exc.strerror}") from exc
    if mode & 0o077:
        raise ModelMismatchError(f"the API key file {file} must have permissions 600")
    if not key:
        raise ModelMismatchError(f"the API key file {file} is empty")
    return key


def to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Esquemas de `tools.json` (formato de funciones) → `tools` de la API de mensajes, con el
    mismo nombre, descripción y esquema de parámetros."""
    out = []
    for tool in tools:
        function = tool["function"]
        out.append(
            {
                "name": function["name"],
                "description": function.get("description", ""),
                "input_schema": function["parameters"],
            }
        )
    return out


def _json_or_empty(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text) if text and text.strip() else {}
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _assistant_blocks(message: dict[str, Any], keep_thinking: bool) -> list[dict[str, Any]]:
    raw = message.get("raw_blocks")
    if raw is not None:
        return [b for b in raw if keep_thinking or b.get("type") not in _THINKING_TYPES]
    blocks: list[dict[str, Any]] = []
    if message.get("content"):
        blocks.append({"type": "text", "text": message["content"]})
    for call in message.get("tool_calls") or []:
        function = call["function"]
        blocks.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": function["name"],
                "input": _json_or_empty(function.get("arguments", "")),
            }
        )
    return blocks


_THINKING_TYPES = ("thinking", "redacted_thinking")


def to_anthropic_messages(
    messages: Messages, *, keep_thinking: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`messages` de Chat Completions → (bloques del sistema, mensajes de la API de mensajes).

    Los resultados de tools consecutivos y el mensaje de usuario que les sigue (el recordatorio)
    van en un solo mensaje de usuario, con los resultados primero. Un mensaje del asistente
    sin contenido se omite."""
    system: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            if role == "user":
                results = [b for b in out[-1]["content"] if b["type"] == "tool_result"]
                rest = [b for b in out[-1]["content"] if b["type"] != "tool_result"]
                new_results = [b for b in blocks if b["type"] == "tool_result"]
                new_rest = [b for b in blocks if b["type"] != "tool_result"]
                out[-1]["content"] = [*results, *new_results, *rest, *new_rest]
            else:
                out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for message in messages:
        role = message["role"]
        if role == "system":
            system.append({"type": "text", "text": message["content"]})
        elif role == "user":
            push("user", [{"type": "text", "text": message["content"]}])
        elif role == "tool":
            push(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message["content"],
                    }
                ],
            )
        elif role == "assistant":
            push("assistant", _assistant_blocks(message, keep_thinking))
    return system, out


def _dump(block: Any) -> dict[str, Any]:
    return block.model_dump(mode="json", exclude_none=True)


class ClaudeLlm:
    """`LlmClient` real de la API de mensajes. `timeout_s` de cada petición manda."""

    def __init__(
        self,
        model: str,
        api_key_file: str | None = None,
        pricing: dict[str, float] | None = None,
        *,
        client: Any = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.model = model
        self.pricing = pricing
        self._sleep = sleep
        self._fatal: str | None = None
        self._spent_usd = 0.0
        cap = os.environ.get(ENV_RUN_CAP)
        self._run_cap_usd = float(cap) if cap else None
        if client is not None:
            self._client = client
        else:
            self._client = anthropic.AsyncAnthropic(
                api_key=read_key(api_key_file), max_retries=0, timeout=60.0
            )

    def __repr__(self) -> str:  # nunca se imprime la clave
        return f"ClaudeLlm(model={self.model!r})"

    async def check(self) -> None:
        """Comprueba la clave y el modelo con `GET /v1/models/{id}` (no consume tokens)."""
        try:
            await self._client.models.retrieve(self.model, timeout=15.0)
        except anthropic.APIStatusError as exc:
            raise ModelMismatchError(
                f"the API rejects the model {self.model} (HTTP {exc.status_code})"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ModelMismatchError(f"cannot reach the API ({type(exc).__name__})") from exc

    # --- petición -----------------------------------------------------------------------

    def _params(
        self, messages: Messages, tools: list[dict[str, Any]], sampling: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        extra = sampling.get("extra_body") or {}
        mode = extra.get("thinking_mode")
        betas: list[str] = []
        if mode == "disabled":
            thinking: dict[str, Any] = {"type": "disabled"}
        elif mode == "between_tools":
            thinking = {"type": "between_tools"}
        else:
            thinking = {
                "type": "adaptive",
                "display": "summarized",
                "block_binding": {"prefix_mismatch_behavior": "drop_block"},
            }
            betas.append(BINDING_BETA)
        system, converted = to_anthropic_messages(messages, keep_thinking=mode != "between_tools")
        if tools and system:
            system[-1]["cache_control"] = CACHE
        if tools and converted and converted[-1]["content"]:
            converted[-1]["content"][-1]["cache_control"] = CACHE
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": sampling["max_tokens"],
            "messages": converted,
            "thinking": thinking,
        }
        if system:
            params["system"] = system if tools else "\n\n".join(s["text"] for s in system)
        effort = extra.get("reasoning_effort")
        if effort:
            params["output_config"] = {"effort": effort}
        if tools:
            params["tools"] = to_anthropic_tools(tools)
            choice = "any" if sampling.get("tool_choice") == "required" else "auto"
            params["tool_choice"] = {"type": choice}
        if betas:
            params["betas"] = betas
        return params, betas

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
        if self._fatal is not None:
            raise FatalLlmError(f"no more requests after a fatal error: {self._fatal}")
        if self._run_cap_usd is not None and self._spent_usd >= self._run_cap_usd:
            self._fatal = f"the cost cap of this run ({self._run_cap_usd:.2f} USD) is reached"
            raise FatalLlmError(self._fatal)
        params, _ = self._params(messages, tools, sampling)
        start = time.monotonic()
        deadline = None if timeout_s is None else start + timeout_s
        retries: list[dict[str, Any]] = []
        attempt = 0
        while True:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError("API timeout")
            try:
                message = await self._send(params, stream, on_delta, remaining)
                break
            except anthropic.APIStatusError as exc:
                wait = self._classify(exc, attempt)
                retries.append({"status": exc.status_code, "wait_s": wait})
            except anthropic.APITimeoutError:
                raise
            except anthropic.APIConnectionError as exc:
                if attempt >= len(RETRY_DELAYS_S):
                    raise
                wait = RETRY_DELAYS_S[attempt]
                retries.append({"status": type(exc).__name__, "wait_s": wait})
            attempt += 1
            if deadline is not None and time.monotonic() + wait >= deadline:
                raise TimeoutError("API timeout while waiting to retry")
            log.warning("API retry %d in %.1f s (%s)", attempt, wait, retries[-1]["status"])
            await self._sleep(wait)
        response = self._response(message, time.monotonic() - start, retries)
        self._spent_usd += self.cost_usd(response)
        return response

    async def _send(
        self,
        params: dict[str, Any],
        stream: bool,
        on_delta: DeltaCallback | None,
        timeout_s: float | None,
    ) -> Any:
        options = {} if timeout_s is None else {"timeout": timeout_s}
        beta = self._client.beta.messages
        if not stream:
            return await beta.create(**params, **options)
        async with beta.stream(**params, **options) as events:
            async for text in events.text_stream:
                if on_delta is not None:
                    await on_delta(text)
            return await events.get_final_message()

    def _classify(self, exc: anthropic.APIStatusError, attempt: int) -> float:
        """Espera antes de reintentar un error de estado, o `FatalLlmError` si repetir no sirve."""
        status = exc.status_code
        if isinstance(exc, anthropic.EnforcedSpendLimitReachedError):
            self._fatal = "the monthly spend limit is reached (HTTP 429)"
        elif status in (400, 401, 402, 403, 404, 413, 422):
            self._fatal = f"HTTP {status} {type(exc).__name__}: {self._detail(exc)}"
        elif status == 429 or status >= 500:
            if attempt >= len(RETRY_DELAYS_S):
                raise exc
            header = exc.response.headers.get("retry-after") if exc.response else None
            try:
                return max(float(header), 0.0) if header else RETRY_DELAYS_S[attempt]
            except ValueError:
                return RETRY_DELAYS_S[attempt]
        else:
            self._fatal = f"HTTP {status} {type(exc).__name__}"
        raise FatalLlmError(self._fatal) from exc

    @staticmethod
    def _detail(exc: anthropic.APIStatusError) -> str:
        body = exc.body if isinstance(exc.body, dict) else {}
        error = body.get("error") if isinstance(body.get("error"), dict) else body
        return str(error.get("message", ""))[:300]

    # --- respuesta ----------------------------------------------------------------------

    def _response(
        self, message: Any, latency_s: float, retries: list[dict[str, Any]]
    ) -> LlmResponse:
        blocks = [_dump(b) for b in message.content]
        text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
        thinking = "\n".join(
            b["thinking"] for b in blocks if b["type"] == "thinking" and b.get("thinking")
        )
        calls = [
            ToolCall(b["id"], b["name"], json.dumps(b.get("input", {}), ensure_ascii=False))
            for b in blocks
            if b["type"] == "tool_use"
        ]
        usage = message.usage
        cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
        details = getattr(usage, "output_tokens_details", None)
        thinking_tokens = getattr(details, "thinking_tokens", None)
        stop = message.stop_reason
        finish = FINISH_REASONS.get(stop, stop)
        if stop == "refusal":
            category = getattr(message, "stop_details", None) or {}
            category = getattr(category, "category", None) or (
                category.get("category") if isinstance(category, dict) else None
            )
            finish = f"refusal:{category}" if category else "refusal"
        return LlmResponse(
            content=text,
            tool_calls=calls,
            finish_reason=finish,
            prompt_tokens=usage.input_tokens + cache_read + cache_write,
            completion_tokens=usage.output_tokens,
            latency_s=latency_s,
            reasoning=thinking,
            reasoning_tokens=thinking_tokens if isinstance(thinking_tokens, int) else None,
            cached_tokens=cache_read,
            cache_write_tokens=cache_write,
            retries=retries,
            raw_blocks=blocks,
        )

    def cost_usd(self, response: LlmResponse) -> float:
        """Coste de una respuesta con los precios del perfil (0 si no hay precios)."""
        if not self.pricing:
            return 0.0
        return call_cost(
            self.pricing,
            response.prompt_tokens,
            response.cached_tokens or 0,
            response.cache_write_tokens or 0,
            response.completion_tokens,
        )


def call_cost(
    pricing: dict[str, float], prompt: int, cache_read: int, cache_write: int, output: int
) -> float:
    """Coste en USD de una llamada. `prompt` incluye lo leído y lo escrito en caché; los precios
    son por millón de tokens (`input`, `cache_write`, `cache_read`, `output`)."""
    fresh = max(prompt - cache_read - cache_write, 0)
    return (
        fresh * pricing["input"]
        + cache_write * pricing["cache_write"]
        + cache_read * pricing["cache_read"]
        + output * pricing["output"]
    ) / 1_000_000
