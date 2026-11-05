"""Pruebas del cliente `ClaudeLlm` con un cliente falso (sin red)."""

import asyncio
import json
import os
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest
from cloud_adapter.claude_llm import (
    BINDING_BETA,
    ClaudeLlm,
    call_cost,
    read_key,
    to_anthropic_messages,
    to_anthropic_tools,
)

from ai_module.agent.llm import FatalLlmError, ModelMismatchError

PRICING = {"input": 0.10, "cache_write": 0.125, "cache_read": 0.01, "output": 0.50}
SAMPLING = {
    "temperature": 0,
    "top_p": 1.0,
    "presence_penalty": 0.0,
    "max_tokens": 4000,
    "tool_choice": "auto",
    "extra_body": {"top_k": -1, "repetition_penalty": 1.0, "reasoning_effort": "medium"},
}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "d",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


class Block:
    def __init__(self, **data: Any) -> None:
        self.data = data

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return dict(self.data)


def message(blocks, stop="end_turn", inp=100, out=20, read=0, write=0, thinking=None):
    details = None if thinking is None else SimpleNamespace(thinking_tokens=thinking)
    usage = SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        cache_read_input_tokens=read,
        cache_creation_input_tokens=write,
        output_tokens_details=details,
    )
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=usage, stop_details=None)


def text(t):
    return Block(type="text", text=t)


def tool_use(i, name="get_events", **args):
    return Block(type="tool_use", id=i, name=name, input=args)


def status_error(cls, status, body=None, headers=None):
    request = httpx.Request("POST", "http://api.test/v1/messages")
    response = httpx.Response(status, request=request, headers=headers or {}, json=body or {})
    return cls("error", response=response, body=body or {})


class FakeStream:
    def __init__(self, final):
        self.final = final
        self.text_stream = self._texts()

    async def _texts(self):
        for block in self.final.content:
            if block.data["type"] == "text":
                yield block.data["text"]

    async def get_final_message(self):
        return self.final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=self)
        self.models = SimpleNamespace(retrieve=self._retrieve)

    async def _retrieve(self, model, **_):
        return SimpleNamespace(id=model)

    def _next(self, params):
        self.calls.append(params)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def create(self, **params):
        return self._next(params)

    def stream(self, **params):
        return FakeStream(self._next(params))


def llm(script, **kw):
    sleeps: list[float] = []

    async def sleep(s):
        sleeps.append(s)

    client = FakeClient(script)
    return ClaudeLlm("claude-haiku-5-5", pricing=PRICING, client=client, sleep=sleep, **kw), (
        client,
        sleeps,
    )


def run(coro):
    return asyncio.run(coro)


# --- conversión ------------------------------------------------------------------------------


def test_tools_keep_name_description_and_schema():
    out = to_anthropic_tools(TOOLS)
    assert out == [
        {
            "name": "get_events",
            "description": "d",
            "input_schema": TOOLS[0]["function"]["parameters"],
        }
    ]


def test_tool_results_and_reminder_go_in_one_user_message_with_results_first():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "thinking out loud",
            "tool_calls": [
                {
                    "id": "t1",
                    "type": "function",
                    "function": {"name": "a", "arguments": '{"x": 1}'},
                },
                {"id": "t2", "type": "function", "function": {"name": "b", "arguments": "oops"}},
            ],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "r1"},
        {"role": "tool", "tool_call_id": "t2", "content": "r2"},
        {"role": "user", "content": "reminder"},
    ]
    system, out = to_anthropic_messages(messages)
    assert system == [{"type": "text", "text": "sys"}]
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assistant = out[1]["content"]
    assert [b["type"] for b in assistant] == ["text", "tool_use", "tool_use"]
    assert assistant[1]["input"] == {"x": 1} and assistant[2]["input"] == {}
    last = out[2]["content"]
    assert [b["type"] for b in last] == ["tool_result", "tool_result", "text"]


def test_empty_assistant_message_is_skipped():
    _, out = to_anthropic_messages(
        [{"role": "user", "content": "q"}, {"role": "assistant", "content": None}]
    )
    assert [m["role"] for m in out] == ["user"]


def test_raw_blocks_are_replayed_and_thinking_can_be_stripped():
    raw = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "tool_use", "id": "t1", "name": "a", "input": {}},
    ]
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "raw_blocks": raw, "tool_calls": []},
        {"role": "tool", "tool_call_id": "t1", "content": "r"},
    ]
    _, kept = to_anthropic_messages(messages)
    assert kept[1]["content"] == raw
    _, stripped = to_anthropic_messages(messages, keep_thinking=False)
    assert [b["type"] for b in stripped[1]["content"]] == ["tool_use"]


# --- petición --------------------------------------------------------------------------------


def request(messages=None, tools=TOOLS, sampling=None, **kw):
    sampling = sampling or SAMPLING
    script = kw.pop("script", [message([text("ok")])])
    adapter, (client, _) = llm(script)
    msgs = messages or [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    run(adapter.complete(msgs, tools, sampling, **kw))
    return client.calls[0]


def test_sampling_parameters_are_not_sent_and_effort_is():
    params = request()
    for forbidden in ("temperature", "top_p", "top_k", "presence_penalty", "repetition_penalty"):
        assert forbidden not in params
    assert params["output_config"] == {"effort": "medium"}
    assert params["max_tokens"] == 4000
    assert params["tool_choice"] == {"type": "auto"}


def test_default_thinking_is_adaptive_summarized_with_drop_block():
    params = request()
    assert params["thinking"] == {
        "type": "adaptive",
        "display": "summarized",
        "block_binding": {"prefix_mismatch_behavior": "drop_block"},
    }
    assert params["betas"] == [BINDING_BETA]


@pytest.mark.parametrize("mode", ["disabled", "between_tools"])
def test_thinking_off_modes_carry_no_other_field_and_no_beta(mode):
    sampling = {**SAMPLING, "extra_body": {**SAMPLING["extra_body"], "thinking_mode": mode}}
    params = request(sampling=sampling)
    assert params["thinking"] == {"type": mode}
    assert "betas" not in params


def test_between_tools_strips_thinking_blocks_from_history():
    raw = [{"type": "thinking", "thinking": "n", "signature": "s"}, tool_use("t1").data]
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "raw_blocks": raw},
        {"role": "tool", "tool_call_id": "t1", "content": "r"},
    ]
    sampling = {
        **SAMPLING,
        "extra_body": {"reasoning_effort": "medium", "thinking_mode": "between_tools"},
    }
    params = request(messages=messages, sampling=sampling)
    assert [b["type"] for b in params["messages"][1]["content"]] == ["tool_use"]


def test_required_maps_to_any():
    params = request(sampling={**SAMPLING, "tool_choice": "required"})
    assert params["tool_choice"] == {"type": "any"}


def test_cache_points_with_tools_and_none_without():
    with_tools = request()
    assert with_tools["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert with_tools["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    without = request(tools=[])
    assert without["system"] == "sys"
    assert "tools" not in without and "tool_choice" not in without
    assert "cache_control" not in json.dumps(without["messages"])


# --- respuesta -------------------------------------------------------------------------------


def test_response_with_tool_call_tokens_and_reasoning():
    reply = message(
        [Block(type="thinking", thinking="why", signature="s"), text("hi"), tool_use("t1", x=2)],
        stop="tool_use",
        inp=50,
        out=40,
        read=900,
        write=100,
        thinking=25,
    )
    adapter, _ = llm([reply])
    r = run(adapter.complete([{"role": "user", "content": "q"}], TOOLS, SAMPLING))
    assert [(c.id, c.name, json.loads(c.arguments)) for c in r.tool_calls] == [
        ("t1", "get_events", {"x": 2})
    ]
    assert r.content == "hi" and r.reasoning == "why" and r.finish_reason == "tool_calls"
    assert (r.prompt_tokens, r.completion_tokens) == (1050, 40)
    assert (r.cached_tokens, r.cache_write_tokens, r.reasoning_tokens) == (900, 100, 25)
    assert r.raw_blocks and r.raw_blocks[0]["type"] == "thinking"
    assert r.assistant_message()["raw_blocks"] == r.raw_blocks


def test_finish_reasons_and_refusal():
    adapter, _ = llm([message([text("cut")], stop="max_tokens"), message([], stop="refusal")])
    a = run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    b = run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    assert a.finish_reason == "length" and b.finish_reason == "refusal"
    assert b.content == "" and b.tool_calls == []


def test_streaming_delivers_text_to_on_delta():
    adapter, (client, _) = llm([message([text("hel"), text("lo")])])
    seen: list[str] = []

    async def on_delta(d):
        seen.append(d)

    r = run(
        adapter.complete(
            [{"role": "user", "content": "q"}], [], SAMPLING, stream=True, on_delta=on_delta
        )
    )
    assert seen == ["hel", "lo"] and r.content == "hello"


# --- errores y reintentos --------------------------------------------------------------------


def test_overloaded_then_rate_limit_are_retried_and_recorded():
    script = [
        status_error(anthropic.OverloadedError, 529),
        status_error(anthropic.RateLimitError, 429, headers={"retry-after": "3"}),
        message([text("ok")]),
    ]
    adapter, (client, sleeps) = llm(script)
    r = run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING, timeout_s=60))
    assert sleeps == [1.0, 3.0]
    assert [x["status"] for x in r.retries] == [529, 429] and len(client.calls) == 3


def test_retries_stop_after_the_last_delay():
    script = [status_error(anthropic.OverloadedError, 529)] * 6
    adapter, (client, _) = llm(script)
    with pytest.raises(anthropic.APIStatusError):
        run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING, timeout_s=600))
    assert len(client.calls) == 5


def test_retry_that_does_not_fit_in_the_timeout_gives_up():
    adapter, (client, _) = llm([status_error(anthropic.OverloadedError, 529), message([text("x")])])
    with pytest.raises(TimeoutError):
        run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING, timeout_s=0.5))
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "status,cls",
    [
        (400, anthropic.BadRequestError),
        (401, anthropic.AuthenticationError),
        (402, anthropic.APIStatusError),
        (403, anthropic.PermissionDeniedError),
    ],
)
def test_fatal_errors_stop_all_later_requests(status, cls):
    body = {"error": {"type": "invalid_request_error", "message": "credit balance is too low"}}
    adapter, (client, _) = llm([status_error(cls, status, body), message([text("never")])])
    with pytest.raises(FatalLlmError, match="credit balance"):
        run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    with pytest.raises(FatalLlmError):
        run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    assert len(client.calls) == 1


def test_spend_limit_is_fatal_not_retried():
    err = status_error(anthropic.EnforcedSpendLimitReachedError, 429)
    adapter, (client, sleeps) = llm([err, message([text("never")])])
    with pytest.raises(FatalLlmError, match="spend limit"):
        run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    assert sleeps == [] and len(client.calls) == 1


def test_run_cost_cap_stops_further_requests(monkeypatch):
    monkeypatch.setenv("LLM_RUN_CAP_USD", "0.0001")
    adapter, (client, _) = llm([message([text("a")], inp=10000), message([text("b")])])
    run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    with pytest.raises(FatalLlmError, match="cost cap"):
        run(adapter.complete([{"role": "user", "content": "q"}], [], SAMPLING))
    assert len(client.calls) == 1


# --- coste y clave ---------------------------------------------------------------------------


def test_call_cost_splits_fresh_cached_written_and_output():
    # 1050 de prompt: 900 leídos, 100 escritos, 50 nuevos; 40 de salida
    cost = call_cost(PRICING, 1050, 900, 100, 40)
    expected = (50 * 0.10 + 100 * 0.125 + 900 * 0.01 + 40 * 0.50) / 1e6
    assert cost == pytest.approx(expected)


def test_key_file_is_read_checked_and_never_in_repr(tmp_path):
    key = tmp_path / "k"
    key.write_text("fake-key-for-tests\n")
    os.chmod(key, 0o644)
    with pytest.raises(ModelMismatchError, match="600"):
        read_key(str(key))
    os.chmod(key, 0o600)
    assert read_key(str(key)) == "fake-key-for-tests"
    adapter = ClaudeLlm("m", api_key_file=str(key))
    assert "fake-key" not in repr(adapter)
    with pytest.raises(ModelMismatchError):
        read_key(str(tmp_path / "missing"))
    err = ""
    try:
        read_key(str(tmp_path / "missing"))
    except ModelMismatchError as exc:
        err = str(exc)
    assert "fake-key" not in err


def test_check_reports_a_rejected_model():
    adapter, (client, _) = llm([])

    async def bad(model, **_):
        raise status_error(anthropic.NotFoundError, 404)

    client.models = SimpleNamespace(retrieve=bad)
    with pytest.raises(ModelMismatchError, match="404"):
        run(adapter.check())
