"""El generador es determinista con la semilla del escenario."""

from pathlib import Path

import pytest

from helpers import scenario_config
from platform_app.generator.build import generate, write_run

FILES = ["plan.json", "truth.json", "labels.json", "events.jsonl"]


@pytest.mark.parametrize("name", ["demo", "faults"])
def test_same_seed_gives_byte_identical_files(tmp_path: Path, name: str) -> None:
    for i in (1, 2):
        write_run(generate(scenario_config(name)), tmp_path / str(i))
    for f in FILES:
        assert (tmp_path / "1" / f).read_bytes() == (tmp_path / "2" / f).read_bytes(), f


def test_the_files_on_disk_match_a_fresh_generation_of_the_same_scenario(
    tmp_path: Path, runs_dir: Path
) -> None:
    write_run(generate(scenario_config("wind")), tmp_path)
    for f in FILES:
        assert (tmp_path / f).read_bytes() == (runs_dir / "wind" / f).read_bytes(), f


def test_another_seed_changes_the_noise_but_not_the_trajectory(tmp_path: Path) -> None:
    write_run(generate(scenario_config("nominal")), tmp_path / "a")
    write_run(generate(scenario_config("nominal", seed=7)), tmp_path / "b")
    assert (tmp_path / "a" / "events.jsonl").read_bytes() != (
        tmp_path / "b" / "events.jsonl"
    ).read_bytes()
    assert (tmp_path / "a" / "truth.json").read_bytes() == (
        tmp_path / "b" / "truth.json"
    ).read_bytes()
    assert (tmp_path / "a" / "plan.json").read_bytes() == (
        tmp_path / "b" / "plan.json"
    ).read_bytes()
