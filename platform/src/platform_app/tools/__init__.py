"""Tools de datos de la plataforma (`contracts/eventos.md` §7).

Trabajan solo sobre el timeline, con el corte temporal y sin el dominio `sim` (ver `context`).
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from poc_contracts.tools import TOOL_MODELS

from .context import ToolContext, ToolFailure
from .events import get_events, get_mission_plan, get_my_alerts
from .metrics import get_track_metrics
from .summary import get_flight_summary

TOOLS: dict[str, Callable[[ToolContext, Any], BaseModel]] = {
    "get_events": get_events,
    "get_mission_plan": get_mission_plan,
    "get_track_metrics": get_track_metrics,
    "get_my_alerts": get_my_alerts,
    "get_flight_summary": get_flight_summary,
}


def call_tool(ctx: ToolContext, name: str, raw_args: dict[str, Any] | None) -> dict[str, Any]:
    """Valida los argumentos, ejecuta la tool y devuelve su resultado como JSON.

    Lanza `ToolFailure` (mensaje en español) si la tool no existe, los argumentos no valen o la
    tool no puede responder.
    """
    if name not in TOOLS:
        raise ToolFailure(f"tool desconocida: {name!r} (disponibles: {', '.join(TOOLS)})")
    args_model = TOOL_MODELS[name][0]
    try:
        args = args_model.model_validate(raw_args or {})
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'arguments'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ToolFailure(f"invalid arguments for {name}: {details}") from exc
    return TOOLS[name](ctx, args).model_dump(mode="json")


__all__ = ["TOOLS", "ToolContext", "ToolFailure", "call_tool"]
