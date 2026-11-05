"""Fase 15: `monitor.link_anomaly`. Cuando vuelve el controlador de la misión al enlace con la
alerta `HIJACK` activa y la desviación de la ruta aún abierta, el cierre de la `LINK_ANOMALY` lleva
a una alerta `HIJACK` que sustituye a la anterior en fase `recovering` (la fase la decide el código;
la severidad, `low` o `medium`, es del modelo) y reconocerlo se veta."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    alert_args,
    call,
    detection_event,
    make_runtime,
    reset_ids,
    run,
    seed_evidence,
    text_response,
    tool_response,
)
from test_coherence import GOOD, checks, index_with, link_events, metrics
from test_monitor_state import alert

from ai_module.agent.guardrails import (
    TAG_LINK_RECOVERY_ACK_VETO,
    InvocationFacts,
    check_acknowledge,
    check_publish_alert,
)
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def hijack_state(*, link_open: bool = False, route_open: bool = True, phase: str = "active"):
    """`det-1` LINK_ANOMALY y `det-2` ROUTE_DEVIATION dentro de `ai-1` HIJACK (`high`)."""
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 335.0, rule="LINK_ANOMALY", source="link"))
    s.apply(alert("ai-1", ["det-1"], cause="HIJACK", t=335.5, phase=phase))
    s.apply(detection_event("raised", "det-2", 338.0))
    from test_monitor_state import ack

    s.apply(ack("ai-2", "det-2", "ai-1", t=338.5))
    if not route_open:
        s.apply(detection_event("cleared", "det-2", 360.0))
    if not link_open:
        s.apply(detection_event("cleared", "det-1", 385.0, rule="LINK_ANOMALY"))
    return s


# --- Estado ---


def test_the_link_recovery_alert_needs_the_whole_situation() -> None:
    assert hijack_state().link_recovery_alert("det-1").alert_id == "ai-1"
    assert hijack_state(link_open=True).link_recovery_alert("det-1") is None  # el enlace sigue mal
    assert hijack_state(route_open=False).link_recovery_alert("det-1") is None  # ya no hay desvío
    assert hijack_state(phase="recovering").link_recovery_alert("det-1") is None  # ya recupera
    assert hijack_state().link_recovery_alert("det-2") is None  # no es la detección del enlace
    assert hijack_state().link_recovery_alert("det-9") is None
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0, rule="LINK_ANOMALY", source="link"))
    s.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT", t=6.0))
    s.apply(detection_event("raised", "det-2", 8.0))
    s.apply(detection_event("cleared", "det-1", 20.0, rule="LINK_ANOMALY"))
    assert s.link_recovery_alert("det-1") is None  # solo el secuestro tiene recuperación


# --- Guardrails ---


def recovery_args(**changes: Any) -> dict[str, Any]:
    args = alert_args(
        ["det-1"],
        cause="HIJACK",
        severity="medium",
        confidence=0.7,
        supersedes="ai-1",
        phase="recovering",
        checks=checks(link_checked=True, link_anomalous=True),
    )
    args.update(changes)
    return args


def publish(args: dict[str, Any], s: MonitorState, *, enabled: bool = True):
    facts = InvocationFacts(metrics=metrics(), link_events=link_events("hijack", 360, 385))
    return check_publish_alert(
        args,
        as_of=386.0,
        state=s,
        index=index_with(**GOOD),
        seen_ids={"gps-000001", "gps-000002"},
        facts=facts,
        coherence=True,
        pending={"det-1"},
        unanswered={"det-1"},
        link_recovery=enabled,
    )


def test_the_recovery_is_accepted_and_published_as_recovering() -> None:
    verdict = publish(recovery_args(), hijack_state())
    assert verdict.ok, verdict.errors
    assert verdict.phase == "recovering"
    omitted = {k: v for k, v in recovery_args().items() if k != "phase"}
    verdict = publish(omitted, hijack_state(), enabled=True)
    assert verdict.ok and verdict.phase == "recovering"  # la fase la pone el módulo


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"cause": "WIND"}, "expected cause HIJACK and supersedes ai-1"),
        ({"supersedes": None}, "is already in the open alert ai-1"),
        ({"severity": "high"}, "severity high does not fit"),
        ({"phase": "active"}, "wrong phase for this data"),
    ],
)
def test_what_the_code_decides_is_rejected_with_data(changes, fragment) -> None:
    verdict = publish(recovery_args(**changes), hijack_state())
    assert not verdict.ok
    assert any(fragment in e for e in verdict.errors), verdict.errors


def test_without_the_switch_nothing_changes() -> None:
    verdict = publish(recovery_args(severity="high", phase="active"), hijack_state(), enabled=False)
    assert "hijacking recovery" not in " ".join(verdict.errors)


def acknowledge(s: MonitorState, *, enabled: bool = True):
    return check_acknowledge(
        {"detection_ids": ["det-1"], "alert_id": "ai-1", "reason": "r"},
        state=s,
        unanswered={"det-1"},
        pending={"det-1"},
        link_recovery=enabled,
    )


def test_the_recovery_cannot_be_acknowledged() -> None:
    verdict = acknowledge(hijack_state())
    assert not verdict.ok and verdict.tag == TAG_LINK_RECOVERY_ACK_VETO
    assert "ai-1" in verdict.errors[0] and "recovering" in verdict.errors[0]
    assert acknowledge(hijack_state(), enabled=False).ok
    assert acknowledge(hijack_state(phase="recovering")).ok  # ya está en recuperación


# --- Monitor ---


def setup(tmp_path: Path, script: Script, **switches: Any):
    platform = FakePlatform({"get_track_metrics": metrics(), "get_events": link_result()})
    rt, published = make_runtime(tmp_path, FakeLlm(script), platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(386.0)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, **switches)
    rt.state = hijack_state(link_open=True)
    return rt, published, monitor


def link_result() -> dict[str, Any]:
    events = link_events("hijack", 360, 385)
    return {
        "events": [
            {"event_id": f"lnk-{i}", "type": "LinkStatus", **e} for i, e in enumerate(events)
        ]
    }


def cleared_event():
    return detection_event("cleared", "det-1", 385.0, rule="LINK_ANOMALY", source="link")


def alerts_of(published: list) -> list:
    return [e for e in published if e.type == EventType.ANOMALY_DETECTED]


def acks_of(published: list) -> list:
    return [e for e in published if e.type == EventType.DETECTION_ACKNOWLEDGED]


def recovery_script() -> Script:
    return Script(
        tool_response(call("get_track_metrics", since=366.0, until=386.0)),
        tool_response(call("get_events", source="link", last_n=3)),
        tool_response(call("publish_alert", **recovery_args())),
    )


def test_the_cleared_link_goes_to_the_model_with_its_own_section(tmp_path: Path) -> None:
    rt, published, monitor = setup(tmp_path, recovery_script(), link_anomaly=True)
    run(monitor.handle_batch([cleared_event()]))
    [recovery] = alerts_of(published)
    assert recovery.payload["cause"] == "HIJACK" and recovery.payload["phase"] == "recovering"
    assert recovery.payload["supersedes"] == "ai-1" and recovery.payload["severity"] == "medium"
    assert acks_of(published) == []
    assert rt.state.alerts["ai-1"].status.value == "superseded"
    assert rt.state.head("ai-1").alert_id == recovery.payload["alert_id"]
    prompt = monitor_prompt(rt)
    assert "has returned to normal" in prompt and "**recovery** of the hijacking" in prompt
    assert "alert ai-1" in prompt


def monitor_prompt(rt) -> str:
    return rt.trace.records[0]["messages"][1]["content"]


def test_without_the_switch_the_cleared_link_is_acknowledged_without_the_model(
    tmp_path: Path,
) -> None:
    rt, published, monitor = setup(tmp_path, Script(text_response("x")), link_anomaly=False)
    run(monitor.handle_batch([cleared_event()]))
    [ack] = acks_of(published)
    assert "stays open because it still has open detections (det-2)" in ack.payload["reason"]
    assert ack.payload["alert_id"] == "ai-1" and alerts_of(published) == []
    assert rt.trace.records[0]["deterministic"] is True


def test_if_the_model_does_not_conclude_the_alert_is_not_closed(tmp_path: Path) -> None:
    rt, published, monitor = setup(tmp_path, Script(text_response("no sé")), link_anomaly=True)
    run(monitor.handle_batch([cleared_event()]))
    [ack] = acks_of(published)
    assert ack.payload["fallback"] is True and ack.payload["alert_id"] is None
    assert not [e for e in published if e.type == EventType.ALERT_CLOSED]
    assert rt.state.alerts["ai-1"].status.value == "open"


def test_the_model_cannot_acknowledge_nor_close_the_recovery(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("get_track_metrics", since=366.0, until=386.0)),
        tool_response(call("acknowledge_detection", reason="the link is back")),
        tool_response(call("close_alert", reason="back to normal")),
        tool_response(call("get_events", source="link", last_n=3)),
        tool_response(call("publish_alert", **recovery_args())),
    )
    rt, published, monitor = setup(tmp_path, script, link_anomaly=True)
    run(monitor.handle_batch([cleared_event()]))
    errors = [e for r in rt.trace.records[0]["guardrail_rejections"] for e in r["errors"]]
    assert any("cannot be acknowledged" in e for e in errors)
    assert any("still has open detections" in e for e in errors)
    [recovery] = alerts_of(published)
    assert recovery.payload["phase"] == "recovering"
