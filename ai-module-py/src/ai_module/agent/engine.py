"""Motor de agente: bucle de tool calling escrito a mano sobre Chat Completions.

Un solo motor para el monitor, el informe y los dos chats. Cada instancia recibe su
configuración (`AgentConfig`), los esquemas de tools que ve el modelo y un ejecutor de tools.

El bucle termina cuando:
- `is_done()` es verdadero tras ejecutar tools (el monitor: todas las detecciones tienen
  respuesta; así no hay una llamada de más), o
- el modelo responde con texto sin pedir tools (respuesta final; el monitor recibe antes un
  recordatorio), o
- se agotan las iteraciones o el tiempo, o el LLM falla.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .assets import AgentConfig
from .llm import DeltaCallback, LlmClient, LlmResponse, Messages
from .trace import CallTrace, InvocationTrace

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 4000


class ToolError(Exception):
    """Un error de una tool: el mensaje (en español) vuelve al modelo como resultado."""


class AbortInvocation(Exception):
    """Una tool pide cortar la invocación (el modelo repite una llamada rechazada): el motor
    termina con `end_reason: repeated_rejection` y el monitor aplica el fallback."""


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]


@dataclass
class EngineResult:
    end_reason: str
    """`done` | `final` | `text` | `max_iterations` | `timeout` | `error`."""
    text: str
    """Texto de la última respuesta del modelo (en un chat, la respuesta)."""
    streamed_text: str
    """Todo el texto entregado a `on_delta` (puede incluir texto previo a tool calls)."""
    tool_names: list[str]
    iterations: int


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def limit_result(text: str, max_chars: int = MAX_RESULT_CHARS) -> tuple[str, bool]:
    """Recorta un resultado enorme avisando de que se ha recortado."""
    if len(text) <= max_chars:
        return text, False
    note = f"… [recortado: {max_chars} de {len(text)} caracteres; pide menos datos]"
    return text[:max_chars] + note, True


class AgentEngine:
    def __init__(
        self,
        llm: LlmClient,
        config: AgentConfig,
        tools: list[dict[str, Any]],
        execute: ToolExecutor,
    ) -> None:
        self.llm = llm
        self.config = config
        self.tools = tools
        self.execute = execute
        self._offered = {t["function"]["name"] for t in tools}

    def _tools_for(self, index: int) -> tuple[list[dict[str, Any]], list[str] | None]:
        """Tools de la iteración `index`. En la última permitida, solo las `final_tools` del
        agente (si las tiene): así no puede seguir encadenando tools de datos hasta el tope. Se
        ofrecen todas a la vez, sin forzar ninguna por nombre. Devuelve también los nombres si
        la lista se ha reducido (para la traza)."""
        config = self.config
        if index < config.max_iterations or not config.final_tools:
            return self.tools, None
        names = set(config.last_iteration_tools)
        tools = [t for t in self.tools if t["function"]["name"] in names]
        return tools, [t["function"]["name"] for t in tools]

    async def run(
        self,
        messages: Messages,
        trace: InvocationTrace,
        *,
        is_done: Callable[[], bool] | None = None,
        reminder: Callable[[], str] | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> EngineResult:
        """Ejecuta el bucle sobre `messages` (que se va ampliando). Rellena `trace`."""
        config = self.config
        trace.model = self.llm.model
        trace.sampling = config.sampling()
        trace.stream = config.stream
        trace.tools_offered = [t["function"]["name"] for t in self.tools]
        deadline = time.monotonic() + config.max_invocation_s
        reminded = False
        streamed = ""
        tool_names: list[str] = []
        text = ""

        async def collect(delta: str) -> None:
            nonlocal streamed
            streamed += delta
            if on_delta is not None:
                await on_delta(delta)

        def result(reason: str) -> EngineResult:
            trace.end_reason = reason
            trace.messages = messages
            return EngineResult(reason, text, streamed, tool_names, len(trace.calls))

        for index in range(1, config.max_iterations + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return result("timeout")
            offered, restricted = self._tools_for(index)
            try:
                response = await asyncio.wait_for(
                    self.llm.complete(
                        messages,
                        offered,
                        config.sampling(),
                        stream=config.stream,
                        on_delta=collect if config.stream else None,
                        timeout_s=min(remaining, config.llm_timeout_s),
                    ),
                    timeout=min(remaining, config.llm_timeout_s) + 1.0,
                )
            except TimeoutError:
                log.warning("%s: LLM timeout", trace.invocation_id)
                return result("timeout")
            except Exception as exc:
                # el SDK lanza su propio error de tiempo (APITimeoutError) además de otros
                log.warning("%s: LLM error: %s: %s", trace.invocation_id, type(exc).__name__, exc)
                reason = "timeout" if "timeout" in type(exc).__name__.lower() else "error"
                trace.calls.append(
                    CallTrace(index, 0.0, 0, 0, None, f"[{type(exc).__name__}] {exc}")
                )
                return result(reason)

            call_trace = _call_trace(index, response)
            call_trace.restricted_tools = restricted
            trace.calls.append(call_trace)
            text = response.content

            if not response.tool_calls:  # nunca se mira finish_reason
                if is_done is None:
                    messages.append(response.assistant_message())
                    return result("final")
                if is_done():
                    messages.append(response.assistant_message())
                    return result("done")
                if reminder is not None and not reminded:
                    # Un intento fallido que es solo texto no se guarda en los `messages`
                    # (el modelo lo imitaría): lo sustituye el recordatorio. En la traza, en
                    # `calls`, sí queda.
                    reminded = True
                    trace.reminders += 1
                    messages.append({"role": "user", "content": reminder()})
                    continue
                messages.append(response.assistant_message())
                return result("text")
            messages.append(response.assistant_message())

            for call in response.tool_calls:
                tool_names.append(call.name)
                try:
                    outcome = await self._run_tool(call.name, call.arguments, trace)
                except AbortInvocation as exc:
                    call_trace.tool_calls.append(
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                            "result": None,
                            "error": str(exc),
                            "truncated": False,
                        }
                    )
                    return result("repeated_rejection")
                shown = outcome["result"]
                # un texto (una skill) se entrega tal cual; el resto, como JSON compacto
                rendered = shown if isinstance(shown, str) else compact_json(shown)
                content, truncated = limit_result(rendered)
                call_trace.tool_calls.append(
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "result": outcome["result"],
                        "error": outcome["error"],
                        "truncated": truncated,
                    }
                )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
            if is_done is not None and is_done():
                return result("done")
        return result("max_iterations")

    async def _run_tool(self, name: str, raw_arguments: str, trace: InvocationTrace) -> dict:
        """Ejecuta una tool; cualquier problema vuelve al modelo como `{"error": …}`."""
        if name not in self._offered:
            return _failure(f"tool desconocida o no disponible: {name!r}")
        try:
            arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except json.JSONDecodeError as exc:
            trace.invalid_json += 1
            return _failure(f"los argumentos no son JSON válido ({exc.msg}); reenvíalos")
        if not isinstance(arguments, dict):
            trace.invalid_json += 1
            return _failure("los argumentos deben ser un objeto JSON")
        try:
            return {"result": await self.execute(name, arguments), "error": None}
        except ToolError as exc:
            return _failure(str(exc))
        except AbortInvocation:
            raise
        except Exception as exc:
            log.exception("tool %s failed", name)
            return _failure(f"error interno de la tool: {type(exc).__name__}: {exc}")


def _failure(message: str) -> dict:
    return {"result": {"error": message}, "error": message}


def _call_trace(index: int, response: LlmResponse) -> CallTrace:
    return CallTrace(
        index=index,
        latency_s=response.latency_s,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        finish_reason=response.finish_reason,
        content=response.content,
    )
