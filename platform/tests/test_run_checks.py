"""Comprobación de detecciones contra etiquetas del comando de extremo a extremo (sin procesos)."""

import argparse

import pytest

from platform_app.run import Detection, ManualFault, check_detections


def raised(t: float, rule: str, source: str | None = None, det_id: str = "det-1") -> Detection:
    return Detection("Raised", t, det_id, rule, source, "medium", 1.0, 1.0, "m", "x")


LOSS = {
    "id": "F2", "type": "gps_loss", "source": "gps", "start_s": 245.0, "end_s": 290.0,
    "expected_rules": ["GPS_DEGRADED", "SOURCE_DISCREPANCY", "ROUTE_DEVIATION"],
    "eval_window": [245.0, 350.0],
}  # fmt: skip
SILENT = {
    "id": "F1", "type": "source_silent", "source": "radar", "start_s": 120.0, "end_s": 180.0,
    "expected_rules": ["SOURCE_SILENT"], "eval_window": [120.0, 240.0],
}  # fmt: skip


def test_nominal_must_have_no_detections() -> None:
    assert all(c.ok for c in check_detections([], []))
    assert not all(c.ok for c in check_detections([], [raised(10, "ROUTE_DEVIATION")]))


def test_a_gps_loss_needs_gps_degraded_first_then_discrepancy() -> None:
    good = [
        raised(245.0, "GPS_DEGRADED", "gps", "det-1"),
        raised(258.0, "SOURCE_DISCREPANCY", None, "det-2"),
        raised(291.0, "ROUTE_DEVIATION", None, "det-3"),
    ]
    assert all(c.ok for c in check_detections([LOSS], good))
    late = [raised(250.0, "GPS_DEGRADED", "gps"), *good[1:]]
    assert not all(c.ok for c in check_detections([LOSS], late))
    swapped = [raised(245.5, "GPS_DEGRADED", "gps"), raised(245.0, "SOURCE_DISCREPANCY")]
    assert not all(c.ok for c in check_detections([LOSS], swapped))


def test_a_muted_source_must_fire_its_own_silent_rule_once() -> None:
    assert all(c.ok for c in check_detections([SILENT], [raised(126, "SOURCE_SILENT", "radar")]))
    wrong = check_detections([SILENT], [raised(126, "SOURCE_SILENT", "gps")])
    assert not all(c.ok for c in wrong)
    twice = [raised(126, "SOURCE_SILENT", "radar", "a"), raised(130, "SOURCE_SILENT", "radar", "b")]
    assert not all(c.ok for c in check_detections([SILENT], twice))


def test_detections_outside_the_windows_are_false_alarms() -> None:
    found = [raised(126, "SOURCE_SILENT", "radar"), raised(400, "ROUTE_DEVIATION", None, "det-9")]
    assert not all(c.ok for c in check_detections([SILENT], found))


def test_manual_fault_argument() -> None:
    assert ManualFault.parse("radar:mute:150:200") == ManualFault("radar", "mute", 150.0, 200.0)
    with pytest.raises(argparse.ArgumentTypeError):
        ManualFault.parse("radar:150")
