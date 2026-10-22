"""Motor de agente con un LLM falso guionizado: parámetros, tools, bucle y fin."""

import asyncio
from dataclasses import replace
from typing import Any

import pytest
from agent_helpers import FakeLlm, Script, call, run, text_response, tool_response

from ai_module.agent.assets import Assets
from ai_module.agent.engine import MAX_RESULT_CHARS, AgentEngine, ToolError, limit_result
from ai_module.agent.trace import InvocationTrace

ASSETS = Assets()
CONFIG = ASSETS.agent("monitor")


def make_engine(llm: FakeLlm, execute=None, config=CONFIG) -> AgentEngine:
    async def default(name: str, args: dict[str, Any]) -> Any:
        return {"echo": name, "args": args}

    return AgentEngine(llm, config, ASSETS.tool_schemas(config.active_tools), execute or default)


def new_trace() -> InvocationTrace:
    return InvocationTrace(invocation_id="inv-1", agent="monitor")


def go(engine, messages=None, trace=None, **kwargs):
    messages = messages if messages is not None else [{"role": "user", "content": "hola"}]
    trace = trace or new_trace()
    return run(engine.run(messages, trace, **kwargs)), messages, trace


def test_every_request_carries_explicit_sampling_and_the_tools_as_they_are() -> None:
    llm = FakeLlm(Script(text_response("hecho")))
    result, _, trace = go(make_engine(llm))
    request = llm.requests[0]
    assert request["sampling"] == {
        "temperature": 0.0, "top_p": 1.0, "max_tokens": 800, "tool_choice": "required",
        "extra_body": {"top_k": -1, "repetition_penalty": 1.05},
    }  # fmt: skip
    offered = [t["function"]["name"] for t in request["tools"]]
    assert offered == [t["function"]["name"] for t in ASSETS.tool_schemas(CONFIG.active_tools)]
    assert request["tools"] == ASSETS.tool_schemas(CONFIG.active_tools)  # sin regenerar
    assert trace.sampling == request["sampling"] and trace.tools_offered == offered
    assert result.end_reason == "final" and result.text == "hecho"


def test_disabled_tools_are_not_offered() -> None:
    config = replace(CONFIG, disabled_tools=["get_track_metrics", "get_events"])
    llm = FakeLlm(Script(text_response("x")))
    go(make_engine(llm, config=config))
    offered = {t["function"]["name"] for t in llm.requests[0]["tools"]}
    assert "get_track_metrics" not in offered and "get_events" not in offered
    assert "publish_alert" in offered


def test_tool_calls_are_detected_by_tool_calls_even_with_finish_reason_stop() -> None:
    llm = FakeLlm(Script(tool_response(call("get_events", source="gps")), text_response("listo")))
    result, messages, trace = go(make_engine(llm))
    assert trace.calls[0].finish_reason == "stop"  # solo anotación
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[1]["tool_calls"][0]["function"]["name"] == "get_events"
    assert messages[2]["content"] == '{"echo":"get_events","args":{"source":"gps"}}'
    assert result.tool_names == ["get_events"] and result.end_reason == "final"


def test_text_without_tool_calls_is_the_final_answer_in_chats() -> None:
    llm = FakeLlm(Script(text_response("respuesta")))
    result, _, trace = go(make_engine(llm))
    assert result.end_reason == "final" and len(trace.calls) == 1


def test_invalid_json_and_unknown_tool_go_back_to_the_model_and_count() -> None:
    bad = tool_response(call("get_events"), content="")
    bad.tool_calls[0] = type(bad.tool_calls[0])("c1", "get_events", "{no es json")
    unknown = tool_response(call("hackear_dron"))
    llm = FakeLlm(Script(bad, unknown, text_response("ok")))
    result, messages, trace = go(make_engine(llm))
    assert trace.invalid_json == 1
    tool_messages = [m["content"] for m in messages if m["role"] == "tool"]
    assert "no son JSON válido" in tool_messages[0]
    assert "tool desconocida o no disponible" in tool_messages[1]
    assert len(trace.calls) == 3  # cada fallo consumió una iteración
    assert trace.calls[0].tool_calls[0]["error"]


def test_a_tool_error_is_returned_as_the_result() -> None:
    async def failing(name: str, args: dict) -> Any:
        raise ToolError("la plataforma no responde")

    llm = FakeLlm(Script(tool_response(call("get_events", source="gps")), text_response("ok")))
    _, messages, _ = go(make_engine(llm, failing))
    assert messages[2]["content"] == '{"error":"la plataforma no responde"}'


def test_results_are_trimmed_with_a_notice() -> None:
    async def big(name: str, args: dict) -> Any:
        return {"data": "x" * 10_000}

    llm = FakeLlm(Script(tool_response(call("get_events", source="gps")), text_response("ok")))
    _, messages, trace = go(make_engine(llm, big))
    content = messages[2]["content"]
    assert len(content) < MAX_RESULT_CHARS + 120 and "recortado" in content
    assert trace.calls[0].tool_calls[0]["truncated"] is True
    short, truncated = limit_result("corto")
    assert short == "corto" and not truncated


def test_a_text_result_such_as_a_skill_is_delivered_as_it_is() -> None:
    async def skill(name: str, args: dict) -> Any:
        return "# Skill\nlínea 1\nlínea 2"

    llm = FakeLlm(Script(tool_response(call("load_skill", name="x")), text_response("ok")))
    _, messages, _ = go(make_engine(llm, skill))
    assert messages[2]["content"] == "# Skill\nlínea 1\nlínea 2"  # sin comillas ni \n escapados


def test_iteration_cap() -> None:
    llm = FakeLlm(Script(tool_response(call("get_events", source="gps"))))
    result, _, trace = go(make_engine(llm))
    assert result.end_reason == "max_iterations" and len(trace.calls) == CONFIG.max_iterations


def test_loop_ends_as_soon_as_everything_is_answered() -> None:
    answered: list[bool] = []

    async def publish(name: str, args: dict) -> Any:
        answered.append(True)
        return {"ok": True}

    llm = FakeLlm(Script(tool_response(call("publish_alert")), text_response("no debería llegar")))
    result, _, trace = go(make_engine(llm, publish), is_done=lambda: bool(answered))
    assert result.end_reason == "done" and len(trace.calls) == 1  # ni una llamada de más


def test_reminder_once_then_text_means_no_conclusion() -> None:
    llm = FakeLlm(Script(text_response("pienso..."), text_response("sigo pensando")))
    result, messages, trace = go(
        make_engine(llm), is_done=lambda: False, reminder=lambda: "RECUERDA responder"
    )
    assert result.end_reason == "text" and trace.reminders == 1 and len(trace.calls) == 2
    # el primer intento (solo texto) no queda en los messages: lo sustituye el recordatorio
    assert messages[1] == {"role": "user", "content": "RECUERDA responder"}
    assert [m["content"] for m in messages if m["role"] == "assistant"] == ["sigo pensando"]
    assert [c.content for c in trace.calls] == ["pienso...", "sigo pensando"]  # en la traza sí


def test_reminder_works_when_the_model_answers_after_it() -> None:
    state = {"done": False}

    async def publish(name: str, args: dict) -> Any:
        state["done"] = True
        return {"ok": True}

    llm = FakeLlm(Script(text_response("hmm"), tool_response(call("publish_alert"))))
    result, _, trace = go(make_engine(llm, publish), is_done=lambda: state["done"],
                          reminder=lambda: "r")  # fmt: skip
    assert result.end_reason == "done" and trace.reminders == 1


def test_llm_exception_ends_the_invocation_with_an_error() -> None:
    llm = FakeLlm(Script(RuntimeError("vLLM caído")))
    result, _, trace = go(make_engine(llm))
    assert result.end_reason == "error" and "vLLM caído" in trace.calls[0].content


def test_overall_time_limit() -> None:
    def slow(messages, tools, sampling):
        raise TimeoutError

    config = replace(CONFIG, max_invocation_s=0.2, llm_timeout_s=0.05)

    class Sleeper(FakeLlm):
        async def complete(self, *args, **kwargs):
            await asyncio.sleep(5)

    result, _, _ = go(make_engine(Sleeper(slow), config=config))
    assert result.end_reason == "timeout"


def test_streaming_with_tool_calls_reports_the_deltas() -> None:
    chat = ASSETS.agent("chat_monitor")
    deltas: list[str] = []

    async def on_delta(text: str) -> None:
        deltas.append(text)

    llm = FakeLlm(
        Script(
            tool_response(call("get_my_alerts"), content="Miro."), text_response("Hay una alerta")
        )
    )
    engine = AgentEngine(llm, chat, ASSETS.tool_schemas(chat.active_tools), lambda n, a: _ok())
    result, _, _ = go(engine, on_delta=on_delta)
    assert llm.requests[0]["stream"] is True
    assert "".join(deltas) == "Miro. Hay una alerta "
    assert result.streamed_text == "Miro. Hay una alerta " and result.text == "Hay una alerta"
    assert result.tool_names == ["get_my_alerts"]


async def _ok() -> Any:
    return {"alerts": []}


@pytest.mark.parametrize("name", ["chat_monitor", "chat_report", "report"])
def test_other_agents_use_their_own_sampling(name: str) -> None:
    config = ASSETS.agent(name)
    llm = FakeLlm(Script(text_response("x")))
    go(make_engine(llm, config=config))
    sampling = llm.requests[0]["sampling"]
    assert sampling["temperature"] == 0.7 and sampling["top_p"] == 0.8
    assert sampling["tool_choice"] == "auto"
    assert sampling["extra_body"] == {"top_k": 20, "repetition_penalty": 1.05}


def test_a_failed_text_attempt_is_not_kept_but_the_next_tool_call_is() -> None:
    state = {"done": False}

    async def publish(name: str, args: dict) -> Any:
        state["done"] = True
        return {"ok": True}

    llm = FakeLlm(
        Script(text_response('```json {"name": ...}```'), tool_response(call("publish_alert")))
    )
    result, messages, trace = go(
        make_engine(llm, publish), is_done=lambda: state["done"], reminder=lambda: "r"
    )
    assert result.end_reason == "done"
    assert [m["role"] for m in messages] == ["user", "user", "assistant", "tool"]
    assert trace.calls[0].content.startswith("```json")


def test_last_iteration_offers_only_the_final_tools_without_forcing_one() -> None:
    llm = FakeLlm(Script(tool_response(call("get_events", source="gps"))))
    result, _, trace = go(make_engine(llm))
    assert result.end_reason == "max_iterations"
    offered = [[t["function"]["name"] for t in r["tools"]] for r in llm.requests]
    full = [t["function"]["name"] for t in ASSETS.tool_schemas(CONFIG.active_tools)]
    assert all(names == full for names in offered[:-1])
    assert offered[-1] == ["publish_alert", "acknowledge_detection", "close_alert"]
    assert all(r["sampling"]["tool_choice"] == "required" for r in llm.requests)  # sin nombre
    assert [c.restricted_tools for c in trace.calls] == [None] * (CONFIG.max_iterations - 1) + [
        offered[-1]
    ]


def test_agents_without_final_tools_keep_offering_everything_to_the_end() -> None:
    config = ASSETS.agent("chat_monitor")
    llm = FakeLlm(Script(tool_response(call("get_my_alerts"))))
    go(make_engine(llm, config=config))
    assert len({len(r["tools"]) for r in llm.requests}) == 1
