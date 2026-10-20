"""Fixtures comunes: los seis escenarios generados una vez por sesión en una carpeta temporal."""

from pathlib import Path

import pytest

from platform_app.generator.build import generate, write_run
from platform_app.generator.scenario_io import list_scenarios, load_scenario


@pytest.fixture(scope="session")
def runs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`runs/` temporal con los seis escenarios de `scenarios/` generados."""
    out = tmp_path_factory.mktemp("runs")
    for name in list_scenarios():
        write_run(generate(load_scenario(name)), out / name)
    return out
