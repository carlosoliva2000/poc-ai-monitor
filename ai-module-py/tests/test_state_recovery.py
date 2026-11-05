"""Fase 14.3: la línea de estado `recovery_data` dice como dato si el GPS ha saltado.

El módulo pide las métricas a la plataforma antes de la primera llamada al modelo solo ante un
`ROUTE_DEVIATION` con la alerta del GPS abierta y activa; la línea da la alerta, su causa, el salto
y el id al que sustituye, sin frases que copiar; los guardrails no cambian y se cuenta aparte
cuando el guardrail, con la ventana que pidió el modelo, no veía el salto."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    call,
    detection_event,
    make_runtime,
    reset_ids,
    run,
    seed_evidence,
    tool_response,
)
from test_monitor_state import alert, closed

from ai_module.agent.assets import Assets
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState

ASSETS = Assets()
STATE_PREFIX = "- Recent GPS alert (open or closed ≤ 60 s ago): "


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def spoofing_alert(state: MonitorState, phase: str = "active") -> None:
    state.apply(detection_event("raised", "det-0001", 5.0, rule="SOURCE_DISCREPANCY"))
    state.apply(alert("ai-0008", ["det-0001"], cause="GPS_SPOOFING", phase=phase))


def monitor_with(tmp_path: Path, results: dict, policy=None, state_line: str = "recovery_data"):
    platform = FakePlatform(results)
    llm = FakeLlm(policy or Script("x"))
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    monitor = Monitor(rt)
    # la llamada del módulo para la fase (Fase 14.4) es otra ayuda: estas pruebas son de la línea
    monitor.config = replace(monitor.config, state_line=state_line, recovery_jump_from_module=False)
    return rt, platform, monitor, llm


def prompt_line(llm: FakeLlm) -> str:
    content = llm.requests[0]["messages"][1]["content"]
    return next(x for x in content.splitlines() if x.startswith(STATE_PREFIX))[len(STATE_PREFIX) :]


def test_the_style_is_available_but_the_assets_do_not_use_it() -> None:
    """Medido en la Fase 14.3 y no adoptado: con el salto en el estado el modelo sigue publicando
    primero sin `supersedes` y reconociendo (mismos rechazos). Los assets usan `phase`."""
    assert ASSETS.agent("monitor").state_line == "phase"


def test_the_line_gives_the_alert_the_jump_and_what_it_replaces() -> None:
    s = MonitorState()
    assert s.describe_gps_alert(10.0, "recovery_data") == "no"
    spoofing_alert(s)
    assert (
        s.describe_gps_alert(10.0, "recovery_data") == "yes — ai-0008 GPS_SPOOFING (open, active)"
    )
    assert s.describe_gps_alert(10.0, "recovery_data", 67.94) == (
        "yes — ai-0008 GPS_SPOOFING (open, active); GPS jump 67.9 m; replaces ai-0008"
    )
    s.apply(detection_event("cleared", "det-0001", 40.0))
    s.apply(closed("ai-0008", t=50.0))
    # cerrada: no hay nada que sustituir, aunque haya salto
    assert s.describe_gps_alert(60.0, "recovery_data", 67.9) == (
        "yes — ai-0008 GPS_SPOOFING (closed 10 s ago, active)"
    )


def test_an_alert_already_recovering_does_not_get_the_jump() -> None:
    s = MonitorState()
    spoofing_alert(s, phase="recovering")
    assert s.describe_gps_alert(10.0, "recovery_data", 67.9) == (
        "yes — ai-0008 GPS_SPOOFING (open, recovering)"
    )


def test_the_line_has_no_threshold_no_names_and_no_copyable_phrase() -> None:
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
    spoofing_alert(s)
    lines = [
        s.describe_gps_alert(10.0, "recovery_data"),
        s.describe_gps_alert(10.0, "recovery_data", 67.9),
    ]
    for line in lines:
        assert "threshold" not in line and "30" not in line and "phase" not in line.split("(")[0]
        names, _enums, bools = tm.find_names(line.replace("GPS_SPOOFING", "spoofing"))
        assert names == [] and bools == [], line
        assert tm.copied_spans(line, corpus) == [], line


def test_the_module_asks_for_the_metrics_before_the_model_and_says_the_jump(tmp_path: Path) -> None:
    results = {"get_track_metrics": {"gps_max_step_m": 67.9}}
    rt, platform, monitor, llm = monitor_with(tmp_path, results)
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    assert platform.calls[0] == ("get_track_metrics", {"since": 30.0, "until": 60.0})
    assert prompt_line(llm) == (
        "yes — ai-0008 GPS_SPOOFING (open, active); GPS jump 67.9 m; replaces ai-0008"
    )
    state = rt.trace.records[0]["state_metrics"]
    assert state["jump"] is True and state["gps_max_step_m"] == 67.9
    assert state["guardrail_view"] == "no_metrics"  # el modelo (falso) no pidió las métricas


def test_without_a_jump_the_line_has_only_the_alert(tmp_path: Path) -> None:
    rt, platform, monitor, llm = monitor_with(
        tmp_path, {"get_track_metrics": {"gps_max_step_m": 4.0}}
    )
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    assert prompt_line(llm) == "yes — ai-0008 GPS_SPOOFING (open, active)"
    state = rt.trace.records[0]["state_metrics"]
    assert state["jump"] is False and "guardrail_view" not in state


@pytest.mark.parametrize(
    "rule,kind,with_alert",
    [
        ("SOURCE_DISCREPANCY", "raised", True),  # no es un ROUTE_DEVIATION
        ("ROUTE_DEVIATION", "raised", False),  # sin alerta del GPS
        ("ROUTE_DEVIATION", "cleared", True),  # un cierre no es la recuperación
    ],
)
def test_the_platform_is_not_called_in_other_warnings(
    tmp_path: Path, rule: str, kind: str, with_alert: bool
) -> None:
    rt, platform, monitor, llm = monitor_with(tmp_path, {"get_track_metrics": {}})
    if with_alert:
        spoofing_alert(rt.state)
    event = detection_event(kind, "det-0002", 60.0, rule=rule)
    run(monitor.handle_batch([event]))
    assert not platform.calls
    assert not rt.trace.records[0].get("state_metrics")


def test_other_state_styles_do_not_call_the_platform_either(tmp_path: Path) -> None:
    rt, platform, monitor, llm = monitor_with(
        tmp_path,
        {"get_track_metrics": {"gps_max_step_m": 67.9}},
        state_line="phase",
    )
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    assert not platform.calls
    assert "GPS jump" not in prompt_line(llm)


def test_a_failing_platform_call_leaves_the_line_without_the_jump(tmp_path: Path) -> None:
    def boom(args: dict) -> dict:
        raise RuntimeError("platform down")

    rt, platform, monitor, llm = monitor_with(tmp_path, {"get_track_metrics": boom})
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    assert prompt_line(llm) == "yes — ai-0008 GPS_SPOOFING (open, active)"
    assert "platform down" in rt.trace.records[0]["state_metrics"]["error"]


def test_the_guardrail_view_says_when_the_models_window_misses_the_jump(tmp_path: Path) -> None:
    """El estado vio el salto (ventana del módulo) pero el modelo pidió otra ventana, sin salto: se
    cuenta como `window_without_jump`. El guardrail no usa lo que calculó el módulo."""

    def metrics(args: dict) -> dict:
        return {"gps_max_step_m": 67.9 if args["since"] <= 30.0 else None}

    policy = Script(
        tool_response(call("get_track_metrics", since=59.0, until=60.0)),
        tool_response(call("acknowledge_detection", reason="x")),
    )
    rt, platform, monitor, llm = monitor_with(tmp_path, {"get_track_metrics": metrics}, policy)
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    state = rt.trace.records[0]["state_metrics"]
    assert state["jump"] is True
    assert state["guardrail_view"] == "window_without_jump"


def test_the_guardrail_view_says_jump_when_the_model_sees_it(tmp_path: Path) -> None:
    results = {"get_track_metrics": {"gps_max_step_m": 67.9}}
    policy = Script(
        tool_response(call("get_track_metrics", since=30.0, until=60.0)),
        tool_response(call("acknowledge_detection", reason="x")),
    )
    rt, platform, monitor, llm = monitor_with(tmp_path, results, policy)
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    assert rt.trace.records[0]["state_metrics"]["guardrail_view"] == "jump"


def test_the_duration_of_the_invocation_includes_the_state_call(tmp_path: Path) -> None:
    import asyncio

    async def slow(url, name, args, timeout_s=10.0):
        await asyncio.sleep(0.2)
        return {"gps_max_step_m": 67.9}

    rt, platform, monitor, llm = monitor_with(tmp_path, {})
    rt.platform_call = slow
    spoofing_alert(rt.state)
    run(monitor.handle_batch([detection_event("raised", "det-0002", 60.0)]))
    assert rt.trace.records[0]["duration_s"] >= 0.2
