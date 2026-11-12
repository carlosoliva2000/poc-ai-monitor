"""Ejecución de tools para el motor: las de datos (HTTP a la plataforma) y `load_skill`.

Las tools que publican (`publish_alert`, `acknowledge_detection`, `close_alert`) las añade el
monitor como tools locales. Aquí se impone una garantía más: el corte temporal del módulo. Si el
agente tiene un `as_of` (el monitor), `until` de `get_events` y `get_track_metrics` nunca pasa de
él; la plataforma aplica además su propio corte con el instante actual de la simulación.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from poc_contracts.times import parse_duration, parse_sim_time

from ..bus_client import PlatformToolError, call_platform_tool
from ..outbox import format_t
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


def prepare_window(
    name: str, args: dict[str, Any], as_of: float
) -> tuple[dict[str, Any], float | None]:
    """Fase 15.1 (`window_rules`): la ventana de una llamada de datos con el instante de partida
    (`as_of`) de la interacción. El código convierte los tiempos (segundos, `T+mm:ss`, `last_s`):
    el modelo no hace aritmética. Un `since` posterior a `as_of` se **rechaza** (error con el
    instante de partida, para que corrija en vez de concluir «no hay eventos»); un `until`
    posterior se recorta. Devuelve los argumentos para la plataforma y el instante al que se
    recortó (`None` si no hizo falta). `ToolError` si algo no vale."""
    out = dict(args)
    try:
        since = None if out.get("since") is None else parse_sim_time(out["since"])
        until = None if out.get("until") is None else parse_sim_time(out["until"])
        last_s = None if out.get("last_s") is None else parse_duration(out["last_s"])
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    out.pop("last_s", None)
    if last_s is not None:
        if since is not None:
            raise ToolError("use either last_s or since/until, not both")
        since, until = max(as_of - last_s, 0.0), as_of
    if since is not None and since > as_of:
        raise ToolError(
            f"The start {format_t(since)} ({since:g} s) is after the current time "
            f"{format_t(as_of)} ({as_of:g} s): nothing has happened there yet. Ask for a window "
            f"that starts at or before {as_of:g} s"
        )
    clipped = as_of if until is not None and until > as_of else None
    if since is not None:
        out["since"] = since
    if until is not None:
        out["until"] = as_of if clipped is not None else until
    elif name == "get_events":
        out["until"] = as_of
    return out, clipped


def note_clipped(name: str, result: Any, as_of: float) -> Any:
    """Añade al resultado que `until` se recortó (`until_clipped_to`, y `note` en `get_events`)."""
    if not isinstance(result, dict):
        return result
    out = {**result, "until_clipped_to": as_of}
    if name == "get_events":
        note = f"until was later than the current time: it was clipped to {format_t(as_of)}"
        out["note"] = f"{result['note']}; {note}" if result.get("note") else note
    return out


def count_after(result: Any, as_of: float) -> int:
    """Cuántos eventos de un resultado de datos son posteriores a `as_of` (debe ser 0)."""
    if not isinstance(result, dict):
        return 0
    late = sum(1 for e in result.get("events", []) if float(e.get("sim_time", 0.0)) > as_of)
    until = result.get("until")
    return late + (1 if isinstance(until, int | float) and until > as_of else 0)


def strip_now_facts(result: Any) -> Any:
    """Quita el bloque `now` de un resultado de `get_track_metrics` (interruptor `now_facts`
    apagado: los assets anteriores a la Fase 14.1). Devuelve una copia."""
    if not isinstance(result, dict):
        return result
    return {k: v for k, v in result.items() if k != "now"}


def strip_route_trend(result: Any) -> Any:
    """Quita `route_trend`, `route_change_m` y `route_trend_source` del bloque `now` de un
    resultado de `get_track_metrics` (interruptor `now_route_trend` sin `all`: los assets anteriores
    a la Fase 15.1). Devuelve una copia."""
    if not isinstance(result, dict) or not isinstance(result.get("now"), dict):
        return result
    drop = ("route_trend", "route_change_m", "route_trend_source")
    return {**result, "now": {k: v for k, v in result["now"].items() if k not in drop}}


def strip_computed_facts(result: Any) -> Any:
    """Quita de un resultado de `get_track_metrics` los campos calculados (interruptor
    `computed_facts` apagado): `wind_to_deg`, `drift_vs_wind_deg`, `notable`, `with_drift`,
    `gps_radar` (`disagreed`) y `gps_max_step_m`. Devuelve una copia."""
    if not isinstance(result, dict):
        return result
    out = {k: v for k, v in result.items() if k not in ("gps_radar", "gps_max_step_m", "now")}
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
        window_rules: bool = False,
    ) -> None:
        self.assets = assets
        self.skills = skills
        self.platform_url = platform_url
        self.as_of = as_of
        self.local = local or {}
        self._platform_call = platform_call
        self._on_skill = on_skill
        self._loaded: set[str] = set()  # skills ya entregadas en esta invocación
        self.window_rules = window_rules
        """Fase 15.1: conversión de tiempos, rechazo de `since` futuro y recorte avisado."""
        self.after_as_of = 0
        """Eventos de resultados de datos posteriores a `as_of` (debe quedar a 0): la traza lo
        cuenta."""

    async def __call__(self, name: str, args: dict[str, Any]) -> Any:
        if name in self.local:
            return await self.local[name](args)
        if name == "load_skill":
            return self._load_skill(args)
        if name in DATA_TOOLS:
            clipped: float | None = None
            if self.window_rules and self.as_of is not None and name in CAPPED_TOOLS:
                call_args, clipped = prepare_window(name, args, self.as_of)
            else:
                call_args = cap_until(name, args, self.as_of)
            try:
                result = await self._platform_call(self.platform_url, name, call_args)
            except PlatformToolError as exc:
                raise ToolError(str(exc)) from exc
            if self.as_of is not None:
                self.after_as_of += count_after(result, self.as_of)
                if clipped is not None:
                    result = note_clipped(name, result, self.as_of)
            return result
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
