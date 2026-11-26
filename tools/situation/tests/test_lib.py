"""Puntuación por incidente (`tools/situation/lib.py`): emparejado, retraso, falsos y parpadeos."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import Record, Variant, merge, monitor_policy, records, score, truth_policy  # noqa: E402

from ai_module.situation.policy import load_policy  # noqa: E402

CALM = {
    "gps.availability": "normal", "gps.quality": "good", "gps.integrity": "reliable",
    "link.availability": "connected", "link.quality": "good", "environment.wind": "calm",
    "drone.mode": "mission", "drone.situation": "on_route", "drone.cause": "n/a",
}  # fmt: skip


def rec(kind: str, opened: float, closed: float, family: str, **kinds: float) -> Record:
    return Record(f"i-{kind}-{opened}", {family}, {kind: opened, **kinds}, kind, opened, closed)


def test_truth_incidents_open_at_once_and_a_monitor_with_k_and_m_opens_later() -> None:
    policy = load_policy()
    spoof = {**CALM, "gps.integrity": "spoofed"}
    trace = [(float(t), spoof if 10 <= t < 30 else CALM, {}) for t in range(60)]
    (truth,) = records(truth_policy(policy), trace, 59.0)
    (mon,) = records(monitor_policy(policy, 3, 10), trace, 59.0)
    assert (truth.final_kind, truth.opened) == ("GPS_SPOOFING", 10.0)
    assert mon.opened == 12.0  # k = 3 instantes seguidos
    assert mon.closed > truth.closed  # cierra tras m instantes normales


def test_the_truth_merges_the_flicker_of_a_threshold() -> None:
    merged = merge([rec("GPS_DEGRADED", 10, 20, "gnss"), rec("GPS_DEGRADED", 25, 40, "gnss")])
    assert len(merged) == 1 and (merged[0].opened, merged[0].closed) == (10, 40)


def test_score_counts_detections_delays_and_the_two_kinds_of_false_alarm() -> None:
    truth = [rec("HIJACK", 100, 200, "control")]
    renamed = rec("LINK_LOSS", 105, 210, "control", HIJACK=118)
    renamed.final_kind = "HIJACK"
    false_attack = rec("GPS_SPOOFING", 500, 520, "spoofing")  # la verdad no tiene engaño
    false_other = rec("WIND", 700, 720, "wind")
    result = score([Variant("v", 1.0, truth, [renamed, false_attack, false_other])])
    hijack = result["per_kind"]["HIJACK"]
    assert (hijack["truth"], hijack["detected"], hijack["kind_ok"]) == (1, 1, 1)
    assert hijack["delay_open_median"] == 5 and hijack["delay_kind_median"] == 18
    assert result["false_attack_per_h"] == 1.0 and result["false_other_per_h"] == 1.0
    assert result["false_weighted_per_h"] == 4.0  # el de ataque pesa 3


def test_a_missed_incident_and_a_reopened_one_are_counted() -> None:
    truth = [rec("WIND", 100, 200, "wind"), rec("LINK_LOSS", 400, 450, "control")]
    wind = rec("WIND", 105, 215, "wind")
    wind.reopened = 1
    again = rec("WIND", 225, 240, "wind")  # vuelve a abrir a los 10 s: parpadeo
    result = score([Variant("v", 1.0, truth, [wind, again])])
    assert result["per_kind"]["LINK_LOSS"]["detected"] == 0
    assert result["flicker_pct"] == 100.0  # (1 reabierto + 1 reapertura) entre 2 de verdad


def test_the_trace_uses_the_periods_of_the_variant(tmp_path: Path) -> None:
    from lib import variant_monitor

    from ai_module.situation.features import FRESH_PERIODS, load_assets

    default = load_assets()
    (tmp_path / "assets.yaml").write_text(
        "radar: {x: 0.0, y: 0.0, max_range_m: 5000.0}\n"
        f"periods_s: {{gps: {3 * default.gps_period_s}, radar: {default.radar_period_s / 4}}}\n",
        encoding="utf-8",
    )
    monitor = variant_monitor(tmp_path)
    fresh = monitor.features._fresh_s
    assert fresh["gps"] == FRESH_PERIODS * 3 * default.gps_period_s
    assert fresh["radar"] == FRESH_PERIODS * default.radar_period_s / 4
