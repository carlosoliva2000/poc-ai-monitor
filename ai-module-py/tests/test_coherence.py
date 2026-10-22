"""Hechos calculados, `checks` y guardrail de coherencia de `publish_alert`, y los interruptores
del monitor (`tool_choice`, `final_iteration_response_tools_only`, `require_checks`,
`coherence_guardrail`, `computed_facts`)."""

import json
from dataclasses import replace
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
from test_guardrails import GOOD, index_with
from test_monitor_state import alert, closed

from ai_module.agent.guardrails import (
    InvocationFacts,
    check_publish_alert,
    expected_checks,
    link_is_anomalous,
)
from ai_module.agent.tools import strip_computed_facts
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType

RUNS = Path(__file__).resolve().parents[2] / "runs"


def metrics(
    *, notable=False, with_drift=False, disagreed=False, step=5.0, mean=1.9, gust=4.1, drift=62.1
) -> dict[str, Any]:
    """Un resultado de `get_track_metrics` con los hechos calculados."""
    return {
        "since": 308.0,
        "until": 338.0,
        "gps_radar_distance_m": {"mean": 5.8, "max": 12.4, "trend": "stable"},
        "wind": {
            "mean_speed_mps": mean,
            "max_gust_mps": gust,
            "from_deg": 303.9,
            "wind_to_deg": 123.9,
            "drift_vs_wind_deg": drift,
            "notable": notable,
            "with_drift": with_drift,
            "samples": 3,
            "last_event_id": "met-0033",
        },
        "gps_radar": {"disagreed": disagreed},
        "gps_max_step_m": step,
    }


def checks(**changes: Any) -> dict[str, Any]:
    return {**NO_CHECKS, **changes}


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


@pytest.fixture
def state() -> MonitorState:
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0))  # ROUTE_DEVIATION
    return s


def check(args: dict, state: MonitorState, facts: InvocationFacts, *, require=True, coherence=True):
    return check_publish_alert(
        args,
        as_of=10.0,
        state=state,
        index=index_with(**GOOD),
        seen_ids={"gps-000001", "gps-000002"},
        facts=facts,
        coherence=coherence,
        require_checks=require,
    )


# --- Enlace anómalo ---


def link_events(sc: str, since: float, until: float) -> list[dict]:
    out = []
    for line in (RUNS / sc / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["type"] == "LinkStatus" and since <= e["sim_time"] <= until:
            out.append(e["payload"])
    return out


def test_link_anomaly_on_real_flights() -> None:
    assert link_is_anomalous(link_events("secuestro", 310, 338))  # otro controller_id
    assert not link_is_anomalous(link_events("secuestro", 310, 330))  # aún normal
    for start in range(10, 500, 5):  # ninguna ventana de 6 enlaces de un vuelo normal
        window = link_events("nominal", start, start + 25)
        assert not link_is_anomalous(window), start
    assert link_is_anomalous(
        [
            {"controller_id": "A", "rssi_dbm": -60, "latency_ms": 40},
            {"controller_id": "A", "rssi_dbm": -75, "latency_ms": 40},
        ]
    )
    assert link_is_anomalous(
        [
            {"controller_id": "A", "rssi_dbm": -60, "latency_ms": 40},
            {"controller_id": "A", "rssi_dbm": -61, "latency_ms": 120},
        ]
    )
    assert not link_is_anomalous([])


# --- (a) los checks coinciden con las tools y el estado ---


def test_expected_checks_come_from_tools_and_state(state: MonitorState) -> None:
    facts = InvocationFacts(metrics=metrics(notable=True, with_drift=True, disagreed=True))
    want = expected_checks(facts, state, 10.0)
    assert want == checks(wind_notable=True, wind_with_drift=True, gps_radar_disagreed=True)
    state.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING"))
    assert expected_checks(facts, state, 10.0)["gps_alert_recent"] is True
    with_link = InvocationFacts(link_events=link_events("secuestro", 310, 338))
    assert expected_checks(with_link, state, 10.0)["link_checked"] is True
    assert expected_checks(with_link, state, 10.0)["link_anomalous"] is True


def test_checks_must_match_the_tool_results(state: MonitorState) -> None:
    facts = InvocationFacts(metrics=metrics())  # viento flojo
    ok = check(alert_args(["det-1"]), state, facts)
    assert ok.ok
    lie = alert_args(["det-1"], checks=checks(wind_notable=True))
    verdict = check(lie, state, facts)
    assert any(
        "checks.wind_notable = true no coincide con get_track_metrics (false)" in e
        for e in verdict.errors
    )
    # sin haber llamado a get_track_metrics, declarar un hecho de esa tool se rechaza
    verdict = check(lie, state, InvocationFacts())
    assert any("no has llamado a get_track_metrics" in e for e in verdict.errors)
    # estado: declarar una alerta del GPS que no existe
    verdict = check(alert_args(["det-1"], checks=checks(gps_alert_recent=True)), state, facts)
    assert any("gps_alert_recent" in e and "estado" in e for e in verdict.errors)
    # enlace: declarar que se miró sin haberlo mirado, o no declararlo habiéndolo mirado
    verdict = check(alert_args(["det-1"], checks=checks(link_checked=True)), state, facts)
    assert any("link_checked" in e for e in verdict.errors)
    looked = InvocationFacts(metrics=metrics(), link_events=link_events("nominal", 10, 35))
    verdict = check(alert_args(["det-1"]), state, looked)
    assert any("link_checked" in e for e in verdict.errors)
    good = alert_args(["det-1"], checks=checks(link_checked=True, link_anomalous=False))
    assert check(good, state, looked).ok


def test_missing_checks_are_rejected_when_required(state: MonitorState) -> None:
    args = alert_args(["det-1"])
    del args["checks"]
    assert any("falta `checks`" in e for e in check(args, state, InvocationFacts()).errors)
    assert check(args, state, InvocationFacts(), require=False).ok


# --- (b) la causa es coherente ---


def test_wind_needs_a_notable_wind_that_agrees_with_the_drift(state: MonitorState) -> None:
    wind = alert_args(
        ["det-1"], cause="WIND", checks=checks(wind_notable=True, wind_with_drift=True)
    )
    assert check(wind, state, InvocationFacts(metrics=metrics(notable=True, with_drift=True))).ok
    weak = check(alert_args(["det-1"], cause="WIND"), state, InvocationFacts(metrics=metrics()))
    assert weak.errors == [
        "WIND exige viento notable: media 1,9 y racha 4,1 no lo son; mira el enlace (paso 5)"
    ]
    against = check(
        alert_args(["det-1"], cause="WIND", checks=checks(wind_notable=True)),
        state,
        InvocationFacts(metrics=metrics(notable=True, with_drift=False, drift=101.6)),
    )
    assert against.errors == [
        "WIND exige que la deriva vaya a favor del viento: difieren 101,6° (máximo 45°); "
        "mira el enlace (paso 5)"
    ]
    none = check(alert_args(["det-1"], cause="WIND"), state, InvocationFacts())
    assert any("WIND exige llamar antes a get_track_metrics" in e for e in none.errors)


def test_hijack_needs_the_link_checked(state: MonitorState) -> None:
    hijack = alert_args(["det-1"], cause="HIJACK", severity="high")
    verdict = check(hijack, state, InvocationFacts(metrics=metrics()))
    assert any("HIJACK exige haber mirado el enlace" in e for e in verdict.errors)
    looked = InvocationFacts(link_events=link_events("secuestro", 310, 338))
    ok = alert_args(
        ["det-1"],
        cause="HIJACK",
        severity="high",
        checks=checks(link_checked=True, link_anomalous=True),
    )
    assert check(ok, state, looked).ok


def test_gps_recovery_is_exclusive_to_the_cause_of_the_recent_gps_alert(
    state: MonitorState,
) -> None:
    state.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING"))
    state.apply(detection_event("raised", "det-2", 9.0))  # el RD de la recuperación
    facts = InvocationFacts(metrics=metrics(disagreed=True))
    both = checks(gps_alert_recent=True, gps_radar_disagreed=True)
    ok = alert_args(
        ["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", severity="medium", checks=both
    )
    assert check(ok, state, facts).ok
    jump = alert_args(
        ["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", checks=checks(gps_alert_recent=True)
    )
    assert check(jump, state, InvocationFacts(metrics=metrics(disagreed=False, step=68.0))).ok
    expected = (
        "Es la recuperación del GPS_SPOOFING de ai-1: publica cause GPS_SPOOFING, "
        "severity medium y supersedes ai-1"
    )
    for cause in ("GPS_JAMMING", "SENSOR_FAULT", "HIJACK", "WIND", "UNKNOWN"):
        other = alert_args(["det-2"], cause=cause, supersedes="ai-1", checks=both)
        assert expected in check(other, state, facts).errors, cause
    no_chain = alert_args(["det-2"], cause="GPS_SPOOFING", checks=both)
    assert expected in check(no_chain, state, facts).errors  # sin supersedes tampoco vale
    # sin los hechos de la recuperación (GPS y radar coinciden, sin salto) no es recuperación:
    # ninguna causa del GPS vale
    calm = InvocationFacts(metrics=metrics(step=14.8))
    gps_cause = alert_args(["det-2"], cause="GPS_JAMMING", checks=checks(gps_alert_recent=True))
    assert any("gps_max_step_m=14,8" in e for e in check(gps_cause, state, calm).errors)


def test_exclusive_recovery_when_the_gps_alert_is_already_closed(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))
    state.apply(detection_event("cleared", "det-1", 8.0))
    state.apply(closed("ai-1", t=9.0))
    state.apply(detection_event("raised", "det-2", 10.0))
    facts = InvocationFacts(metrics=metrics(step=90.0))
    good = alert_args(["det-2"], cause="GPS_JAMMING", checks=checks(gps_alert_recent=True))
    assert check(good, state, facts).ok  # cerrada: sin supersedes
    bad = alert_args(
        ["det-2"], cause="GPS_JAMMING", supersedes="ai-1", checks=checks(gps_alert_recent=True)
    )
    # una alerta cerrada no se puede sustituir (la regla de supersedes ya lo rechaza)
    assert any("no es una alerta abierta" in e for e in check(bad, state, facts).errors)


def test_gps_recovery_must_be_published_with_severity_medium(state: MonitorState) -> None:
    """Además de la causa y del `supersedes`, la recuperación se publica con `severity medium`."""
    state.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING"))  # severidad high
    state.apply(detection_event("raised", "det-2", 9.0))
    facts = InvocationFacts(metrics=metrics(disagreed=True))
    both = checks(gps_alert_recent=True, gps_radar_disagreed=True)
    expected = (
        "Es la recuperación del GPS_SPOOFING de ai-1: publica cause GPS_SPOOFING, "
        "severity medium y supersedes ai-1"
    )
    for severity in ("high", "low"):
        # con `high` (la de la alerta) la regla de la recuperación pasa por delante de «No cambia
        # nada»: si no, el rechazo mandaría reconocer y la recuperación perdería su `supersedes`
        wrong = alert_args(
            ["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", severity=severity, checks=both
        )
        assert check(wrong, state, facts).errors == [expected], severity
    ok = alert_args(
        ["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", severity="medium", checks=both
    )
    assert check(ok, state, facts).ok


def test_gps_recovery_with_a_closed_alert_also_needs_severity_medium(state: MonitorState) -> None:
    state.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))
    state.apply(detection_event("cleared", "det-1", 8.0))
    state.apply(closed("ai-1", t=9.0))
    state.apply(detection_event("raised", "det-2", 10.0))
    facts = InvocationFacts(metrics=metrics(step=90.0))
    high = alert_args(
        ["det-2"], cause="GPS_JAMMING", severity="high", checks=checks(gps_alert_recent=True)
    )
    assert check(high, state, facts).errors == [
        "Es la recuperación del GPS_JAMMING de ai-1: publica cause GPS_JAMMING, severity medium "
        "y sin supersedes (ai-1 ya está cerrada)"
    ]


def test_recovery_of_a_gps_alert_that_is_already_medium_is_an_acknowledgement(
    state: MonitorState,
) -> None:
    """La regla excluyente pide `severity medium` con `supersedes`; si la alerta ya es de esa
    severidad no cambia nada, y las dos reglas no pueden contradecirse: se dice que reconozca."""
    state.apply(alert("ai-1", ["det-1"], cause="GPS_SPOOFING", severity="medium"))
    state.apply(detection_event("raised", "det-2", 9.0))
    facts = InvocationFacts(metrics=metrics(disagreed=True))
    both = checks(gps_alert_recent=True, gps_radar_disagreed=True)
    same = alert_args(
        ["det-2"], cause="GPS_SPOOFING", supersedes="ai-1", severity="medium", checks=both
    )
    assert check(same, state, facts).errors == [
        "Es la recuperación del GPS_SPOOFING de ai-1, que ya es medium: no cambia nada, "
        "usa acknowledge_detection con alert_id ai-1"
    ]
    other = alert_args(["det-2"], cause="SENSOR_FAULT", supersedes="ai-1", checks=both)
    assert check(other, state, facts).errors == [
        "Es la recuperación del GPS_SPOOFING de ai-1, que ya es medium: no cambia nada, "
        "usa acknowledge_detection con alert_id ai-1"
    ]


def test_gps_recovery_without_a_recent_gps_alert_is_rejected(state: MonitorState) -> None:
    args = alert_args(
        ["det-1"], cause="GPS_JAMMING", severity="high", checks=checks(gps_radar_disagreed=True)
    )
    verdict = check(args, state, InvocationFacts(metrics=metrics(disagreed=True)))
    assert any("no la hay" in e for e in verdict.errors)


def test_gps_causes_on_other_rules_are_not_recoveries(state: MonitorState) -> None:
    state.apply(detection_event("raised", "det-3", 9.0, rule="SOURCE_DISCREPANCY"))
    spoof = alert_args(
        ["det-3"], cause="GPS_SPOOFING", severity="high", checks=checks(gps_radar_disagreed=True)
    )
    assert check(spoof, state, InvocationFacts(metrics=metrics(disagreed=True))).ok


def test_gps_alert_recent_window() -> None:
    s = MonitorState()
    s.apply(detection_event("raised", "det-1", 5.0, rule="GPS_DEGRADED", source="gps"))
    s.apply(alert("ai-1", ["det-1"], cause="SENSOR_FAULT"))
    assert s.gps_alert_recent(10.0)  # abierta
    s.apply(detection_event("cleared", "det-1", 40.0))
    s.apply(closed("ai-1", t=50.0))
    assert s.gps_alert_recent(110.0) and not s.gps_alert_recent(110.5)  # 60 s
    radar = MonitorState()
    radar.apply(detection_event("raised", "det-9", 5.0, rule="SOURCE_SILENT", source="radar"))
    radar.apply(alert("ai-9", ["det-9"], cause="SENSOR_FAULT"))
    assert not radar.gps_alert_recent(10.0)  # un SENSOR_FAULT del radar no es del GPS


# --- strip_computed_facts ---


def test_strip_computed_facts_removes_only_the_computed_fields() -> None:
    full = metrics(notable=True, with_drift=True, disagreed=True)
    stripped = strip_computed_facts(full)
    assert "gps_radar" not in stripped and "gps_max_step_m" not in stripped
    assert set(stripped["wind"]) == {
        "mean_speed_mps",
        "max_gust_mps",
        "from_deg",
        "samples",
        "last_event_id",
    }
    assert "gps_radar" in full  # el original no se toca
    assert strip_computed_facts({"wind": None})["wind"] is None


# --- interruptores en el monitor ---

WIND_METRICS = metrics(notable=True, with_drift=True, mean=7.2, gust=9.7, drift=3.4)


def monitor_with(tmp_path: Path, policy: Any, **switches: Any):
    platform = FakePlatform({"get_track_metrics": WIND_METRICS})
    llm = FakeLlm(policy)
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, **switches)
    return rt, published, monitor, llm


def wind_script(**alert_changes: Any) -> Script:
    wind = alert_args(
        ["det-0001"],
        cause="WIND",
        severity="low",
        confidence=0.8,
        checks=checks(wind_notable=True, wind_with_drift=True),
    )
    wind.update(alert_changes)
    return Script(
        tool_response(call("get_track_metrics", since=0.0, until=20.0)),
        tool_response(call("publish_alert", **wind)),
    )


def responses(published: list) -> list:
    return [e for e in published if e.type == EventType.ANOMALY_DETECTED]


def test_default_switches_are_all_on_and_recorded_in_the_trace(tmp_path: Path) -> None:
    rt, published, monitor, llm = monitor_with(tmp_path, wind_script())
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    [alert_event] = responses(published)
    assert alert_event.payload["cause"] == "WIND"
    assert alert_event.payload["checks"] == checks(wind_notable=True, wind_with_drift=True)
    assert rt.trace.records[0]["aids"] == {
        "tool_choice": "required",
        "final_iteration_response_tools_only": True,
        "require_checks": True,
        "coherence_guardrail": True,
        "computed_facts": True,
    }


def test_the_model_never_sees_the_event_id_of_a_detection(tmp_path: Path) -> None:
    rt, published, monitor, llm = monitor_with(tmp_path, wind_script())
    event = detection_event("updated", "det-0001", 20.0)
    rt.state.apply(detection_event("raised", "det-0001", 5.0))
    run(monitor.handle_batch([event]))
    prompt = llm.requests[0]["messages"][1]["content"]
    assert event.event_id not in prompt and '"event_id"' not in prompt
    assert '"detection_id":"det-0001"' in prompt


def test_cleared_prompt_fixes_the_window_from_the_start_of_the_detection(tmp_path: Path) -> None:
    rt, _, monitor, llm = monitor_with(tmp_path, Script("x"))
    rt.state.apply(detection_event("raised", "det-0001", 106.0))
    rt.state.apply(alert("ai-0001", ["det-0001"]))
    rt.clock.observe(156.0)
    run(monitor.handle_batch([detection_event("cleared", "det-0001", 156.0)]))
    prompt = llm.requests[0]["messages"][1]["content"]
    assert "`since` = 106 y `until` = 156" in prompt and "una sola vez" in prompt


def test_coherence_guardrail_rejects_and_the_switch_turns_it_off(tmp_path: Path) -> None:
    bad = alert_args(["det-0001"], cause="WIND", severity="low")  # checks en falso
    script = Script(
        tool_response(call("get_track_metrics", since=0.0, until=20.0)),
        tool_response(call("publish_alert", **bad)),
    )
    rt, published, monitor, _ = monitor_with(tmp_path, script)
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    assert rt.trace.records[0]["guardrail_rejections"][0]["errors"][0].startswith(
        "checks.wind_notable"
    )
    reset_ids()
    rt, published, monitor, _ = monitor_with(
        tmp_path, Script(tool_response(call("publish_alert", **bad))), coherence_guardrail=False
    )
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    assert responses(published)[0].payload["cause"] == "WIND"  # sin guardrail, pasa
    assert rt.trace.records[0]["aids"]["coherence_guardrail"] is False


def test_require_checks_switch_changes_the_schema_and_the_requirement(tmp_path: Path) -> None:
    on = monitor_with(tmp_path, Script(text_response("x")))
    run(on[2].handle_batch([detection_event("raised", "det-0001", 20.0)]))
    publish = next(
        t for t in on[3].requests[0]["tools"] if t["function"]["name"] == "publish_alert"
    )
    assert "checks" in publish["function"]["parameters"]["required"]
    assert publish["function"]["parameters"]["required"][0] == "checks"
    props = list(publish["function"]["parameters"]["properties"])
    assert props.index("checks") < props.index("cause")  # `checks` antes de `cause`
    reset_ids()
    no_checks = alert_args(["det-0001"])
    del no_checks["checks"]
    off = monitor_with(
        tmp_path, Script(tool_response(call("publish_alert", **no_checks))), require_checks=False
    )
    run(off[2].handle_batch([detection_event("raised", "det-0001", 20.0)]))
    publish = next(
        t for t in off[3].requests[0]["tools"] if t["function"]["name"] == "publish_alert"
    )
    assert "checks" not in publish["function"]["parameters"]["required"]
    assert "checks" in publish["function"]["parameters"]["properties"]
    assert responses(off[1])[0].payload["checks"] is None  # se publica sin checks
    # el esquema original no se ha modificado
    assert (
        "checks"
        in on[0].assets.tool_schemas(["publish_alert"])[0]["function"]["parameters"]["required"]
    )


def test_with_checks_off_the_coherence_rules_still_use_the_tool_results(tmp_path: Path) -> None:
    weak = metrics()
    platform = FakePlatform({"get_track_metrics": weak})
    llm = FakeLlm(
        Script(
            tool_response(call("get_track_metrics", since=0.0, until=20.0)),
            tool_response(
                call(
                    "publish_alert",
                    **{
                        k: v
                        for k, v in alert_args(["det-0001"], cause="WIND", severity="low").items()
                        if k != "checks"
                    },
                )
            ),
        )
    )
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, require_checks=False)
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    assert (
        "WIND exige viento notable: media 1,9 y racha 4,1"
        in (rt.trace.records[0]["guardrail_rejections"][0]["errors"][0])
    )


def test_computed_facts_off_hides_the_fields_from_the_model_but_not_from_the_guardrail(
    tmp_path: Path,
) -> None:
    rt, published, monitor, llm = monitor_with(tmp_path, wind_script(), computed_facts=False)
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    shown = next(m for m in llm.requests[1]["messages"] if m["role"] == "tool")["content"]
    result = json.loads(shown)
    assert "gps_radar" not in result and "gps_max_step_m" not in result
    assert "notable" not in result["wind"] and "drift_vs_wind_deg" not in result["wind"]
    assert result["wind"]["mean_speed_mps"] == 7.2
    assert responses(published)[0].payload["cause"] == "WIND"  # el guardrail conoce los hechos
    assert rt.trace.records[0]["aids"]["computed_facts"] is False
    # con los hechos activados el modelo sí los ve
    reset_ids()
    rt, published, monitor, llm = monitor_with(tmp_path, wind_script())
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    full = json.loads(
        next(m for m in llm.requests[1]["messages"] if m["role"] == "tool")["content"]
    )
    assert full["wind"]["notable"] is True and full["gps_radar"] == {"disagreed": False}


def test_tool_choice_switch(tmp_path: Path) -> None:
    for choice in ("required", "auto"):
        reset_ids()
        rt, _, monitor, llm = monitor_with(tmp_path, wind_script(), tool_choice=choice)
        run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
        assert all(r["sampling"]["tool_choice"] == choice for r in llm.requests)
        assert rt.trace.records[0]["aids"]["tool_choice"] == choice


def test_final_iteration_switch(tmp_path: Path) -> None:
    for only in (True, False):
        reset_ids()
        rt, _, monitor, llm = monitor_with(
            tmp_path,
            Script(tool_response(call("get_events", source="gps"))),
            final_iteration_response_tools_only=only,
        )
        monitor.config = replace(monitor.config, max_iterations=3)
        run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
        last = [t["function"]["name"] for t in llm.requests[-1]["tools"]]
        assert (last == ["publish_alert", "acknowledge_detection", "close_alert"]) is only
        assert rt.trace.records[0]["aids"]["final_iteration_response_tools_only"] is only


def test_until_as_text_is_capped_too() -> None:
    from ai_module.agent.tools import cap_until

    assert cap_until("get_events", {"source": "gps", "until": "9999"}, 20.0)["until"] == 20.0
    assert cap_until("get_events", {"source": "gps", "until": "3"}, 20.0)["until"] == "3"
    assert cap_until("get_track_metrics", {"since": 1, "until": 99.0}, 20.0)["until"] == 20.0
    assert cap_until("get_events", {"source": "gps", "until": "pronto"}, 20.0)["until"] == "pronto"


def test_ephemeral_events_are_not_valid_evidence() -> None:
    from ai_module.agent.guardrails import EventIndex
    from poc_contracts.envelope import EventDraft

    index = EventIndex()
    index.add(
        EventDraft(
            event_id="act-0042",
            topic="citadel.pub.evt.ai.agent.AgentActivity.v1",
            type=EventType.AGENT_ACTIVITY,
            source="ai-module",
            asset=None,
            sim_time=1.0,
            event_time="2026-10-20T10:00:00Z",
            ephemeral=True,
            payload={
                "agent": "monitor",
                "state": "started",
                "invocation_id": "inv-1",
                "causation_id": None,
            },  # fmt: skip
        )
    )
    assert index.get("act-0042") is None


def test_a_wrong_cause_on_a_recovery_with_a_closed_gps_alert_says_there_is_no_supersedes(
    state: MonitorState,
) -> None:
    state.apply(alert("ai-1", ["det-1"], cause="GPS_JAMMING"))
    state.apply(detection_event("cleared", "det-1", 8.0))
    state.apply(closed("ai-1", t=9.0))
    state.apply(detection_event("raised", "det-2", 10.0))
    facts = InvocationFacts(metrics=metrics(step=90.0))
    wrong = alert_args(["det-2"], cause="HIJACK", checks=checks(gps_alert_recent=True))
    assert (
        "Es la recuperación del GPS_JAMMING de ai-1: publica cause GPS_JAMMING, severity medium "
        "y sin supersedes (ai-1 ya está cerrada)"
    ) in check(wrong, state, facts).errors
