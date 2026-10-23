"""Humo de las gráficas: se generan las tres figuras y no están vacías."""

from pathlib import Path

import pytest

from platform_app.plot_scenario import plot_scenario


@pytest.mark.parametrize("name", ["faults", "hijack"])
def test_the_three_figures_are_written(runs_dir: Path, name: str) -> None:
    paths = plot_scenario(name, runs_dir=runs_dir)
    assert [p.name for p in paths] == ["plan_xy.png", "scenario_xy.png", "scenario_time.png"]
    for p in paths:
        assert p.stat().st_size > 20_000
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_only_one_figure_can_be_requested(runs_dir: Path) -> None:
    assert [p.name for p in plot_scenario("nominal", only="plan", runs_dir=runs_dir)] == [
        "plan_xy.png"
    ]
