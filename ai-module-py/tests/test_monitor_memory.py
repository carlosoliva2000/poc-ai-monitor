"""Modo guiado (`monitor.guided_skills`) y memoria A (`monitor.memory: per_run`) del monitor."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from agent_helpers import (
    FakeLlm,
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

from ai_module.agent.assets import Assets, sections
from ai_module.agent.profiles import ProfileError, load_profile
from ai_module.agent.trace import InvocationTrace
from ai_module.monitor import Invocation, Monitor, Pending
from ai_module.monitor_memory import MonitorMemory

ACK = call("acknowledge_detection", reason="no alert needed")


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def monitor_with(tmp_path: Path, script: Script, **config: Any):
    llm = FakeLlm(script)
    rt, published = make_runtime(tmp_path, llm)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    monitor = Monitor(rt)
    monitor.config = replace(monitor.config, **config)
    return rt, published, monitor, llm


def raised(det: str = "det-0001", t: float = 20.0, **kw: Any):
    return detection_event("raised", det, t, **kw)


# --- Modo guiado -----------------------------------------------------------------------------


def test_guided_skills_is_off_by_default_and_messages_are_the_usual_two(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, _, monitor, llm = monitor_with(tmp_path, script)
    assert monitor.config.guided_skills is False and monitor.config.memory == "per_detection"
    run(monitor.handle_batch([raised(rule="GPS_DEGRADED", source="gps")]))
    messages = llm.requests[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Skill for this warning" not in messages[1]["content"]
    assert rt.trace.records[0]["skills_loaded"] == [] and rt.trace.records[0]["memory"] == {}


def test_guided_skills_puts_the_skill_of_the_rule_in_the_first_user_message(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, _, monitor, llm = monitor_with(tmp_path, script, guided_skills=True)
    run(monitor.handle_batch([raised(rule="GPS_DEGRADED", source="gps")]))
    messages = llm.requests[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]  # sin llamada falsa a load_skill
    content = messages[1]["content"]
    assert "Skill for this warning (`source-discrepancy`)" in content
    assert monitor.rt.assets.skills["source-discrepancy"].content in content
    assert "<<" not in content
    trace = rt.trace.records[0]
    assert trace["skills_loaded"] == [{"name": "source-discrepancy", "by": "guided"}]
    assert trace["guided_mode"] is True and trace["aids"]["guided_skills"] is True


def test_guided_skills_skips_cleared_and_repeats_no_skill(tmp_path: Path) -> None:
    rt, _, monitor, _ = monitor_with(tmp_path, Script("x"), guided_skills=True)
    _, secs = sections(rt.assets.prompt(monitor.config.objective_prompt or ""))
    trace = InvocationTrace("inv-0001", "monitor")
    pending = [
        Pending(raised("det-0001", rule="SOURCE_SILENT", source="radar"), "raised", "det-0001"),
        Pending(raised("det-0002", rule="GPS_DEGRADED", source="gps"), "raised", "det-0002"),
        Pending(raised("det-0003", rule="ROUTE_DEVIATION"), "updated", "det-0003"),
        Pending(detection_event("cleared", "det-0004", 20.0), "cleared", "det-0004"),
    ]
    inv = Invocation("inv-0001", 20.0, pending, trace)
    parts = monitor._guided_sections(inv, secs)
    assert [p.split("`")[1] for p in parts] == ["source-discrepancy", "route-deviation"]
    assert [s["name"] for s in trace.skills_loaded] == ["source-discrepancy", "route-deviation"]
    monitor.config = replace(monitor.config, guided_skills=False)
    assert monitor._guided_sections(inv, secs) == []


# --- Memoria A en el monitor -----------------------------------------------------------------


def test_per_run_keeps_one_conversation_across_invocations(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("publish_alert", **alert_args(["det-0001"]))),
        tool_response(ACK),
    )
    rt, _, monitor, llm = monitor_with(tmp_path, script, memory="per_run")
    run(monitor.handle_batch([raised("det-0001", 20.0)]))
    run(monitor.handle_batch([detection_event("updated", "det-0001", 30.0)]))
    first, second = llm.requests
    assert len(second["messages"]) == len(first["messages"]) + 2 + 1  # + assistant, tool, user
    assert second["messages"][: len(first["messages"])] == first["messages"]
    roles = [m["role"] for m in second["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "user"]
    assert roles.count("system") == 1
    assert second["messages"][-1]["content"].startswith("This conversation continues.")
    assert (
        "det-0001" in second["messages"][-1]["content"]
        and "Current time: T+00:30" in (second["messages"][-1]["content"])
    )
    memory = [r["memory"] for r in rt.trace.records]
    assert [m["turn"] for m in memory] == [1, 2] and all(m["mode"] == "per_run" for m in memory)
    # la traza guarda lo que vio el modelo en cada invocación (una copia)
    assert len(rt.trace.records[0]["messages"]) == 4
    assert len(rt.trace.records[1]["messages"]) == 7


def test_reset_starts_a_new_conversation(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, _, monitor, llm = monitor_with(tmp_path, script, memory="per_run")
    run(monitor.handle_batch([raised("det-0001", 20.0)]))
    monitor.reset()
    rt.reset_run()
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    run(monitor.handle_batch([raised("det-0001", 20.0)]))
    assert [m["role"] for m in llm.requests[1]["messages"]] == ["system", "user"]
    assert "This conversation continues" not in llm.requests[1]["messages"][1]["content"]


def test_evidence_from_the_history_is_rejected_until_requested_again(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("publish_alert", **alert_args(["det-0001"]))),
        tool_response(call("publish_alert", **alert_args(["det-0002"]))),  # cita gps-000001
        tool_response(ACK),
    )
    rt, _, monitor, _ = monitor_with(tmp_path, script, memory="per_run")
    run(monitor.handle_batch([raised("det-0001", 20.0)]))
    second = raised("det-0002", 21.0, rule="SOURCE_DISCREPANCY", trigger=("gps-000009",))
    run(monitor.handle_batch([second]))
    errors = [e for r in rt.trace.records[1]["guardrail_rejections"] for e in r["errors"]]
    assert any(
        "'gps-000001' comes from an earlier warning" in e and "request it again" in e
        for e in errors
    )


def test_per_detection_does_not_reject_unseen_evidence(tmp_path: Path) -> None:
    script = Script(tool_response(call("publish_alert", **alert_args(["det-0001"]))))
    rt, _, monitor, _ = monitor_with(tmp_path, script)
    run(monitor.handle_batch([raised("det-0001", 20.0, trigger=("gps-000009",))]))
    assert rt.trace.records[0]["guardrail_rejections"] == []
    assert rt.trace.records[0]["unseen_evidence"] == 2


def test_an_aborted_turn_leaves_a_valid_history(tmp_path: Path) -> None:
    bad = tool_response(call("publish_alert", **alert_args(["det-0009"])))  # id equivocado
    script = Script(bad, bad, bad, tool_response(ACK))
    rt, _, monitor, llm = monitor_with(tmp_path, script, memory="per_run")
    run(monitor.handle_batch([raised("det-0001", 20.0)]))
    assert rt.trace.records[0]["end_reason"] == "repeated_rejection"
    run(monitor.handle_batch([detection_event("updated", "det-0001", 30.0)]))
    messages = llm.requests[-1]["messages"]
    calls = {c["id"] for m in messages for c in (m.get("tool_calls") or [])}
    answered = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
    assert calls <= answered


# --- MonitorMemory (unidad) ------------------------------------------------------------------

TEXTS = Assets().prompt("prompts/monitor_memory.md")


def tool_call_message(call_id: str, name: str) -> dict[str, Any]:
    function = {"name": name, "arguments": "{}"}
    call = {"id": call_id, "type": "function", "function": function}
    return {"role": "assistant", "content": None, "tool_calls": [call]}


def engine_turn(memory: MonitorMemory, n: int, big: int = 3000, *, abort: bool = False) -> list:
    """Lo que añade el motor en un turno: una lectura grande, la decisión y un recordatorio."""
    messages, _ = memory.begin_turn(
        "SYSTEM",
        f"objective {n} " + "x" * 200,
        t=f"T+00:{n:02d}",
        warnings=f"det-{n:04d} (R, raised)",
    )
    messages += [
        tool_call_message(f"r{n}", "get_events"),
        {"role": "tool", "tool_call_id": f"r{n}", "content": f"gps-{n:06d} " + "y" * big},
        {"role": "user", "content": "You have not yet responded to: det-0001."},
        tool_call_message(f"d{n}", "publish_alert"),
    ]
    if not abort:
        messages.append({"role": "tool", "tool_call_id": f"d{n}", "content": '{"ok":true}'})
    memory.end_turn(messages, f"ai-{n:04d} WIND low")
    return messages


def test_no_compaction_below_the_budget() -> None:
    memory = MonitorMemory(TEXTS, budget=100_000, target=50_000)
    engine_turn(memory, 1)
    _, info = memory.begin_turn("SYSTEM", "objective 2", t="T+00:02", warnings="det-0002")
    assert (info.turn, info.compacted_a, info.compacted_b) == (2, 0, 0)
    assert info.tokens_before == info.tokens_after


def test_level_a_removes_old_data_results_but_keeps_decisions_and_pairing() -> None:
    memory = MonitorMemory(TEXTS, budget=2500, target=2300)
    for n in (1, 2):
        engine_turn(memory, n)
    flat, info = memory.begin_turn("SYSTEM", "objective 3", t="T+00:03", warnings="det-0003")
    assert info.compacted_a >= 1 and info.tokens_after < info.tokens_before
    old = memory.turns[0].messages
    assert old[0]["content"].startswith("[T+00:01] Warning(s) already answered: det-0001")
    results = {m["tool_call_id"]: m["content"] for m in old if m["role"] == "tool"}
    assert results["r1"].startswith("[Older tool result removed")
    assert results["d1"] == '{"ok":true}'  # la decisión se conserva
    assert not any(m["role"] == "user" and "not yet responded" in m["content"] for m in old)
    ids = {c["id"] for m in old for c in (m.get("tool_calls") or [])}
    assert ids == set(results)  # cada llamada sigue emparejada
    assert flat[0] == {"role": "system", "content": "SYSTEM"}


def test_level_b_collapses_old_turns_into_one_digest_message() -> None:
    memory = MonitorMemory(TEXTS, budget=1500, target=1200)
    for n in (1, 2, 3):
        engine_turn(memory, n)
    flat, info = memory.begin_turn("SYSTEM", "objective 4", t="T+00:04", warnings="det-0004")
    assert info.compacted_b >= 1
    digest = flat[1]["content"]
    assert flat[1]["role"] == "user" and digest.startswith("Earlier warnings, already answered")
    assert "- [T+00:01] det-0001 (R, raised) -> ai-0001 WIND low" in digest
    assert len(memory.digest) == 2 and len(memory.turns) == 2  # 3 turnos viejos: 2 al resumen


def test_the_previous_turn_is_never_collapsed_and_the_current_one_is_untouched() -> None:
    memory = MonitorMemory(TEXTS, budget=10, target=5)  # imposible de cumplir
    engine_turn(memory, 1)
    engine_turn(memory, 2)
    flat, _ = memory.begin_turn("SYSTEM", "objective 3 " + "z" * 500, t="T+00:03", warnings="d")
    assert flat[-1]["content"].endswith("z" * 500)  # el turno en curso no se toca
    assert len(memory.turns) == 2  # el turno 2 (el anterior) sigue, aunque no se cumpla el objetivo


def test_a_cut_turn_gets_its_pending_tool_calls_closed() -> None:
    memory = MonitorMemory(TEXTS, budget=100_000, target=50_000)
    messages = engine_turn(memory, 1, abort=True)
    saved = memory.turns[0].messages
    assert saved[-1]["tool_call_id"] == "d1"
    assert saved[-1]["content"].startswith("[This call was not executed")
    assert len(messages) - 1 == len(saved) - 1  # la lista del motor no se toca (lleva el sistema)


def test_history_ids_are_the_ones_still_visible_in_earlier_turns() -> None:
    memory = MonitorMemory(TEXTS, budget=100_000, target=50_000)
    engine_turn(memory, 1)
    memory.begin_turn("SYSTEM", "objective det-0002 gps-000099", t="T+00:02", warnings="d")
    ids = memory.history_ids()
    assert "gps-000001" in ids and "gps-000099" not in ids


def test_observe_fits_tokens_to_characters() -> None:
    memory = MonitorMemory(TEXTS, budget=1, target=1)
    memory.observe((7000, 3600), (17000, 6400))  # 0,28 tokens por carácter, 1640 fijos
    assert memory.slope == pytest.approx(0.28) and memory.overhead == pytest.approx(1640)
    memory.observe((7000, 3600), (7500, 3700))  # poca diferencia: se ignora
    assert memory.slope == pytest.approx(0.28)


# --- Perfiles --------------------------------------------------------------------------------


def write_profile(tmp_path: Path, **monitor: Any) -> Path:
    content = {
        "server": {"model": "Qwen/Qwen3-14B-AWQ", "tool_call_parser": "hermes",
                   "max_model_len": 32768},
        "agents": {"monitor": monitor},
    }  # fmt: skip
    (tmp_path / "p.yaml").write_text(yaml.safe_dump(content), encoding="utf-8")
    return tmp_path


def test_the_phase_11_profiles_load_and_set_only_their_switch() -> None:
    expected = {
        "actual-guiado": (True, "per_detection"),
        "actual-memoria-a": (False, "per_run"),
        "actual-guiado-memoria-a": (True, "per_run"),
    }
    for name, (guided, memory) in expected.items():
        config = Assets(profile=load_profile(name)).agent("monitor")
        assert (config.guided_skills, config.memory) == (guided, memory), name


def test_a_memory_budget_that_does_not_fit_in_the_context_is_an_error(tmp_path: Path) -> None:
    base = Assets(profile=None)
    raw = {
        "llm": {"model": "m"},
        "agents": {n: {} for n in ("monitor", "chat_monitor", "report", "chat_report")},
    }
    del raw, base
    directory = write_profile(tmp_path, memory="per_run", memory_budget_tokens=31000)
    profile = load_profile("p", directory)
    with pytest.raises(ProfileError, match="must fit in max_model_len"):
        Assets(profile=profile)
    directory = write_profile(tmp_path, memory="per_run", memory_budget_tokens=26000)
    Assets(profile=load_profile("p", directory))  # cabe
