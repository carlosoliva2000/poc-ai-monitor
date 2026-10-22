"""Guardrails de `publish_alert`, `acknowledge_detection` y `close_alert`: cada regla, aceptada y
rechazada."""

import pytest
from agent_helpers import alert_args, detection_event
from test_monitor_state import alert, closed

from ai_module.agent.guardrails import (
    EventIndex,
    check_acknowledge,
    check_close_alert,
    check_publish_alert,
)
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft


def index_with(**times: float) -> EventIndex:
    index = EventIndex()
    for event_id, t in times.items():
        index.add(
            EventDraft(
                event_id=event_id.replace("_", "-"),
                topic="citadel.pub.evt.air.d1.PositionUpdated.v1",
                type=EventType.POSITION_UPDATED,
                source="d1-gps",
                asset="d1",
                sim_time=t,
                event_time="2026-10-20T10:00:00Z",
                payload={
                    "x": 0.0,
                    "y": 0.0,
                    "alt_m": 60.0,
                    "speed_mps": 15.0,
                    "heading_deg": 0.0,
                    "fix": "3d",
                    "sats": 14,
                    "hdop": 0.8,
                },  # fmt: skip
            )
        )
    return index


@pytest.fixture
def state() -> MonitorState:
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0))
    return s


GOOD = {"gps_000001": 4.0, "gps_000002": 5.0}


def check(raw, state, index=None, as_of=10.0, seen=()):
    return check_publish_alert(
        raw, as_of=as_of, state=state, index=index or index_with(**GOOD), seen_ids=set(seen)
    )


def test_publish_alert_accepts_a_valid_alert(state: MonitorState) -> None:
    verdict = check(alert_args(["det-1"]), state, seen={"gps-000001", "gps-000002"})
    assert verdict.ok and verdict.unseen_evidence == []


def test_unseen_evidence_is_counted_not_rejected(state: MonitorState) -> None:
    verdict = check(alert_args(["det-1"]), state, seen={"gps-000001"})
    assert verdict.ok and verdict.unseen_evidence == ["gps-000002"]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"cause": "ALIENS"}, "cause"),
        ({"severity": "extreme"}, "severity"),
        ({"confidence": 1.5}, "confidence"),
        ({"confidence": -0.1}, "confidence"),
        ({"summary": "x" * 161}, "summary"),
        ({"evidence_event_ids": []}, "evidence_event_ids"),
        ({"detection_ids": []}, "detection_ids"),
    ],
)
def test_publish_alert_rejects_invalid_fields(state, override, message) -> None:
    args = alert_args(["det-1"])
    args.update(override)
    verdict = check(args, state)
    assert not verdict.ok and any(message in e for e in verdict.errors)


def test_publish_alert_rejects_missing_future_or_unknown_evidence(state: MonitorState) -> None:
    index = index_with(gps_000001=4.0, gps_000009=50.0)
    verdict = check(
        alert_args(["det-1"], evidence_event_ids=["gps-000001", "gps-000009", "gps-424242"]),
        state,
        index,
    )
    assert any("gps-000009" in e and "posterior" in e for e in verdict.errors)
    assert any("gps-424242" in e and "no existe" in e for e in verdict.errors)
    assert not any("gps-000001" in e for e in verdict.errors)


def test_publish_alert_rejects_unknown_detection(state: MonitorState) -> None:
    verdict = check(alert_args(["det-77"]), state)
    assert any("det-77" in e for e in verdict.errors)


def test_publish_alert_rejects_a_detection_already_in_an_open_alert(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"]))
    verdict = check(alert_args(["det-1"]), state)
    assert any("ya está en la alerta abierta ai-1" in e for e in verdict.errors)
    # con supersedes a esa alerta sí vale
    assert check(alert_args(["det-1"], supersedes="ai-1"), state).ok


def test_supersedes_must_point_to_an_open_alert(state: MonitorState) -> None:
    assert not check(alert_args(["det-1"], supersedes="ai-9"), state).ok
    state.apply(alert("ai-1", ["det-1"]))
    state.apply(closed("ai-1"))
    verdict = check(alert_args(["det-1"], supersedes="ai-1"), state)
    assert any("no es una alerta abierta" in e for e in verdict.errors)
    # una alerta cerrada ya no bloquea una alerta nueva para la misma detección
    assert check(alert_args(["det-1"]), state).ok


def test_supersedes_must_change_the_cause_or_the_severity(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))  # severidad high
    state.apply(detection_event("updated", "det-1", 8.0))
    same = check(
        alert_args(["det-1"], cause="GPS_JAMMING", severity="high", supersedes="ai-1"), state
    )
    assert not same.ok
    assert any(
        e.startswith("No cambia nada respecto a ai-1") and "usa acknowledge_detection" in e
        for e in same.errors
    )
    # cambia la severidad, o cambia la causa: vale
    assert check(
        alert_args(["det-1"], cause="GPS_JAMMING", severity="medium", supersedes="ai-1"), state
    ).ok
    assert check(
        alert_args(["det-1"], cause="SENSOR_FAULT", severity="high", supersedes="ai-1"), state
    ).ok


def test_acknowledge_rules(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"]))
    state.apply(detection_event("raised", "det-2", 8.0))
    ok = check_acknowledge(
        {"detection_ids": ["det-2"], "alert_id": "ai-1", "reason": "r"},
        state=state, unanswered={"det-2"}, pending={"det-2"},
    )  # fmt: skip
    assert ok.ok
    no_alert = check_acknowledge(
        {"detection_ids": ["det-2"], "reason": "no hace falta"},
        state=state, unanswered={"det-2"}, pending={"det-2"},
    )  # fmt: skip
    assert no_alert.ok and no_alert.args.alert_id is None
    bad_alert = check_acknowledge(
        {"detection_ids": ["det-2"], "alert_id": "ai-9", "reason": "r"},
        state=state, unanswered={"det-2"}, pending={"det-2"},
    )  # fmt: skip
    assert any("no es una alerta abierta" in e for e in bad_alert.errors)
    foreign = check_acknowledge(
        {"detection_ids": ["det-5"], "reason": "r"},
        state=state, unanswered={"det-2"}, pending={"det-2"},
    )  # fmt: skip
    assert any("no es de las que debes atender" in e for e in foreign.errors)
    answered = check_acknowledge(
        {"detection_ids": ["det-2"], "reason": "r"},
        state=state, unanswered=set(), pending={"det-2"},
    )  # fmt: skip
    assert any("ya tiene respuesta" in e for e in answered.errors)
    missing = check_acknowledge(
        {"detection_ids": [], "reason": "r"}, state=state, unanswered=set(), pending=set()
    )
    assert not missing.ok


def test_close_alert_rules(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"]))
    still_open = check_close_alert({"alert_id": "ai-1", "reason": "ok"}, state=state)
    assert any("detecciones abiertas (det-1)" in e for e in still_open.errors)
    state.apply(detection_event("cleared", "det-1", 30.0))
    assert check_close_alert({"alert_id": "ai-1", "reason": "ok"}, state=state).ok
    assert any("no existe" in e for e in check_close_alert(
        {"alert_id": "ai-7", "reason": "x"}, state=state).errors)  # fmt: skip
    state.apply(alert("ai-2", ["det-1"], supersedes="ai-1"))
    superseded = check_close_alert({"alert_id": "ai-1", "reason": "x"}, state=state)
    assert any("sustituida por ai-2" in e for e in superseded.errors)
    state.apply(closed("ai-2"))
    assert any("ya está cerrada" in e for e in check_close_alert(
        {"alert_id": "ai-2", "reason": "x"}, state=state).errors)  # fmt: skip


def test_event_index_only_keeps_air_env_ai_ops_domains() -> None:
    index = EventIndex()
    index.add(
        EventDraft(
            event_id="plr-0001",
            topic="citadel.pub.evt.sim.player.SimulationPaused.v1",
            type=EventType.SIMULATION_PAUSED,
            source="platform-player",
            asset=None,
            sim_time=1.0,
            event_time="2026-10-20T10:00:00Z",
            payload={"reason": "user"},
        )
    )
    assert index.get("plr-0001") is None  # el dominio `sim` no vale como evidencia
    assert index_with(gps_000001=3.0).get("gps-000001") == 3.0
