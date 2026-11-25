"""Etiquetas por faceta (`states.jsonl`) y verdad ampliada: las reglas de la especificación."""

import pytest

from helpers import scenario_config
from platform_app.generator.build import generate
from poc_contracts.states import FACETS, StateRow


def segments(run, facet: str) -> list[tuple[str, float, float]]:
    """Tramos (estado, desde, hasta) de una faceta."""
    out: list[list] = []
    for row in run.states:
        value = row.facets[facet]
        if out and out[-1][0] == value:
            out[-1][2] = row.t
        else:
            out.append([value, row.t, row.t])
    return [tuple(s) for s in out]


@pytest.fixture(scope="module")
def demo():
    return generate(scenario_config("demo"))


@pytest.fixture(scope="module")
def faults():
    return generate(scenario_config("faults"))


def test_every_row_has_every_facet_with_a_state_of_the_catalogue(demo, faults) -> None:
    for run in (demo, faults):
        assert [r.t for r in run.states] == [s.t for s in run.truth.trajectory]
        for row in run.states:
            StateRow.model_validate(row.model_dump()).check()
            assert set(row.facets) == set(FACETS)


def test_the_situation_and_the_cause_follow_the_demo_injections(demo) -> None:
    """Viento por encima del límite del dron (T+125), engaño (el dron se desvía unos 30 s
    después de empezar) y secuestro: la causa es la de mayor prioridad y pega mientras vuelve."""
    causes: dict = {}
    for cause, a, b in segments(demo, "drone.cause"):
        causes.setdefault(cause, (a, b))  # el primer tramo de cada causa
    assert segments(demo, "drone.situation")[0][:2] == ("on_route", 0.0)
    assert [c for c, _, _ in segments(demo, "drone.cause")] == [
        "n/a", "wind", "n/a", "wind", "n/a", "spoofed_position", "n/a", "foreign_control", "n/a"
    ]  # fmt: skip
    assert 130.0 <= causes["wind"][0] <= 145.0  # el viento supera al dron hacia T+135
    assert 198.0 < causes["spoofed_position"][0] < 245.0  # desde que el desfase pasa de 25 m
    start, end = causes["foreign_control"]
    assert 369.0 <= start <= 395.0 and 418.0 < end < 470.0  # dura hasta que vuelve a la ruta
    assert "unexplained" not in causes


def test_the_hijack_is_a_lost_link_and_the_telemetry_is_not_observable(demo) -> None:
    """Secuestro = nuestra estación pierde el enlace: la telemetría del dron vale `?` (con su
    estado real en `hidden`), el radar y la estación siguen, y el modo es control ajeno."""
    row = next(r for r in demo.states if r.t == 390.0)
    assert row.facets["link.availability"] == "lost" and row.facets["link.quality"] == "n/a"
    assert row.facets["drone.mode"] == "foreign_control"
    for facet in ("gps.availability", "gps.quality", "gps.integrity", "battery.level"):
        assert row.facets[facet] == "?" and facet in row.hidden
    assert row.facets["radar.availability"] == "normal" and row.facets["drone.situation"] != "?"
    truth = next(s for s in demo.truth.trajectory if s.t == 390.0)
    assert truth.mode == "foreign_control" and not truth.link_up


def test_with_the_gps_unavailable_its_other_facets_do_not_apply(faults) -> None:
    """`faults`: pérdida de GPS (T+245–290) y receptor callado (T+300–312)."""
    avail = {r.t: r.facets for r in faults.states}
    assert avail[250.0]["gps.availability"] == "no_fix"
    assert avail[305.0]["gps.availability"] == "no_data"
    for t in (250.0, 305.0):
        assert avail[t]["gps.quality"] == avail[t]["gps.integrity"] == "n/a"
    assert avail[130.0]["radar.availability"] == "no_data"  # radar callado de T+120 a T+180
    assert avail[130.0]["gps.quality"] == "good"


def test_the_gps_quality_comes_from_the_real_sigma_not_from_the_episode_window() -> None:
    """Un episodio suave (σ real bajo el umbral) es `good`; uno fuerte, `degraded`."""
    gps = scenario_config("nominal").sensors.gps.model_dump()
    gps["episodes"] = [
        {"start_s": 50.0, "end_s": 80.0, "sats": 11, "hdop": 1.2},  # σ = 1,5 · 1,2 / 0,8 = 2,25 m
        {"start_s": 150.0, "end_s": 180.0, "sats": 5, "hdop": 4.0},  # σ = 7,5 m
    ]
    sensors = {**scenario_config("nominal").sensors.model_dump(), "gps": gps}
    run = generate(scenario_config("nominal", sensors=sensors))
    quality = {r.t: r.facets["gps.quality"] for r in run.states}
    assert quality[60.0] == "good" and quality[160.0] == "degraded" and quality[200.0] == "good"


def test_notable_wind_is_a_fraction_of_the_wind_limit_of_each_drone() -> None:
    """«Notable» desde 0,4 × `wind_limit` (v1.2): 6 m/s son notables con un límite de 12 m/s
    (umbral 4,8) y calma con uno de 20 m/s (umbral 8)."""
    base = scenario_config("nominal")
    wind = {"base": {"speed_mps": 6.0, "from_deg": 90.0}, "episodes": []}

    def states(limit: float) -> set[str]:
        drone = {**base.drone.model_dump(), "wind_limit_mps": limit}
        run = generate(scenario_config("nominal", wind=wind, drone=drone))
        return {r.facets["environment.wind"] for r in run.states}

    assert states(12.0) == {"notable"}
    assert states(20.0) == {"calm"}
