"""Casos válidos y no válidos de los modelos (sobre, payloads, WebSocket, API y tools)."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from helpers import POSITION, draft, position_draft
from poc_contracts.api import ScenariosResponse, TimelineResponse
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.payloads import AnomalyDetected, DetectionRaised, FaultCleared, FaultInjected
from poc_contracts.run_files import Label
from poc_contracts.scenario import FaultConfig
from poc_contracts.tools import (
    GetEventsArgs,
    PublishAlertArgs,
    PublishAlertResult,
    TrackMetrics,
)
from poc_contracts.ws import ClientMessage, ServerMessage

CLIENT = TypeAdapter(ClientMessage)
SERVER = TypeAdapter(ServerMessage)


# --- Sobre -----------------------------------------------------------------------------------


def test_valid_draft_and_envelope() -> None:
    assert EventDraft.model_validate(position_draft()).typed_payload().x == 512.3
    full = position_draft(seq=214, ingestion_time="2026-10-20T08:15:32.418Z")
    assert Envelope.model_validate(full).seq == 214


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"topic": "citadel.pub.evt.air.d1.TrackUpdated.v1"}, "expected topic"),
        ({"topic": "citadel.pub.evt.air.d1.PositionUpdated.v2"}, "expected topic"),
        ({"source": "radar-1"}, "expected source"),
        ({"asset": None}, "expected asset"),
        ({"event_id": "rad-000061"}, "lacks the prefix"),
        ({"event_id": "gps-abc"}, "lacks the prefix"),
        ({"ephemeral": True}, "ephemeral"),
        ({"sim_time": -1.0}, "greater_than_equal"),
        ({"event_time": "2026-10-20 10:01:01"}, "string_pattern_mismatch"),
        ({"extra_field": 1}, "extra_forbidden"),
        ({"payload": {**POSITION, "fix": "4d"}}, "fix"),
        ({"payload": {**POSITION, "extra": 1}}, "extra"),
    ],
)
def test_invalid_draft(override: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        EventDraft.model_validate(position_draft(**override))


def test_draft_rejects_seq_but_envelope_requires_it() -> None:
    with pytest.raises(ValidationError):
        EventDraft.model_validate(position_draft(seq=1, ingestion_time="2026-10-20T08:15:32Z"))
    with pytest.raises(ValidationError):
        Envelope.model_validate(position_draft())


def test_chat_topic_follows_conversation_id() -> None:
    payload = {
        "conversation_id": "report",
        "reply_to": "ops-0004",
        "text": "hola",
        "tool_calls": [],
    }
    ok = draft(EventType.AGENT_REPLY, payload, "ai-0010", ConversationId.REPORT)
    assert ok["topic"].endswith("ai.report.AgentReply.v1") and ok["source"] == "ai-chat-report"
    EventDraft.model_validate(ok)
    bad = {**ok, "topic": "citadel.pub.evt.ai.monitor.AgentReply.v1"}
    with pytest.raises(ValidationError, match="expected topic"):
        EventDraft.model_validate(bad)


def test_ephemeral_types() -> None:
    chunk = {"conversation_id": "monitor", "reply_to": "ops-0004", "delta": "Porque la"}
    assert draft(EventType.AGENT_REPLY_CHUNK, chunk, "chk-0011", ConversationId.MONITOR)[
        "ephemeral"
    ]
    activity = {
        "agent": "report",
        "state": "started",
        "invocation_id": "inv-0001",
        "causation_id": None,
    }
    event = draft(EventType.AGENT_ACTIVITY, activity, "act-0012")
    assert event["ephemeral"] and event["asset"] is None
    EventDraft.model_validate(event)


# --- Payloads --------------------------------------------------------------------------------

DETECTION: dict[str, Any] = {
    "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "severity": "medium",
    "value": 34.8, "threshold": 30.0, "unit": "m", "source": None,
    "window": {"since": 80.0, "until": 84.0}, "trigger_event_ids": ["gps-000083"],
    "message": "x",
}  # fmt: skip


def test_source_silent_needs_source_and_seconds() -> None:
    silent = {**DETECTION, "rule": "SOURCE_SILENT", "unit": "s", "source": "radar"}
    assert DetectionRaised.model_validate(silent).source == "radar"
    with pytest.raises(ValidationError, match="exige `source`"):
        DetectionRaised.model_validate({**silent, "source": None})
    with pytest.raises(ValidationError, match="unit"):
        DetectionRaised.model_validate({**silent, "unit": "m"})
    with pytest.raises(ValidationError, match="no lleva `source`"):
        DetectionRaised.model_validate({**DETECTION, "source": "gps"})


def test_gps_degraded_is_about_the_gps() -> None:
    degraded = {**DETECTION, "rule": "GPS_DEGRADED", "unit": "hdop", "source": "gps"}
    assert DetectionRaised.model_validate(degraded).source == "gps"
    for bad in (None, "radar"):
        with pytest.raises(ValidationError, match="exige `source: gps`"):
            DetectionRaised.model_validate({**degraded, "source": bad})


def test_anomaly_limits() -> None:
    alert: dict[str, Any] = {
        "alert_id": "ai-0003", "detection_ids": ["det-0002"], "cause": "WIND", "severity": "low",
        "confidence": 0.8, "summary": "x", "explanation": "x", "recommendation": "x",
        "evidence_event_ids": ["gps-000084"], "supersedes": None, "as_of_sim_time": 84.0,
        "fallback": False,
    }  # fmt: skip
    assert AnomalyDetected.model_validate(alert).cause == "WIND"
    for bad in ({"confidence": 1.2}, {"cause": "REPLAY"}, {"severity": "critical"},
                {"summary": "x" * 161}):  # fmt: skip
        with pytest.raises(ValidationError):
            AnomalyDetected.model_validate({**alert, **bad})


# --- WebSocket -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        {"op": "hello", "client": "web"},
        {"op": "hello", "client": "ai-module"},
        {"op": "subscribe", "patterns": ["citadel.pub.evt.>", "citadel.pub.evt.ai.d1.>"]},
        {"op": "publish", "event": position_draft()},
        {"op": "control", "action": "load", "value": "demo"},
        {"op": "control", "action": "play"},
        {"op": "control", "action": "step", "value": None},
        {"op": "control", "action": "speed", "value": 16},
        {"op": "control", "action": "speed", "value": 0.5},
        {"op": "control", "action": "wait_agent", "value": True},
        {"op": "control", "action": "interactive", "value": True},
        {
            "op": "control",
            "action": "fault",
            "value": {"source": "radar", "mode": "mute", "active": True},
        },
        {
            "op": "control",
            "action": "fault",
            "value": {"source": "gps", "mode": "loss", "active": False},
        },
    ],
)
def test_valid_client_messages(message: dict[str, Any]) -> None:
    CLIENT.validate_python(message)


@pytest.mark.parametrize(
    "message",
    [
        {"op": "hello", "client": "mobile"},
        {"op": "subscribe", "patterns": []},
        {"op": "subscribe", "patterns": ["citadel.*.evt.ai.d1.Detection*"]},
        {"op": "subscribe", "patterns": ["citadel.>.evt"]},
        {"op": "publish", "event": position_draft(seq=1)},
        {"op": "control", "action": "speed", "value": 3},
        {"op": "control", "action": "wait_agent", "value": "yes"},
        {"op": "control", "action": "load"},
        {"op": "control", "action": "interactive", "value": "yes"},
        {
            "op": "control",
            "action": "fault",
            "value": {"source": "sim", "mode": "mute", "active": True},
        },
        {
            "op": "control",
            "action": "fault",
            "value": {"source": "radar", "mode": "loss", "active": True},
        },
        {"op": "control", "action": "fault", "value": {"source": "radar", "muted": True}},
        {"op": "control", "action": "rewind", "value": 1},
        {"op": "dance"},
    ],
)
def test_invalid_client_messages(message: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CLIENT.validate_python(message)


def test_server_messages() -> None:
    state = {
        "op": "state", "status": "running", "scenario": "demo", "run_id": "20261020-101500",
        "sim_time": 61.0, "speed": 4.0, "wait_agent": True, "interactive": True,
        "active_faults": [{"source": "gps", "mode": "loss", "origin": "manual"}],
        "cursor": 212, "total_events": 913,
    }  # fmt: skip
    SERVER.validate_python(state)
    SERVER.validate_python({**state, "status": "idle", "scenario": None, "run_id": None})
    SERVER.validate_python({"op": "error", "message": "x"})
    full = position_draft(seq=214, ingestion_time="2026-10-20T08:15:32.418Z")
    SERVER.validate_python({"op": "event", "event": full})
    with pytest.raises(ValidationError):
        SERVER.validate_python({"op": "event", "event": position_draft()})  # sin seq
    with pytest.raises(ValidationError):
        SERVER.validate_python({**state, "active_faults": [{"source": "gps", "mode": "mute"}]})
    with pytest.raises(ValidationError):
        SERVER.validate_python({**state, "muted_sources": ["radar"]})


# --- API y tools -----------------------------------------------------------------------------


def test_scenarios_response() -> None:
    ScenariosResponse.model_validate(
        {
            "scenarios": [
                {"name": "demo", "description": "d", "generated": False, "duration_s": None}
            ]
        }
    )


def test_get_events_args() -> None:
    assert GetEventsArgs.model_validate({"source": "gps"}).last_n == 10
    assert GetEventsArgs.model_validate({"source": "gps", "last_n": 500}).last_n == 50
    assert GetEventsArgs.model_validate({"source": "gps", "last_n": 0}).last_n == 1
    for bad in ({"source": "sim"}, {"source": "gps", "type": "Nope"}, {}):
        with pytest.raises(ValidationError):
            GetEventsArgs.model_validate(bad)


def test_publish_alert_args_and_result() -> None:
    args: dict[str, Any] = {
        "detection_ids": ["det-0002"], "cause": "WIND", "severity": "low", "confidence": 0.8,
        "summary": "s", "explanation": "e", "recommendation": "r", "evidence_event_ids": ["gps-1"],
    }  # fmt: skip
    assert PublishAlertArgs.model_validate(args).supersedes is None
    with pytest.raises(ValidationError):
        PublishAlertArgs.model_validate({**args, "evidence_event_ids": []})
    result = TypeAdapter(PublishAlertResult)
    assert result.validate_python({"ok": True, "alert_id": "ai-0003"}).alert_id == "ai-0003"
    assert result.validate_python({"ok": False, "errors": ["x"]}).errors == ["x"]


def test_track_metrics_without_radar() -> None:
    """Sin radar no se inventa nada: todo lo que depende del radar es null y `samples` es real."""
    metrics = TrackMetrics.model_validate(
        {
            "since": 120.0, "until": 150.0,
            "gps_deviation_from_plan_m": {"mean": 3.1, "max": 5.0, "trend": "stable"},
            "radar_deviation_from_plan_m": None, "gps_radar_distance_m": None,
            "drift_direction_deg": 182.0,
            "course_deg": {"gps": 95.0, "radar": None},
            "bearing_to_next_waypoint_deg": 71.0, "next_waypoint": "WP2",
            "mean_speed_mps": {"gps": 14.6, "radar": None},
            "wind": None, "gps_radar": None, "gps_max_step_m": 0.5,
            "samples": {"gps": 30, "radar": 0},
            "gps_available": True, "radar_available": False,
            "last_seen_sim_time": {"gps": 150.0, "radar": 119.0},
            "first_event_ids": ["gps-000120"], "last_event_ids": ["gps-000150"],
        }
    )  # fmt: skip
    assert not metrics.radar_available and metrics.samples.radar == 0


# --- Fallos: mute y loss ---------------------------------------------------------------------


def test_loss_only_exists_for_the_gps() -> None:
    assert FaultInjected.model_validate({"source": "gps", "mode": "loss", "origin": "manual"})
    assert FaultCleared.model_validate({"source": "radar", "mode": "mute", "origin": "scenario"})
    with pytest.raises(ValidationError, match="only exists for the GPS"):
        FaultInjected.model_validate({"source": "radar", "mode": "loss", "origin": "manual"})
    with pytest.raises(ValidationError):  # el tipo de fallo es obligatorio
        FaultInjected.model_validate({"source": "radar", "origin": "manual"})


def test_scenario_fault_needs_a_mode() -> None:
    assert FaultConfig.model_validate({"source": "gps", "mode": "loss", "start_s": 1, "end_s": 2})
    for bad in (
        {"source": "gps", "start_s": 1, "end_s": 2},
        {"source": "link", "mode": "loss", "start_s": 1, "end_s": 2},
    ):
        with pytest.raises(ValidationError):
            FaultConfig.model_validate(bad)


def test_labels_of_faults_need_a_source() -> None:
    label: dict[str, Any] = {
        "id": "F1", "type": "gps_loss", "source": "gps", "start_s": 245.0, "end_s": 290.0,
        "expected_rules": ["GPS_DEGRADED"], "expected_cause": "GPS_JAMMING",
        "also_accepted_causes": ["SENSOR_FAULT"], "eval_window": [245.0, 350.0],
    }  # fmt: skip
    assert Label.model_validate(label).also_accepted_causes == ["SENSOR_FAULT"]
    with pytest.raises(ValidationError, match="mandatory in faults"):
        Label.model_validate({**label, "source": None})
    with pytest.raises(ValidationError, match="mandatory in faults"):
        Label.model_validate({**label, "type": "wind"})


def test_timeline_response() -> None:
    full = position_draft(seq=1, ingestion_time="2026-10-20T08:15:32.418Z")
    assert (
        TimelineResponse.model_validate({"events": [full], "truncated": False}).events[0].seq == 1
    )
    with pytest.raises(ValidationError):
        TimelineResponse.model_validate({"events": [position_draft()], "truncated": False})
