"""Criterio de recuperación (función pura) sobre los datos de `demo`: el `ROUTE_DEVIATION` de
T+03:42 (fin del spoofing) lo cumple y el de T+05:38 (secuestro) no. Comprueba que la skill
`route-deviation` está bien planteada sobre los datos; el monitor no ejecuta este código."""

from pathlib import Path

import pytest

from ai_module.detect_file import read_events
from ai_module.detector import Detector
from ai_module.geometry import distance_to_route
from ai_module.recovery import has_sudden_jump, is_gps_recovery
from poc_contracts.enums import EventType

RUNS = Path(__file__).resolve().parents[2] / "runs"
DEMO = RUNS / "demo" / "events.jsonl"


def demo_context(path: Path = DEMO) -> dict[str, dict]:
    """Por cada `ROUTE_DEVIATION` Raised de `demo`: su instante, la desviación del GPS de los
    últimos 5 s y hasta cuándo hubo una alerta del GPS (el episodio de `SOURCE_DISCREPANCY`)."""
    events = list(read_events(path))
    route: list[tuple[float, float]] = []
    gps: list[tuple[float, float]] = []
    detector = Detector()
    raised: dict[str, float] = {}
    gps_alert_until: float | None = None
    out: dict[str, dict] = {}
    for event in events:
        if event.type == EventType.MISSION_PLANNED:
            route = [(w["x"], w["y"]) for w in event.payload["waypoints"]]
        if event.type == EventType.POSITION_UPDATED and route:
            p = event.payload
            gps.append((event.sim_time, distance_to_route((p["x"], p["y"]), route)))
        for d in detector.feed(event):
            p = d.payload
            if d.type == EventType.DETECTION_RAISED and p["rule"] == "SOURCE_DISCREPANCY":
                raised[p["detection_id"]] = d.sim_time
                gps_alert_until = float("inf")  # alerta del GPS abierta mientras dure
            elif d.type == EventType.DETECTION_CLEARED and p["detection_id"] in raised:
                gps_alert_until = d.sim_time  # la alerta se cierra con su última detección
            elif d.type == EventType.DETECTION_RAISED and p["rule"] == "ROUTE_DEVIATION":
                recent = [(t, v) for t, v in gps if d.sim_time - 5 <= t <= d.sim_time]
                until = d.sim_time if gps_alert_until == float("inf") else gps_alert_until
                out[f"T+{int(d.sim_time) // 60:02d}:{int(d.sim_time) % 60:02d}"] = {
                    "now": d.sim_time, "deviation": recent, "until": until,
                }  # fmt: skip
    return out


def test_demo_recovery_after_the_spoofing_meets_the_criterion() -> None:
    ctx = demo_context()["T+03:42"]
    assert has_sudden_jump(ctx["deviation"])
    assert is_gps_recovery(ctx["deviation"], ctx["now"], ctx["until"])


def test_demo_hijack_deviation_is_not_a_recovery() -> None:
    ctx = demo_context()["T+05:38"]
    # el dron se aleja a ~15 m/s (7 m, 21 m, 37 m): nunca de < 15 m a > 30 m en una muestra
    assert not has_sudden_jump(ctx["deviation"])
    assert not is_gps_recovery(ctx["deviation"], ctx["now"], ctx["until"])


def test_the_other_scenarios_agree_with_demo() -> None:
    for scenario, key, expected in [
        ("spoofing", "T+03:42", True),
        ("faults", "T+04:50", True),  # fin de la pérdida de GPS
        ("hijack", "T+05:38", False),
        ("wind", "T+01:46", False),
    ]:
        ctx = demo_context(RUNS / scenario / "events.jsonl")[key]
        until = ctx["until"] if expected else None
        assert is_gps_recovery(ctx["deviation"], ctx["now"], until) is expected, scenario
        assert has_sudden_jump(ctx["deviation"]) is expected, scenario


def test_demo_wind_deviation_is_not_a_recovery() -> None:
    ctx = demo_context()["T+01:46"]
    assert not is_gps_recovery(ctx["deviation"], ctx["now"], ctx["until"])  # ni alerta ni salto


def test_the_hijack_would_not_pass_even_with_a_recent_gps_alert() -> None:
    """La condición 2 sola ya descarta el secuestro: no depende de la antigüedad de la alerta."""
    ctx = demo_context()["T+05:38"]
    assert not is_gps_recovery(ctx["deviation"], ctx["now"], ctx["now"])


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        ([(0, 5.0), (1, 6.0), (2, 40.0)], True),  # el salto está en el último segundo
        ([(0, 5.0), (1, 20.0), (2, 40.0)], False),  # < 15 -> > 30, pero en dos pasos
        ([(0, 5.0), (1, 40.0)], True),  # una muestra
        ([(0, 5.0), (2, 40.0)], False),  # tarda 2 s
        ([(0, 20.0), (1, 40.0)], False),  # ya partía de 15 m o más
        ([(0, 5.0), (1, 25.0), (2, 29.0)], False),  # no supera 30 m
        ([(0, 10.0), (1, 14.0), (2, 17.0), (3, 20.0), (4, 24.0), (5, 33.0)], False),  # gradual
        ([], False),
    ],
)
def test_sudden_jump(series: list[tuple[float, float]], expected: bool) -> None:
    assert has_sudden_jump(series) is expected


def test_recent_gps_alert_window() -> None:
    jump = [(0, 5.0), (1, 60.0)]
    assert is_gps_recovery(jump, now=100.0, gps_alert_active_until=40.0)  # cerrada hace 60 s
    assert not is_gps_recovery(jump, now=100.0, gps_alert_active_until=39.0)  # hace 61 s
    assert not is_gps_recovery(jump, now=100.0, gps_alert_active_until=None)  # nunca hubo
