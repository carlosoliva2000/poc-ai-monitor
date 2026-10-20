"""Criterios de aceptación de `scenarios/README.md`, medidos sobre la salida generada.

La medición está en `platform_app.scenario_metrics`; aquí se exige que todas pasen.
"""

from pathlib import Path

import pytest

from platform_app.scenario_metrics import (
    DISCREPANCY_LIMIT_M,
    gps_radar_distance,
    load_run,
    recovery_time,
    run_checks,
)

ALL = ["demo", "fallos", "nominal", "secuestro", "spoofing", "viento"]


@pytest.mark.parametrize("name", ALL)
def test_every_acceptance_criterion_holds(runs_dir: Path, name: str) -> None:
    checks = run_checks(name, runs_dir)
    assert checks
    failed = [f"{c.criterion}: {c.value}" for c in checks if not c.ok]
    assert not failed, failed


@pytest.mark.parametrize("name", ALL)
def test_gps_radar_distance_stays_within_noise_outside_the_anomalies(
    runs_dir: Path, name: str
) -> None:
    """Fuera de las ventanas etiquetadas (con el margen de la media móvil), por debajo de 20 m."""
    run = load_run(name, runs_dir)
    windows = [(lb.start_s, lb.end_s + 6.0) for lb in run.labels]
    quiet = [v for t, v in gps_radar_distance(run) if not any(a <= t <= b for a, b in windows)]
    assert quiet
    assert max(quiet) < DISCREPANCY_LIMIT_M


def test_nominal_is_checked_against_the_nominal_criteria_only(runs_dir: Path) -> None:
    criteria = [c.criterion for c in run_checks("nominal", runs_dir)]
    assert any("desviación de la verdad" in c for c in criteria)
    assert not any("viento:" in c or "spoofing:" in c or "secuestro:" in c for c in criteria)


def test_the_demo_anomalies_are_separated_and_ordered(runs_dir: Path) -> None:
    checks = run_checks("demo", runs_dir)
    order = next(c for c in checks if "orden" in c.criterion)
    assert order.ok
    assert sum("recupera la ruta" in c.criterion for c in checks) == 3


def test_recovery_time_helper() -> None:
    dev = [(float(t), 50.0 if t < 10 else 5.0) for t in range(0, 20)]
    assert recovery_time(dev, after_s=0.0) == 10.0
    assert recovery_time([(1.0, 50.0), (2.0, 50.0)], after_s=0.0) is None
    assert recovery_time(dev, after_s=0.0, until_s=5.0) is None
