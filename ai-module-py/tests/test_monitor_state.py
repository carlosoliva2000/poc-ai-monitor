"""Estado del monitor: cadenas de alertas, pertenencia de las detecciones, abiertas y decisiones."""

from agent_helpers import detection_event

from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft


def alert(
    alert_id: str,
    detections: list[str],
    cause: str = "GPS_JAMMING",
    supersedes=None,
    t=10.0,
    severity: str = "high",
):
    return EventDraft(
        event_id=alert_id,
        topic="citadel.pub.evt.ai.d1.AnomalyDetected.v1",
        type=EventType.ANOMALY_DETECTED,
        source="ai-monitor",
        asset="d1",
        sim_time=t,
        event_time="2026-10-20T10:00:00Z",
        payload={
            "alert_id": alert_id, "detection_ids": detections, "cause": cause, "severity": severity,
            "confidence": 0.8, "summary": "resumen", "explanation": "x", "recommendation": "y",
            "evidence_event_ids": ["gps-000001"], "supersedes": supersedes, "as_of_sim_time": t,
            "fallback": False,
        },
    )  # fmt: skip


def ack(event_id: str, detection_id: str, alert_id: str | None, t=11.0) -> EventDraft:
    return EventDraft(
        event_id=event_id,
        topic="citadel.pub.evt.ai.d1.DetectionAcknowledged.v1",
        type=EventType.DETECTION_ACKNOWLEDGED,
        source="ai-monitor",
        asset="d1",
        sim_time=t,
        event_time="2026-10-20T10:00:00Z",
        payload={
            "detection_id": detection_id,
            "alert_id": alert_id,
            "reason": "r",
            "as_of_sim_time": t,
            "fallback": False,
        },  # fmt: skip
    )


def closed(alert_id: str, t=50.0) -> EventDraft:
    return EventDraft(
        event_id="ai-0099",
        topic="citadel.pub.evt.ai.d1.AlertClosed.v1",
        type=EventType.ALERT_CLOSED,
        source="ai-monitor",
        asset="d1",
        sim_time=t,
        event_time="2026-10-20T10:00:00Z",
        payload={"alert_id": alert_id, "reason": "ok", "as_of_sim_time": t},
    )


def test_chain_supersedes_keeps_one_open_alert_and_inherits_detections() -> None:
    state = MonitorState()
    state.apply(detection_event("raised", "det-1", 5.0, rule="GPS_DEGRADED", source="gps"))
    state.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT"))
    state.apply(detection_event("raised", "det-2", 8.0, rule="SOURCE_DISCREPANCY"))
    state.apply(alert("ai-2", ["det-2"], supersedes="ai-1"))
    assert [a.alert_id for a in state.open_alerts()] == ["ai-2"]
    assert state.alerts["ai-1"].status.value == "superseded"
    assert state.head("ai-1").alert_id == "ai-2"
    # la detección de la alerta sustituida pertenece ahora a la vigente
    assert state.alert_of("det-1").alert_id == "ai-2"
    assert {d.detection_id for d in state.detections_of("ai-2")} == {"det-1", "det-2"}
    assert state.chains_published == 1


def test_ack_links_a_detection_to_the_open_alert_and_cleared_closes_it() -> None:
    state = MonitorState()
    state.apply(detection_event("raised", "det-1", 5.0))
    state.apply(alert("ai-1", ["det-1"]))
    state.apply(detection_event("raised", "det-2", 8.0, rule="SOURCE_DISCREPANCY"))
    state.apply(ack("ai-3", "det-2", "ai-1"))
    assert state.alert_of("det-2").alert_id == "ai-1"
    assert len(state.open_detections_of("ai-1")) == 2
    state.apply(detection_event("cleared", "det-1", 30.0))
    assert [d.detection_id for d in state.open_detections_of("ai-1")] == ["det-2"]
    state.apply(detection_event("cleared", "det-2", 40.0))
    assert state.open_detections_of("ai-1") == []
    state.apply(closed("ai-1"))
    assert state.open_alerts() == []
    assert state.alert_of("det-1").status.value == "closed"


def test_ack_without_alert_leaves_the_detection_unattached() -> None:
    state = MonitorState()
    state.apply(detection_event("raised", "det-1", 5.0))
    state.apply(ack("ai-1", "det-1", None))
    assert state.alert_of("det-1") is None
    assert [d.detection_id for d in state.open_detections()] == ["det-1"]


def test_updated_keeps_the_same_detection_with_a_new_severity() -> None:
    state = MonitorState()
    state.apply(detection_event("raised", "det-1", 5.0))
    state.apply(detection_event("updated", "det-1", 9.0, severity="high"))
    assert len(state.detections) == 1 and state.detections["det-1"].severity == "high"


def test_apply_is_idempotent_by_event_id() -> None:
    state = MonitorState()
    event = alert("ai-1", ["det-9"])
    assert state.apply(event) is True
    assert state.apply(event) is False  # el eco de un evento propio no se cuenta dos veces
    assert state.chains_published == 1


def test_only_the_last_decisions_are_kept_and_text_is_in_spanish() -> None:
    state = MonitorState(last_decisions=3)
    for n in range(5):
        state.apply(ack(f"ai-{n}", f"det-{n}", None, t=float(n)))
    assert len(state.decisions) == 3
    assert state.decisions[-1].startswith("T+00:04 det-4 → acknowledged")
    assert state.describe_decisions().count(";") == 2
    assert MonitorState().describe_decisions() == "none yet"
    assert MonitorState().describe_open_alerts() == "none"


def test_descriptions_for_the_prompt() -> None:
    state = MonitorState()
    state.apply(detection_event("raised", "det-1", 5.0, rule="GPS_DEGRADED", source="gps"))
    state.apply(alert("ai-1", ["det-1"]))
    assert "det-1 GPS_DEGRADED gps (medium, since T+00:05, in alert ai-1)" in (
        state.describe_open_detections()
    )
    assert "ai-1 GPS_JAMMING" in state.describe_open_alerts()
    assert "det-1 (open)" in state.describe_open_alerts()
    assert state.describe_related_alerts("det-1") == "ai-1 (GPS_JAMMING, high, open)"
    assert state.describe_related_alerts("det-9") == "none"


def test_reset_clears_everything() -> None:
    state = MonitorState()
    state.apply(alert("ai-1", ["det-1"]))
    state.reset()
    assert not state.alerts and not state.decisions and state.chains_published == 0
