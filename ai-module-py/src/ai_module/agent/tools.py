"""Ejecución de tools para el motor: las de datos (HTTP a la plataforma) y `load_skill`.

Las tools que publican (`publish_alert`, `acknowledge_detection`, `close_alert`) las añade el
monitor como tools locales. Aquí se impone una garantía más: el corte temporal del módulo. Si el
agente tiene un `as_of` (el monitor), `until` de `get_events` y `get_track_metrics` nunca pasa de
él; la plataforma aplica además su propio corte con el instante actual de la simulación.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from ..bus_client import PlatformToolError, call_platform_tool
from .assets import Assets
from .engine import ToolError

DATA_TOOLS = ("get_events", "get_mission_plan", "get_track_metrics", "get_my_alerts",
              "get_flight_summary")  # fmt: skip
CAPPED_TOOLS = ("get_events", "get_track_metrics")

LocalTool = Callable[[dict[str, Any]], Awaitable[Any]]
PlatformCall = Callable[[str, str, dict[str, Any]], Awaitable[Any]]


def cap_until(name: str, args: dict[str, Any], as_of: float | None) -> dict[str, Any]:
    """Pone `until = as_of` si falta o es mayor (solo `get_events` y `get_track_metrics`)."""
    if as_of is None or name not in CAPPED_TOOLS:
        return args
    until = args.get("until")
    if name == "get_track_metrics" and until is None:
        return args  # `until` es obligatorio: que la validación de la plataforma lo diga
    if until is None:
        return {**args, "until": as_of}
    try:  # el modelo a veces manda los números como texto ("200")
        too_late = float(until) > as_of
    except (TypeError, ValueError):
        return args  # la validación de la plataforma lo rechazará
    return {**args, "until": as_of} if too_late else args


def strip_computed_facts(result: Any) -> Any:
    """Quita de un resultado de `get_track_metrics` los campos calculados (interruptor
    `computed_facts` apagado): `wind_to_deg`, `drift_vs_wind_deg`, `notable`, `with_drift`,
    `gps_radar` (`disagreed`) y `gps_max_step_m`. Devuelve una copia."""
    if not isinstance(result, dict):
        return result
    out = {k: v for k, v in result.items() if k not in ("gps_radar", "gps_max_step_m")}
    wind = out.get("wind")
    if isinstance(wind, dict):
        drop = ("wind_to_deg", "drift_vs_wind_deg", "notable", "with_drift")
        out["wind"] = {k: v for k, v in wind.items() if k not in drop}
    return out


class Toolbox:
    """Despacha cada llamada del modelo: local (`local`), `load_skill` o dato (plataforma)."""

    def __init__(
        self,
        assets: Assets,
        skills: list[str],
        platform_url: str,
        *,
        as_of: float | None = None,
        local: dict[str, LocalTool] | None = None,
        platform_call: PlatformCall = call_platform_tool,
        on_skill: Callable[[str], None] | None = None,
    ) -> None:
        self.assets = assets
        self.skills = skills
        self.platform_url = platform_url
        self.as_of = as_of
        self.local = local or {}
        self._platform_call = platform_call
        self._on_skill = on_skill
        self._loaded: set[str] = set()  # skills ya entregadas en esta invocación

    async def __call__(self, name: str, args: dict[str, Any]) -> Any:
        if name in self.local:
            return await self.local[name](args)
        if name == "load_skill":
            return self._load_skill(args)
        if name in DATA_TOOLS:
            try:
                return await self._platform_call(
                    self.platform_url, name, cap_until(name, args, self.as_of)
                )
            except PlatformToolError as exc:
                raise ToolError(str(exc)) from exc
        raise ToolError(f"unknown tool: {name!r}")

    def _load_skill(self, args: dict[str, Any]) -> str:
        name = args.get("name")
        if name not in self.skills:
            raise ToolError(f"unknown skill: {name!r} (available: {', '.join(self.skills)})")
        if name in self._loaded:
            # no se reenvía: repetirla gasta contexto e iteraciones (el modelo alternaba skills)
            return f"You already have the skill {name} loaded (above): continue with its next step."
        self._loaded.add(name)
        if self._on_skill is not None:
            self._on_skill(name)
        return self.assets.skills[name].content
