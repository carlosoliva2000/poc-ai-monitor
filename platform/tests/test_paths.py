"""E6: `POC_SCENARIOS_DIR` y `POC_RUNS_DIR` cambian de dónde se leen los escenarios y dónde van
las salidas; sin ellas, las rutas son las del repositorio."""

import os
import subprocess
import sys
from pathlib import Path

from platform_app.paths import REPO_ROOT

CODE = (
    "from platform_app.paths import RUNS_DIR, SCENARIOS_DIR; print(SCENARIOS_DIR); print(RUNS_DIR)"
)


def paths_with(env: dict[str, str]) -> list[str]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("POC_")}
    done = subprocess.run(
        [sys.executable, "-c", CODE], env={**clean, **env}, capture_output=True, text=True,
        check=True,
    )  # fmt: skip
    return done.stdout.split()


def test_default_paths_are_the_repo_ones() -> None:
    assert paths_with({}) == [str(REPO_ROOT / "scenarios"), str(REPO_ROOT / "runs")]


def test_environment_overrides_both_paths(tmp_path: Path) -> None:
    env = {"POC_SCENARIOS_DIR": str(tmp_path / "s"), "POC_RUNS_DIR": str(tmp_path / "r")}
    assert paths_with(env) == [str(tmp_path / "s"), str(tmp_path / "r")]
