"""Regla determinista de la situación del dron: entradas y tabla."""

from ai_module.decision.table import load_tables
from ai_module.situation.policy import HERE
from ai_module.situation.situation_rule import cause_active, position_used, rule_inputs

TABLE = load_tables(HERE / "situation_rule.yaml")["drone_situation_rule"]
CALM = {
    "environment.wind": "calm", "gps.integrity": "reliable", "gps.availability": "normal",
    "drone.mode": "mission",
}  # fmt: skip


def step(dev: float | None, previous: str, states=None, source="gps", sigma=2.0, k=1.0) -> str:  # noqa: ANN001
    values = {"gps_dev_m": None, "radar_dev_m": None, "gps_sigma_m": sigma, "radar_sigma_m": sigma}
    values["gps_dev_m" if source == "gps" else "radar_dev_m"] = dev
    inputs = rule_inputs(values, states or CALM, previous, k)
    return str(TABLE.evaluate(inputs).then["state"])


def test_the_hysteresis_of_the_label_with_and_without_an_active_cause() -> None:
    windy = {**CALM, "environment.wind": "notable"}
    assert step(10.0, "on_route") == "on_route"
    assert step(20.0, "on_route") == "on_route"  # entre 15 y 25 desde «en ruta», se queda
    assert step(40.0, "on_route", windy) == "deviated"
    assert step(20.0, "deviated", windy) == "deviated"  # entre 15 y 25 con la causa activa
    assert step(20.0, "deviated") == "returning"  # sin causa activa: volviendo
    assert step(20.0, "returning", windy) == "returning"  # y no vuelve a «desviado» entre 15 y 25
    assert step(40.0, "returning", windy) == "deviated"  # pero a más de 25 m con causa, sí
    assert step(40.0, "deviated") == "returning"  # a más de 25 m, sin causa, ya vuelto: volviendo
    assert step(40.0, "on_route") == "deviated"  # rebasamiento: fuera de ruta sin causa
    assert step(8.0, "returning") == "on_route"  # a menos de 15 m, en ruta


def test_no_usable_position_keeps_the_previous_situation() -> None:
    assert step(None, "deviated") == "deviated"
    assert step(None, "returning") == "returning"
    assert step(None, "on_route") == "on_route"


def test_the_margin_stops_a_false_deviation_from_noise_near_25_m() -> None:
    """El dron está a 24 m (en ruta) y la medida tiene σ = 4 m: sin margen una lectura de 28 m lo
    declara desviado; con un margen de 1σ hace falta estar seguro de que pasa de 25 m."""
    readings = [24.0, 28.0, 23.0, 27.0, 22.0, 29.0]
    windy = {**CALM, "environment.wind": "notable"}
    for k, final in ((0.0, "deviated"), (1.0, "on_route")):
        state = "on_route"
        for dev in readings:
            state = step(dev, state, windy, sigma=4.0, k=k)
        assert state == final


def test_the_gps_is_believed_only_if_it_is_not_spoofed_and_the_radar_is_the_fallback() -> None:
    values = {"gps_dev_m": 5.0, "radar_dev_m": 60.0, "gps_sigma_m": 1.5, "radar_sigma_m": 8.0}
    assert position_used(values, CALM) == ("gps", 5.0, 1.5)
    assert position_used(values, {**CALM, "gps.integrity": "spoofed"}) == ("radar", 60.0, 8.0)
    assert position_used({**values, "gps_dev_m": None}, CALM)[0] == "radar"  # sin telemetría
    assert position_used({**values, "gps_dev_m": None, "radar_dev_m": None}, CALM)[0] is None
    spoofed = {**CALM, "gps.integrity": "spoofed"}
    assert step(60.0, "on_route", spoofed, source="radar") == "deviated"  # el GPS dice 5 m, miente


def test_the_causes_are_the_four_of_the_label() -> None:
    assert not cause_active(CALM)
    active = (
        ("environment.wind", "beyond_limit"),
        ("gps.integrity", "spoofed"),
        ("gps.availability", "no_fix"),
        ("drone.mode", "foreign_control"),
    )
    for key, value in active:
        assert cause_active({**CALM, key: value})
    assert not cause_active({**CALM, "environment.wind": "calm", "drone.mode": "failsafe_return"})
