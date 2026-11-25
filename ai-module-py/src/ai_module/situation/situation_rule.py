"""Entradas de la regla determinista de la situación del dron (`situation_rule.yaml`).

La tabla decide con una distancia a la referencia del modo y no con el viento ni la velocidad (esos
son de la causa). Lo difícil está aquí, antes de la tabla:
- **qué posición creer:** la del GPS si es reciente, tiene fix y la tabla de integridad no dice que
  está engañado; si está engañado, perdido o sin telemetría, el radar promediado;
- **un margen** de `MARGIN_K` veces el error esperado de esa posición (el del receptor, o el del
  radar a esa distancia entre √trazas promediadas), para no parpadear cerca de los 25 y 15 m;
- **causa activa:** viento notable, GPS engañado, GPS sin fix o control ajeno, según los estados
  que dan las tablas aprendidas de esas facetas.
"""

from typing import Any

MARGIN_K = (
    1.0  # veces el error esperado; se elige en validación (`tools/training/situation_eval.py`)
)


def cause_active(states: dict[str, str]) -> bool:
    """Si alguna de las causas de una desviación está activa según las facetas aprendidas."""
    return (
        states.get("environment.wind") in ("notable", "beyond_limit")
        or states.get("gps.integrity") == "spoofed"
        or states.get("gps.availability") == "no_fix"
        or states.get("drone.mode") == "foreign_control"
    )


def position_used(
    values: dict[str, Any], states: dict[str, str]
) -> tuple[str | None, float | None, float | None]:
    """`(fuente, distancia a la referencia, error esperado)` de la posición que se cree."""
    gps_ok = values.get("gps_dev_m") is not None and states.get("gps.integrity") != "spoofed"
    if gps_ok:
        return "gps", values["gps_dev_m"], values.get("gps_sigma_m")
    if values.get("radar_dev_m") is not None:
        return "radar", values["radar_dev_m"], values.get("radar_sigma_m")
    return None, None, None


def rule_inputs(
    values: dict[str, Any], states: dict[str, str], previous: str, margin_k: float = MARGIN_K
) -> dict[str, Any]:
    """Las entradas de `drone_situation_rule` en un segundo."""
    _, dev, sigma = position_used(values, states)
    if dev is None:
        lo = hi = None
    else:
        margin = margin_k * (sigma or 0.0)
        lo, hi = max(0.0, dev - margin), dev + margin
    return {
        "dev_lo_m": lo, "dev_hi_m": hi, "previous": previous,
        "cause_active": cause_active(states),
    }  # fmt: skip
