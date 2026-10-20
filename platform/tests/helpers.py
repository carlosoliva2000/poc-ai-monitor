"""Utilidades de las pruebas de la plataforma."""

import yaml

from platform_app.paths import SCENARIOS_DIR
from poc_contracts.scenario import ScenarioConfig


def scenario_config(name: str = "nominal", **overrides: object) -> ScenarioConfig:
    """Escenario de `scenarios/` con campos de primer nivel sustituidos (diccionarios ya listos)."""
    raw = yaml.safe_load((SCENARIOS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    raw.update(overrides)
    return ScenarioConfig.model_validate(raw)
