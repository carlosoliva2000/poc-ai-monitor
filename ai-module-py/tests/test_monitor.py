"""Monitor con un LLM falso: cada detección recibe respuesta, con o sin LLM, pase lo que pase."""

import asyncio
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
    tool_response,
)
from test_monitor_state import alert

from ai_module.monitor import Monitor
from poc_contracts.enums import EventType

RESPONSES = (EventType.ANOMALY_DETECTED, EventType.ALERT_CLOSED, EventType.DETECTION_ACKNOWLEDGED)


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def setup(tmp_path: Path, policy: Any, platform: FakePlatform | None = None):
    llm = FakeLlm(policy)
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    return rt, published, Monitor(rt), llm


def responses(published: list) -> list:
    return [e for e in published if e.type in RESPONSES]


def activity(published: list) -> list[str]:
    return [e.payload["state"] for e in published if e.type == EventType.AGENT_ACTIVITY]


def raised(det: str = "det-0001", t: float = 20.0, **kw: Any):
    return detection_event("raised", det, t, **kw)


def test_a_new_alert_answers_its_detection(tmp_path: Path) -> None:
    llm_script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, published, monitor, llm = setup(tmp_path, llm_script)
    event = raised()
    run(monitor.handle_batch([event]))
    [alert_event] = responses(published)
    assert alert_event.type == EventType.ANOMALY_DETECTED
    assert alert_event.causation_id == event.event_id
    assert alert_event.event_id == alert_event.payload["alert_id"]  # el alert_id es el event_id
    assert (
        alert_event.payload["fallback"] is False and alert_event.payload["as_of_sim_time"] == 20.0
    )
    assert len(llm.requests) == 1  # el bucle termina al responder: ni una llamada de más
    # el monitor responde siempre con una tool call: `required`, y el muestreo va explícito
    assert llm.requests[0]["sampling"]["tool_choice"] == "required"
    assert llm.requests[0]["sampling"]["extra_body"] == {"top_k": -1, "repetition_penalty": 1.05}
    assert activity(published) == ["started", "finished"]
    assert [a.alert_id for a in rt.state.open_alerts()] == [alert_event.event_id]
    [trace] = rt.trace.records
    assert trace["end_reason"] == "done" and not trace["fallback"]
    assert trace["published"][0]["causation_id"] == event.event_id
    # el prompt lleva el estado y la detección
    first_user = llm.requests[0]["messages"][1]["content"]
    assert "Open alerts: none" in first_user and "det-0001" in first_user
    assert "<<" not in first_user


def test_text_only_gets_one_reminder_then_unknown_fallback(tmp_path: Path) -> None:
    rt, published, monitor, llm = setup(tmp_path, Script("no sé qué hacer"))
    event = raised()
    run(monitor.handle_batch([event]))
    [fallback] = responses(published)
    assert fallback.type == EventType.ANOMALY_DETECTED
    assert fallback.payload["cause"] == "UNKNOWN" and fallback.payload["fallback"] is True
    assert fallback.causation_id == event.event_id
    assert fallback.payload["evidence_event_ids"] == ["gps-000001", "gps-000002"]
    assert len(llm.requests) == 2  # un recordatorio, y a la segunda se rinde
    assert "You have not yet responded to: det-0001" in llm.requests[1]["messages"][-1]["content"]
    [trace] = rt.trace.records
    assert trace["fallback"] and trace["reminders"] == 1 and trace["end_reason"] == "text"


def test_fallback_with_an_open_alert_is_an_acknowledge_without_alert(tmp_path: Path) -> None:
    rt, published, monitor, _ = setup(tmp_path, Script("nada"))
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0001", ["det-0001"]))
    event = raised("det-0002", 20.0, rule="SOURCE_DISCREPANCY")
    run(monitor.handle_batch([event]))
    [response] = responses(published)
    assert response.type == EventType.DETECTION_ACKNOWLEDGED
    assert response.payload["fallback"] is True and response.payload["alert_id"] is None
    assert response.causation_id == event.event_id


def test_updated_without_an_alert_also_falls_back_to_an_acknowledge(tmp_path: Path) -> None:
    rt, published, monitor, _ = setup(tmp_path, Script("nada"))
    run(monitor.handle_batch([detection_event("updated", "det-0001", 20.0)]))
    [response] = responses(published)
    assert response.type == EventType.DETECTION_ACKNOWLEDGED and response.payload["fallback"]


def test_llm_error_and_timeout_fall_back(tmp_path: Path) -> None:
    rt, published, monitor, _ = setup(tmp_path, Script(RuntimeError("vLLM caído")))
    run(monitor.handle_batch([raised()]))
    assert responses(published)[0].payload["fallback"] is True
    assert rt.trace.records[0]["end_reason"] == "error"

    class Sleeper(FakeLlm):
        async def complete(self, *args: Any, **kwargs: Any):
            await asyncio.sleep(5)

    reset_ids()
    llm = Sleeper(Script("x"))
    rt, published = make_runtime(tmp_path, llm)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, max_invocation_s=0.2, llm_timeout_s=0.1)
    run(monitor.handle_batch([raised()]))
    assert responses(published)[0].payload["cause"] == "UNKNOWN"
    assert rt.trace.records[0]["end_reason"] == "timeout"


def test_updated_acknowledge_with_the_open_alert(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("acknowledge_detection", detection_ids=["det-0001"], alert_id="ai-0001",
                           reason="sigue igual")))  # fmt: skip
    rt, published, monitor, _ = setup(tmp_path, script)
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0001", ["det-0001"]))
    event = detection_event("updated", "det-0001", 20.0, severity="high")
    run(monitor.handle_batch([event]))
    [response] = responses(published)
    assert response.type == EventType.DETECTION_ACKNOWLEDGED
    assert response.payload["alert_id"] == "ai-0001" and not response.payload["fallback"]
    assert response.causation_id == event.event_id  # el del Updated, no el detection_id


def test_updated_with_supersedes_keeps_a_single_chain(tmp_path: Path) -> None:
    args = alert_args(["det-0001"], supersedes="ai-0001", severity="high")
    rt, published, monitor, _ = setup(
        tmp_path, Script(tool_response(call("publish_alert", **args)))
    )
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0001", ["det-0001"], cause="SENSOR_FAULT"))
    run(monitor.handle_batch([detection_event("updated", "det-0001", 20.0)]))
    [new] = responses(published)
    assert new.payload["supersedes"] == "ai-0001"
    assert [a.alert_id for a in rt.state.open_alerts()] == [new.payload["alert_id"]]
    assert rt.state.chains_published == 1


def test_a_batch_of_three_gets_three_responses(tmp_path: Path) -> None:
    """Dos avisos de la misma detección y uno de otra, resueltos con una sola alerta."""
    args = alert_args(["det-0001", "det-0002"])
    rt, published, monitor, llm = setup(
        tmp_path, Script(tool_response(call("publish_alert", **args)))
    )
    events = [
        raised("det-0001", 20.0),
        raised("det-0002", 20.0, rule="SOURCE_DISCREPANCY"),
        detection_event("updated", "det-0001", 21.0),
    ]
    run(monitor.handle_batch(events))
    answers = responses(published)
    assert sorted(e.causation_id for e in answers) == sorted(e.event_id for e in events)
    kinds = [e.type for e in answers]
    assert kinds.count(EventType.ANOMALY_DETECTED) == 1
    assert kinds.count(EventType.DETECTION_ACKNOWLEDGED) == 2
    alert_id = next(e for e in answers if e.type == EventType.ANOMALY_DETECTED).event_id
    assert all(e.payload["alert_id"] == alert_id for e in answers if e.payload.get("alert_id"))
    assert len(llm.requests) == 1
    assert "You have 3 detector warnings" in llm.requests[0]["messages"][1]["content"]


def test_a_batch_with_one_unanswered_event_gets_the_fallback_for_that_one(tmp_path: Path) -> None:
    args = alert_args(["det-0001"])
    script = Script(tool_response(call("publish_alert", **args)), "ya está")
    rt, published, monitor, _ = setup(tmp_path, script)
    events = [raised("det-0001", 20.0), raised("det-0002", 20.0, rule="SOURCE_DISCREPANCY")]
    run(monitor.handle_batch(events))
    answers = {e.causation_id: e for e in responses(published)}
    assert set(answers) == {e.event_id for e in events}
    assert answers["det-0001"].type == EventType.ANOMALY_DETECTED
    assert answers["det-0002"].type == EventType.DETECTION_ACKNOWLEDGED
    assert answers["det-0002"].payload["fallback"] is True  # ya hay una alerta abierta


def test_deterministic_acknowledge_for_a_cleared_that_changes_nothing(tmp_path: Path) -> None:
    rt, published, monitor, llm = setup(tmp_path, Script("no debería llamarse"))
    # 1) sin alerta
    rt.state.apply(raised("det-0001", 5.0))
    c1 = detection_event("cleared", "det-0001", 30.0)
    run(monitor.handle_batch([c1]))
    # 2) a la alerta le quedan detecciones abiertas
    rt.state.apply(raised("det-0002", 31.0))
    rt.state.apply(raised("det-0003", 31.0, rule="SOURCE_DISCREPANCY"))
    rt.state.apply(alert("ai-0010", ["det-0002", "det-0003"]))
    c2 = detection_event("cleared", "det-0002", 40.0)
    run(monitor.handle_batch([c2]))
    # 3) la alerta is already closed
    rt.state.apply(detection_event("cleared", "det-0003", 41.0))
    from test_monitor_state import closed

    rt.state.apply(closed("ai-0010"))
    c3 = detection_event("cleared", "det-0003", 50.0, event_id="det-0777")
    run(monitor.handle_batch([c3]))
    assert llm.requests == []  # ninguna llamada al LLM
    answers = responses(published)
    assert [e.causation_id for e in answers] == [c1.event_id, c2.event_id, c3.event_id]
    assert all(e.type == EventType.DETECTION_ACKNOWLEDGED for e in answers)
    assert answers[0].payload["alert_id"] is None and answers[1].payload["alert_id"] == "ai-0010"
    assert "still has open detections (det-0003)" in answers[1].payload["reason"]
    # la alerta ya cerrada no es «la alerta abierta a la que pertenece»: alert_id nulo
    assert (
        answers[2].payload["alert_id"] is None
        and "was already closed" in answers[2].payload["reason"]
    )
    assert all(t["deterministic"] for t in rt.trace.records)
    assert activity(published) == []  # sin LLM no hay actividad de agente


def test_the_last_cleared_of_an_alert_goes_to_the_llm_which_closes_it(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("close_alert", alert_id="ai-0090", reason="La desviación se corrigió"))
    )
    rt, published, monitor, llm = setup(tmp_path, script)
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0090", ["det-0001"]))
    cleared = detection_event("cleared", "det-0001", 30.0)
    run(monitor.handle_batch([cleared]))
    [closed] = responses(published)
    assert closed.type == EventType.ALERT_CLOSED and closed.causation_id == cleared.event_id
    assert closed.payload["alert_id"] == "ai-0090"
    assert rt.state.open_alerts() == []
    assert (
        "was the **last open detection** of alert ai-0090"
        in (llm.requests[0]["messages"][1]["content"])
    )


def test_the_llm_may_keep_the_alert_open_and_it_is_respected(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("acknowledge_detection", detection_ids=["det-0001"], alert_id="ai-0001",
                           reason="otra fuente sigue mal")))  # fmt: skip
    rt, published, monitor, _ = setup(tmp_path, script)
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0001", ["det-0001"]))
    cleared = detection_event("cleared", "det-0001", 30.0)
    run(monitor.handle_batch([cleared]))
    [response] = responses(published)
    assert response.type == EventType.DETECTION_ACKNOWLEDGED
    assert response.payload["alert_id"] == "ai-0001" and not response.payload["fallback"]
    assert [a.alert_id for a in rt.state.open_alerts()] == ["ai-0001"]  # sigue abierta


def test_fallback_close_when_the_last_cleared_ends_without_conclusion(tmp_path: Path) -> None:
    rt, published, monitor, _ = setup(tmp_path, Script("hmm"))
    rt.state.apply(raised("det-0001", 5.0))
    rt.state.apply(alert("ai-0090", ["det-0001"]))
    cleared = detection_event("cleared", "det-0001", 30.0)
    run(monitor.handle_batch([cleared]))
    [closed] = responses(published)
    assert closed.type == EventType.ALERT_CLOSED
    assert closed.payload["reason"] == "all its detections have been cleared"
    assert closed.causation_id == cleared.event_id
    assert rt.state.open_alerts() == []
    [trace] = rt.trace.records
    assert trace["fallback"] and trace["fallback_close"]


def test_guardrail_rejections_go_back_to_the_model_and_are_counted(tmp_path: Path) -> None:
    bad = alert_args(["det-0001"], evidence_event_ids=["gps-000001", "gps-999999"])
    good = alert_args(["det-0001"])
    script = Script(tool_response(call("publish_alert", **bad)),
                    tool_response(call("publish_alert", **good)))  # fmt: skip
    rt, published, monitor, llm = setup(tmp_path, script)
    run(monitor.handle_batch([raised()]))
    [alert_event] = responses(published)
    assert alert_event.payload["evidence_event_ids"] == ["gps-000001", "gps-000002"]
    feedback = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert '"ok":false' in feedback and "gps-999999" in feedback
    [trace] = rt.trace.records
    assert len(trace["guardrail_rejections"]) == 1 and trace["iterations"] == 2


def test_unseen_evidence_is_counted_in_the_trace(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, _, monitor, _ = setup(tmp_path, script)
    run(monitor.handle_batch([raised(trigger=("gps-000001",))]))
    # gps-000002 existe pero el modelo no lo ha visto en ninguna tool ni en el prompt
    assert rt.trace.records[0]["unseen_evidence"] == 1


def test_data_tools_are_capped_at_as_of_and_skills_are_traced(tmp_path: Path) -> None:
    platform = FakePlatform({"get_events": {"events": [], "truncated": False}})
    script = Script(
        tool_response(call("load_skill", name="route-deviation")),
        tool_response(call("get_events", source="gps", until=9999.0),
                      call("get_track_metrics", since=1.0, until=9999.0),
                      call("get_events", source="radar", until=3.0)),
        tool_response(call("publish_alert", **alert_args(["det-0001"]))),
    )  # fmt: skip
    rt, published, monitor, _ = setup(tmp_path, script, platform)
    run(monitor.handle_batch([raised()]))
    assert [c[1].get("until") for c in platform.calls] == [20.0, 20.0, 3.0]
    trace = rt.trace.records[0]
    assert trace["skills_loaded"] == [{"name": "route-deviation", "by": "model"}]


def test_guided_mode_preloads_the_skill_of_the_rule(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, _, monitor, llm = setup(tmp_path, script)
    monitor.config = replace(monitor.config, guided_mode=True)
    run(monitor.handle_batch([raised(rule="GPS_DEGRADED", source="gps")]))
    messages = llm.requests[0]["messages"]
    assert messages[2]["tool_calls"][0]["function"]["name"] == "load_skill"
    assert "source-discrepancy" in messages[3]["content"]
    assert rt.trace.records[0]["skills_loaded"] == [{"name": "source-discrepancy", "by": "guided"}]


def test_a_cleared_waits_for_the_alert_of_its_own_detection() -> None:
    from collections import deque

    rt, _, monitor, _ = setup(Path("."), Script("x"))
    r1, c1 = raised("det-0001"), detection_event("cleared", "det-0001", 25.0)
    r2 = raised("det-0002")
    monitor.queue = deque([r1, r2, c1])
    assert [e.event_id for e in monitor._take_batch()] == [r1.event_id, r2.event_id]
    assert [e.event_id for e in monitor._take_batch()] == [c1.event_id]


def test_worker_serialises_invocations_and_wait_idle(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))), "x")
    rt, published, monitor, _ = setup(tmp_path, script)

    async def scenario() -> None:
        task = asyncio.create_task(monitor.run_forever())
        monitor.submit(raised("det-0001"))
        await asyncio.wait_for(monitor.wait_idle(), 5)
        task.cancel()

    run(scenario())
    assert len(responses(published)) == 1
