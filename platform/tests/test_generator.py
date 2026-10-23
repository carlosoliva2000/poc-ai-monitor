"""Salida del generador: formato, ids, orden, contenido de los ficheros y etiquetas."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from helpers import scenario_config
from platform_app.generator.build import generate
from platform_app.generator.events import event_time
from platform_app.generator.scenario_io import list_scenarios, load_scenario
from platform_app.scenario_metrics import load_run
from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.run_files import LabelsFile, PlanFile, TruthFile

SENSOR_TYPES = {"PositionUpdated", "TrackUpdated", "WindReported", "LinkStatus", "BatteryStatus"}
ALL = ["demo", "faults", "hijack", "nominal", "spoofing", "wind"]


def test_all_scenarios_in_the_repo_are_the_six_expected() -> None:
    assert list_scenarios() == ALL


@pytest.mark.parametrize("name", ALL)
def test_every_event_line_is_a_valid_draft_sorted_by_time_with_unique_ids(
    runs_dir: Path, name: str
) -> None:
    lines = (runs_dir / name / "events.jsonl").read_text("utf-8").splitlines()
    drafts = [EventDraft.model_validate_json(line) for line in lines]
    assert [d.sim_time for d in drafts] == sorted(d.sim_time for d in drafts)
    ids = [d.event_id for d in drafts]
    assert len(ids) == len(set(ids))
    for line in lines:  # el generador no escribe lo que pone el bus
        assert "seq" not in json.loads(line)
        assert "ingestion_time" not in json.loads(line)


@pytest.mark.parametrize("name", ALL)
def test_run_files_validate_against_the_contract_models(runs_dir: Path, name: str) -> None:
    d = runs_dir / name
    plan = PlanFile.model_validate_json((d / "plan.json").read_text("utf-8"))
    truth = TruthFile.model_validate_json((d / "truth.json").read_text("utf-8"))
    LabelsFile.model_validate_json((d / "labels.json").read_text("utf-8"))
    assert plan.trajectory[0].t == 0.0
    assert truth.trajectory[0].t == 0.0
    assert [s.t for s in truth.trajectory[:3]] == [0.0, 1.0, 2.0]
    assert len(truth.wind) == len(truth.trajectory)
    assert truth.trajectory[-1].t == truth.duration_s


def test_mission_events_follow_the_route(runs_dir: Path) -> None:
    run = load_run("nominal", runs_dir)
    mission = [e for e in run.events if e["event_id"].startswith("mis-")]
    assert [e["type"] for e in mission] == [
        "MissionPlanned",
        "MissionStarted",
        *["WaypointReached"] * 5,
        "MissionCompleted",
    ]
    assert [e["event_id"] for e in mission] == [f"mis-{i:04d}" for i in range(1, 9)]
    planned = mission[0]["payload"]
    assert [w["id"] for w in planned["waypoints"]] == ["BASE", "WP1", "WP2", "WP3", "WP4", "BASE"]
    etas = [w["eta_s"] for w in planned["waypoints"]]
    assert etas[0] == 0.0
    assert etas == sorted(etas)
    reached = [e["payload"] for e in mission if e["type"] == "WaypointReached"]
    assert [r["index"] for r in reached] == [1, 2, 3, 4, 5]
    assert reached[-1]["waypoint_id"] == "BASE"
    done = mission[-1]
    assert done["payload"] == {
        "mission_id": "MSN-NOMINAL",
        "completed": True,
        "reason": "returned_to_base",
    }
    assert done["sim_time"] == run.truth.duration_s


def test_sensor_periods_ids_and_nothing_after_the_end(runs_dir: Path) -> None:
    run = load_run("nominal", runs_dir)
    end = run.truth.duration_s
    for etype, period, prefix, width in [
        ("PositionUpdated", 1.0, "gps", 6),
        ("TrackUpdated", 2.0, "rad", 6),
        ("WindReported", 10.0, "met", 4),
        ("LinkStatus", 5.0, "lnk", 4),
        ("BatteryStatus", 10.0, "bat", 4),
    ]:
        events = run.of_type(etype)
        assert len(events) == int(end // period)
        for k, e in enumerate(events, start=1):
            assert e["sim_time"] == pytest.approx(k * period)
            assert e["event_id"] == f"{prefix}-{k:0{width}d}"
    assert max(e["sim_time"] for e in run.events if e["type"] in SENSOR_TYPES) <= end


def test_event_ids_match_the_examples_of_the_contract(runs_dir: Path) -> None:
    run = load_run("nominal", runs_dir)
    by_id = {e["event_id"]: e for e in run.events}
    assert by_id["gps-000061"]["sim_time"] == 61.0
    assert by_id["gps-000061"]["event_time"] == "2026-10-20T10:01:01Z"
    assert by_id["rad-000042"]["sim_time"] == 84.0
    assert by_id["met-0008"]["sim_time"] == 80.0
    assert by_id["gps-000061"]["topic"] == "citadel.pub.evt.air.d1.PositionUpdated.v1"
    assert by_id["met-0008"]["topic"] == "citadel.pub.evt.env.zone1.WindReported.v1"
    assert by_id["met-0008"]["asset"] == "zone1"


def test_event_time_is_t0_plus_sim_time() -> None:
    assert event_time("2026-10-20T10:00:00Z", 0.0) == "2026-10-20T10:00:00Z"
    assert event_time("2026-10-20T10:00:00Z", 3661.0) == "2026-10-20T11:01:01Z"
    assert event_time("2026-10-20T10:00:00Z", 441.1) == "2026-10-20T10:07:21.100Z"


def test_gps_reports_the_spoofed_position_and_radar_the_real_one(runs_dir: Path) -> None:
    run = load_run("spoofing", runs_dir)
    truth = {s.t: s for s in run.truth.trajectory}
    at = 220.0  # a punto de acabar el engaño: desfase ≈ 78 m
    gps = next(e for e in run.of_type("PositionUpdated") if e["sim_time"] == at)["payload"]
    radar = next(e for e in run.of_type("TrackUpdated") if e["sim_time"] == at)["payload"]
    s = truth[at]
    assert ((gps["x"] - s.x) ** 2 + (gps["y"] - s.y) ** 2) ** 0.5 > 60.0
    assert ((radar["x"] - s.x) ** 2 + (radar["y"] - s.y) ** 2) ** 0.5 < 25.0


def test_link_changes_controller_only_during_the_hijack(runs_dir: Path) -> None:
    run = load_run("hijack", runs_dir)
    for e in run.of_type("LinkStatus"):
        hijacked = 335.0 <= e["sim_time"] < 380.0
        assert (e["payload"]["controller_id"] == "UNK-4F2A") == hijacked


def test_battery_drains_and_gps_fix_is_3d(runs_dir: Path) -> None:
    run = load_run("nominal", runs_dir)
    pct = [e["payload"]["battery_pct"] for e in run.of_type("BatteryStatus")]
    assert pct[0] > pct[-1]
    assert pct[-1] == pytest.approx(100 - 1.2 * run.truth.duration_s / 60, abs=0.6)
    assert {e["payload"]["fix"] for e in run.of_type("PositionUpdated")} == {"3d"}


def test_labels_of_the_demo(runs_dir: Path) -> None:
    labels = load_run("demo", runs_dir).labels
    assert [(lb.id, lb.type.value, lb.start_s, lb.end_s) for lb in labels] == [
        ("A1", "wind", 95.0, 150.0),
        ("A2", "gps_spoofing", 168.0, 222.0),
        ("A3", "hijack", 335.0, 380.0),
    ]
    assert [lb.expected_cause.value for lb in labels] == ["WIND", "GPS_SPOOFING", "HIJACK"]
    assert labels[0].eval_window == (95.0, 210.0)
    assert [r.value for r in labels[0].expected_rules] == ["ROUTE_DEVIATION"]
    assert "SOURCE_DISCREPANCY" in [r.value for r in labels[1].expected_rules]
    assert all(lb.source is None for lb in labels)


def test_labels_of_the_scheduled_faults(runs_dir: Path) -> None:
    labels = load_run("faults", runs_dir).labels
    assert [lb.model_dump(mode="json") for lb in labels] == [
        {
            "id": "F1",
            "type": "source_silent",
            "source": "radar",
            "start_s": 120.0,
            "end_s": 180.0,
            "expected_rules": ["SOURCE_SILENT"],
            "expected_cause": "SENSOR_FAULT",
            "also_accepted_causes": [],
            "eval_window": [120.0, 240.0],
        },
        {
            "id": "F2",
            "type": "gps_loss",
            "source": "gps",
            "start_s": 245.0,
            "end_s": 290.0,
            "expected_rules": ["GPS_DEGRADED", "SOURCE_DISCREPANCY", "ROUTE_DEVIATION"],
            "expected_cause": "GPS_JAMMING",
            "also_accepted_causes": ["SENSOR_FAULT"],
            "eval_window": [245.0, 350.0],
        },
        {
            "id": "F3",
            "type": "source_silent",
            "source": "gps",
            "start_s": 300.0,
            "end_s": 312.0,
            "expected_rules": ["SOURCE_SILENT"],
            "expected_cause": "SENSOR_FAULT",
            "also_accepted_causes": [],
            "eval_window": [300.0, 372.0],
        },
    ]


def test_fault_events_use_the_player_source_and_are_numbered_in_order(runs_dir: Path) -> None:
    faults = [e for e in load_run("faults", runs_dir).events if e["event_id"].startswith("sim-")]
    assert [(e["type"], e["event_id"], e["payload"]["mode"]) for e in faults] == [
        ("FaultInjected", "sim-0001", "mute"),
        ("FaultCleared", "sim-0002", "mute"),
        ("FaultInjected", "sim-0003", "loss"),
        ("FaultCleared", "sim-0004", "loss"),
        ("FaultInjected", "sim-0005", "mute"),
        ("FaultCleared", "sim-0006", "mute"),
    ]
    assert {e["source"] for e in faults} == {"platform-player"}
    assert {e["asset"] for e in faults} == {None}
    assert {e["payload"]["origin"] for e in faults} == {"scenario"}


def test_scenario_name_must_match_the_file(tmp_path: Path) -> None:
    (tmp_path / "otro.yaml").write_text(
        (Path(__file__).resolve().parents[2] / "scenarios" / "nominal.yaml").read_text("utf-8")
    )
    with pytest.raises(ValueError, match="name"):
        load_scenario("otro", tmp_path)


def test_a_fault_that_outlasts_the_mission_is_clipped_to_its_end() -> None:
    cfg = scenario_config(
        "nominal", faults=[{"source": "battery", "mode": "mute", "start_s": 400.0, "end_s": 900.0}]
    )
    run = generate(cfg)
    end = run.truth.duration_s
    cleared = next(e for e in run.events if e.type == EventType.FAULT_CLEARED)
    assert cleared.sim_time == end
    assert run.labels.labels[0].end_s == end
    assert not [e for e in run.events if e.type == "BatteryStatus" and e.sim_time >= 400.0]


def test_a_fault_that_starts_after_the_mission_is_not_written() -> None:
    cfg = scenario_config(
        "nominal", faults=[{"source": "gps", "mode": "mute", "start_s": 800.0, "end_s": 850.0}]
    )
    run = generate(cfg)
    assert not [e for e in run.events if e.type.value.startswith("Fault")]
    assert run.labels.labels == []


def test_radar_and_meteo_ids_must_match_the_envelope_source() -> None:
    sensors = scenario_config("nominal").sensors.model_dump()
    sensors["radar"]["id"] = "radar-2"
    with pytest.raises(ValidationError, match="radar-1"):
        scenario_config("nominal", sensors=sensors)
