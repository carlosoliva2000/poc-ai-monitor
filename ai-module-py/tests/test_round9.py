"""Ronda 9: ids que rellena el módulo, corte por llamada repetida y chats sin tools."""

import json
from pathlib import Path
from typing import Any

import pytest
from agent_helpers import (
    NO_CHECKS,
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
from test_monitor_state import alert
from test_report_chat import operator_message

from ai_module.agent.assets import Assets
from ai_module.chat import Chat
from ai_module.monitor import Monitor
from ai_module.report import ReportAgent
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.tools import AcknowledgeDetectionArgs, CloseAlertArgs, PublishAlertArgs

ASSETS = Assets()
TOOLS_JSON = json.loads((ASSETS.root / "tools.json").read_text(encoding="utf-8"))
SCHEMAS = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS_JSON}


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def setup(tmp_path: Path, policy: Any, platform: FakePlatform | None = None):
    llm = FakeLlm(policy)
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    return rt, published, Monitor(rt), llm


def raised(det="det-0001", t=20.0, **kw):
    return detection_event("raised", det, t, **kw)


def without(args: dict, *keys: str) -> dict:
    return {k: v for k, v in args.items() if k not in keys}


def responses(published: list) -> list:
    return [
        e
        for e in published
        if e.type
        in (EventType.ANOMALY_DETECTED, EventType.ALERT_CLOSED, EventType.DETECTION_ACKNOWLEDGED)
    ]


# --- 2. ids que rellena el módulo ------------------------------------------------------------


def test_the_schemas_make_those_ids_optional() -> None:
    assert "detection_ids" not in SCHEMAS["publish_alert"]["required"]
    assert SCHEMAS["acknowledge_detection"]["required"] == ["reason"]
    assert SCHEMAS["close_alert"]["required"] == ["reason"]
    # y el contrato los acepta sin ellos
    assert (
        PublishAlertArgs.model_validate(without(alert_args([]), "detection_ids")).detection_ids
        is None
    )
    assert AcknowledgeDetectionArgs.model_validate({"reason": "x"}).detection_ids is None
    assert CloseAlertArgs.model_validate({"reason": "x"}).alert_id is None


def test_a_single_pending_detection_is_filled_in_publish_alert(tmp_path: Path) -> None:
    args = without(alert_args(["x"]), "detection_ids")
    rt, published, monitor, llm = setup(
        tmp_path, Script(tool_response(call("publish_alert", **args)))
    )
    event = raised()
    run(monitor.handle_batch([event]))
    [alert_event] = responses(published)
    assert alert_event.payload["detection_ids"] == ["det-0001"]
    assert alert_event.causation_id == event.event_id
    assert not rt.trace.records[0]["guardrail_rejections"]


def test_a_single_pending_detection_is_filled_in_acknowledge(tmp_path: Path) -> None:
    rt, published, monitor, _ = setup(
        tmp_path, Script(tool_response(call("acknowledge_detection", reason="sin alerta")))
    )
    run(monitor.handle_batch([raised()]))
    [ack] = responses(published)
    assert (
        ack.type == EventType.DETECTION_ACKNOWLEDGED and ack.payload["detection_id"] == "det-0001"
    )


def test_a_wrong_detection_id_is_rejected_with_the_right_one(tmp_path: Path) -> None:
    wrong = alert_args(["det-0007"])
    rt, published, monitor, _ = setup(
        tmp_path,
        Script(
            tool_response(call("publish_alert", **wrong)),
            tool_response(call("publish_alert", **without(wrong, "detection_ids"))),
        ),
    )
    run(monitor.handle_batch([raised()]))
    [rejection] = rt.trace.records[0]["guardrail_rejections"]
    assert rejection["errors"] == [
        "This invocation handles det-0001, not det-0007: use det-0001 (or leave out detection_ids)"
    ]
    assert responses(published)[0].payload["detection_ids"] == ["det-0001"]


def test_with_several_pending_detections_the_ids_are_required(tmp_path: Path) -> None:
    args = without(alert_args(["x"]), "detection_ids")
    rt, published, monitor, _ = setup(
        tmp_path, Script(tool_response(call("publish_alert", **args)), "x")
    )
    run(monitor.handle_batch([raised("det-0001"), raised("det-0002", rule="SOURCE_DISCREPANCY")]))
    [rejection] = rt.trace.records[0]["guardrail_rejections"]
    assert rejection["errors"][0].startswith(
        "`detection_ids` is missing: there are several pending detections"
    )


def closure_setup(tmp_path: Path, policy: Any):
    rt, published, monitor, llm = setup(tmp_path, policy)
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0001", ["det-0001"], cause="WIND"))
    return rt, published, monitor, llm, detection_event("cleared", "det-0001", 30.0)


def test_in_a_closure_the_alert_id_is_filled_in_close_alert(tmp_path: Path) -> None:
    rt, published, monitor, _, cleared = closure_setup(
        tmp_path, Script(tool_response(call("close_alert", reason="normalizada")))
    )
    run(monitor.handle_batch([cleared]))
    [closed] = responses(published)
    assert closed.type == EventType.ALERT_CLOSED and closed.payload["alert_id"] == "ai-0001"
    assert closed.causation_id == cleared.event_id


def test_in_a_closure_the_alert_id_is_filled_in_acknowledge_and_keeps_it_open(
    tmp_path: Path,
) -> None:
    rt, published, monitor, _, cleared = closure_setup(
        tmp_path, Script(tool_response(call("acknowledge_detection", reason="sigue el problema")))
    )
    run(monitor.handle_batch([cleared]))
    [ack] = responses(published)
    assert ack.payload["alert_id"] == "ai-0001" and not ack.payload["fallback"]
    assert [a.alert_id for a in rt.state.open_alerts()] == ["ai-0001"]


def test_a_wrong_alert_id_in_a_closure_is_rejected_with_the_right_one(tmp_path: Path) -> None:
    rt, published, monitor, _, cleared = closure_setup(
        tmp_path,
        Script(
            tool_response(call("close_alert", alert_id="ai-0099", reason="x")),
            tool_response(call("close_alert", reason="x")),
        ),
    )
    run(monitor.handle_batch([cleared]))
    [rejection] = rt.trace.records[0]["guardrail_rejections"]
    assert rejection["errors"] == [
        "In this closing warning the alert is ai-0001, not ai-0099: use ai-0001 "
        "(or leave out alert_id)"
    ]
    assert responses(published)[0].type == EventType.ALERT_CLOSED


def test_close_alert_without_a_closure_still_needs_the_alert_id(tmp_path: Path) -> None:
    rt, _, monitor, _ = setup(
        tmp_path, Script(tool_response(call("close_alert", reason="x")), text_response("x"))
    )
    run(monitor.handle_batch([raised()]))
    assert rt.trace.records[0]["guardrail_rejections"][0]["errors"] == [
        "`alert_id` is missing: say which alert you are closing"
    ]


# --- 3. corte por llamada repetida ---------------------------------------------------------------


def test_the_second_repetition_of_a_rejected_call_cuts_the_invocation(tmp_path: Path) -> None:
    bad = alert_args(["det-0001"], evidence_event_ids=["gps-999999"])
    rt, published, monitor, llm = setup(
        tmp_path, Script(tool_response(call("publish_alert", **bad)))
    )
    event = raised()
    run(monitor.handle_batch([event]))
    trace = rt.trace.records[0]
    assert len(llm.requests) == 3  # la original, una repetición avisada y la segunda: se corta
    assert trace["end_reason"] == "repeated_rejection" and trace["fallback"] is True
    errors = [r["errors"][0] for r in trace["guardrail_rejections"]]
    assert errors[1] == "This is the same call as before; change what I told you."
    assert errors[2] == "repeats a rejected call for the second time"
    [fallback] = responses(published)  # y el módulo responde igualmente
    assert fallback.causation_id == event.event_id and fallback.payload["fallback"] is True
    assert fallback.payload["cause"] == "UNKNOWN"
    assert "repeated_rejection" in fallback.payload["explanation"]


# --- 4. chats sin tools ---------------------------------------------------------------------------


def chat_runtime(tmp_path: Path, *, tools: bool, text: str = "respuesta"):
    llm = FakeLlm(lambda m, t, s: text_response(text))
    rt, published = make_runtime(tmp_path, llm, FakePlatform())
    rt.assets._raw.setdefault("chat", {})["tools_enabled"] = tools
    rt.state.apply(raised("det-0001", 5.0))
    full = alert_args(["det-0001"], cause="WIND", severity="low", confidence=0.85)
    full["checks"] = {**NO_CHECKS, "wind_notable": True, "wind_with_drift": True}
    full.update(explanation="El viento de 7,2 m/s empuja hacia el sur.", alert_id="ai-0002")
    rt.state.apply(_alert_event(full))
    rt.last_metrics = {
        "since": 76.0, "until": 106.0,
        "wind": {"mean_speed_mps": 7.2, "max_gust_mps": 9.7, "notable": True, "with_drift": True},
        "gps_radar": {"disagreed": False}, "gps_max_step_m": 15.5,
    }  # fmt: skip
    rt.last_metrics_note = "monitor query at T+01:46 (window 76–106 s)"
    rt.clock.observe(110.0)
    return rt, published, llm


def _alert_event(args: dict):
    from poc_contracts.envelope import EventDraft

    payload = {
        **args, "as_of_sim_time": 106.0, "fallback": False, "supersedes": None,
        "alert_id": args["alert_id"],
    }  # fmt: skip
    return EventDraft(
        event_id=args["alert_id"],
        topic="citadel.pub.evt.ai.d1.AnomalyDetected.v1",
        type=EventType.ANOMALY_DETECTED,
        source="ai-monitor",
        asset="d1",
        sim_time=106.0,
        event_time="2026-10-20T10:01:46Z",
        payload=payload,
    )


def test_chat_without_tools_carries_alerts_checks_evidence_and_facts(tmp_path: Path) -> None:
    rt, published, llm = chat_runtime(tmp_path, tools=False)
    chat = Chat(rt, ConversationId.MONITOR)
    run(chat.answer(operator_message("monitor", "¿por qué viento?")))
    request = llm.requests[0]
    assert request["tools"] == []  # no recibe tools
    system = request["messages"][0]["content"]
    assert "You have no tools" in system and "<<" not in system
    assert "ai-0002 WIND (low, confidence 0.85)" in system
    assert "El viento de 7,2 m/s empuja hacia el sur." not in system  # sin la prosa del monitor
    assert "notable wind: yes" in system and "link anomalous: not looked at" in system  # checks
    assert "Evidence: gps-000001, gps-000002" in system
    assert "monitor query at T+01:46" in system and "The wind is notable: yes" in system  # hechos
    assert rt.trace.records[0]["aids"] == {"chat_tools_enabled": False}
    [reply] = [e for e in published if e.type == EventType.AGENT_REPLY]
    assert reply.payload["tool_calls"] == []


def test_chat_with_tools_enabled_keeps_its_tools(tmp_path: Path) -> None:
    rt, _, llm = chat_runtime(tmp_path, tools=True)
    run(Chat(rt, ConversationId.MONITOR).answer(operator_message("monitor", "¿qué hay?")))
    assert llm.requests[0]["tools"]
    system = llm.requests[0]["messages"][0]["content"]
    assert "You have no tools" not in system and "Explicación:" not in system
    assert rt.trace.records[0]["aids"] == {"chat_tools_enabled": True}


def test_report_chat_without_tools_also_gets_the_data(tmp_path: Path) -> None:
    rt, _, llm = chat_runtime(tmp_path, tools=False)
    report = ReportAgent(rt, Monitor(rt))
    report.markdown = "# Informe de prueba"
    run(Chat(rt, ConversationId.REPORT, report).answer(operator_message("report", "¿qué pasó?")))
    system = llm.requests[0]["messages"][0]["content"]
    assert llm.requests[0]["tools"] == []
    assert (
        "# Informe de prueba" in system
        and "ai-0002 WIND" in system
        and "You have no tools" in system
    )


def test_the_demo_default_is_chats_without_tools() -> None:
    assert Assets().chat_tools_enabled is False


def test_the_monitor_remembers_the_last_metrics_for_the_chats(tmp_path: Path) -> None:
    metrics = {"since": 1.0, "until": 20.0, "wind": None, "gps_radar": None, "gps_max_step_m": 2.0}
    script = Script(
        tool_response(call("get_track_metrics", since=1.0, until=20.0)),
        tool_response(call("publish_alert", **without(alert_args(["x"]), "detection_ids"))),
    )
    rt, _, monitor, _ = setup(tmp_path, script, FakePlatform({"get_track_metrics": metrics}))
    run(monitor.handle_batch([raised()]))
    assert rt.last_metrics == metrics
    assert rt.last_metrics_note == "monitor query at T+00:20 (window 1–20 s)"
    assert "Sudden GPS jump" in rt.describe_last_facts()
    assert "2.0 m" in rt.describe_last_facts()


def test_the_monitor_remembers_the_link_it_looked_at_for_the_chats(tmp_path: Path) -> None:
    link = [
        {"event_id": "lnk-0001", "sim_time": 5.0, "controller_id": "GCS-1", "rssi_dbm": -62.0,
         "latency_ms": 45.0},
        {"event_id": "lnk-0002", "sim_time": 10.0, "controller_id": "UNK-4F2A", "rssi_dbm": -79.0,
         "latency_ms": 122.0},
    ]  # fmt: skip
    script = Script(
        tool_response(call("get_events", source="link", last_n=10, until=20.0)),
        tool_response(call("publish_alert", **without(alert_args(["x"]), "detection_ids"))),
    )
    platform = FakePlatform({"get_events": {"events": link, "truncated": False}})
    rt, _, monitor, _ = setup(tmp_path, script, platform)
    assert "enlace de mando" not in rt.describe_last_facts()
    run(monitor.handle_batch([raised()]))
    assert rt.last_link == link
    facts = rt.describe_last_facts()
    assert (
        "The command link is anomalous: yes (the controller changes from GCS-1 to UNK-4F2A" in facts
    )
    rt.reset_run()
    assert rt.last_link is None
