"""Estado de cada faceta por segundo (`states.jsonl`, `contracts/eventos.md` §8.7, v1.0).

Las facetas y sus estados son el catálogo de la especificación del núcleo v2. `n/a` (no aplica)
y `?` (no observable) valen en cualquier faceta. Es solo para el generador, la evaluación y la
vista del instructor: el agente nunca lo ve.
"""

from pydantic import BaseModel, ConfigDict

NOT_APPLICABLE = "n/a"
NOT_OBSERVABLE = "?"

FACETS: dict[str, tuple[str, ...]] = {
    "gps.availability": ("normal", "no_data", "no_fix"),
    "gps.quality": ("good", "degraded"),
    "gps.integrity": ("reliable", "spoofed"),
    "radar.availability": ("normal", "no_data", "out_of_range"),
    "link.availability": ("connected", "lost"),
    "link.quality": ("good", "degraded"),
    "meteo.availability": ("normal", "no_data"),
    "battery.availability": ("normal", "no_data"),
    "battery.level": ("normal", "low", "critical"),
    "battery.endurance": ("sufficient", "cannot_reach_home"),
    "environment.wind": ("calm", "notable", "beyond_limit"),
    "drone.mode": (
        "mission",
        "failsafe_return",
        "failsafe_hold",
        "failsafe_land",
        "foreign_control",
    ),
    "drone.situation": ("on_route", "deviated", "returning"),
    # `unexplained`: desviado sin ninguna causa conocida. No es una etiqueta de la verdad (el
    # sistema dice «sin determinar» por baja confianza): es un aviso para el que escribe el
    # escenario, que debe valer 0 instantes.
    "drone.cause": ("foreign_control", "spoofed_position", "dead_reckoning", "wind", "unexplained"),
}


class StateRow(BaseModel):
    """Una fila de `states.jsonl`: `facets` es lo que se entrena y evalúa; `hidden` guarda, para
    las facetas con `?`, el estado que habría tenido (para la vista del instructor)."""

    model_config = ConfigDict(extra="forbid")

    t: float
    facets: dict[str, str]
    hidden: dict[str, str] = {}

    def check(self) -> None:
        """Lanza `ValueError` si una faceta falta o tiene un estado fuera del catálogo."""
        if set(self.facets) != set(FACETS):
            raise ValueError("the row does not have exactly the facets of the catalogue")
        for name, value in {**self.facets, **self.hidden}.items():
            if value not in (*FACETS[name], NOT_APPLICABLE, NOT_OBSERVABLE):
                raise ValueError(f"{name}: unknown state {value!r}")
