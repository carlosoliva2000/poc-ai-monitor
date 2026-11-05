"""Fase 14.4: `monitor.recovery_jump_from_module`. La fase de la recuperación del GPS se decide con
el salto que calcula el módulo (ventana fija: desde el inicio de la detección menos 30 s, sin salir
por atrás de la publicación de la primera alerta de la cadena), no con la ventana que pida el
modelo."""

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
from test_coherence import checks, metrics
from test_monitor_state import alert

from ai_module.agent.guardrails import (
    TAG_RECOVERY_ACK_NO_METRICS,
    TAG_RECOVERY_ACK_VETO,
    InvocationFacts,
    ModuleJump,
    check_acknowledge,
    gps_step,
)
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType

ALERT_AT = 10.0  # publicación de la alerta del GPS
DETECTED_AT = 20.0  # inicio del ROUTE_DEVIATION
BOTH = {"gps_alert_recent": True, "gps_radar_disagreed": True}


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def platform_with_jump_at(jump_at: float, fails_first: bool = False) -> FakePlatform:
    """Plataforma falsa: `gps_max_step_m` es 67,9 si la ventana pedida incluye el instante del
    salto y 3,0 si no."""
    state = {"calls": 0}

    def get_track_metrics(args: dict[str, Any]) -> dict[str, Any]:
        state["calls"] += 1
        if fails_first and state["calls"] == 1:
            raise RuntimeError("platform down")
        return metrics(disagreed=True, step=67.9 if args["since"] <= jump_at else 3.0)

    return FakePlatform({"get_track_metrics": get_track_metrics})


def setup(tmp_path: Path, script: Script, platform: FakePlatform, **switches: Any):
    rt, published = make_runtime(tmp_path, FakeLlm(script), platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.state.apply(detection_event("raised", "det-0001", 5.0))
    rt.state.apply(alert("ai-9001", ["det-0001"], cause="GPS_SPOOFING", t=ALERT_AT))
    rt.state.apply(detection_event("raised", "det-0002", DETECTED_AT))
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, **{"recovery_jump_from_module": True, **switches})
    return rt, published, monitor


def recovery(**changes: Any) -> dict[str, Any]:
    args = alert_args(
        ["det-0002"],
        cause="GPS_SPOOFING",
        severity="medium",
        confidence=0.8,
        supersedes="ai-9001",
        checks=checks(**BOTH),
    )
    args.update(changes)
    return args


def updated(at: float = 30.0):
    return detection_event("updated", "det-0002", at)


def alerts_of(published: list) -> list:
    return [e for e in published if e.type == EventType.ANOMALY_DETECTED]


# --- Guardrail ---


def test_the_module_step_wins_over_the_model_window() -> None:
    facts = InvocationFacts(metrics=metrics(step=67.9), module_jump=ModuleJump(3.0))
    assert gps_step(facts) == 3.0
    assert gps_step(InvocationFacts(metrics=metrics(step=67.9))) == 67.9
    assert gps_step(InvocationFacts(module_jump=ModuleJump(None))) is None
    assert gps_step(InvocationFacts()) is None


def state() -> MonitorState:
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0))
    s.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING"))
    s.apply(detection_event("raised", "det-2", 9.0))
    return s


def ack(facts: InvocationFacts):
    return check_acknowledge(
        {"detection_ids": ["det-2"], "alert_id": "ai-1", "reason": "r"},
        state=state(),
        unanswered={"det-2"},
        pending={"det-2"},
        facts=facts,
        as_of=10.0,
        recovery_ack_veto=True,
    )


def test_the_veto_uses_the_module_jump_and_needs_no_metrics_from_the_model() -> None:
    assert ack(InvocationFacts()).tag == TAG_RECOVERY_ACK_NO_METRICS  # como hoy
    vetoed = ack(InvocationFacts(module_jump=ModuleJump(67.9)))
    assert vetoed.tag == TAG_RECOVERY_ACK_VETO and "GPS jump 67.9 m" in vetoed.errors[0]
    assert ack(InvocationFacts(module_jump=ModuleJump(3.0))).ok  # sin salto, se puede reconocer
    # el salto del módulo manda aunque la ventana del modelo viera otro
    assert ack(InvocationFacts(metrics=metrics(step=67.9), module_jump=ModuleJump(3.0))).ok
    assert not ack(InvocationFacts(metrics=metrics(step=3.0), module_jump=ModuleJump(67.9))).ok


def test_the_chain_root_is_the_first_alert_of_the_chain() -> None:
    s = state()
    s.apply(alert("ai-2", ["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", t=25.0))
    assert s.chain_root(s.alerts["ai-2"]).alert_id == "ai-1"
    assert s.chain_root(s.alerts["ai-1"]).alert_id == "ai-1"


# --- Con el monitor entero ---


def test_the_module_asks_for_a_fixed_window(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0)
    script = Script(tool_response(call("publish_alert", **recovery())))
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    # desde max(20 − 30, 10, 0) = 10 hasta el instante de la invocación
    assert platform.calls[0] == ("get_track_metrics", {"since": 10.0, "until": DETECTED_AT})
    info = rt.trace.records[0]["recovery_jump"]
    assert info["jump"] is True and info["gps_max_step_m"] == 67.9


def test_a_model_window_without_the_jump_still_gets_recovering(tmp_path: Path) -> None:
    """Lo que justifica el paso: el 14B pide `since` = la detección y no ve el salto."""
    platform = platform_with_jump_at(15.0)  # el salto, entre la alerta y la detección
    script = Script(
        tool_response(call("get_track_metrics", since=DETECTED_AT, until=DETECTED_AT)),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    [event] = alerts_of(published)
    assert event.payload["phase"] == "recovering"
    record = rt.trace.records[0]
    assert record["recovery_jump"]["model_view"] == "window_without_jump"
    assert record["guardrail_rejections"] == []


def test_the_model_cannot_publish_high_nor_active_in_the_recovery(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0)
    script = Script(
        tool_response(call("get_track_metrics", since=DETECTED_AT, until=DETECTED_AT)),
        tool_response(call("publish_alert", **recovery(severity="high"))),
        tool_response(call("publish_alert", **recovery(phase="active"))),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    errors = [e for r in rt.trace.records[0]["guardrail_rejections"] for e in r["errors"]]
    assert any("severity high does not fit" in e for e in errors)
    assert any("wrong phase" in e for e in errors)
    assert alerts_of(published)[0].payload["phase"] == "recovering"


def test_acknowledging_is_vetoed_even_if_the_model_asked_for_no_metrics(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0)
    script = Script(
        tool_response(call("acknowledge_detection", alert_id="ai-9001", reason="same")),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    tags = [r.get("tag") for r in rt.trace.records[0]["guardrail_rejections"]]
    # el veto sí (y no `recovery_ack_no_metrics`); lo que siga son los `checks` de una publicación
    # sin haber pedido las métricas (eso lo exige el guardrail de coherencia, no la fase)
    assert tags[0] == TAG_RECOVERY_ACK_VETO and TAG_RECOVERY_ACK_NO_METRICS not in tags


def test_a_jump_before_the_alert_is_not_the_recovery(tmp_path: Path) -> None:
    """Un engaño que empieza con un salto brusco: el salto es anterior a la alerta del GPS y no
    puede quedar en la ventana durante toda la detección."""
    platform = platform_with_jump_at(5.0)  # antes de ALERT_AT
    script = Script(
        tool_response(call("get_track_metrics", since=0.0, until=30.0)),  # el modelo sí lo ve
        tool_response(call("acknowledge_detection", alert_id="ai-9001", reason="same spoofing")),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([updated(30.0)]))
    assert platform.calls[0] == ("get_track_metrics", {"since": ALERT_AT, "until": 30.0})
    record = rt.trace.records[0]
    assert record["recovery_jump"]["jump"] is False
    assert record["guardrail_rejections"] == []  # reconocer vale
    assert not alerts_of(published)


def test_a_jump_before_the_alert_gives_phase_active_when_publishing(tmp_path: Path) -> None:
    platform = platform_with_jump_at(5.0)
    script = Script(
        tool_response(call("get_track_metrics", since=0.0, until=30.0)),
        tool_response(call("publish_alert", **recovery(phase="recovering"))),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([updated(30.0)]))
    errors = [e for r in rt.trace.records[0]["guardrail_rejections"] for e in r["errors"]]
    assert any("phase recovering needs a GPS jump" in e for e in errors)
    assert alerts_of(published)[0].payload["phase"] == "active"


def test_the_normal_case_after_the_alert_is_recovering_on_an_update(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0)
    script = Script(
        tool_response(call("get_track_metrics", since=29.0, until=30.0)),
        tool_response(call("acknowledge_detection", alert_id="ai-9001", reason="same")),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([updated(30.0)]))
    assert platform.calls[0][1]["since"] == 10.0  # detección (20) − 30 < alerta (10)
    tags = [r.get("tag") for r in rt.trace.records[0]["guardrail_rejections"]]
    assert tags == [TAG_RECOVERY_ACK_VETO]
    assert alerts_of(published)[0].payload["phase"] == "recovering"


def test_a_head_already_recovering_keeps_seeing_the_jump(tmp_path: Path) -> None:
    """La ventana arranca en la primera alerta de la cadena, no en la cabeza (publicada después
    del salto): un `updated` posterior sigue viéndolo."""
    platform = platform_with_jump_at(15.0)
    script = Script(tool_response(call("acknowledge_detection", alert_id="ai-9002", reason="x")))
    rt, published, monitor = setup(tmp_path, script, platform)
    rt.state.apply(
        alert("ai-9002", ["det-0002"], cause="GPS_SPOOFING", supersedes="ai-9001",
              severity="medium", phase="recovering", t=25.0)
    )  # fmt: skip
    run(monitor.handle_batch([updated(30.0)]))
    assert platform.calls[0][1]["since"] == 10.0  # no 25
    assert rt.trace.records[0]["recovery_jump"]["jump"] is True


def test_a_failed_call_falls_back_to_the_model_window_and_is_traced(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0, fails_first=True)
    script = Script(
        tool_response(call("get_track_metrics", since=0.0, until=DETECTED_AT)),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    record = rt.trace.records[0]
    assert record["recovery_jump"]["error"] == "platform down"
    assert alerts_of(published)[0].payload["phase"] == "recovering"  # con la ventana del modelo


def test_a_failed_call_keeps_todays_rejection_without_model_metrics(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0, fails_first=True)
    script = Script(
        tool_response(call("acknowledge_detection", alert_id="ai-9001", reason="same")),
        tool_response(call("get_track_metrics", since=0.0, until=DETECTED_AT)),
        tool_response(call("publish_alert", **recovery())),
    )
    rt, published, monitor = setup(tmp_path, script, platform)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    tags = [r.get("tag") for r in rt.trace.records[0]["guardrail_rejections"]]
    assert tags == [TAG_RECOVERY_ACK_NO_METRICS]


def test_the_switch_off_is_todays_behaviour(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0)
    script = Script(
        tool_response(call("get_track_metrics", since=DETECTED_AT, until=DETECTED_AT)),
        tool_response(call("publish_alert", **recovery(phase="active"))),
    )
    rt, published, monitor = setup(tmp_path, script, platform, recovery_jump_from_module=False)
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    assert [c[1]["since"] for c in platform.calls] == [DETECTED_AT]  # solo la del modelo
    assert rt.trace.records[0]["recovery_jump"] == {}
    assert alerts_of(published)[0].payload["phase"] == "active"  # ventana sin salto, como hoy


def test_no_call_without_a_recent_gps_alert_or_for_other_rules(tmp_path: Path) -> None:
    platform = platform_with_jump_at(15.0)
    rt, published, monitor = setup(tmp_path, Script("no tool call"), platform)
    rt.state.alerts.clear()
    run(monitor.handle_batch([detection_event("raised", "det-0002", DETECTED_AT)]))
    assert platform.calls == []
    platform2 = platform_with_jump_at(15.0)
    rt2, _, monitor2 = setup(tmp_path / "b", Script("no tool call"), platform2)
    rt2.state.apply(detection_event("raised", "det-0003", 21.0, rule="SOURCE_DISCREPANCY"))
    run(
        monitor2.handle_batch(
            [detection_event("updated", "det-0003", 22.0, rule="SOURCE_DISCREPANCY")]
        )
    )
    assert platform2.calls == []


def test_the_switch_is_off_in_the_frozen_assets_and_on_in_the_current_ones() -> None:
    from ai_module.agent.assets import Assets

    root = Path(__file__).resolve().parents[2]
    assert Assets(root / "agent-assets-v13").agent("monitor").recovery_jump_from_module is False
