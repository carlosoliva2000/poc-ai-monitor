"""Pruebas de las características por segundo del monitor de situación (`situation/features.py`)
con eventos sencillos, a mano, y con un `events.jsonl` real."""

import re
from pathlib import Path
from typing import Any

import pytest

from ai_module.situation.features import FEATURES, Assets, FeatureExtractor, FeatureRow
from ai_module.situation.replay import is_world, read_events

ROOT = Path(__file__).resolve().parents[2]
ROUTE = [  # base → WP1 → WP2 → base; 100 s por tramo largo
    {"id": "BASE", "x": 0.0, "y": 0.0, "eta_s": 0.0},
    {"id": "WP1", "x": 1000.0, "y": 0.0, "eta_s": 100.0},
    {"id": "WP2", "x": 1000.0, "y": 1000.0, "eta_s": 200.0},
    {"id": "BASE", "x": 0.0, "y": 0.0, "eta_s": 300.0},
]


def ev(kind: str, src: str, t: float, **payload: Any) -> dict[str, Any]:
    return {"type": kind, "source": src, "sim_time": t, "event_id": f"{kind}-{t}",
            "topic": f"citadel.pub.evt.air.d1.{kind}.v1", "payload": payload}  # fmt: skip


def plan(t: float = 0.0) -> dict[str, Any]:
    return ev("MissionPlanned", "d1-mission", t, cruise_speed_mps=10.0, waypoints=ROUTE)


def gps(t: float, x: float, y: float, sats: int = 14, fix: str = "3d") -> dict[str, Any]:
    return ev("PositionUpdated", "d1-gps", t, x=x, y=y, fix=fix, sats=sats, hdop=0.8)


def track(t: float, x: float, y: float) -> dict[str, Any]:
    return ev("TrackUpdated", "radar-1", t, x=x, y=y, speed_mps=10.0, course_deg=90.0)


def gnss(t: float, cn0: float = 40.0, agc: float = 0.0) -> dict[str, Any]:
    return ev("GnssStatus", "d1-gnss", t, h_acc_m=2.0, cn0_dbhz=cn0, agc_db=agc)


def autopilot(t: float, mode: str = "mission", est=(0.0, 0.0), speed: float = 10.0) -> dict:
    return ev("AutopilotStatus", "d1-autopilot", t, mode=mode, heading_deg=90.0, airspeed_mps=speed,
              wind_est_speed_mps=3.0, wind_est_from_deg=0.0, innovation_m=1.0, est_x=est[0],
              est_y=est[1], ground_speed_mps=speed, course_deg=90.0)  # fmt: skip


def rows_of(events: list[dict[str, Any]], assets: Assets | None = None) -> list[FeatureRow]:
    fx = FeatureExtractor(assets or Assets(0.0, 0.0, 1000.0))
    rows: list[FeatureRow] = []
    for e in events:
        rows += fx.push(e)
    return rows + fx.flush()


def test_one_row_per_second_even_without_events_and_ages_grow() -> None:
    rows = rows_of([plan(), gps(0.0, 10.0, 0.0), gps(5.0, 60.0, 0.0)])
    assert [r.t for r in rows] == [0, 1, 2, 3, 4, 5]
    assert rows[0].values["age_gps"] == 0.0
    assert rows[3].values["age_gps"] == 3.0  # hace 3 s del último GPS
    assert rows[3].values["gps_dev_m"] is None  # y un dato de 3 s ya no vale
    assert rows[5].values["gps_dev_m"] == 0.0


def test_distance_to_the_pending_leg_and_leg_change() -> None:
    rows = rows_of([plan(), gps(0.0, 500.0, 30.0), ev("WaypointReached", "d1-mission", 0.5,
                    waypoint_id="WP1", index=1), gps(1.0, 1030.0, 500.0)])  # fmt: skip
    assert rows[0].values["gps_dev_m"] == 30.0 and rows[0].leg == 1 or rows[0].leg == 2
    assert rows[-1].leg == 2 and rows[-1].values["gps_dev_m"] == pytest.approx(30.0)


def test_the_reference_of_a_failsafe_return_is_the_leg_home() -> None:
    start, near = (300.0, 400.0), (290.0, 390.0)
    events = [
        plan(),
        autopilot(0.0, "mission", start),
        gps(0.0, *start),
        autopilot(1.0, "failsafe_return", start),
        gps(1.0, 150.0, 210.0),
        autopilot(2.0, "failsafe_return", near),
        gps(2.0, 150.0, 210.0),
    ]
    last = rows_of(events)[-1]
    # el tramo va de (300, 400) a la base: (150, 210) queda a 10 · 300/500 m de él
    assert last.values["mode_return"] == 1.0
    assert last.values["gps_dev_m"] == pytest.approx(10.0 * 300.0 / 500.0, abs=0.01)


def test_leg_delay_is_the_time_minus_the_planned_time_of_that_progress() -> None:
    # a mitad del tramo 1 (eta 0 → 100 s: la mitad es a los 50 s) en el segundo 60: 10 s de retraso
    last = rows_of([plan(), gps(60.0, 500.0, 0.0), gps(61.0, 500.0, 0.0)])[-2]
    assert last.values["gps_delay_s"] == pytest.approx(10.0)


def test_delay_rate_is_its_slope_over_ten_seconds() -> None:
    events = [plan()] + [
        gps(float(t), 500.0, 0.0) for t in range(60, 80)
    ]  # parado: el retraso crece
    assert rows_of(events)[-1].values["gps_delay_rate"] == pytest.approx(1.0)


def test_cusum_accumulates_the_gps_radar_gap_above_the_allowance() -> None:
    events = [plan()]
    for t in (0, 2, 4):
        events += [gps(float(t), 500.0, 0.0), track(float(t), 532.0, 0.0), gps(t + 1.0, 500.0, 0.0)]
    last = rows_of(events)[-1]
    assert last.values["gps_radar_cusum_m"] == pytest.approx(3 * (32.0 - 12.0))
    assert last.values["gps_radar_avg_m"] == pytest.approx(32.0)


def test_receiver_references_do_not_depend_on_anything_the_monitor_decides() -> None:
    events = [plan()] + [gnss(float(t), 40.0, 0.0) for t in range(60)]
    events += [gnss(60.0 + t, 46.0, -3.0) for t in range(5)]  # el C/N0 sube, el AGC baja
    last = rows_of(events)[-1]
    assert last.values["cn0_vs_base_db"] == 6.0 and last.values["agc_vs_base_db"] == -3.0
    assert last.values["cn0_vs_slow_db"] is None  # aún no hay 90 s de historia


def test_radar_range_ratio_and_no_raw_coordinates() -> None:
    row = rows_of([plan(), gps(0.0, 300.0, 400.0)], Assets(0.0, 0.0, 1000.0))[0]
    assert row.values["radar_range_ratio"] == pytest.approx(0.5)
    far = Assets(5000.0, 5000.0, 1000.0)  # el mismo dron con el radar en otro sitio
    assert rows_of([plan(), gps(0.0, 300.0, 400.0)], far)[0].values["radar_range_ratio"] > 4.0
    # ninguna característica es una coordenada suelta (ni del dron, ni del radar, ni de la base)
    assert not [n for n in FEATURES if re.search(r"(^|_)(x|y|lat|lon)(_|$)", n)]


def test_the_row_has_every_feature_and_nothing_else() -> None:
    row = rows_of([plan(), gps(0.0, 1.0, 1.0)])[0]
    assert tuple(row.values) == FEATURES


def test_no_leaks_from_other_domains_or_from_the_absolute_time() -> None:
    base = [plan(), gps(0.0, 500.0, 30.0), gnss(0.0), autopilot(0.0), track(0.0, 505.0, 20.0)]
    extra = base + [ev("FaultInjected", "platform-player", 0.5, source="gps", mode="mute")]
    extra[-1]["topic"] = "citadel.pub.evt.sim.d1.FaultInjected.v1"
    clean = [e for e in extra if is_world(e)]
    assert [r.values for r in rows_of(clean)] == [r.values for r in rows_of(base)]
    # el mismo vuelo 1000 s más tarde (y su plan con los instantes previstos igual de corridos)
    late = []
    for e in base:
        e = {**e, "sim_time": e["sim_time"] + 1000.0}
        if e["type"] == "MissionPlanned":
            e["payload"] = {**e["payload"], "waypoints": [
                {**w, "eta_s": w["eta_s"] + 1000.0} for w in ROUTE]}  # fmt: skip
        late.append(e)
    assert [r.values for r in rows_of(late)] == [r.values for r in rows_of(base)]


def test_feeding_in_chunks_gives_the_same_rows_on_a_real_run() -> None:
    events = [e for e in read_events(ROOT / "runs" / "demo" / "events.jsonl") if is_world(e)]
    whole = rows_of(events)
    live = FeatureExtractor(Assets(0.0, 0.0, 1000.0))
    rows: list[FeatureRow] = []
    for e in events:  # uno a uno, como en directo
        rows += live.push(e)
    rows += live.flush()
    assert [(r.t, r.values) for r in rows] == [(r.t, r.values) for r in whole]
    assert [r.t for r in whole] == [float(t) for t in range(len(whole))]  # sin huecos


def test_the_monitor_process_reads_only_from_the_bus() -> None:
    """El plan sale de `MissionPlanned`: el proceso no pide nada por HTTP a la plataforma."""
    source = (ROOT / "ai-module-py" / "src" / "ai_module" / "situation" / "__main__.py").read_text()
    assert "fetch_mission_plan" not in source and "httpx" not in source


# --- Características relativas (E7b, paso 2b) -------------------------------------------------


def _autopilot(t: float, wind: float = 3.0, airspeed: float = 10.0, ground: float = 10.0) -> dict:
    e = autopilot(t, speed=airspeed)
    e["payload"] |= {"wind_est_speed_mps": wind, "ground_speed_mps": ground}
    return e


def test_ages_are_in_periods_of_each_source_and_freshness_follows_them() -> None:
    slow = Assets(0.0, 0.0, 1000.0, gps_period_s=2.0)  # el GPS publica cada 2 s
    rows = rows_of([plan(), gps(0.0, 10.0, 0.0), gps(6.0, 60.0, 0.0)], slow)
    assert rows[1].values["age_gps_p"] == 0.5 and rows[1].values["gps_dev_m"] is not None  # < 1,5
    assert rows[3].values["age_gps_p"] == 1.5 and rows[3].values["gps_dev_m"] is None  # caducado
    assert rows[5].values["age_gps_p"] == 2.5 and rows[5].values["tele_gap_p"] == 2.5


def test_wind_and_speeds_are_relative_to_the_drone() -> None:
    small = Assets(0.0, 0.0, 1000.0, max_airspeed_mps=10.0, wind_limit_mps=6.0, cruise_mps=5.0)
    big = Assets(0.0, 0.0, 1000.0, max_airspeed_mps=20.0, wind_limit_mps=12.0, cruise_mps=10.0)
    a = rows_of([plan(), _autopilot(0.0, wind=3.0, airspeed=5.0, ground=5.0)], small)[0]
    b = rows_of([plan(), _autopilot(0.0, wind=6.0, airspeed=10.0, ground=10.0)], big)[0]
    for name in (
        "wind_est_over_limit", "wind_est_over_airspeed", "airspeed_over_max",
        "airspeed_over_cruise", "ground_speed_over_cruise",
    ):  # fmt: skip
        assert a.values[name] == b.values[name]
    assert a.values["wind_est_over_limit"] == 0.5 and a.values["airspeed_over_cruise"] == 1.0


def test_deviations_are_in_multiples_of_the_expected_error_of_each_sensor() -> None:
    # GPS: el receptor dice h_acc 3 m, o sea σ = 3/√2; el dron está a 30 m de la ruta
    row = rows_of([plan(), gnss(0.0), gps(0.0, 500.0, 30.0)], Assets(0.0, 0.0, 1000.0))[0]
    sigma = 2.0 / 2**0.5  # `gnss()` da h_acc_m = 2,0
    assert row.values["gps_dev_sigma"] == pytest.approx(30.0 / sigma)
    # sin receptor, el σ nominal de los activos
    row = rows_of([plan(), gps(0.0, 500.0, 30.0)], Assets(0.0, 0.0, 1000.0, gps_sigma_m=3.0))[0]
    assert row.values["gps_dev_sigma"] == pytest.approx(10.0)
    # radar: σ0 = 5 y 2 m/km, traza a 2 km del radar: σ = 9 m; 18 m de desviación son 2σ
    far = Assets(0.0, 0.0, 6000.0, radar_sigma0_m=5.0, radar_sigma_per_km_m=2.0)
    row = rows_of([plan(), track(0.0, 500.0, 18.0)], far)[0]
    expected = 18.0 / (5.0 + 2.0 * (math_dist(500.0, 18.0) / 1000.0))
    assert row.values["radar_dev_sigma"] == pytest.approx(expected, rel=1e-6)


def math_dist(x: float, y: float) -> float:
    return (x * x + y * y) ** 0.5


def test_the_same_error_in_sigmas_gives_the_same_feature_with_other_sensors() -> None:
    noisy = Assets(0.0, 0.0, 1000.0, gps_sigma_m=4.0)
    quiet = Assets(0.0, 0.0, 1000.0, gps_sigma_m=2.0)
    a = rows_of([plan(), gps(0.0, 500.0, 20.0)], noisy)[0]
    b = rows_of([plan(), gps(0.0, 500.0, 10.0)], quiet)[0]
    assert a.values["gps_dev_sigma"] == b.values["gps_dev_sigma"] == pytest.approx(5.0)


def test_receiver_levels_are_relative_to_the_nominal_of_that_receiver() -> None:
    row = rows_of([plan(), gnss(0.0, cn0=46.0, agc=-1.0)], Assets(0.0, 0.0, 1000.0))[0]
    assert row.values["cn0_vs_nominal_db"] == 1.0 and row.values["agc_vs_nominal_db"] == -1.0
    other = Assets(0.0, 0.0, 1000.0, cn0_nominal_dbhz=50.0, agc_nominal_db=2.0)
    row = rows_of([plan(), gnss(0.0, cn0=46.0, agc=-1.0)], other)[0]
    assert row.values["cn0_vs_nominal_db"] == -4.0 and row.values["agc_vs_nominal_db"] == -3.0


def test_the_link_is_compared_with_its_own_baseline() -> None:
    def link(t: float, rssi: float, latency: float) -> dict:
        return ev(
            "LinkStatus", "d1-link", t, rssi_dbm=rssi, latency_ms=latency, packet_loss_pct=0.0
        )

    events = (
        [plan()]
        + [link(float(t), -60.0, 40.0) for t in range(0, 30, 5)]
        + [link(30.0, -72.0, 100.0)]
    )
    last = rows_of(events)[-1]
    assert (
        last.values["link_rssi_vs_base_db"] == -12.0 and last.values["link_latency_vs_base"] == 2.5
    )


def test_assets_files_without_the_new_sections_load_with_defaults(tmp_path: Path) -> None:
    from ai_module.situation.features import load_assets

    old = tmp_path / "assets.yaml"
    old.write_text("radar: {x: 100.0, y: 0.0, max_range_m: 3000.0}\n", encoding="utf-8")
    assets = load_assets(old)
    assert assets.radar_x == 100.0 and assets.wind_limit_mps == 12.0 and assets.gps_period_s == 1.0


def test_the_default_assets_file_describes_the_reference_drone() -> None:
    from ai_module.situation.features import load_assets

    a = load_assets()
    assert (a.max_airspeed_mps, a.wind_limit_mps, a.cn0_nominal_dbhz) == (17.0, 12.0, 45.0)


def test_expected_errors_of_each_position_in_meters() -> None:
    assets = Assets(0.0, 0.0, 6000.0, radar_sigma0_m=5.0, radar_sigma_per_km_m=2.0, gps_sigma_m=3.0)
    row = rows_of([plan(), gnss(0.0), gps(0.0, 500.0, 30.0), track(0.0, 2000.0, 0.0)], assets)[0]
    assert row.values["gps_sigma_m"] == pytest.approx(2.0 / 2**0.5)  # h_acc / √2 del receptor
    assert row.values["radar_sigma_m"] == pytest.approx(9.0)  # 5 + 2 m/km × 2 km, una traza
    two = rows_of([plan(), track(0.0, 2000.0, 0.0), track(2.0, 2000.0, 0.0)], assets)[-1]
    assert two.values["radar_sigma_m"] == pytest.approx(9.0 / 2**0.5)  # media de dos trazas
    none = rows_of([plan(), gps(0.0, 500.0, 30.0)], assets)[0]
    assert none.values["gps_sigma_m"] == 3.0 and none.values["radar_sigma_m"] is None


def test_the_hold_point_is_between_the_two_estimates_around_the_mode_change() -> None:
    """El modo cambia en algún instante entre dos mensajes del autopiloto: con un dron rápido, la
    referencia del punto de espera es el punto medio de las dos estimas, no la del primer mensaje
    con el modo nuevo (que ya está hasta una velocidad × periodo más allá)."""
    events = [
        plan(),
        autopilot(0.0, "mission", (500.0, 0.0), speed=20.0),
        gps(0.0, 500.0, 0.0),
        autopilot(1.0, "failsafe_hold", (520.0, 0.0), speed=3.0),  # a 20 m/s: 20 m más allá
        gps(1.0, 510.0, 0.0),
        autopilot(2.0, "failsafe_hold", (512.0, 0.0), speed=0.0),
        gps(2.0, 530.0, 0.0),
    ]
    rows = rows_of(events)
    assert rows[1].values["gps_dev_m"] == pytest.approx(0.0)  # (510, 0) es el punto medio
    # al pararse (velocidad < 1 m/s) el punto de espera pasa a ser donde está: (512, 0)
    assert rows[2].values["gps_dev_m"] == pytest.approx(18.0)
    # sin mensaje anterior reciente, vale la estima del primer mensaje
    late = [plan(), autopilot(30.0, "failsafe_hold", (520.0, 0.0)), gps(30.0, 520.0, 0.0)]
    assert rows_of(late)[-1].values["gps_dev_m"] == pytest.approx(0.0)


def test_a_drone_that_is_still_moving_keeps_the_provisional_hold_point_until_it_stops() -> None:
    events = [
        plan(),
        autopilot(0.0, "mission", (500.0, 0.0), speed=20.0),
        autopilot(3.0, "failsafe_hold", (560.0, 0.0), speed=8.0),  # GPS lento: llega 3 s tarde
        gps(3.0, 560.0, 0.0),
        autopilot(6.0, "failsafe_hold", (528.0, 0.0), speed=2.0),  # va hacia el punto, aún se mueve
        gps(6.0, 528.0, 0.0),
        autopilot(9.0, "failsafe_hold", (520.0, 0.0), speed=0.3),  # parado: ese es el punto
        gps(9.0, 520.0, 0.0),
        autopilot(12.0, "failsafe_hold", (520.0, 0.0), speed=0.0),
        gps(12.0, 524.0, 0.0),
    ]
    rows = {
        r.t: r.values["gps_dev_m"]
        for r in rows_of(events, Assets(0.0, 0.0, 1000.0, gps_period_s=3.0))
    }
    assert rows[3.0] == pytest.approx(30.0)  # provisional: el punto medio (530, 0)
    assert rows[9.0] == pytest.approx(0.0)  # ya parado: el punto es donde está
    assert rows[12.0] == pytest.approx(4.0)
