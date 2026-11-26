"""Argumentos del comando de ejecución sin web (`platform_app.run`)."""

import pytest

from platform_app.run import Ask, ManualFault, _incident_line


def test_manual_fault_argument() -> None:
    assert ManualFault.parse("radar:mute:150:200") == ManualFault("radar", "mute", 150.0, 200.0)
    with pytest.raises(Exception, match="fuente:modo:inicio:fin"):
        ManualFault.parse("radar:150")


def test_ask_argument() -> None:
    assert Ask.parse("monitor:200:Why?") == Ask("monitor", 200.0, "Why?")
    assert Ask.parse("report:end:What?").when is None
    with pytest.raises(Exception, match="conversación:cuándo:texto"):
        Ask.parse("nobody:1:x")


def test_an_incident_revision_is_printed_in_one_line() -> None:
    event = {
        "payload": {
            "incident_id": "inc-0001", "change": "opened", "name": "GPS spoofing", "state": "open",
            "severity": "high", "confidence": "confirmed", "as_of_sim_time": 200.0,
        }
    }  # fmt: skip
    assert (
        _incident_line(event) == "T+03:20  opened   inc-0001 GPS spoofing · open · high · confirmed"
    )


def _fake_main(monkeypatch: pytest.MonkeyPatch, *, vllm_up: bool, assistant_fails: bool = False):
    """`main()` con procesos y WebSocket falsos: devuelve lo que se arrancó y se paró."""
    import contextlib
    import sys

    from platform_app import run

    calls: dict[str, list] = {"started": [], "stopped": []}
    monkeypatch.setattr(run, "http_get", lambda url, timeout=2.0: {} if vllm_up else None)
    monkeypatch.setattr(run, "start_platform", lambda port, host="127.0.0.1": "platform")
    monkeypatch.setattr(
        run, "start_ai_module", lambda url, tables: calls["started"].append("monitor") or "monitor"
    )

    def start_assistant(url: str):
        if assistant_fails:
            raise SystemExit("the assistant stopped at startup: vLLM serves another model")
        calls["started"].append("assistant")
        return "assistant"

    monkeypatch.setattr(run, "start_assistant", start_assistant)
    monkeypatch.setattr(run, "start_instructor_assistant", lambda url: "instructor")
    monkeypatch.setattr(run, "stop", lambda proc: calls["stopped"].append(proc))

    @contextlib.contextmanager
    def fake_connect(*args, **kwargs):
        yield type("WS", (), {"send": lambda self, m: None})()

    monkeypatch.setattr(run, "connect", fake_connect)
    seen: dict = {}

    def fake_run_scenario(ws, name, *a, reports=False, **kw):
        seen["reports"] = reports
        return run.RunResult([])

    monkeypatch.setattr(run, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(sys, "argv", ["run", "--scenario", "nominal"])
    return run, calls, seen


def test_without_vllm_the_run_says_so_clearly_and_keeps_the_monitor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run, calls, seen = _fake_main(monkeypatch, vllm_up=False)
    assert run.main() == 0
    err = capsys.readouterr().err
    assert "vLLM no responde" in err and "serve.sh start" in err and "--no-llm" in err
    assert calls["started"] == ["monitor"] and seen["reports"] is False


def test_an_assistant_that_does_not_start_does_not_take_the_monitor_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run, calls, seen = _fake_main(monkeypatch, vllm_up=True, assistant_fails=True)
    assert run.main() == 0
    assert "el asistente no ha arrancado" in capsys.readouterr().err
    assert calls["started"] == ["monitor"] and seen["reports"] is False
    assert "monitor" in calls["stopped"]  # y se para limpio al terminar


def test_with_vllm_up_the_assistant_starts_and_the_run_waits_for_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, calls, seen = _fake_main(monkeypatch, vllm_up=True)
    assert run.main() == 0
    assert calls["started"] == ["monitor", "assistant"] and seen["reports"] is True
    monkeypatch.setattr("sys.argv", ["run", "--scenario", "nominal", "--no-llm"])
    calls["started"].clear()
    assert run.main() == 0 and calls["started"] == ["monitor"]
