"""Traductor de órdenes del instructor (E7d, §7): de una frase a una orden del catálogo.

Catálogo: `set_wind` y `cancel_wind` (lo que la plataforma sabe aplicar). El LLM **solo propone**:
llama a una tool; el código convierte el rumbo a grados, rellena lo que falte (y lo dice), valida
con los rangos de la plataforma y escribe el texto de la propuesta. La web enseña la propuesta y
solo con «Confirm» manda el comando (`control` → `instructor`, `issued_by: llm`). Una frase que no
es una orden, es ambigua o está fuera del catálogo no produce propuesta.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from poc_contracts.commands import (
    MAX_DURATION_S,
    MAX_RAMP_S,
    MAX_WIND_SPEED_MPS,
    WindCommandParams,
)

from ..assistant.checks import check_text
from ..assistant.config import AssistantConfig
from ..assistant.facts import PromptInput
from ..assistant.llm import LlmError, LlmPort

DEFAULT_RAMP_S = 10.0
DEFAULT_DURATION_S = 60.0
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")  # fmt: skip
_WORDS = {"north": "N", "south": "S", "east": "E", "west": "W"}

NOT_AN_ORDER_REPLIES = {
    "other_command": (
        "From this chat I can only propose wind. Faults are injected from the fault panel."
    ),
    "wrong_unit": "Please say the speed in m/s.",
}
NO_PROPOSAL_REPLY = (
    "I could not prepare a proposal. Say the wind again with its direction and speed in m/s, "
    "for example: wind from the north at 12 m/s."
)
NO_WIND_TO_CANCEL = "There is no instructor wind to cancel right now."


def parse_direction(value: str | float | int) -> float:
    """Rumbo (`NE`, `north-east`, `from the north-east`) o grados (`225`, `225°`) a grados de
    procedencia (0 = norte). `ValueError` si no se entiende."""
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
            point = {"NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE",
                     "SOUTHWEST": "SW"}.get(point, point)  # fmt: skip
            if point not in COMPASS:
                raise ValueError(
                    f"Cannot read the direction {value!r}: give a compass point such as N, NE, "
                    "ENE or north-east, or degrees from 0 to 360"
                )
            degrees = COMPASS.index(point) * 22.5
    if not 0.0 <= degrees <= 360.0:
        raise ValueError(f"The direction must be between 0 and 360 degrees, not {degrees:g}")
    return degrees % 360.0


_LIMITS = {
    "speed_mps": f"at most {MAX_WIND_SPEED_MPS:g} m/s",
    "ramp_s": f"more than 0 and at most {MAX_RAMP_S:g} s",
    "duration_s": f"more than 0 and at most {MAX_DURATION_S:g} s",
}


class SpeedNotSaid(ValueError):
    """La velocidad (o su unidad) que propone el modelo no está en la frase del instructor."""


def resolve_speed(args: dict[str, Any], text: str) -> tuple[float, str | None]:
    """La velocidad en m/s a partir de lo que dijo el instructor: cifra o palabra y unidad tal
    cual (`speed`, `unit`); el código comprueba que está en la frase, convierte y devuelve la nota
    de la conversión («20 knots = 10.3 m/s»). `ValueError` si no se entiende o no estaba."""
    raw = args.get("speed", args.get("speed_mps"))
    if raw is None or str(raw).strip() == "":
        raise SpeedNotSaid("the speed is missing")
    spoken = str(raw).strip().lower().replace(",", ".")
    try:
        value = float(spoken)
    except ValueError:
        words = words_to_numbers(spoken)
        if len(words) != 1:
            raise ValueError(f"cannot read the speed {raw!r}") from None
        value = words[0]
    if not says_the_speed(text, value):
        raise SpeedNotSaid(f"the speed {value:g} is not in what the instructor said")
    unit = _UNIT_ALIASES.get(str(args.get("unit") or "m/s").strip().lower())
    if unit is None:
        raise ValueError(f"the unit {args.get('unit')!r} is not m/s, knots, km/h or mph")
    if unit != "m/s" and not re.search(_UNIT_WORD[unit], text, re.I):
        raise SpeedNotSaid(f"the unit {unit} is not in what the instructor said")
    mps = round(value * _UNIT_FACTORS[unit], 1)
    note = None if unit == "m/s" else f"{_num(value)} {_UNIT_LABEL[unit]} = {_num(mps)} m/s"
    return mps, note


def build_proposal(args: dict[str, Any], text: str) -> dict[str, Any]:
    """`propose_wind` → `{"ok": True, "proposal": {...}, "note": ...}` (con lo que el código
    rellenó en `defaults_used`) o `{"ok": False, "errors": [...]}` / `{"ok": False, "missing_speed":
    True}`. No publica nada."""
    try:
        from_deg = parse_direction(args["from_direction"])
        speed, note = resolve_speed(args, text)
    except KeyError as exc:
        return {"ok": False, "errors": [f"{exc.args[0]} is missing"]}
    except SpeedNotSaid:
        return {"ok": False, "missing_speed": True, "errors": []}
    except (ValueError, TypeError) as exc:
        return {"ok": False, "errors": [str(exc)]}
    if not 0.0 <= speed <= MAX_WIND_SPEED_MPS:
        detail = f" ({note})" if note else ""
        return {
            "ok": False,
            "errors": [f"speed_mps is out of range: it must be {_LIMITS['speed_mps']}{detail}"],
        }
    defaults: list[str] = []
    duration: float | None = args.get("duration_s")
    if args.get("until_cancelled"):
        duration = None
    elif duration is None:
        duration, defaults = DEFAULT_DURATION_S, [*defaults, "duration_s"]
    ramp = args.get("ramp_s")
    if ramp is None:
        ramp, defaults = DEFAULT_RAMP_S, [*defaults, "ramp_s"]
    try:
        params = WindCommandParams(
            from_deg=from_deg, speed_mps=speed, ramp_s=ramp, duration_s=duration
        )
    except ValidationError as exc:
        errors = []
        for e in exc.errors():
            name = str(e["loc"][-1])
            errors.append(f"{name} is out of range: it must be {_LIMITS.get(name, 'valid')}")
        return {"ok": False, "errors": errors}
    proposal = {"command": "set_wind", "params": params.model_dump(), "defaults_used": defaults}
    return {"ok": True, "proposal": proposal, "note": note}


def _num(value: float) -> str:
    return f"{round(value, 1):g}"


def describe_from(degrees: float) -> str:
    nearest = COMPASS[round((degrees % 360.0) / 22.5) % 16]
    if abs(COMPASS.index(nearest) * 22.5 - degrees % 360.0) < 1e-6:
        return f"{nearest} ({_num(degrees)}°)"
    return f"{_num(degrees)}° (≈{nearest})"


def describe_proposal(proposal: dict[str, Any]) -> str:
    """El texto de la propuesta, escrito por el código: las cifras son las validadas y «por
    defecto» solo sale de lo que el código rellenó de verdad."""
    params = proposal["params"]
    if proposal["command"] == "cancel_wind" or params is None:
        return "Cancel the wind from the instructor. Confirm or discard it."
    duration = (
        "until cancelled" if params["duration_s"] is None else f"{_num(params['duration_s'])} s"
    )
    text = (
        f"Wind from {describe_from(params['from_deg'])}, {_num(params['speed_mps'])} m/s, "
        f"{duration}, ramp {_num(params['ramp_s'])} s."
    )
    if proposal["defaults_used"]:
        text += f" Filled in by default: {', '.join(proposal['defaults_used'])}."
    return f"{text} Confirm it, edit it or discard it."


def describe_active_wind(active: dict[str, Any] | None) -> str:
    if not active:
        return "No wind from the instructor is active."
    left = active["remaining_s"]
    ends = "until it is cancelled" if left is None else f"{left:g} s left"
    origin = describe_from(active["from_deg"])
    return f"Active: from {origin}, {_num(active['speed_mps'])} m/s, {ends}."


_UNITS_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
               "eighty": 80, "ninety": 90}  # fmt: skip


def words_to_numbers(text: str) -> list[float]:
    """Los números escritos con palabras en un texto («twenty», «twenty five», «twelve»)."""
    tokens = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    found: list[float] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _TENS_WORDS:
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt in _UNITS_WORDS and 0 < _UNITS_WORDS[nxt] < 10:
                found.append(_TENS_WORDS[token] + _UNITS_WORDS[nxt])
                i += 2
                continue
            found.append(_TENS_WORDS[token])
        elif token in _UNITS_WORDS:
            found.append(_UNITS_WORDS[token])
        i += 1
    return found


def numbers_in_text(text: str) -> list[float]:
    digits = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)]
    return digits + words_to_numbers(text)


_SPEED_UNIT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m/s|mps|m\s*/\s*s|metres? per second|meters? per second)", re.I
)


def says_the_speed(text: str, speed: float) -> bool:
    """¿La frase del instructor dice esa velocidad (en cifras o en palabras)? El modelo no puede
    inventarla: con un viento sin velocidad rellenaba un 0."""
    return any(abs(n - speed) < 0.05 for n in numbers_in_text(text))


def speed_over_limit(text: str) -> float | None:
    """La velocidad dicha en m/s que pasa el límite de la plataforma, si la hay (se contesta sin
    llamar al modelo: es una validación, no una interpretación)."""
    over = [float(n.replace(",", ".")) for n in _SPEED_UNIT.findall(text)]
    over = [n for n in over if n > MAX_WIND_SPEED_MPS]
    return max(over) if over else None


# Unidades que el código convierte a m/s (como el rumbo a grados): el modelo no hace cuentas.
_UNIT_FACTORS = {"m/s": 1.0, "knot": 0.514444, "km/h": 1000 / 3600, "mph": 0.44704}
_UNIT_WORD = {
    "knot": r"\bkn(?:ots?)?\b|\bkts?\b",
    "km/h": r"km\s*/\s*h|\bkmh\b|\bkph\b|kilomet(?:re|er)s? per hour",
    "mph": r"\bmph\b|miles? per hour",
}
_UNIT_LABEL = {"knot": "knots", "km/h": "km/h", "mph": "mph"}
_UNIT_ALIASES = {"m/s": "m/s", "mps": "m/s", "knots": "knot", "knot": "knot", "kn": "knot",
                 "kt": "knot", "kts": "knot", "km/h": "km/h", "kmh": "km/h", "kph": "km/h",
                 "mph": "mph"}  # fmt: skip
_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(knots?|kn|kts?|km\s*/\s*h|kmh|kph|kilomet(?:re|er)s? per hour|mph|"
    r"miles? per hour)\b",
    re.I,
)


def _unit_name(raw: str) -> str:
    low = re.sub(r"\s+", "", raw.lower())
    if low.startswith(("kn", "kt")):
        return "knot"
    if low.startswith("mi") or low == "mph":
        return "mph"
    return "km/h"


def convert_units(text: str) -> tuple[str, list[str]]:
    """Sustituye «20 knots», «50 km/h» o «30 mph» por su valor en m/s y devuelve las notas
    («20 knots = 10.3 m/s») para decirlo en la propuesta. Lo demás de la frase no se toca."""
    notes: list[str] = []

    def swap(match: re.Match[str]) -> str:
        value = float(match.group(1).replace(",", "."))
        unit = _unit_name(match.group(2))
        mps = round(value * _UNIT_FACTORS[unit], 1)
        notes.append(f"{_num(value)} {unit if unit != 'knot' else 'knots'} = {_num(mps)} m/s")
        return f"{_num(mps)} m/s"

    return _UNIT_RE.sub(swap, text), notes


@dataclass
class Translation:
    """Qué sale de una frase: una propuesta, un texto para el instructor o pasar al chat."""

    text: str | None = None
    proposal: dict[str, Any] | None = None
    to_chat: bool = False
    tool: str | None = None
    reasons: list[str] = field(default_factory=list)
    conversions: list[str] = field(default_factory=list)  # «20 knots = 10.3 m/s»
    latency_s: float = 0.0
    raw: list[Any] = field(default_factory=list)


class Translator:
    def __init__(self, config: AssistantConfig, llm: LlmPort) -> None:
        self.config = config
        self.llm = llm

    async def translate(self, text: str, active_wind: dict[str, Any] | None) -> Translation:
        out = Translation()
        # validación sin el modelo: una velocidad en cifras que ya pasa el límite (tras convertir)
        converted, out.conversions = convert_units(text)
        too_fast = speed_over_limit(converted)
        if too_fast is not None:
            out.text = (
                f"That is out of range: the speed must be {_LIMITS['speed_mps']}, not "
                f"{_num(too_fast)} m/s."
            )
            if out.conversions:
                out.text += f" (Converted: {'; '.join(out.conversions)}.)"
            return out
        cfg = self.config.role("translator")
        system = cfg.system_prompt(self.config.assets)
        tools = cfg.tool_schemas(self.config.assets)
        user = (
            f"Wind the instructor has now: {describe_active_wind(active_wind)}\n\n"
            f'The instructor says: "{text}"'
        )
        for _attempt in range(2):
            try:
                result = await self.llm.complete(cfg, system, user, tools)
            except LlmError as exc:
                out.text, out.reasons = "The assistant is not available right now.", [f"llm: {exc}"]
                return out
            out.latency_s += result.latency_s
            out.tool = result.tool_name
            out.raw.append({"tool": result.tool_name, "args": result.tool_args})
            args = result.tool_args or {}
            if result.tool_name == "propose_cancel_wind":
                if active_wind is None:
                    out.text = NO_WIND_TO_CANCEL
                    return out
                proposal = {"command": "cancel_wind", "params": None, "defaults_used": []}
                out.proposal, out.text = proposal, describe_proposal(proposal)
                return out
            if result.tool_name == "propose_wind":
                built = build_proposal(args, text)
                if built.get("missing_speed"):
                    return self._not_an_order({"reason": "missing_speed"}, active_wind, out)
                if built["ok"]:
                    out.proposal, out.text = built["proposal"], describe_proposal(built["proposal"])
                    if built["note"]:  # la conversión la hizo el código y se dice
                        out.conversions = [built["note"]]
                        said = f"Converted by the assistant: {built['note']}."
                        out.text = out.text.replace(" Confirm it,", f" {said} Confirm it,")
                    return out
                out.reasons = built["errors"]
                user += "\n\nThe proposal was rejected:\n" + "\n".join(
                    f"- {e}" for e in out.reasons
                )
                user += "\nFix the call if the instructor's words allow it."
                continue
            if result.tool_name == "not_an_order":
                return self._not_an_order(args, active_wind, out)
            out.reasons = ["format: call one of the tools"]
        # dos intentos sin propuesta: lo que dicen los errores del código (rango, rumbo), si lo hay
        bad_wind = [r for r in out.reasons if not r.startswith("format")]
        out.text = (
            ("That cannot be proposed: " + "; ".join(bad_wind) + ".")
            if bad_wind
            else (NO_PROPOSAL_REPLY)
        )
        return out

    def _not_an_order(
        self, args: dict[str, Any], active_wind: dict[str, Any] | None, out: Translation
    ) -> Translation:
        reason = args.get("reason")
        if reason == "question":
            out.to_chat = True
        elif reason == "missing_speed":
            out.text = "What speed, in m/s?"
            if active_wind:
                out.text += f" The wind now is {_num(active_wind['speed_mps'])} m/s."
        elif reason in NOT_AN_ORDER_REPLIES:
            out.text = NOT_AN_ORDER_REPLIES[reason]
        else:  # ambiguous
            ask = str(args.get("ask") or "")
            inp = PromptInput(text=describe_active_wind(active_wind), current="", opening="")
            verdict = check_text(ask, inp, "explain", now_rule="loose") if ask else None
            out.text = (
                verdict.text
                if verdict and verdict.ok
                else ("Which wind do you want? Give the direction and the speed in m/s.")
            )
        return out
