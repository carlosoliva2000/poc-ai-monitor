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
    assert any("gps-000009" in e and "later than" in e for e in verdict.errors)
    assert any("gps-424242" in e and "does not exist" in e for e in verdict.errors)
    assert not any("gps-000001" in e for e in verdict.errors)


def test_publish_alert_rejects_unknown_detection(state: MonitorState) -> None:
    verdict = check(alert_args(["det-77"]), state)
    assert any("det-77" in e for e in verdict.errors)


def test_publish_alert_rejects_a_detection_already_in_an_open_alert(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"]))
    verdict = check(alert_args(["det-1"]), state)
    assert any("is already in the open alert ai-1" in e for e in verdict.errors)
    # con supersedes a esa alerta sí vale
    assert check(alert_args(["det-1"], supersedes="ai-1"), state).ok


def test_supersedes_must_point_to_an_open_alert(state: MonitorState) -> None:
    assert not check(alert_args(["det-1"], supersedes="ai-9"), state).ok
    state.apply(alert("ai-1", ["det-1"]))
    state.apply(closed("ai-1"))
    verdict = check(alert_args(["det-1"], supersedes="ai-1"), state)
    assert any("is not an open alert" in e for e in verdict.errors)
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
        e.startswith("Nothing changes with respect to ai-1") and "use acknowledge_detection" in e
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
    assert any("is not an open alert" in e for e in bad_alert.errors)
    foreign = check_acknowledge(
        {"detection_ids": ["det-5"], "reason": "r"},
        state=state, unanswered={"det-2"}, pending={"det-2"},
    )  # fmt: skip
    assert any("is not one you must handle" in e for e in foreign.errors)
    answered = check_acknowledge(
        {"detection_ids": ["det-2"], "reason": "r"},
        state=state, unanswered=set(), pending={"det-2"},
    )  # fmt: skip
    assert any("already has a response" in e for e in answered.errors)
    missing = check_acknowledge(
        {"detection_ids": [], "reason": "r"}, state=state, unanswered=set(), pending=set()
    )
    assert not missing.ok


def test_close_alert_rules(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"]))
    still_open = check_close_alert({"alert_id": "ai-1", "reason": "ok"}, state=state)
    assert any("open detections (det-1)" in e for e in still_open.errors)
    state.apply(detection_event("cleared", "det-1", 30.0))
    assert check_close_alert({"alert_id": "ai-1", "reason": "ok"}, state=state).ok
    assert any("does not exist" in e for e in check_close_alert(
        {"alert_id": "ai-7", "reason": "x"}, state=state).errors)  # fmt: skip
    state.apply(alert("ai-2", ["det-1"], supersedes="ai-1"))
    superseded = check_close_alert({"alert_id": "ai-1", "reason": "x"}, state=state)
    assert any("superseded by ai-2" in e for e in superseded.errors)
    state.apply(closed("ai-2"))
    assert any("is already closed" in e for e in check_close_alert(
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


# --- Fuente callada (`source_silent_own_alert`) ---


@pytest.fixture
def silent_gps() -> MonitorState:
    """Alerta `GPS_JAMMING` abierta (ai-1) y un `SOURCE_SILENT` del GPS sin alerta (det-8)."""
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0))
    s.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))
    s.apply(detection_event("raised", "det-8", 9.0, rule="SOURCE_SILENT", source="gps"))
    return s


def silent_check(raw, state, *, switch=True):
    return check_publish_alert(
        raw,
        as_of=10.0,
        state=state,
        index=index_with(**GOOD),
        seen_ids=set(),
        source_silent_own_alert=switch,
    )


def test_source_silent_cannot_be_acknowledged_into_another_alert(silent_gps) -> None:
    raw = {"detection_ids": ["det-8"], "alert_id": "ai-1", "reason": "r"}
    kwargs = {"state": silent_gps, "unanswered": {"det-8"}, "pending": {"det-8"}}
    verdict = check_acknowledge(raw, **kwargs, source_silent_own_alert=True)
    assert any("own alert" in e and "SENSOR_FAULT" in e and "without supersedes" in e
               for e in verdict.errors)  # fmt: skip
    assert check_acknowledge(raw, **kwargs).ok  # interruptor apagado


def test_source_silent_cannot_supersede_an_alert_of_another_cause(silent_gps) -> None:
    raw = alert_args(["det-8"], cause="GPS_JAMMING", severity="medium", supersedes="ai-1")
    errors = silent_check(raw, silent_gps).errors
    assert any("different fault from ai-1 (GPS_JAMMING)" in e and "without supersedes" in e
               for e in errors)  # fmt: skip
    assert silent_check(raw, silent_gps, switch=False).ok


def test_source_silent_with_its_own_alert_is_accepted(silent_gps) -> None:
    own = alert_args(["det-8"], cause="SENSOR_FAULT")
    assert silent_check(own, silent_gps).ok


def test_silent_radar_without_other_alert_is_unchanged() -> None:
    """F1: radar mudo sin ninguna alerta abierta; publica `SENSOR_FAULT` y no se toca."""
    s = MonitorState()
    s.apply(detection_event("raised", "det-2", 5.0, rule="SOURCE_SILENT", source="radar"))
    assert silent_check(alert_args(["det-2"], cause="SENSOR_FAULT"), s).ok
    assert silent_check(alert_args(["det-2"], cause="SENSOR_FAULT", severity="high"), s).ok


def test_source_silent_already_in_its_own_alert_can_be_acknowledged(silent_gps) -> None:
    """Un `DetectionUpdated` de un silencio que ya tiene alerta propia se reconoce como siempre."""
    silent_gps.apply(alert("ai-2", ["det-8"], cause="SENSOR_FAULT", severity="medium"))
    silent_gps.apply(detection_event("updated", "det-8", 12.0, rule="SOURCE_SILENT", source="gps"))
    verdict = check_acknowledge(
        {"detection_ids": ["det-8"], "alert_id": "ai-2", "reason": "r"},
        state=silent_gps, unanswered={"det-8"}, pending={"det-8"},
        source_silent_own_alert=True,
    )  # fmt: skip
    assert verdict.ok


def test_other_rules_are_not_affected(silent_gps) -> None:
    silent_gps.apply(detection_event("raised", "det-9", 9.5, rule="SOURCE_DISCREPANCY"))
    verdict = check_acknowledge(
        {"detection_ids": ["det-9"], "alert_id": "ai-1", "reason": "r"},
        state=silent_gps, unanswered={"det-9"}, pending={"det-9"},
        source_silent_own_alert=True,
    )  # fmt: skip
    assert verdict.ok


# --- Causa duplicada (`no_duplicate_cause`) ---


@pytest.fixture
def two_detections(state: MonitorState) -> MonitorState:
    """Alerta `WIND` abierta (ai-1) sobre det-1 y una detección nueva sin alerta (det-2)."""
    state.apply(alert("ai-1", ["det-1"], cause="WIND"))
    state.apply(detection_event("raised", "det-2", 8.0))
    return state


def dup_check(raw, state, *, switch=True, own_alert=False):
    return check_publish_alert(
        raw,
        as_of=10.0,
        state=state,
        index=index_with(**GOOD),
        seen_ids=set(),
        no_duplicate_cause=switch,
        source_silent_own_alert=own_alert,
    )


def test_a_new_alert_with_the_cause_of_an_open_one_is_rejected(two_detections) -> None:
    verdict = dup_check(alert_args(["det-2"], cause="WIND"), two_detections)
    assert verdict.errors == [
        "ai-1 (WIND) is open: use supersedes ai-1 if the cause or severity changes, "
        "or acknowledge_detection"
    ]


def test_the_same_cause_with_supersedes_is_accepted(two_detections) -> None:
    raw = alert_args(["det-2"], cause="WIND", severity="low", supersedes="ai-1")
    assert dup_check(raw, two_detections).ok


def test_a_different_cause_is_accepted(two_detections) -> None:
    assert dup_check(alert_args(["det-2"], cause="HIJACK"), two_detections).ok


def test_a_closed_alert_of_the_same_cause_does_not_count(two_detections) -> None:
    two_detections.apply(closed("ai-1"))
    assert dup_check(alert_args(["det-2"], cause="WIND"), two_detections).ok


def test_a_superseded_alert_does_not_count_only_the_head_of_the_chain(two_detections) -> None:
    """WIND ai-1 sustituida por SENSOR_FAULT (ai-2): una WIND nueva sin supersedes vale."""
    two_detections.apply(alert("ai-2", ["det-2"], cause="SENSOR_FAULT", supersedes="ai-1"))
    two_detections.apply(detection_event("raised", "det-3", 9.0))
    assert dup_check(alert_args(["det-3"], cause="WIND"), two_detections).ok
    # pero sí cuenta la cabeza de la cadena
    again = dup_check(alert_args(["det-3"], cause="SENSOR_FAULT"), two_detections)
    assert any(e.startswith("ai-2 (SENSOR_FAULT) is open") for e in again.errors)


def test_a_new_source_silent_is_exempt_even_with_a_sensor_fault_open() -> None:
    """Un silencio nuevo lleva alerta propia aunque haya otra SENSOR_FAULT abierta (otra fuente)."""
    s = MonitorState()
    s.apply(detection_event("raised", "det-2", 5.0, rule="SOURCE_SILENT", source="radar"))
    s.apply(alert("ai-1", ["det-2"], cause="SENSOR_FAULT"))
    s.apply(detection_event("raised", "det-8", 9.0, rule="SOURCE_SILENT", source="gps"))
    own = alert_args(["det-8"], cause="SENSOR_FAULT")
    assert dup_check(own, s, own_alert=True).ok


def test_the_switch_off_keeps_the_previous_behaviour(two_detections) -> None:
    assert dup_check(alert_args(["det-2"], cause="WIND"), two_detections, switch=False).ok
