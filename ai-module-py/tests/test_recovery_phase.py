"""Fase de la alerta (v0.14): veto del reconocimiento de la recuperación del GPS y su traza, y
la fase que lleva la alerta publicada."""

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
from test_guardrails import GOOD, index_with
from test_monitor_state import alert, closed

from ai_module.agent.guardrails import (
    TAG_RECOVERY_ACK_NO_METRICS,
    TAG_RECOVERY_ACK_VETO,
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


@pytest.fixture
def state() -> MonitorState:
    """Alerta del GPS abierta (`ai-1`, spoofing) y un `ROUTE_DEVIATION` nuevo (`det-2`)."""
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0))
    s.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING"))
    s.apply(detection_event("raised", "det-2", 9.0))
    return s


def ack(
    state: MonitorState,
    facts: InvocationFacts | None,
    *,
    alert_id: str | None = "ai-1",
    veto: bool = True,
    detection: str = "det-2",
):
    raw: dict[str, Any] = {"detection_ids": [detection], "reason": "r"}
    if alert_id is not None:
        raw["alert_id"] = alert_id
    return check_acknowledge(
        raw,
        state=state,
        unanswered={detection},
        pending={detection},
        facts=facts,
        as_of=10.0,
        recovery_ack_veto=veto,
    )


def test_acknowledging_the_recovery_is_vetoed_with_data(state: MonitorState) -> None:
    facts = InvocationFacts(metrics=metrics(disagreed=True, step=67.9))
    verdict = ack(state, facts)
    assert verdict.tag == TAG_RECOVERY_ACK_VETO
    assert verdict.errors == [
        "GPS recovery of ai-1 (GPS_SPOOFING), GPS jump 67.9 m (threshold 30 m): it cannot be "
        "acknowledged; publish the alert with that cause, supersedes ai-1 and phase recovering"
    ]
    # sin `alert_id` tampoco vale: si no, se esquivaría omitiéndolo
    assert ack(state, facts, alert_id=None).tag == TAG_RECOVERY_ACK_VETO


def test_without_get_track_metrics_it_cannot_be_known_so_it_asks_for_them(
    state: MonitorState,
) -> None:
    for facts in (None, InvocationFacts()):
        verdict = ack(state, facts)
        assert verdict.tag == TAG_RECOVERY_ACK_NO_METRICS
        assert "request the track metrics of the last 30 s" in verdict.errors[0]


def test_acknowledging_with_the_spoofing_still_active_is_valid(state: MonitorState) -> None:
    """Un `ROUTE_DEVIATION` con el engaño en marcha: GPS y radar discrepan (41,8 m) pero el GPS
    no ha saltado (5,1 m): reconocer sigue valiendo."""
    facts = InvocationFacts(metrics=metrics(disagreed=True, step=5.1))
    verdict = ack(state, facts)
    assert verdict.ok and verdict.tag is None


def test_acknowledging_when_the_alert_is_already_recovering_is_valid(state: MonitorState) -> None:
    state.apply(
        alert(
            "ai-5",
            ["det-2"],
            cause="GPS_SPOOFING",
            supersedes="ai-1",
            severity="medium",
            phase="recovering",
        )
    )
    facts = InvocationFacts(metrics=metrics(disagreed=True, step=67.9))
    assert ack(state, facts, alert_id="ai-5").ok


def test_the_veto_only_applies_to_an_open_route_deviation_and_an_open_alert(
    state: MonitorState,
) -> None:
    facts = InvocationFacts(metrics=metrics(disagreed=True, step=67.9))
    assert ack(state, facts, veto=False).ok  # interruptor apagado (assets anteriores)
    # un aviso de cierre: la detección ya no está abierta
    state.apply(detection_event("cleared", "det-2", 9.5))
    assert ack(state, facts).ok
    # alerta del GPS ya cerrada: no hay una que siga en `active`
    closed_state = MonitorState()
    closed_state.apply(detection_event("raised", "det-1", 5.0))
    closed_state.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))
    closed_state.apply(detection_event("cleared", "det-1", 8.0))
    closed_state.apply(closed("ai-1", t=9.0))
    closed_state.apply(detection_event("raised", "det-2", 9.5))
    assert ack(closed_state, facts, alert_id=None).ok
    # otras reglas: un SOURCE_DISCREPANCY abierto no es una recuperación
    other = MonitorState()
    other.apply(detection_event("raised", "det-1", 5.0))
    other.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))
    other.apply(detection_event("raised", "det-3", 9.0, rule="SOURCE_DISCREPANCY"))
    assert ack(other, facts, detection="det-3").ok


def test_the_veto_is_off_in_the_frozen_assets_and_on_in_the_current_ones() -> None:
    from ai_module.agent.assets import Assets

    root = Path(__file__).resolve().parents[2]
    assert Assets(root / "agent-assets").agent("monitor").recovery_ack_veto is True
    assert Assets(root / "agent-assets-v13").agent("monitor").recovery_ack_veto is False


# --- Con el monitor entero -------------------------------------------------------------


def monitor_in_recovery(tmp_path: Path, script: Script):
    platform = FakePlatform({"get_track_metrics": metrics(disagreed=True, step=67.9)})
    rt, published = make_runtime(tmp_path, FakeLlm(script), platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    rt.state.apply(detection_event("raised", "det-0001", 5.0))
    rt.state.apply(alert("ai-9001", ["det-0001"], cause="GPS_SPOOFING"))
    monitor = Monitor(rt)
    return rt, published, monitor


def test_the_model_acknowledges_the_recovery_then_publishes_it(tmp_path: Path) -> None:
    recovery = alert_args(
        ["det-0002"],
        cause="GPS_SPOOFING",
        severity="low",
        confidence=0.8,
        supersedes="ai-9001",
        checks=checks(gps_alert_recent=True, gps_radar_disagreed=True),
    )
    script = Script(
        tool_response(call("get_track_metrics", since=0.0, until=20.0)),
        tool_response(call("acknowledge_detection", alert_id="ai-9001", reason="same spoofing")),
        tool_response(call("publish_alert", **recovery)),
    )
    rt, published, monitor = monitor_in_recovery(tmp_path, script)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 20.0)]))
    [event] = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert event.payload["phase"] == "recovering"  # la puso el módulo
    assert event.payload["severity"] == "low" and event.payload["supersedes"] == "ai-9001"
    [record] = rt.trace.records
    tags = [r.get("tag") for r in record["guardrail_rejections"]]
    assert tags == [TAG_RECOVERY_ACK_VETO]
    assert rt.state.alerts["ai-9001"].phase == "active"
    assert next(a for a in rt.state.alerts.values() if a.supersedes).phase == "recovering"


def test_without_the_veto_the_acknowledgement_leaves_the_alert_active(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("get_track_metrics", since=0.0, until=20.0)),
        tool_response(call("acknowledge_detection", alert_id="ai-9001", reason="same spoofing")),
    )
    rt, published, monitor = monitor_in_recovery(tmp_path, script)
    monitor.config = replace(monitor.config, recovery_ack_veto=False)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 20.0)]))
    assert not [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert rt.trace.records[0]["guardrail_rejections"] == []
    assert rt.state.alerts["ai-9001"].phase == "active"


def test_the_fallback_alert_is_active(tmp_path: Path) -> None:
    rt, published, monitor = monitor_in_recovery(tmp_path, Script("no tool call"))
    rt.state.alerts.clear()
    run(monitor.handle_batch([detection_event("raised", "det-0002", 20.0)]))
    [event] = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert event.payload["fallback"] is True and event.payload["phase"] == "active"


def test_faults_f3_with_the_recovering_alert_still_open(state: MonitorState) -> None:
    """`faults`: la alerta de la pérdida (`recovering`) sigue abierta cuando salta el silencio del
    GPS (F3), que lleva alerta propia (`SENSOR_FAULT`, `active`, sin `supersedes`). Las dos son
    «del GPS»; `recent_gps_alert` devuelve la primera abierta (la de la recuperación), así que un
    `ROUTE_DEVIATION` posterior no se veta por la alerta del silencio. Límite documentado."""
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 245.0, rule="GPS_DEGRADED", source="gps"))
    s.apply(alert("ai-6", ["det-1"], cause="GPS_JAMMING", severity="medium", phase="recovering"))
    s.apply(detection_event("raised", "det-8", 304.0, rule="SOURCE_SILENT", source="gps"))
    s.apply(alert("ai-8", ["det-8"], cause="SENSOR_FAULT", severity="medium"))
    s.apply(detection_event("raised", "det-9", 306.0))  # un ROUTE_DEVIATION
    assert s.recent_gps_alert(306.0).alert_id == "ai-6"
    facts = InvocationFacts(metrics=metrics(disagreed=True, step=67.9))
    assert ack(s, facts, alert_id="ai-6", detection="det-9").ok
    assert s.alerts["ai-8"].phase == "active"  # el silencio no es una recuperación


def test_the_new_rejection_messages_carry_data_but_no_names_or_copyable_phrases() -> None:
    """Condición de la Fase 14.2: los mensajes de la fase y del veto dan datos, pero ningún nombre
    de campo, de tool o de skill, ni `true`/`false`, ni una frase de 6 palabras que ya esté en los
    prompts o las skills (el 14B las copia a los textos de la alerta). Se mide con la propia
    `text_metrics`; el nombre de la causa sí va (hay que escribirlo)."""
    import importlib.util
    import sys

    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "text_metrics", repo / "tools" / "experiments" / "text_metrics.py"
    )
    assert spec and spec.loader
    tm = importlib.util.module_from_spec(spec)
    sys.modules["text_metrics"] = tm
    spec.loader.exec_module(tm)
    corpus = tm.static_corpus()

    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0))
    s.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING"))
    s.apply(detection_event("raised", "det-2", 9.0))
    both = checks(gps_alert_recent=True, gps_radar_disagreed=True)
    jump = InvocationFacts(metrics=metrics(disagreed=True, step=67.9))
    calm = InvocationFacts(metrics=metrics(disagreed=True, step=5.1))

    def publish(facts: InvocationFacts, **changes: Any) -> list[str]:
        args = alert_args(["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", checks=both)
        return check_publish_alert(
            {**args, **changes},
            as_of=10.0,
            state=s,
            index=index_with(**GOOD),
            seen_ids={"gps-000001", "gps-000002"},
            facts=facts,
            coherence=True,
            require_checks=True,
        ).errors

    messages = [
        *publish(jump, severity="high"),
        *publish(jump, phase="active"),
        *publish(calm, phase="recovering"),
        *ack(s, jump).errors,
        *ack(s, None).errors,
    ]
    s.apply(detection_event("raised", "det-3", 9.0, rule="SOURCE_SILENT", source="gps"))
    off_rule = publish(
        jump, detection_ids=["det-3"], cause="SENSOR_FAULT", supersedes=None, phase="recovering"
    )
    messages += [m for m in off_rule if m.startswith("phase")]
    assert len(messages) == 6 and all(messages)
    for message in messages:
        names, _enums, bools = tm.find_names(message)
        assert names == [] and bools == [], message
        assert tm.copied_spans(message, corpus) == [], message
