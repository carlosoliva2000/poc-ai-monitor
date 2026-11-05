"""Fase 14.4: `monitor.fill_link_anomalous`. Si el modelo miró el enlace y deja
`checks.link_anomalous` a `null` (o lo omite), el módulo pone el valor esperado; un valor distinto
se sigue rechazando y, sin haber mirado el enlace, no se rellena nada."""

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
from test_coherence import RUNS, WIND_METRICS, checks, link_events

from ai_module.agent.guardrails import InvocationFacts, fill_link_anomalous
from ai_module.monitor import Monitor
from poc_contracts.enums import EventType


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


NORMAL = link_events("nominal", 10, 35)
HIJACKED = link_events("hijack", 310, 338)


def raw(**link: Any) -> dict[str, Any]:
    return {"cause": "UNKNOWN", "checks": {"link_checked": True, **link}}


def test_fills_a_null_after_looking_at_the_link() -> None:
    for events, want in ((NORMAL, False), (HIJACKED, True)):
        facts = InvocationFacts(link_events=events)
        filled, value = fill_link_anomalous(raw(link_anomalous=None), facts)
        assert value is want and filled["checks"]["link_anomalous"] is want


def test_fills_an_omitted_field() -> None:
    filled, value = fill_link_anomalous(raw(), InvocationFacts(link_events=NORMAL))
    assert value is False and filled["checks"]["link_anomalous"] is False


def test_does_not_touch_a_declared_value() -> None:
    facts = InvocationFacts(link_events=NORMAL)
    for declared in (True, False):
        original = raw(link_anomalous=declared)
        assert fill_link_anomalous(original, facts) == (original, None)


def test_does_nothing_without_looking_at_the_link_or_without_checks() -> None:
    original = raw(link_anomalous=None)
    assert fill_link_anomalous(original, InvocationFacts()) == (original, None)
    no_checks = {"cause": "UNKNOWN"}
    assert fill_link_anomalous(no_checks, InvocationFacts(link_events=NORMAL)) == (no_checks, None)


def test_the_original_call_is_not_modified() -> None:
    original = raw(link_anomalous=None)
    fill_link_anomalous(original, InvocationFacts(link_events=NORMAL))
    assert original["checks"]["link_anomalous"] is None


# --- En el monitor ---


def run_alert(tmp_path: Path, events: list[dict] | None, declared: dict[str, Any], **switches):
    """Una invocación: pide las métricas (y el enlace si `events`) y publica con esos checks."""
    platform = FakePlatform(
        {"get_track_metrics": WIND_METRICS, "get_events": {"events": events or []}}
    )
    alert = alert_args(
        ["det-0001"],
        cause="UNKNOWN",
        severity="low",
        confidence=0.3,
        checks=checks(wind_notable=True, wind_with_drift=True, **declared),
    )
    steps = [tool_response(call("get_track_metrics", since=0.0, until=20.0))]
    if events is not None:
        steps.append(tool_response(call("get_events", source="link", last_n=6)))
    steps.append(tool_response(call("publish_alert", **alert)))
    llm = FakeLlm(Script(*steps, tool_response(call("publish_alert", **alert))))
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, **switches)
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    alerts = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    return rt.trace.records[0], alerts


def test_switch_on_fills_the_null_without_a_rejection(tmp_path: Path) -> None:
    declared = {"link_checked": True, "link_anomalous": None}
    trace, alerts = run_alert(tmp_path, NORMAL, declared, fill_link_anomalous=True)
    assert trace["guardrail_rejections"] == []
    assert alerts[0].payload["checks"]["link_anomalous"] is False
    assert trace["module_filled"] == [
        {"tool": "publish_alert", "field": "checks.link_anomalous", "value": False}
    ]
    assert trace["expected_checks"][alerts[0].payload["alert_id"]]["link_anomalous"] is False


def test_switch_off_rejects_the_null_as_before(tmp_path: Path) -> None:
    declared = {"link_checked": True, "link_anomalous": None}
    trace, alerts = run_alert(tmp_path, NORMAL, declared, fill_link_anomalous=False)
    assert any(
        "checks.link_anomalous = null does not match" in e
        for r in trace["guardrail_rejections"]
        for e in r["errors"]
    )
    assert trace["module_filled"] == []


def test_a_wrong_value_is_still_rejected_with_the_switch_on(tmp_path: Path) -> None:
    declared = {"link_checked": True, "link_anomalous": True}  # el enlace es normal
    trace, _ = run_alert(tmp_path, NORMAL, declared, fill_link_anomalous=True)
    [first, *_] = trace["guardrail_rejections"]
    assert "checks.link_anomalous = true does not match" in first["errors"][0]
    assert trace["module_filled"] == []


def test_not_looking_at_the_link_fills_nothing(tmp_path: Path) -> None:
    declared = {"link_checked": False, "link_anomalous": None}
    trace, alerts = run_alert(tmp_path, None, declared, fill_link_anomalous=True)
    assert trace["guardrail_rejections"] == []
    assert alerts[0].payload["checks"]["link_anomalous"] is None
    assert trace["module_filled"] == []


def test_link_checked_true_without_looking_is_still_rejected(tmp_path: Path) -> None:
    declared = {"link_checked": True, "link_anomalous": None}
    trace, _ = run_alert(tmp_path, None, declared, fill_link_anomalous=True)
    assert any(
        "checks.link_checked = true does not match" in e
        for r in trace["guardrail_rejections"]
        for e in r["errors"]
    )


def test_looking_and_declaring_link_checked_false_is_still_rejected(tmp_path: Path) -> None:
    declared = {"link_checked": False, "link_anomalous": None}
    trace, _ = run_alert(tmp_path, NORMAL, declared, fill_link_anomalous=True)
    assert any(
        "checks.link_checked = false does not match" in e
        for r in trace["guardrail_rejections"]
        for e in r["errors"]
    )


def test_the_frozen_assets_have_it_off_and_the_current_ones_declare_it() -> None:
    from ai_module.agent.assets import Assets

    root = RUNS.parent
    assert Assets(root / "agent-assets-v13").agent("monitor").fill_link_anomalous is False


def test_eval_counts_the_rejections_and_the_fills(tmp_path: Path) -> None:
    from ai_module.evaluate import agent_stats

    declared = {"link_checked": True, "link_anomalous": None}
    off, _ = run_alert(tmp_path / "off", NORMAL, declared, fill_link_anomalous=False)
    on, _ = run_alert(tmp_path / "on", NORMAL, declared, fill_link_anomalous=True)
    assert agent_stats([off])["monitor"]["link_null_rejections"] >= 1
    assert agent_stats([off])["monitor"]["link_filled"] == 0
    assert agent_stats([on])["monitor"]["link_null_rejections"] == 0
    assert agent_stats([on])["monitor"]["link_filled"] == 1
