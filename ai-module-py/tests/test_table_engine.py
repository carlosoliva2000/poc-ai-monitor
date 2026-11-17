"""E6: el monitor con `engine: table` (la tabla de decisión, sin LLM) con una plataforma falsa.

Cada aviso recibe respuesta sin llamar al LLM, por las mismas rutas que las del modelo (con los
guardrails), y la alerta lleva `decided_by: table` y la fila (`rule_id`). Con `engine: llm` (por
defecto) nada cambia.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    detection_event,
    make_runtime,
    reset_ids,
    run,
)

from ai_module.agent.assets import Assets
from ai_module.agent.profiles import load_profile
from ai_module.monitor import Monitor
from poc_contracts.enums import EventType

RESPONSES = (EventType.ANOMALY_DETECTED, EventType.ALERT_CLOSED, EventType.DETECTION_ACKNOWLEDGED)
IDS = ("gps-000001", "gps-000002", "gps-000003", "rad-000001", "rad-000002", "met-0001",
       "lnk-0001", "lnk-0002")  # fmt: skip


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def metrics(**overrides: Any) -> dict[str, Any]:
    """Un `get_track_metrics` de viento: notable, a favor de la deriva, GPS y radar de acuerdo."""
    base: dict[str, Any] = {
        "since": 0.0,
        "until": 20.0,
        "gps_deviation_from_plan_m": {"mean": 20.0, "max": 35.0, "trend": "increasing"},
        "radar_deviation_from_plan_m": {"mean": 19.0, "max": 34.0, "trend": "increasing"},
        "gps_radar_distance_m": {"mean": 5.0, "max": 7.0, "trend": "stable"},
        "drift_direction_deg": 170.0,
        "course_deg": {"gps": 90.0, "radar": 91.0},
        "bearing_to_next_waypoint_deg": 80.0,
        "wind": {
            "mean_speed_mps": 11.0,
            "max_gust_mps": 15.0,
            "from_deg": 350.0,
            "wind_to_deg": 170.0,
            "drift_vs_wind_deg": 3.0,
            "notable": True,
            "with_drift": True,
            "samples": 2,
            "last_event_id": "met-0001",
        },  # fmt: skip
        "gps_radar": {"disagreed": False},
        "gps_max_step_m": 3.0,
        "radar_available": True,
        "gps_available": True,
        "first_event_ids": ["gps-000001", "rad-000001"],
        "last_event_ids": ["gps-000003", "rad-000002"],
        "now": {
            "as_of": 20.0,
            "gps_fix": "3d",
            "gps_radar_distance_m": 5.0,
            "gps_radar_agree": True,
            "gps_deviation_from_plan_m": 35.0,
            "radar_deviation_from_plan_m": 34.0,
            "wind": "from N (350°), pushing S",
            "route_trend": "moving_away",
        },  # fmt: skip
    }
    base.update(overrides)
    return base


def events(args: dict[str, Any]) -> dict[str, Any]:
    source = args.get("source")
    if source == "link":
        return {"events": [
            {"event_id": "lnk-0001", "sim_time": 15.0, "controller_id": "GCS-1",
             "rssi_dbm": -62.0, "latency_ms": 45.0},
            {"event_id": "lnk-0002", "sim_time": 20.0, "controller_id": "GCS-1",
             "rssi_dbm": -61.0, "latency_ms": 44.0},
        ]}  # fmt: skip
    if source == "gps":
        return {"events": [{"event_id": "gps-000003", "sim_time": 20.0, "fix": "3d", "sats": 14,
                            "hdop": 0.8}]}  # fmt: skip
    if source == "radar":
        return {"events": [{"event_id": "rad-000002", "sim_time": 20.0, "quality": 0.9}]}
    return {"events": []}


def setup(tmp_path: Path, engine: str = "table", track: dict[str, Any] | None = None):
    llm = FakeLlm(Script("no debería llamarse"))
    platform = FakePlatform({"get_track_metrics": track or metrics(), "get_events": events})
    profile = load_profile(engine) if engine != "llm" else None
    assets = Assets(profile.assets_dir, profile) if profile else Assets()
    rt, published = make_runtime(tmp_path, llm, platform, assets)
    for event_id in IDS:  # como si hubieran llegado por el WebSocket (cualquier fuente)
        rt.index._times[event_id] = 1.0
    rt.clock.observe(20.0)
    return rt, published, Monitor(rt), llm


def responses(published: list) -> list:
    return [e for e in published if e.type in RESPONSES]


def test_the_table_answers_a_wind_deviation_without_the_llm(tmp_path: Path) -> None:
    rt, published, monitor, llm = setup(tmp_path)
    event = detection_event("raised", "det-0001", 20.0)
    run(monitor.handle_batch([event]))
    [alert] = responses(published)
    p = alert.payload
    assert alert.type == EventType.ANOMALY_DETECTED and alert.causation_id == event.event_id
    assert (p["cause"], p["decided_by"], p["rule_id"]) == ("WIND", "table", "C17")
    # el dron se aleja (`moving_away`): la situación empeora → medium (S08)
    assert p["severity"] == "medium" and p["phase"] == "active"
    assert p["confidence"] == 0.8  # estación y posición, sin contradicciones (K02)
    assert p["checks"]["wind_notable"] and p["checks"]["link_checked"]
    assert "_" not in p["summary"] and "true" not in p["explanation"].lower()
    assert llm.requests == []  # ni una llamada al LLM
    [trace] = rt.trace.records
    assert trace["engine"] == "table" and len(trace["table_hash"]) == 64
    assert trace["table"][0]["rows"] == {"cause": "C17", "severity": "S08", "confidence": "K02"}
    assert trace["guardrail_rejections"] == [] and not trace["fallback"]
    # la web ve la fila como una «llamada» `decision_table` bajo el aviso
    [shown] = [e for e in published if e.type == EventType.AGENT_TOOL_CALL]
    assert shown.payload["tool"] == "decision_table" and shown.causation_id == event.event_id


def test_a_wind_under_control_is_low(tmp_path: Path) -> None:
    now = {**metrics()["now"], "route_trend": "approaching"}
    _, published, monitor, _ = setup(tmp_path, track=metrics(now=now))
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    [alert] = responses(published)
    assert (alert.payload["severity"], alert.payload["rule_id"]) == ("low", "C17")


def test_same_episode_is_acknowledged_and_the_last_clearing_closes(tmp_path: Path) -> None:
    rt, published, monitor, _ = setup(tmp_path)
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    run(monitor.handle_batch([detection_event("updated", "det-0001", 20.0)]))
    run(monitor.handle_batch([detection_event("cleared", "det-0001", 20.0)]))
    kinds = [e.type for e in responses(published)]
    assert kinds == [
        EventType.ANOMALY_DETECTED,
        EventType.DETECTION_ACKNOWLEDGED,
        EventType.ALERT_CLOSED,
    ]
    ack = responses(published)[1].payload
    assert ack["alert_id"] == responses(published)[0].payload["alert_id"]
    assert "40.0 m" in responses(published)[2].payload["reason"]  # duración y máximo, con unidad
    assert not rt.state.open_alerts()


def test_a_silent_source_gets_its_own_sensor_fault(tmp_path: Path) -> None:
    _, published, monitor, _ = setup(tmp_path)
    event = detection_event(
        "raised", "det-0001", 20.0, rule="SOURCE_SILENT", source="battery", trigger=("gps-000001",)
    )
    run(monitor.handle_batch([event]))
    [alert] = responses(published)
    p = alert.payload
    assert (p["cause"], p["rule_id"], p["severity"]) == ("SENSOR_FAULT", "C01", "low")
    assert "battery" in p["summary"]


def test_the_default_engine_is_the_llm_and_alerts_keep_their_old_shape(tmp_path: Path) -> None:
    rt, _, monitor, _ = setup(tmp_path, engine="llm")
    assert monitor.config.engine == "llm" and monitor.tables is None
    assert "engine" not in monitor.config.effective()  # profile.json de L no cambia


def test_no_llm_needs_the_table_engine() -> None:
    from ai_module.__main__ import run as run_module

    with pytest.raises(SystemExit, match="--no-llm only works"):
        asyncio.run(run_module("http://127.0.0.1:1", no_llm=True))


def test_engine_values_are_checked() -> None:
    from ai_module.agent.assets import AssetError, _engine

    assert _engine("monitor", None) == "llm"
    assert _engine("monitor", "hybrid") == "hybrid"
    with pytest.raises(AssetError, match="must be one of"):
        _engine("monitor", "rules")
    with pytest.raises(AssetError, match="only the monitor"):
        _engine("report", "table")


def test_the_enrich_hook_only_fires_with_hybrid(tmp_path: Path) -> None:
    for engine, expected in (("table", 0), ("hybrid", 1)):
        reset_ids()
        _, _, monitor, _ = setup(tmp_path / engine, engine=engine)
        seen: list[dict[str, Any]] = []
        monitor.enrich_hook = seen.append
        run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
        assert len(seen) == expected
        if seen:
            assert seen[0]["rows"]["cause"] == "C17" and seen[0]["alert_id"].startswith("ai-")
