"""Lectura de escenarios: `scenarios/<nombre>.yaml` -> `ScenarioConfig`."""

from pathlib import Path

import yaml

from poc_contracts.scenario import ScenarioConfig

from ..paths import SCENARIOS_DIR


def scenario_path(name: str, scenarios_dir: Path = SCENARIOS_DIR) -> Path:
    return scenarios_dir / f"{name}.yaml"


def load_scenario(name: str, scenarios_dir: Path = SCENARIOS_DIR) -> ScenarioConfig:
    """Lee y valida un escenario. El nombre del fichero debe coincidir con `name:` del YAML."""
    path = scenario_path(name, scenarios_dir)
    config = ScenarioConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if config.name != name:
        raise ValueError(f"{path.name}: `name` es {config.name!r}, se esperaba {name!r}")
    return config


def list_scenarios(scenarios_dir: Path = SCENARIOS_DIR) -> list[str]:
    """Nombres de los escenarios disponibles, por orden alfabético."""
    return sorted(p.stem for p in scenarios_dir.glob("*.yaml"))
