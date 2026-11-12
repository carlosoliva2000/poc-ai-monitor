"""Fase 15.1, paso 5: tiempos, `last_s`, instante de partida de la interacción y «los últimos».

- `prepare_window` / `Toolbox` (`window_rules`): el código convierte los tiempos, rechaza un `since`
  posterior al instante de partida y recorta un `until` posterior diciéndolo.
- El resultado no depende de si la simulación se pausó: con el mismo `as_of`, una plataforma que va
  50 s por delante devuelve lo mismo que una pausada en él.
- `monitor.as_of_from_warning`: el `as_of` de una invocación es el del aviso y los lotes solo juntan
  avisos del mismo instante.
- El chat del monitor recibe sus decisiones (`describe_monitor_decisions`).
"""

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

from ai_module.agent.assets import Assets
from ai_module.agent.engine import ToolError
from ai_module.agent.tools import Toolbox, prepare_window
from ai_module.chat_facts import describe_monitor_decisions
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import EventType

ASSETS = Assets()


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def events_platform(now: float) -> FakePlatform:
    """Una plataforma cuyo `get_events` devuelve un evento por segundo hasta el menor entre `until`
    y su propio «ahora» (como la real) y solo desde `since`."""

    def get_events(args: dict[str, Any]) -> dict[str, Any]:
        until = min(float(args.get("until", now)), now)
        since = float(args.get("since", 0.0))
        times = [t for t in range(int(since), int(until) + 1) if since <= t <= until]
        return {"events": [{"event_id": f"gps-{t}", "sim_time": float(t)} for t in times][-5:]}

    def track(args: dict[str, Any]) -> dict[str, Any]:
        return {"since": args["since"], "until": min(float(args["until"]), now)}

    return FakePlatform({"get_events": get_events, "get_track_metrics": track})


def toolbox(platform: FakePlatform, as_of: float | None, rules: bool = True) -> Toolbox:
    return Toolbox(ASSETS, [], "http://p", as_of=as_of, platform_call=platform, window_rules=rules)


# --- Ventanas ---


def test_clock_times_become_seconds_in_the_call() -> None:
    args, clipped = prepare_window(
        "get_events", {"source": "gps", "since": "T+01:30", "until": "T+01:50"}, 300.0
    )
    assert (args["since"], args["until"], clipped) == (90.0, 110.0, None)
    metrics, _ = prepare_window("get_track_metrics", {"since": "01:30", "until": 110}, 300.0)
    assert (metrics["since"], metrics["until"]) == (90.0, 110.0)


def test_last_s_is_counted_back_from_the_starting_instant() -> None:
    args, _ = prepare_window("get_events", {"source": "gps", "last_s": "1m30s"}, 300.0)
    assert (args["since"], args["until"]) == (210.0, 300.0) and "last_s" not in args
    near_start, _ = prepare_window("get_track_metrics", {"last_s": 90}, 40.0)
    assert (near_start["since"], near_start["until"]) == (0.0, 40.0)
    with pytest.raises(ToolError, match="either last_s or since"):
        prepare_window("get_events", {"source": "gps", "last_s": 60, "since": 10}, 300.0)


def test_a_start_after_the_starting_instant_is_rejected_with_that_instant() -> None:
    with pytest.raises(ToolError) as error:
        prepare_window("get_events", {"source": "gps", "since": 810, "until": 850}, 222.0)
    message = str(error.value)
    assert "T+03:42 (222 s)" in message and "T+13:30 (810 s)" in message
    assert "starts at or before 222 s" in message


def test_a_later_until_is_clipped_and_the_answer_says_so() -> None:
    args, clipped = prepare_window("get_events", {"source": "gps", "until": 9999}, 222.0)
    assert (args["until"], clipped) == (222.0, 222.0)
    no_until, none_clipped = prepare_window("get_events", {"source": "gps", "last_n": 3}, 222.0)
    assert (no_until["until"], none_clipped) == (222.0, None)

    result = run(
        toolbox(events_platform(300.0), 222.0)("get_events", {"source": "gps", "until": 9999})
    )
    assert result["until_clipped_to"] == 222.0 and "clipped to T+03:42" in result["note"]
    assert max(e["sim_time"] for e in result["events"]) == 222.0
    plain = run(
        toolbox(events_platform(300.0), 222.0)("get_events", {"source": "gps", "last_n": 2})
    )
    assert "until_clipped_to" not in plain


def test_a_bad_time_says_the_valid_formats() -> None:
    with pytest.raises(ToolError, match=r"T\+mm:ss"):
        prepare_window("get_events", {"source": "gps", "since": "tomorrow"}, 222.0)
    with pytest.raises(ToolError, match="1m30s"):
        prepare_window("get_events", {"source": "gps", "last_s": "soon"}, 222.0)


# --- El resultado no depende de la pausa ---


@pytest.mark.parametrize(
    "request_args",
    [
        {"source": "gps", "last_n": 5},
        {"source": "gps", "since": "T+03:30", "until": "T+05:00"},
        {"source": "gps", "last_s": 60},
        {"source": "gps", "until": 9999},
    ],
)
def test_the_answer_is_the_same_paused_or_not(request_args) -> None:
    """La plataforma sin pausa va 50 s por delante del `as_of`; con pausa está en él."""
    paused = run(toolbox(events_platform(222.0), 222.0)("get_events", dict(request_args)))
    ahead_box = toolbox(events_platform(272.0), 222.0)
    ahead = run(ahead_box("get_events", dict(request_args)))
    assert ahead == paused
    assert ahead_box.after_as_of == 0
    metrics_paused = run(
        toolbox(events_platform(222.0), 222.0)("get_track_metrics", {"last_s": 30})
    )
    metrics_ahead = run(toolbox(events_platform(272.0), 222.0)("get_track_metrics", {"last_s": 30}))
    assert metrics_ahead == metrics_paused


def test_late_events_are_counted_when_a_platform_ignores_the_cut() -> None:
    def careless(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "events": [{"event_id": "a", "sim_time": 221.0}, {"event_id": "b", "sim_time": 230.0}]
        }

    box = toolbox(FakePlatform({"get_events": careless}), 222.0)
    run(box("get_events", {"source": "gps"}))
    assert box.after_as_of == 1


def test_without_the_switch_the_old_cut_is_kept() -> None:
    old = toolbox(events_platform(300.0), 222.0, rules=False)
    result = run(old("get_events", {"source": "gps", "until": 9999}))
    assert (
        "until_clipped_to" not in result and max(e["sim_time"] for e in result["events"]) == 222.0
    )


def test_the_report_chat_without_the_switch_has_no_cut() -> None:
    free = toolbox(events_platform(300.0), None, rules=False)
    result = run(free("get_events", {"source": "gps", "until": 9999}))
    assert max(e["sim_time"] for e in result["events"]) == 300.0


# --- El monitor: `as_of` del aviso y lotes por instante ---


def monitor_with(tmp_path: Path, policy: Any, *, switch: bool):
    rt, published = make_runtime(tmp_path, FakeLlm(policy), FakePlatform())
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(300.0)  # sin pausa: el reloj va muy por delante del aviso
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, as_of_from_warning=switch)
    return rt, published, monitor


def test_the_invocation_starts_at_the_warning_not_at_the_clock(tmp_path: Path) -> None:
    for switch, expected in ((True, 20.0), (False, 300.0)):
        reset_ids()
        policy = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
        rt, published, monitor = monitor_with(tmp_path, policy, switch=switch)
        run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
        trace = rt.trace.records[-1]
        assert trace["as_of"] == expected and trace["warnings"] == [
            "det-0001 ROUTE_DEVIATION raised (desviación de prueba)"
        ]
        sent = next(e for e in published if e.type == EventType.ANOMALY_DETECTED)
        assert sent.payload["as_of_sim_time"] == expected


def test_a_batch_uses_the_last_warning_of_the_batch(tmp_path: Path) -> None:
    policy = Script(tool_response(call("publish_alert", **alert_args(["det-0001", "det-0002"]))))
    rt, _, monitor = monitor_with(tmp_path, policy, switch=True)
    events = [
        detection_event("raised", "det-0001", 20.0),
        detection_event("raised", "det-0002", 20.0, rule="SOURCE_DISCREPANCY"),
    ]
    run(monitor.handle_batch(events))
    assert rt.trace.records[-1]["as_of"] == 20.0


def test_batches_only_join_warnings_of_the_same_instant(tmp_path: Path) -> None:
    _, _, monitor = monitor_with(tmp_path, Script("x"), switch=True)
    for event in (
        detection_event("raised", "det-0001", 20.0),
        detection_event("raised", "det-0002", 20.0, rule="SOURCE_DISCREPANCY"),
        detection_event("raised", "det-0003", 25.0, rule="SOURCE_SILENT", source="radar"),
    ):
        monitor.queue.append(event)
    assert [e.payload["detection_id"] for e in monitor._take_batch()] == ["det-0001", "det-0002"]
    assert [e.payload["detection_id"] for e in monitor._take_batch()] == ["det-0003"]
    _, _, old = monitor_with(tmp_path, Script("x"), switch=False)  # sin la clave, todo junto
    for i, t in enumerate((20.0, 25.0)):
        old.queue.append(detection_event("raised", f"det-000{i}", t, rule="SOURCE_DISCREPANCY"))
    assert len(old._take_batch()) == 2


def test_closed_ago_uses_the_starting_instants_with_the_switch() -> None:
    """Sin pausa la alerta sale del monitor mucho después de su aviso: con el interruptor, «cerrada
    hace 60 s» se cuenta con los instantes de partida, no con los de publicación."""
    for switch, recent in ((True, False), (False, True)):
        state = MonitorState(as_of_times=switch)
        state.apply(detection_event("raised", "det-1", 100.0, rule="SOURCE_DISCREPANCY"))
        spoofing = alert("ai-1", ["det-1"], cause="GPS_SPOOFING", t=300.0)  # publicada tarde
        spoofing.payload["as_of_sim_time"] = 101.0
        state.apply(spoofing)
        from test_monitor_state import closed

        end = closed("ai-1", t=320.0)  # cierre publicado a T+320; su aviso era de T+130
        end.payload["as_of_sim_time"] = 130.0
        state.apply(end)
        assert (state.recent_gps_alert(200.0) is not None) is recent  # cerrada a T+130: hace 70 s


# --- Decisiones del monitor para su chat ---


def test_the_monitor_decisions_say_what_it_looked_at_and_why(tmp_path: Path) -> None:
    llm = Script(
        tool_response(call("get_events", source="link", last_n=6)),
        tool_response(call("publish_alert", **alert_args(["det-0001"], cause="HIJACK"))),
    )
    rt, _, monitor = monitor_with(tmp_path, llm, switch=True)
    run(
        monitor.handle_batch(
            [detection_event("raised", "det-0001", 335.0, rule="LINK_ANOMALY", source="link")]
        )
    )
    text = describe_monitor_decisions(rt.trace.records, rt.state)
    assert "T+05:35 · warning det-0001 LINK_ANOMALY raised" in text
    assert "looked at: link events (last 6)" in text
    assert "published: alert ai-0001" in text
    assert (
        describe_monitor_decisions([], MonitorState())
        == "The monitor has not made any decision yet."
    )


def test_the_latest_decisions_of_the_prompt_use_the_starting_instant_with_the_switch() -> None:
    """Sin pausa el aviso es de T+05:04 y la alerta sale a T+07:24: el prompt no puede decir que el
    monitor decidió «a T+07:24» (el modelo cambió de causa por ello en `faults`)."""
    for switch, label in ((True, "T+01:40"), (False, "T+05:00")):
        state = MonitorState(as_of_times=switch)
        state.apply(detection_event("raised", "det-1", 100.0))
        late = alert("ai-1", ["det-1"], cause="WIND", t=300.0)  # publicada a T+05:00
        late.payload["as_of_sim_time"] = 100.0  # su aviso era de T+01:40
        state.apply(late)
        assert state.describe_decisions().startswith(label)


def test_the_route_trend_reaches_the_monitor_only_in_the_hijack_recovery(tmp_path: Path) -> None:
    """`monitor.now_route_trend: link_recovery`: con la tendencia en todas las invocaciones, el
    diagnóstico del spoofing de `demo-battery` falló en 3 de 8 ejecuciones (0 de 6 sin ella)."""
    from ai_module.monitor import Pending

    rt, _, monitor = monitor_with(tmp_path, Script("x"), switch=True)

    def inv_with(link_recovery: bool):
        from types import SimpleNamespace

        event = detection_event("raised", "det-0001", 20.0)
        return SimpleNamespace(
            pending=[Pending(event, "raised", "det-0001", link_recovery=link_recovery)]
        )

    assert monitor.config.now_route_trend == "link_recovery"
    assert monitor._shows_route_trend(inv_with(True)) and not monitor._shows_route_trend(
        inv_with(False)
    )
    monitor.config = replace(monitor.config, now_route_trend="all")
    assert monitor._shows_route_trend(inv_with(False))
    monitor.config = replace(monitor.config, now_route_trend="off")
    assert not monitor._shows_route_trend(inv_with(True))
