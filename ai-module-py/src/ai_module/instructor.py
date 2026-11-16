"""Agente del instructor (Fase 16, contrato v0.18): interpreta una frase del instructor («wind
from the north-east at 8 m/s») y **propone** un viento. No publica nada: la web enseña la
propuesta y, solo si el instructor la confirma, manda el comando a la plataforma.

Reparto: el LLM **interpreta** (qué viento, de dónde, cuánto); el código **convierte el rumbo a
grados, rellena lo que falte (y lo dice) y valida** con los mismos rangos que la plataforma. Sin
tools de datos: el monitor no sabe nada de este chat y el módulo no recibe el comando del
instructor (de ahí que la web mande el viento activo en el mensaje: `context.active_wind`).
"""

import logging
import re
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from poc_contracts.commands import (
    MAX_DURATION_S,
    MAX_RAMP_S,
    MAX_WIND_GUST_MPS,
    MAX_WIND_SPEED_MPS,
    WindCommandParams,
)
from poc_contracts.enums import ActivityState, ConversationId, EventType
from poc_contracts.envelope import Envelope
from poc_contracts.tools import ProposeWindArgs

from .agent.engine import AgentEngine
from .agent.llm import Messages
from .agent.tools import Toolbox
from .agent.trace import InvocationTrace
from .chat import Chat
from .runtime import Runtime

log = logging.getLogger(__name__)

DEFAULT_RAMP_S = 10.0
DEFAULT_DURATION_S = 60.0
DEFAULT_GUST_FACTOR = 1.3

# Una respuesta que habla de una propuesta sin haber llamado a la tool no propone nada: el
# instructor no tendría tarjeta que confirmar. Pasaba cuando el historial (solo texto) hacía que el
# modelo imitara sus respuestas anteriores en vez de llamar a la tool.
PROPOSAL_CLAIM = re.compile(
    r"\bpropos(?:e|ed|al)\b|please confirm|confirm or (?:adjust|edit)", re.I
)
_WIND_FIGURES = re.compile(r"\d\s*m/s", re.I)
_WIND_TALK = re.compile(r"gust|ramp|by default|confirm", re.I)
_REFUSAL = re.compile(r"exceed|limit|maximum|cannot|can't|unable|\?", re.I)


def claims_a_proposal(text: str) -> bool:
    """¿El texto da por hecha una propuesta (con cifras de viento o con la frase de siempre)?
    Una pregunta o un «fuera de rango» no cuentan."""
    if PROPOSAL_CLAIM.search(text):
        return True
    return bool(
        _WIND_FIGURES.search(text) and _WIND_TALK.search(text) and not _REFUSAL.search(text)
    )


NO_TOOL_REMINDER = (
    "Nothing was proposed: you did not call a tool, so the instructor has nothing to confirm. If "
    "the instructor asked for a wind, call propose_wind now (or propose_cancel_wind to remove it) "
    "with what they said; never describe a proposal in text. If something is missing, ask for it "
    "without proposing anything."
)
NO_PROPOSAL_REPLY = (
    "I could not prepare a proposal. Say the wind again with its direction and speed in m/s, "
    "for example: wind from the north at 12 m/s."
)

COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")  # fmt: skip
_WORDS = {"north": "N", "south": "S", "east": "E", "west": "W"}


def parse_direction(value: str | float | int) -> float:
    """Rumbo (`NE`, `north-east`, `north north east`, `from the north-east`) o grados (`225`,
    `225 degrees`, `225°`) a grados de procedencia (0 = norte). `ValueError` si no se entiende."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        degrees = float(value)
    else:
        text = str(value).strip().lower()
        number = re.fullmatch(r"(?:from\s+)?(-?\d+(?:[.,]\d+)?)\s*(?:°|deg|degs|degrees?)?", text)
        if number:
            degrees = float(number.group(1).replace(",", "."))
        else:
            words = re.sub(r"^(?:from|the)\s+", "", re.sub(r"^from\s+the\s+", "", text))
            words = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", words)
            tokens = words.split()
            point = (
                "".join(_WORDS[t][0] if t in _WORDS else "?" for t in tokens)
                if tokens and all(t in _WORDS for t in tokens)
                else re.sub(r"[\s-]", "", words).upper()
            )
            point = {
                "NORTHEAST": "NE",
                "NORTHWEST": "NW",
                "SOUTHEAST": "SE",
                "SOUTHWEST": "SW",
            }.get(point, point)
            if point not in COMPASS:
                raise ValueError(
                    f"Cannot read the direction {value!r}: give a compass point such as N, NE, "
                    "ENE or north-east, or degrees from 0 to 360"
                )
            degrees = COMPASS.index(point) * 22.5
    if not 0.0 <= degrees <= 360.0:
        raise ValueError(f"The direction must be between 0 and 360 degrees, not {degrees:g}")
    return degrees % 360.0


def _r(value: float) -> float:
    return round(value, 1)


def build_proposal(args: dict[str, Any]) -> dict[str, Any]:
    """Resultado de `propose_wind`: la propuesta validada (con lo que el código rellenó, en
    `defaults_used`) o `{"ok": False, "errors": [...]}` para que el modelo corrija. No publica."""
    try:
        a = ProposeWindArgs.model_validate(args)
    except ValidationError as exc:
        return {"ok": False, "errors": [_describe(e) for e in exc.errors()]}
    try:
        from_deg = parse_direction(a.from_direction)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)]}
    if not 0.0 <= a.speed_mps <= MAX_WIND_SPEED_MPS:  # antes de rellenar la racha con ella
        return {"ok": False, "errors": [_describe_range("speed_mps", a.speed_mps)]}
    defaults: list[str] = []
    gust = a.gust_mps
    if gust is None:
        gust = _r(a.speed_mps * DEFAULT_GUST_FACTOR)
        defaults.append("gust_mps")
    duration: float | None = a.duration_s
    if a.until_cancelled:
        duration = None
    elif duration is None:
        duration = DEFAULT_DURATION_S
        defaults.append("duration_s")
    ramp = a.ramp_s
    if ramp is None:
        ramp = DEFAULT_RAMP_S
        defaults.append("ramp_s")
    try:
        params = WindCommandParams(
            from_deg=from_deg,
            speed_mps=a.speed_mps,
            gust_mps=gust,
            ramp_s=ramp,
            duration_s=duration,
        )
    except ValidationError as exc:
        return {"ok": False, "errors": [_describe(e) for e in exc.errors()]}
    return {
        "ok": True,
        "proposal": {
            "command": "set_wind",
            "params": params.model_dump(),
            "defaults_used": defaults,
        },
    }


_LIMITS = {
    "speed_mps": f"at most {MAX_WIND_SPEED_MPS:g} m/s",
    "gust_mps": f"at most {MAX_WIND_GUST_MPS:g} m/s and at least the speed",
    "ramp_s": f"more than 0 and at most {MAX_RAMP_S:g} s",
    "duration_s": f"more than 0 and at most {MAX_DURATION_S:g} s",
}


def _describe_range(field: str, received: object) -> str:
    return f"{field} is out of range: it must be {_LIMITS[field]} (received {received!r})"


def _describe(error: Any) -> str:
    field = str(error["loc"][-1]) if error.get("loc") else ""
    if field in _LIMITS and error["type"] != "missing":
        return _describe_range(field, error.get("input"))
    if error["type"] == "missing":
        return f"{field} is missing"
    message = str(error["msg"]).removeprefix("Value error, ")
    return f"{field}: {message}" if field else message


def _num(value: float) -> str:
    return f"{round(value, 1):g}"


def describe_from(degrees: float) -> str:
    """`NE (45°)`, o `47° (≈NE)` si no es justo un rumbo de la rosa."""
    nearest = COMPASS[round((degrees % 360.0) / 22.5) % 16]
    if abs(COMPASS.index(nearest) * 22.5 - degrees % 360.0) < 1e-6:
        return f"{nearest} ({_num(degrees)}°)"
    return f"{_num(degrees)}° (≈{nearest})"


def describe_proposal(proposal: dict[str, Any]) -> str:
    """Lo que se le dice al instructor de su propuesta, escrito por el código: las cifras son las
    validadas y «por defecto» solo sale de lo que el código rellenó de verdad."""
    params = proposal["params"]
    if proposal["command"] == "cancel_wind" or params is None:
        return "Cancel the wind from the instructor. Confirm or discard it."
    duration = (
        "until cancelled" if params["duration_s"] is None else f"{_num(params['duration_s'])} s"
    )
    text = (
        f"Wind from {describe_from(params['from_deg'])}, {_num(params['speed_mps'])} m/s, gusts "
        f"{_num(params['gust_mps'])} m/s, {duration}, ramp {_num(params['ramp_s'])} s."
    )
    defaults = proposal["defaults_used"]
    if defaults:
        text += f" Filled in by default: {', '.join(defaults)}."
    return f"{text} Confirm it, edit it or discard it."


def describe_active_wind(active: dict[str, Any] | None) -> str:
    """El viento del instructor que manda la web, para el sistema del agente."""
    if not active:
        return "No wind from the instructor is active."
    left = active.get("remaining_s")
    ends = "until it is cancelled" if left is None else f"{left:g} s left"
    return (
        f"Active: from {active['from_deg']:g}°, {active['speed_mps']:g} m/s, gusts "
        f"{active['gust_mps']:g} m/s, {ends}."
    )


class InstructorChat(Chat):
    """Tercer chat del módulo: `conversation_id: instructor`. Como los otros, en su propia tarea y
    en streaming, pero con las tools que **proponen** y sin datos de la simulación."""

    def __init__(self, rt: Runtime) -> None:
        super().__init__(rt, ConversationId.INSTRUCTOR)
        # el historial guarda cada intercambio entero (pregunta, llamada a la tool, resultado y
        # respuesta): con solo el texto, el modelo imitaba sus respuestas y dejaba de llamar a la
        # tool. Cada intercambio son hasta 4 mensajes: hay que dejar sitio a unos cuantos.
        self.history: deque[dict[str, Any]] = deque(maxlen=4 * 6)  # type: ignore[assignment]

    def _usable_history(self) -> list[dict[str, Any]]:
        """El historial desde el primer mensaje de usuario: recortado por delante, no puede
        empezar por un resultado de tool sin su llamada."""
        items = list(self.history)
        while items and items[0]["role"] != "user":
            items.pop(0)
        return items

    async def answer(self, event: Envelope) -> None:
        rt, cfg = self.rt, self.config
        question = str(event.payload["text"])
        active = (event.payload.get("context") or {}).get("active_wind")
        invocation_id = rt.ids.next("inv")
        now = rt.clock.now()
        trace = InvocationTrace(
            invocation_id=invocation_id,
            agent=self.agent_name.value,
            causation_ids=[event.event_id],
            as_of=now,
            wall_start=_wall_iso(),
            conversation_id=self.conversation.value,
        )
        started = time.monotonic()
        proposals: list[dict[str, Any]] = []

        async def propose_wind(args: dict[str, Any]) -> dict[str, Any]:
            result = build_proposal(args)
            if result["ok"]:
                proposals.append(result["proposal"])
            return result

        async def propose_cancel_wind(_: dict[str, Any]) -> dict[str, Any]:
            if not active:
                return {"ok": False, "errors": ["There is no wind from the instructor to cancel"]}
            proposal = {"command": "cancel_wind", "params": None, "defaults_used": []}
            proposals.append(proposal)
            return {"ok": True, "proposal": proposal}

        system = rt.assets.system_prompt(cfg, active_wind=describe_active_wind(active))
        messages: Messages = [
            {"role": "system", "content": system},
            *self._usable_history(),
            {"role": "user", "content": question},
        ]
        start = len(messages) - 1  # la pregunta: desde aquí es el intercambio de esta invocación
        toolbox = Toolbox(
            rt.assets,
            [],
            rt.platform_url,
            local={"propose_wind": propose_wind, "propose_cancel_wind": propose_cancel_wind},
        )
        engine = AgentEngine(rt.llm, cfg, rt.assets.tool_schemas(cfg.active_tools), toolbox)

        async def chunk(delta: str) -> None:
            await rt.emit(
                EventType.AGENT_REPLY_CHUNK,
                {
                    "conversation_id": self.conversation.value,
                    "reply_to": event.event_id,
                    "delta": delta,
                },
                conversation=self.conversation,
            )

        await rt.activity(self.agent_name, ActivityState.STARTED, invocation_id, event.event_id)
        try:
            kwargs = {
                "on_delta": chunk,
                "on_tool_call": rt.tool_call_listener(
                    self.agent_name, invocation_id, event.event_id
                ),
            }
            result = await engine.run(messages, trace, **kwargs)
            tool_names = list(result.tool_names)
            final = result.text.strip()
            text = final if result.tool_names and final else result.streamed_text.strip() or final
            if not proposals and claims_a_proposal(final):
                # habla de una propuesta sin haber llamado a la tool: se descarta esa respuesta
                # (el modelo la imitaría) y se le recuerda una vez
                log.warning("%s: instructor reply without a tool call: retrying", invocation_id)
                if messages[-1]["role"] == "assistant":
                    messages.pop()
                messages.append({"role": "user", "content": NO_TOOL_REMINDER})
                trace.aids = {"retried_without_tool": True}
                result = await engine.run(messages, trace, **kwargs)
                tool_names += result.tool_names
                final = result.text.strip()
                text = final
                if not proposals and claims_a_proposal(final):
                    text = NO_PROPOSAL_REPLY
            if proposals:
                text = describe_proposal(proposals[-1])
            if not text:
                text = f"I could not answer ({result.end_reason}). Try saying it again."
        except Exception:
            log.exception("instructor chat engine failed")
            text, tool_names, trace.end_reason = (
                "I could not answer because of an error.",
                [],
                "error",
            )
        payload: dict[str, Any] = {
            "conversation_id": self.conversation.value,
            "reply_to": event.event_id,
            "text": text,
            "tool_calls": tool_names,
        }
        if proposals:
            payload["proposal"] = proposals[-1]  # la última propuesta válida de la invocación
        reply = await rt.emit(EventType.AGENT_REPLY, payload, conversation=self.conversation)
        trace.published.append(
            {"event_id": reply.event_id, "type": "AgentReply", "causation_id": event.event_id}
        )
        exchange = [m for m in messages[start:] if m.get("content") != NO_TOOL_REMINDER]
        if exchange[-1]["role"] != "assistant":  # sin respuesta del modelo (error, tiempo)
            exchange.append({"role": "assistant", "content": text})
        self.history.extend(exchange)
        trace.sim_time_end = rt.clock.now()
        trace.wall_end = _wall_iso()
        trace.duration_s = time.monotonic() - started
        rt.trace.write(trace)
        await rt.activity(self.agent_name, ActivityState.FINISHED, invocation_id, event.event_id)


def _wall_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
