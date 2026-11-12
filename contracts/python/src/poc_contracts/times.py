"""Tiempos de las tools de datos (contrato v0.17): el código convierte, el modelo no.

`since` y `until` aceptan segundos (`222`, `"222"`) o un instante en texto: `"T+03:42"`, `"03:42"`,
`"T+1:02:03"` y `"1:02:03"`. `last_s` (ventana contada hacia atrás desde «ahora») acepta segundos
(`60`, `"90s"`), `"1:30"` y `"1m30s"`. Los errores dicen los formatos válidos para que el modelo
corrija en vez de adivinar.
"""

import re
from typing import Any

TIME_FORMATS = "seconds (222), T+mm:ss (T+03:42), mm:ss (03:42) or T+h:mm:ss (T+1:02:03)"
DURATION_FORMATS = "seconds (90), 90s, mm:ss (1:30) or 1m30s"

_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds?)?$", re.I)
_CLOCK_RE = re.compile(r"^(?:T\+)?(?:(\d+):)?(\d+):(\d{2})$", re.I)
_UNITS_RE = re.compile(
    r"^(?:(\d+)\s*m(?:in(?:ute)?s?)?)?\s*(?:(\d+(?:\.\d+)?)\s*s(?:ec(?:ond)?s?)?)?$", re.I
)


def _clock_seconds(text: str) -> float | None:
    """`T+mm:ss`, `mm:ss`, `T+h:mm:ss` o `h:mm:ss` en segundos (`None` si no tiene esa forma)."""
    match = _CLOCK_RE.match(text)
    if match is None:
        return None
    hours, minutes, seconds = match.group(1), int(match.group(2)), int(match.group(3))
    if seconds > 59 or (hours is not None and minutes > 59):
        return None
    return int(hours or 0) * 3600.0 + minutes * 60.0 + seconds


def parse_sim_time(value: Any) -> float:
    """Un instante de la simulación en segundos. `ValueError` con los formatos válidos si no."""
    if isinstance(value, bool):
        raise ValueError(f"invalid time {value!r}: use {TIME_FORMATS}")
    if isinstance(value, int | float):
        seconds = float(value)
    elif isinstance(value, str):
        text = value.strip()
        number = _NUMBER_RE.match(text)
        clock = _clock_seconds(text)
        if number is not None:
            seconds = float(number.group(1))
        elif clock is not None:
            seconds = clock
        else:
            raise ValueError(f"invalid time {value!r}: use {TIME_FORMATS}")
    else:
        raise ValueError(f"invalid time {value!r}: use {TIME_FORMATS}")
    if seconds < 0:
        raise ValueError(f"invalid time {value!r}: it cannot be negative; use {TIME_FORMATS}")
    return seconds


def parse_sim_time_or_none(value: Any) -> float | None:
    return None if value is None else parse_sim_time(value)


def parse_duration(value: Any) -> float:
    """Una duración en segundos (`last_s`). `ValueError` con los formatos válidos si no."""
    bad = ValueError(f"invalid duration {value!r}: use {DURATION_FORMATS}")
    if isinstance(value, bool):
        raise bad
    if isinstance(value, int | float):
        seconds = float(value)
    elif isinstance(value, str):
        text = value.strip()
        number = _NUMBER_RE.match(text)
        clock = _clock_seconds(text) if ":" in text and not text.lower().startswith("t+") else None
        units = _UNITS_RE.match(text)
        if number is not None:
            seconds = float(number.group(1))
        elif clock is not None:
            seconds = clock
        elif units is not None and (units.group(1) or units.group(2)):
            seconds = int(units.group(1) or 0) * 60.0 + float(units.group(2) or 0)
        else:
            raise bad
    else:
        raise bad
    if seconds <= 0:
        raise ValueError(
            f"invalid duration {value!r}: it must be longer than zero; use {DURATION_FORMATS}"
        )
    return seconds


def parse_duration_or_none(value: Any) -> float | None:
    return None if value is None else parse_duration(value)
