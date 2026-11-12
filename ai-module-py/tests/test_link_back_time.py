"""Fase 15.1: `report.link_back_time`. El informe da la hora a la que el enlace volvió al
controlador de la misión (el primer `LinkStatus` con él), no la del cierre de la `LINK_ANOMALY`."""

from agent_helpers import detection_event, reset_ids
from test_monitor_state import ack, alert, closed

from ai_module.link_log import LinkLog
from ai_module.monitor_state import MonitorState
from ai_module.report_facts import anomalies_for_llm, build_facts, timeline_table
from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft


def link(event_id: str, t: float, controller: str) -> EventDraft:
    return EventDraft(
        event_id=event_id,
        topic="citadel.pub.evt.air.d1.LinkStatus.v1",
        type=EventType.LINK_STATUS,
        source="d1-link",
        asset="d1",
        sim_time=t,
        event_time="2026-10-20T10:00:00Z",
        payload={"controller_id": controller, "rssi_dbm": -62.0, "latency_ms": 45.0},
    )


def hijack_log() -> LinkLog:
    """GCS-1 hasta T+05:30, UNK-4F2A de T+05:35 a T+06:15 y GCS-1 desde T+06:20."""
    log = LinkLog()
    for i, t in enumerate(range(325, 400, 5)):
        controller = "UNK-4F2A" if 335 <= t < 380 else "GCS-1"
        log.observe(link(f"lnk-{i:04d}", float(t), controller))
    return log


def hijack_state() -> MonitorState:
    """`det-1` LINK_ANOMALY (T+05:35, cierra a T+06:25) y `det-2` ROUTE_DEVIATION (cierra a
    T+07:21) en `ai-1` HIJACK → recuperación `ai-3` a T+06:25."""
    reset_ids()
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 335.0, rule="LINK_ANOMALY", source="link"))
    s.apply(alert("ai-1", ["det-1"], cause="HIJACK", t=335.5))
    s.apply(detection_event("raised", "det-2", 338.0))
    s.apply(ack("ai-2", "det-2", "ai-1", t=338.5))
    s.apply(detection_event("cleared", "det-1", 385.0, rule="LINK_ANOMALY"))
    s.apply(
        alert("ai-3", ["det-1"], cause="HIJACK", supersedes="ai-1", t=385.5, phase="recovering")
    )
    s.apply(detection_event("cleared", "det-2", 441.0))
    s.apply(closed("ai-3", 441.0))
    return s


def test_the_link_log_gives_the_first_event_with_the_mission_controller_after_the_change() -> None:
    log = hijack_log()
    assert log.mission_controller == "GCS-1"
    back = log.back_after(335.0)
    assert back is not None and back.sim_time == 380.0 and back.controller_id == "GCS-1"
    assert log.back_after(381.0) is None  # no hubo otro cambio después


def test_the_link_log_is_none_without_a_change_or_while_the_link_is_away() -> None:
    quiet = LinkLog()
    for i in range(5):
        quiet.observe(link(f"lnk-{i}", float(i * 5), "GCS-1"))
    assert quiet.back_after(0.0) is None
    away = LinkLog()
    away.observe(link("lnk-1", 0.0, "GCS-1"))
    away.observe(link("lnk-2", 5.0, "UNK-4F2A"))
    away.observe(link("lnk-3", 10.0, "UNK-4F2A"))
    assert away.back_after(5.0) is None
    away.reset()
    assert away.mission_controller is None and away.changes == []


def test_the_anomaly_carries_the_link_back_time_apart_from_recovery_and_closing() -> None:
    facts = build_facts(hijack_state(), hijack_log())
    anomaly = facts.anomalies[0]
    assert anomaly.link_back is not None and anomaly.link_back.sim_time == 380.0
    text = anomalies_for_llm(facts, mission=True)
    assert (
        "Times: detected at T+05:35; command link back to GCS-1 at T+06:20; "
        "entered recovery at T+06:25; closed at T+07:21." in text
    )


def test_without_the_switch_the_times_are_the_ones_of_before() -> None:
    facts = build_facts(hijack_state())
    assert facts.anomalies[0].link_back is None
    text = anomalies_for_llm(facts, mission=True)
    assert "command link back" not in text and "entered recovery at T+06:25" in text


def test_the_timeline_lists_the_link_back_row() -> None:
    state = hijack_state()
    facts = build_facts(state, hijack_log())
    table = timeline_table(state, facts, None)
    assert "| T+06:20 | Link | Command link back to GCS-1 (lnk-0011; A1) |" in table
    assert "Command link back" not in timeline_table(state, build_facts(state), None)


# --- Chat del informe: la fase de cada alerta con su hora (`chat.alert_phases`) ---


def test_the_alert_phases_say_when_each_phase_started() -> None:
    from ai_module.report_facts import describe_alert_phases

    facts = build_facts(hijack_state(), hijack_log())
    text = describe_alert_phases(facts)
    assert text == (
        "- A1 · Drone hijacking: active from T+05:35 (ai-1, high); the command link was back to "
        "GCS-1 at T+06:20; in recovery from T+06:25 (ai-3, high); closed at T+07:21."
    )
    assert "link was back" not in describe_alert_phases(build_facts(hijack_state()))
    assert describe_alert_phases(build_facts(MonitorState())) == "There were no alerts."
