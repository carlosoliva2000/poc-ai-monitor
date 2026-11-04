"""La fase de la alerta (v0.14) en los textos que escribe el código: el estado del monitor, la
cronología y las anomalías del informe y las alertas de los chats."""

from agent_helpers import detection_event, reset_ids
from test_monitor_state import alert, closed

from ai_module.monitor_state import MonitorState
from ai_module.report_facts import Narrative, anomalies_for_llm, assemble, build_facts

SUMMARY = {
    "mission_id": "MSN", "duration_s": 200.0, "mission_completed": True,
    "completion_reason": "returned_to_base", "waypoints_planned": ["WP1"],
    "waypoints_reached": [],
}  # fmt: skip


def chain(phase: str = "recovering", close: bool = True) -> MonitorState:
    """Spoofing `high` → recuperación (`phase`), `medium`; cerrada o abierta."""
    reset_ids()
    state = MonitorState()
    state.apply(detection_event("raised", "det-0001", 100.0, rule="SOURCE_DISCREPANCY"))
    state.apply(alert("ai-0002", ["det-0001"], cause="GPS_SPOOFING", t=101.0))
    state.apply(detection_event("raised", "det-0003", 130.0))
    state.apply(
        alert(
            "ai-0004", ["det-0003"], cause="GPS_SPOOFING", supersedes="ai-0002", t=131.0,
            severity="medium", phase=phase,
        )
    )  # fmt: skip
    if close:
        state.apply(detection_event("cleared", "det-0001", 140.0, rule="SOURCE_DISCREPANCY"))
        state.apply(detection_event("cleared", "det-0003", 141.0))
        state.apply(closed("ai-0004", t=150.0))
    return state


def test_state_line_styles_and_the_phase() -> None:
    state = chain(close=False)
    # `legacy` (assets anteriores) no sabe de fases: igual que antes
    assert state.describe_gps_alert(135.0, "legacy") == (
        "yes — ai-0004 GPS_SPOOFING (open). If this warning is the GPS recovery: "
        "cause GPS_SPOOFING, supersedes ai-0004"
    )
    # `phase`: una alerta ya en recuperación no repite la frase de la recuperación
    assert (
        state.describe_gps_alert(135.0, "phase") == "yes — ai-0004 GPS_SPOOFING (open, recovering)"
    )
    active = MonitorState()
    active.apply(detection_event("raised", "det-0001", 100.0, rule="SOURCE_DISCREPANCY"))
    active.apply(alert("ai-0002", ["det-0001"], cause="GPS_SPOOFING", t=101.0))
    assert active.describe_gps_alert(105.0, "phase") == (
        "yes — ai-0002 GPS_SPOOFING (open). If this warning is the GPS recovery: "
        "cause GPS_SPOOFING, supersedes ai-0002, phase recovering"
    )


def test_the_open_alerts_and_the_related_alert_show_the_phase() -> None:
    state = chain(close=False)
    assert (
        "ai-0004 GPS_SPOOFING (medium, recovering, confidence 0.8)" in state.describe_open_alerts()
    )
    assert (
        state.describe_related_alerts("det-0003")
        == "ai-0004 (GPS_SPOOFING, medium, recovering, open)"
    )
    plain = MonitorState()
    plain.apply(detection_event("raised", "det-0001", 100.0))
    plain.apply(alert("ai-0002", ["det-0001"], cause="WIND"))
    assert "(high, confidence 0.8)" in plain.describe_open_alerts()  # activa: sin cambios
    assert plain.describe_related_alerts("det-0001") == "ai-0002 (WIND, high, open)"


def test_the_report_says_in_recovery_where_it_applies() -> None:
    state = chain()
    facts = build_facts(state)
    [anomaly] = facts.anomalies
    assert anomaly.changes == "severity high → medium; now in recovery"
    text = assemble("demo", SUMMARY, state, facts, Narrative(seen={"A1": "Saltó."}))
    assert "Alert ai-0004 (A1): GPS spoofing (medium, in recovery, confidence 0.8)" in text
    assert "(severity high → medium; now in recovery; 2 alerts in the chain)" in text
    data = anomalies_for_llm(facts, mission=True)
    assert "(medium, in recovery, confidence 0.8)" in data


def test_an_anomaly_still_open_in_recovery_is_reported_as_such() -> None:
    state = chain(close=False)
    [anomaly] = build_facts(state).anomalies
    assert anomaly.status == "OPEN at the end (in recovery)"
    active = chain(phase="active", close=False)
    [other] = build_facts(active).anomalies
    assert other.status == "OPEN at the end" and other.changes == "severity high → medium"


def test_the_chat_lists_the_phase_of_each_alert() -> None:
    state = chain(close=False)
    text = state.describe_alerts_detail(explanation=False)
    assert "- ai-0004 GPS_SPOOFING (medium, recovering, confidence 0.8)" in text
    assert "- ai-0002 GPS_SPOOFING (high, confidence 0.8)" in text  # la activa, sin fase
