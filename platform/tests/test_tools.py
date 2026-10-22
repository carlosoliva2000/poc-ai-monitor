"""Tools de datos: corte temporal, sin dominio `sim`, sin verdad, y resultados del contrato."""

import json
from pathlib import Path

import pytest
from test_player import detection, monitor_reply

from helpers import make_player
from platform_app.player import Player
from platform_app.tools import ToolContext, ToolFailure, call_tool
from poc_contracts.enums import EventType, ToolSource
from poc_contracts.tools import (
    FlightSummary,
    GetEventsResult,
    MissionPlanResult,
    MyAlertsResult,
    TrackMetrics,
)

SOURCES = [s.value for s in ToolSource]
FORBIDDEN = ("truth", "faultinjected", "faultcleared", "interactive", "simulation", "origin")


def context(player: Player) -> ToolContext:
    return ToolContext(player.bus.timeline, lambda: player.sim_time)


def at(runs_dir: Path, scenario: str, seconds: float) -> tuple[Player, ToolContext]:
    player = make_player(runs_dir)
    player.load(scenario)
    player.play()
    player.advance(seconds)
    return player, context(player)


def test_time_cut_for_every_tool(runs_dir: Path) -> None:
    player, ctx = at(runs_dir, "demo", 200.3)
    now = player.sim_time
    assert 200.0 <= now < 201.0
    for source in SOURCES:
        result = call_tool(ctx, "get_events", {"source": source, "last_n": 50, "until": 1e9})
        assert all(e["sim_time"] <= now for e in result["events"])
    gps = call_tool(ctx, "get_events", {"source": "gps", "last_n": 1, "until": 1e9})
    assert gps["events"][0]["sim_time"] == 200.0
    metrics = call_tool(ctx, "get_track_metrics", {"since": 0, "until": 1e9})
    assert metrics["until"] == now
    assert metrics["last_seen_sim_time"]["gps"] == 200.0
    assert metrics["samples"]["gps"] == 200
    # una ventana entera en el futuro queda vacía
    future = call_tool(ctx, "get_track_metrics", {"since": 300, "until": 400})
    assert future["samples"] == {"gps": 0, "radar": 0} and not future["gps_available"]
    assert future["until"] == now
    assert call_tool(ctx, "get_events", {"source": "gps", "since": 300})["events"] == []


def test_tools_never_expose_sim_domain_or_truth(runs_dir: Path) -> None:
    player, ctx = at(runs_dir, "fallos", 300.0)
    player.set_interactive(True)
    player.advance(1)
    timeline_types = {e.type for e in player.bus.timeline.all()}
    assert EventType.FAULT_INJECTED in timeline_types  # están en el timeline…
    seen = []
    for source in SOURCES:
        for event_type in (None, "FaultInjected", "SimulationStarted", "InteractiveModeChanged"):
            args = {"source": source, "last_n": 50, "until": 1e9}
            if event_type:
                args["type"] = event_type
            result = call_tool(ctx, "get_events", args)
            seen += [e["type"] for e in result["events"]]
    assert seen
    assert not {"FaultInjected", "FaultCleared"} & set(seen)
    assert not [t for t in seen if t.startswith("Simulation") or t == "InteractiveModeChanged"]
    outputs = [
        call_tool(ctx, name, args)
        for name, args in [
            ("get_mission_plan", {}),
            ("get_track_metrics", {"since": 0, "until": 1e9}),
            ("get_my_alerts", {}),
            ("get_flight_summary", {}),
        ]
    ]
    text = json.dumps(outputs).lower()
    assert not [word for word in FORBIDDEN if word in text]


def test_get_events_compact_format_and_limits(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "demo", 100.2)
    default = GetEventsResult.model_validate(call_tool(ctx, "get_events", {"source": "gps"}))
    assert len(default.events) == 10 and default.truncated
    assert [e.sim_time for e in default.events] == sorted(e.sim_time for e in default.events)
    raw = call_tool(ctx, "get_events", {"source": "meteo", "last_n": 1})
    event = raw["events"][0]
    assert event["event_id"] == "met-0010" and event["type"] == "WindReported"
    assert event["sim_time"] == 100.0 and event["t"] == "T+01:40"
    assert set(event) == {
        "event_id",
        "type",
        "sim_time",
        "t",
        "station_id",
        "speed_mps",
        "gust_mps",
        "from_deg",
    }
    assert len(call_tool(ctx, "get_events", {"source": "gps", "last_n": 500})["events"]) == 50
    only = call_tool(ctx, "get_events", {"source": "mission", "type": "WaypointReached"})
    assert {e["type"] for e in only["events"]} == {"WaypointReached"}


def test_bad_arguments_and_unknown_tool(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "nominal", 5.0)
    with pytest.raises(ToolFailure, match="argumentos no válidos"):
        call_tool(ctx, "get_events", {"source": "sim"})
    with pytest.raises(ToolFailure, match="argumentos no válidos"):
        call_tool(ctx, "get_events", {"source": "gps", "extra": 1})
    with pytest.raises(ToolFailure, match="desconocida"):
        call_tool(ctx, "publish_alert", {})
    with pytest.raises(ToolFailure, match="since"):
        call_tool(ctx, "get_track_metrics", {"since": 10, "until": 5})


def test_mission_plan_and_next_waypoint(runs_dir: Path) -> None:
    player = make_player(runs_dir)
    player.load("demo")
    ctx = context(player)
    with pytest.raises(ToolFailure, match="plan de misión"):
        call_tool(ctx, "get_mission_plan", {})
    player.play()
    player.advance(1)
    plan = MissionPlanResult.model_validate(call_tool(ctx, "get_mission_plan", {}))
    assert plan.next_waypoint == "WP1"
    assert [w.id for w in plan.waypoints][0] == "BASE" and plan.waypoints[-1].id == "BASE"
    player.advance(100)
    assert call_tool(ctx, "get_mission_plan", {})["next_waypoint"] == "WP2"
    player.run_to_end()
    assert call_tool(ctx, "get_mission_plan", {})["next_waypoint"] is None


def test_track_metrics_on_the_wind_episode(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "viento", 150.0)
    quiet = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 20, "until": 50})
    )
    assert quiet.gps_available and quiet.radar_available
    assert quiet.gps_deviation_from_plan_m.max < 15
    assert quiet.samples.gps == 31 and quiet.samples.radar == 16
    assert quiet.first_event_ids == ["gps-000020", "rad-000010"]
    assert quiet.last_event_ids == ["gps-000050", "rad-000025"]
    assert quiet.gps_radar_distance_m.mean < 15
    windy = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 100, "until": 150})
    )
    assert windy.gps_deviation_from_plan_m.max > 30
    assert windy.gps_deviation_from_plan_m.trend is not None
    assert windy.gps_radar_distance_m.max < 25  # las dos fuentes coinciden: es el viento
    assert windy.drift_direction_deg is not None
    assert windy.next_waypoint in {"WP1", "WP2", "WP3", "WP4"}
    assert windy.bearing_to_next_waypoint_deg is not None
    assert windy.course_deg.gps is not None and windy.course_deg.radar is not None
    assert windy.mean_speed_mps.gps and windy.mean_speed_mps.radar


def test_track_metrics_with_the_radar_silenced(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "fallos", 150.2)  # el radar calla de 120 a 180 s
    metrics = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 130, "until": 150})
    )
    assert metrics.radar_available is False and metrics.gps_available is True
    assert metrics.samples.radar == 0 and metrics.samples.gps == 21
    assert metrics.radar_deviation_from_plan_m is None
    assert metrics.gps_radar_distance_m is None
    assert metrics.course_deg.radar is None and metrics.mean_speed_mps.radar is None
    assert metrics.last_seen_sim_time.radar == 118.0
    assert metrics.last_seen_sim_time.gps == 150.0
    assert metrics.last_event_ids == ["gps-000150"]
    assert metrics.gps_deviation_from_plan_m is not None


def test_track_metrics_with_the_gps_silenced(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "fallos", 311.0)  # el GPS calla de 300 a 312 s
    metrics = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 301, "until": 311})
    )
    assert metrics.gps_available is False and metrics.radar_available is True
    assert metrics.gps_deviation_from_plan_m is None and metrics.gps_radar_distance_m is None
    assert metrics.drift_direction_deg is None and metrics.next_waypoint is None
    assert metrics.bearing_to_next_waypoint_deg is None
    assert metrics.course_deg.gps is None and metrics.mean_speed_mps.gps is None
    assert metrics.last_seen_sim_time.gps == 299.0


def test_flight_summary_after_the_flight(runs_dir: Path) -> None:
    player, ctx = at(runs_dir, "demo", 1.0)
    player.run_to_end()
    summary = FlightSummary.model_validate(call_tool(ctx, "get_flight_summary", {}))
    assert summary.mission_id == "MSN-DEMO"
    assert summary.mission_completed and summary.completion_reason == "returned_to_base"
    assert summary.duration_s == pytest.approx(556.3, abs=1.0)
    assert summary.waypoints_planned == ["WP1", "WP2", "WP3", "WP4"]
    assert [w.waypoint_id for w in summary.waypoints_reached] == ["WP1", "WP2", "WP3", "WP4"]
    assert summary.distance_m.gps and summary.distance_m.radar
    assert 0.9 < summary.distance_m.gps / summary.distance_m.radar < 1.1
    assert summary.detections_by_rule.model_dump() == {
        "ROUTE_DEVIATION": 0,
        "SOURCE_DISCREPANCY": 0,
        "SOURCE_SILENT": 0,
        "GPS_DEGRADED": 0,
    }
    assert set(summary.alerts_by_cause.model_dump()) == {
        "WIND",
        "HIJACK",
        "GPS_SPOOFING",
        "SENSOR_FAULT",
        "GPS_JAMMING",
        "UNKNOWN",
    }
    assert summary.alerts_open == summary.alerts_closed == 0


def test_flight_summary_midway_has_every_key(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "nominal", 10.0)
    raw = call_tool(ctx, "get_flight_summary", {})
    assert raw["mission_completed"] is False and raw["completion_reason"] is None
    assert raw["duration_s"] == pytest.approx(10.0, abs=0.2)
    assert len(raw["detections_by_rule"]) == 4 and len(raw["alerts_by_cause"]) == 6
    assert raw["waypoints_reached"] == []


def test_alerts_summary_and_status(runs_dir: Path) -> None:
    player, ctx = at(runs_dir, "nominal", 20.0)
    bus = player.bus
    d1 = bus.publish(detection(1, 20.0))
    bus.publish(monitor_reply(1, d1.event_id, 20.0))
    second = monitor_reply(2, "det-0001", 20.0).model_copy(
        update={"payload": {**monitor_reply(2, "det-0001", 20.0).payload, "supersedes": "ai-0001"}}
    )
    bus.publish(second)
    alerts = MyAlertsResult.model_validate(call_tool(ctx, "get_my_alerts", {}))
    assert [(a.alert_id, a.status.value) for a in alerts.alerts] == [
        ("ai-0001", "superseded"),
        ("ai-0002", "open"),
    ]
    only_open = call_tool(ctx, "get_my_alerts", {"only_open": True})
    assert [a["alert_id"] for a in only_open["alerts"]] == ["ai-0002"]
    summary = call_tool(ctx, "get_flight_summary", {})
    assert summary["detections_by_rule"]["ROUTE_DEVIATION"] == 1
    assert summary["alerts_by_cause"]["WIND"] == 1 and summary["alerts_open"] == 1  # una cadena


def test_detection_acknowledged_is_ignored_by_alerts_and_summary(runs_dir: Path) -> None:
    """Las respuestas que no son alertas no cuentan para `get_my_alerts` ni `get_flight_summary`,
    pero `get_events(source="monitor")` las devuelve (son eventos del monitor)."""
    from platform_app.generator.events import make_event
    from platform_app.generator.scenario_io import load_scenario

    player, ctx = at(runs_dir, "nominal", 20.0)
    d1 = player.bus.publish(detection(1, 20.0))
    payload = {
        "detection_id": "det-0001",
        "alert_id": None,
        "reason": "sin alerta",
        "as_of_sim_time": 20.0,
        "fallback": False,
    }
    ack = make_event(load_scenario("nominal"), EventType.DETECTION_ACKNOWLEDGED, 20.0, 1, payload)
    player.bus.publish(ack.model_copy(update={"causation_id": d1.event_id}))
    assert call_tool(ctx, "get_my_alerts", {})["alerts"] == []
    summary = call_tool(ctx, "get_flight_summary", {})
    assert summary["alerts_open"] == 0 and sum(summary["alerts_by_cause"].values()) == 0
    events = call_tool(ctx, "get_events", {"source": "monitor"})["events"]
    assert [e["type"] for e in events] == ["DetectionAcknowledged"]


def test_track_metrics_wind_of_the_same_window(runs_dir: Path) -> None:
    """El viento de la ventana viene calculado: media, racha máxima, hacia dónde empuja y la
    diferencia con la deriva (el modelo no hace aritmética de ángulos)."""
    _, ctx = at(runs_dir, "viento", 150.0)
    metrics = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 120, "until": 150})
    )
    wind = metrics.wind
    assert wind is not None and wind.samples == 3  # un WindReported cada 10 s
    assert wind.mean_speed_mps >= 5 and wind.max_gust_mps >= 8  # el episodio es viento notable
    assert wind.wind_to_deg == pytest.approx((wind.from_deg + 180) % 360, abs=0.2)
    assert metrics.drift_direction_deg is not None
    expected = abs(metrics.drift_direction_deg - wind.wind_to_deg) % 360
    assert wind.drift_vs_wind_deg == pytest.approx(min(expected, 360 - expected), abs=0.2)
    assert 0 <= wind.drift_vs_wind_deg <= 180
    assert wind.drift_vs_wind_deg <= 45  # la deriva va a favor del viento
    # el id para citar existe y es de la ventana
    raw = call_tool(ctx, "get_events", {"source": "meteo", "last_n": 1, "until": 150})
    assert wind.last_event_id == raw["events"][-1]["event_id"]


def test_track_metrics_wind_is_weak_and_not_aligned_in_the_hijack(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "secuestro", 340.0)
    metrics = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 310, "until": 340})
    )
    assert metrics.wind is not None
    assert metrics.wind.mean_speed_mps < 5 and metrics.wind.max_gust_mps < 8


def test_track_metrics_wind_is_null_without_meteo_in_the_window(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "viento", 150.0)
    metrics = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 141, "until": 149})
    )
    assert metrics.wind is None  # ningún WindReported entre 141 y 149 s


def test_wind_helpers() -> None:
    from platform_app.tools.metrics import _angle_diff

    assert _angle_diff(350, 10) == 20 and _angle_diff(10, 350) == 20
    assert _angle_diff(0, 180) == 180 and _angle_diff(90, 90) == 0


def test_computed_facts_wind(runs_dir: Path) -> None:
    """`notable` (media ≥ 5 o racha ≥ 8) y `with_drift` (≤ 45°) los calcula la plataforma."""
    _, ctx = at(runs_dir, "viento", 150.0)
    windy = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 120, "until": 150})
    )
    assert windy.wind.notable and windy.wind.with_drift
    _, ctx = at(runs_dir, "secuestro", 340.0)
    hijack = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 310, "until": 340})
    )
    assert not hijack.wind.notable and not hijack.wind.with_drift  # media 1,9, 62° de diferencia
    _, ctx = at(runs_dir, "viento", 106.5)  # al abrirse la detección el viento está subiendo
    rising = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 76, "until": 106})
    )
    assert rising.wind.notable and rising.wind.mean_speed_mps < 5  # notable por la racha (9,7)


def test_computed_facts_gps_radar_and_max_step(runs_dir: Path) -> None:
    """Recuperación tras el spoofing: GPS y radar discrepaban y el GPS salta de golpe. Viento y
    secuestro: coinciden y la desviación crece como mucho ~15 m por segundo."""
    _, ctx = at(runs_dir, "spoofing", 222.5)
    recovery = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 192, "until": 222})
    )
    assert recovery.gps_radar.disagreed and recovery.gps_max_step_m >= 30
    _, ctx = at(runs_dir, "secuestro", 338.5)
    hijack = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 308, "until": 338})
    )
    assert not hijack.gps_radar.disagreed and hijack.gps_max_step_m < 30
    _, ctx = at(runs_dir, "viento", 106.5)
    wind = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 76, "until": 106})
    )
    assert not wind.gps_radar.disagreed and wind.gps_max_step_m < 30
    _, ctx = at(runs_dir, "fallos", 290.5)  # fin de la pérdida de GPS
    loss = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 260, "until": 290})
    )
    assert loss.gps_radar.disagreed and loss.gps_max_step_m >= 30


def test_computed_facts_are_null_without_data(runs_dir: Path) -> None:
    _, ctx = at(runs_dir, "fallos", 150.2)  # el radar calla de 120 a 180 s
    metrics = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 130, "until": 150})
    )
    assert metrics.gps_radar is None and metrics.gps_max_step_m is not None
    _, ctx = at(runs_dir, "fallos", 311.0)  # el GPS calla de 300 a 312 s
    silent = TrackMetrics.model_validate(
        call_tool(ctx, "get_track_metrics", {"since": 305, "until": 311})
    )
    assert silent.gps_max_step_m is None and silent.gps_radar is None
