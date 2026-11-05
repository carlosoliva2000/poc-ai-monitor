"""Fase 15: `monitor.sensor_fault_per_source`. Un `SENSOR_FAULT` es de una sola fuente, la de las
detecciones que lo abrieron: lo que se le reconoce después no lo cambia, no se reconoce ni se
sustituye con detecciones de otra fuente y no cuenta como causa duplicada de otra fuente."""

from dataclasses import replace
from pathlib import Path

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
)
from test_coherence import check, checks, metrics
from test_monitor_state import ack, alert

from ai_module.agent.guardrails import (
    TAG_FOREIGN_FAULT,
    InvocationFacts,
    check_acknowledge,
)
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def battery_state(per_source: bool = True) -> MonitorState:
    """Una batería callada (`det-1` → `ai-1` `SENSOR_FAULT`) y una discrepancia GPS–radar nueva."""
    s = MonitorState(sensor_fault_per_source=per_source)
    s.apply(detection_event("raised", "det-1", 5.0, rule="SOURCE_SILENT", source="battery"))
    s.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT", severity="medium", t=6.0))
    s.apply(detection_event("raised", "det-2", 20.0, rule="SOURCE_DISCREPANCY"))
    return s


# --- Estado ---


def test_what_is_acknowledged_later_does_not_make_a_battery_fault_a_gps_alert() -> None:
    s = battery_state()
    s.apply(ack("ai-2", "det-2", "ai-1"))
    assert "det-2" in s.alerts["ai-1"].detection_ids  # sigue en la alerta
    assert not s.is_gps_alert(s.alerts["ai-1"])
    assert s.recent_gps_alert(25.0) is None
    assert s.fault_sources(s.alerts["ai-1"]) == {"battery"}


def test_the_old_behaviour_without_the_switch() -> None:
    s = battery_state(per_source=False)
    s.apply(ack("ai-2", "det-2", "ai-1"))
    assert s.is_gps_alert(s.alerts["ai-1"])  # el fallo de la Fase 14: la batería es «del GPS»
    assert not s.foreign_sensor_fault(s.alerts["ai-1"], "det-2")
    assert "SENSOR_FAULT of" not in s.describe_open_alerts()


def test_the_sources_of_a_sensor_fault_come_from_its_origin() -> None:
    s = MonitorState(sensor_fault_per_source=True)
    s.apply(detection_event("raised", "det-11", 5.0, rule="GPS_DEGRADED", source="gps"))
    s.apply(alert("ai-1", ["det-11"], cause="SENSOR_FAULT", t=6.0))
    assert s.fault_sources(s.alerts["ai-1"]) == {"gps"}
    assert s.is_gps_alert(s.alerts["ai-1"])
    s.apply(detection_event("raised", "det-12", 8.0, rule="SOURCE_SILENT", source="radar"))
    s.apply(alert("ai-2", ["det-12"], cause="SENSOR_FAULT", t=9.0))
    assert s.fault_sources(s.alerts["ai-2"]) == {"radar"}
    assert not s.is_gps_alert(s.alerts["ai-2"])  # un radar mudo no es una alerta del GPS


def test_a_superseding_alert_inherits_the_origin() -> None:
    s = battery_state()
    s.apply(alert("ai-2", ["det-2"], cause="GPS_SPOOFING", t=21.0))  # otra cadena
    assert s.alerts["ai-2"].opened_by == {"det-2"}
    s.apply(detection_event("raised", "det-3", 30.0, rule="SOURCE_SILENT", source="battery"))
    s.apply(alert("ai-3", ["det-3"], cause="SENSOR_FAULT", supersedes="ai-1", t=31.0))
    assert s.alerts["ai-3"].opened_by == {"det-1", "det-3"}


@pytest.mark.parametrize(
    ("rule", "source", "foreign"),
    [
        ("SOURCE_DISCREPANCY", None, True),
        ("ROUTE_DEVIATION", None, True),
        ("GPS_DEGRADED", "gps", True),
        ("SOURCE_SILENT", "gps", True),
        ("SOURCE_SILENT", "radar", True),
        ("SOURCE_SILENT", "battery", False),
    ],
)
def test_which_detections_are_foreign_to_a_battery_fault(rule, source, foreign) -> None:
    s = battery_state()
    s.apply(detection_event("raised", "det-30", 30.0, rule=rule, source=source))
    assert s.foreign_sensor_fault(s.alerts["ai-1"], "det-30") is foreign


def test_a_position_fault_covers_position_detections_and_gps_silence() -> None:
    s = MonitorState(sensor_fault_per_source=True)
    s.apply(detection_event("raised", "det-1", 5.0, rule="SOURCE_DISCREPANCY"))
    s.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT", t=6.0))
    for i, (rule, source) in enumerate((("ROUTE_DEVIATION", None), ("SOURCE_SILENT", "gps"))):
        s.apply(detection_event("raised", f"det-4{i}", 9.0, rule=rule, source=source))
        assert not s.foreign_sensor_fault(s.alerts["ai-1"], f"det-4{i}")
    s.apply(detection_event("raised", "det-50", 9.0, rule="SOURCE_SILENT", source="battery"))
    assert s.foreign_sensor_fault(s.alerts["ai-1"], "det-50")


def test_the_prompt_says_which_source_the_sensor_fault_is_about() -> None:
    s = battery_state()
    assert "ai-1 SENSOR_FAULT of the battery (medium" in s.describe_open_alerts()
    assert "SENSOR_FAULT of the battery (medium" in s.describe_alerts_detail()
    other = MonitorState(sensor_fault_per_source=True)
    other.apply(detection_event("raised", "det-60", 1.0, rule="ROUTE_DEVIATION"))
    other.apply(alert("ai-9", ["det-60"], cause="WIND", t=2.0))
    assert "WIND (" in other.describe_open_alerts()  # solo los SENSOR_FAULT llevan la fuente


# --- Guardrails ---


def publish(s: MonitorState, **changes):
    args = alert_args(["det-2"], checks=checks(gps_radar_disagreed=True), **changes)
    return check(args, s, InvocationFacts(metrics=metrics(disagreed=True)))


def test_a_battery_fault_cannot_be_superseded_by_a_gps_radar_discrepancy() -> None:
    verdict = publish(battery_state(), cause="GPS_SPOOFING", supersedes="ai-1")
    assert not verdict.ok and verdict.tag == TAG_FOREIGN_FAULT
    [error] = verdict.errors
    for data in ("ai-1", "SENSOR_FAULT", "battery", "det-2", "SOURCE_DISCREPANCY"):
        assert data in error
    assert "own alert" in error and "without supersedes" in error


def test_without_the_switch_the_battery_alert_can_still_be_superseded() -> None:
    verdict = publish(battery_state(per_source=False), cause="GPS_SPOOFING", supersedes="ai-1")
    assert verdict.ok


def test_a_new_sensor_fault_of_another_source_is_not_a_duplicate_cause() -> None:
    s = battery_state()
    ok = check_publish_alert_dup(s, cause="SENSOR_FAULT")
    assert ok.ok, ok.errors
    old = check_publish_alert_dup(battery_state(per_source=False), cause="SENSOR_FAULT")
    assert not old.ok and "is open: use supersedes ai-1" in old.errors[0]


def check_publish_alert_dup(s: MonitorState, **changes):
    from test_coherence import GOOD, index_with

    from ai_module.agent.guardrails import check_publish_alert

    args = alert_args(["det-2"], checks=checks(gps_radar_disagreed=True), **changes)
    return check_publish_alert(
        args,
        as_of=25.0,
        state=s,
        index=index_with(**GOOD),
        seen_ids={"gps-000001", "gps-000002"},
        facts=InvocationFacts(metrics=metrics(disagreed=True)),
        coherence=True,
        no_duplicate_cause=True,
    )


def test_the_same_source_still_counts_as_a_duplicate() -> None:
    s = MonitorState(sensor_fault_per_source=True)
    s.apply(detection_event("raised", "det-1", 5.0, rule="SOURCE_DISCREPANCY"))
    s.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT", t=6.0))
    s.apply(detection_event("raised", "det-2", 20.0, rule="ROUTE_DEVIATION"))
    verdict = check_publish_alert_dup(s, cause="SENSOR_FAULT")
    assert not verdict.ok and "ai-1 (SENSOR_FAULT) is open" in verdict.errors[0]


def acknowledge(s: MonitorState, detection: str, alert_id: str | None):
    return check_acknowledge(
        {"detection_ids": [detection], "alert_id": alert_id, "reason": "r"},
        state=s,
        unanswered={detection},
        pending={detection},
    )


def test_a_battery_fault_cannot_be_acknowledged_with_a_gps_radar_discrepancy() -> None:
    verdict = acknowledge(battery_state(), "det-2", "ai-1")
    assert not verdict.ok and verdict.tag == TAG_FOREIGN_FAULT
    assert "battery" in verdict.errors[0] and "own alert" in verdict.errors[0]
    assert acknowledge(battery_state(per_source=False), "det-2", "ai-1").ok


def test_acknowledging_without_an_alert_and_the_same_source_still_work() -> None:
    s = battery_state()
    assert acknowledge(s, "det-2", None).ok  # «no hace falta alerta»
    s.apply(detection_event("raised", "det-3", 21.0, rule="SOURCE_SILENT", source="battery"))
    assert acknowledge(s, "det-3", "ai-1").ok


def test_the_gps_recovery_is_decided_on_its_own_chain_next_to_the_battery_fault() -> None:
    """El caso de `demo-battery` a T+03:42: con la batería abierta y el engaño en su alerta, la
    recuperación sigue a la alerta del GPS y no a la de la batería."""
    s = battery_state()
    s.apply(alert("ai-2", ["det-2"], cause="GPS_SPOOFING", severity="high", t=21.0))
    s.apply(detection_event("raised", "det-4", 30.0))  # ROUTE_DEVIATION
    recent = s.recent_gps_alert(31.0)
    assert recent is not None and recent.alert_id == "ai-2"
    # y el estado del prompt dice la alerta del GPS, no la de la batería
    assert "ai-2 GPS_SPOOFING" in s.describe_gps_alert(31.0)


# --- Monitor ---


def test_the_fallback_is_unknown_when_only_a_foreign_sensor_fault_is_open(tmp_path: Path) -> None:
    rt, published = make_runtime(tmp_path, FakeLlm(Script(text_response("no sé"))), FakePlatform())
    seed_evidence(rt, "gps-000001", "gps-000002")
    rt.clock.observe(21.0)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, sensor_fault_per_source=True)
    rt.state = MonitorState(sensor_fault_per_source=True)
    rt.state.apply(detection_event("raised", "det-1", 5.0, rule="SOURCE_SILENT", source="battery"))
    rt.state.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT", t=6.0))
    event = detection_event("raised", "det-2", 20.0, rule="SOURCE_DISCREPANCY")
    run(monitor.handle_batch([event]))
    alerts = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert [(e.payload["cause"], e.payload["fallback"]) for e in alerts] == [("UNKNOWN", True)]
    assert call  # (import de ayuda usado en otros casos del fichero)


# --- Repetición de la prueba manual (`demo` con la batería callada a mano, 05/11/2026) ---


def replay_manual_run(per_source: bool):
    """Las llamadas de `inv-0004` y `inv-0005` de esa ejecución, contra el estado de entonces:
    T+03:12 el modelo propone `SENSOR_FAULT` para la discrepancia; T+03:42 propone
    `GPS_SPOOFING` `high` `active` para la desviación de la ruta (era lo correcto)."""
    s = battery_state(per_source)
    first = check_publish_alert_dup(s, cause="SENSOR_FAULT", confidence=0.6)
    if first.ok:  # con el interruptor, la alerta nueva se publica
        s.apply(alert("ai-2", ["det-2"], cause="SENSOR_FAULT", severity="medium", t=21.0))
    else:  # sin él, el rechazo empuja a reconocerla dentro de la alerta de la batería
        s.apply(ack("ai-3", "det-2", "ai-1"))
    s.apply(detection_event("raised", "det-3", 30.0))  # ROUTE_DEVIATION de la recuperación
    recovery = alert_args(
        ["det-3"],
        cause="GPS_SPOOFING",
        severity="high",
        confidence=0.8,
        checks=checks(gps_alert_recent=True, gps_radar_disagreed=True),
    )
    from test_coherence import GOOD, index_with

    from ai_module.agent.guardrails import check_publish_alert

    verdict = check_publish_alert(
        recovery,
        as_of=31.0,
        state=s,
        index=index_with(**GOOD),
        seen_ids={"gps-000001", "gps-000002"},
        facts=InvocationFacts(metrics=metrics(disagreed=True, step=67.9)),
        coherence=True,
    )
    return first, s, verdict


def test_replay_without_the_switch_reproduces_the_mixed_chain() -> None:
    first, s, verdict = replay_manual_run(per_source=False)
    assert not first.ok and "ai-1 (SENSOR_FAULT) is open: use supersedes ai-1" in first.errors[0]
    assert s.recent_gps_alert(31.0).alert_id == "ai-1"  # la batería es «la alerta del GPS»
    assert any("expected cause SENSOR_FAULT and supersedes ai-1" in e for e in verdict.errors)


def test_replay_with_the_switch_keeps_the_battery_and_the_discrepancy_apart() -> None:
    first, s, verdict = replay_manual_run(per_source=True)
    assert first.ok  # la discrepancia tiene alerta propia
    assert s.alerts["ai-1"].status.value == "open" and s.alerts["ai-1"].detection_ids == {"det-1"}
    recent = s.recent_gps_alert(31.0)
    assert recent.alert_id == "ai-2"  # la recuperación sigue a la alerta de la discrepancia
    assert any("supersedes ai-2" in e for e in verdict.errors)
    assert not any("ai-1" in e for e in verdict.errors)  # y nunca a la de la batería
