"""Comprobación al arrancar de que vLLM sirve el modelo de la configuración."""

import asyncio
import socket

import pytest

from ai_module.__main__ import run as run_module
from ai_module.agent.llm import ModelMismatchError, check_served_model
from ai_module.testing.fake_llm import FakeLlmServer, default_model, demo_policy


def check(url: str, expected: str, profile: str | None) -> list[str]:
    return asyncio.run(check_served_model(url, "EMPTY", expected, profile))


def test_the_served_model_matches() -> None:
    with FakeLlmServer(demo_policy, model="Qwen/Qwen3-14B-AWQ") as server:
        assert check(server.url, "Qwen/Qwen3-14B-AWQ", "actual") == ["Qwen/Qwen3-14B-AWQ"]


def test_the_default_configuration_expects_what_the_fake_serves_by_default() -> None:
    with FakeLlmServer(demo_policy) as server:
        assert check(server.url, default_model(), None)


def test_a_different_model_stops_with_both_names_and_the_profile() -> None:
    with (
        FakeLlmServer(demo_policy, model="Qwen/Qwen3-14B-AWQ") as server,
        pytest.raises(ModelMismatchError) as error,
    ):
        check(server.url, "Qwen/Qwen2.5-14B-Instruct-AWQ", "qwen2.5-14b")
    text = str(error.value)
    assert "serves Qwen/Qwen3-14B-AWQ" in text
    assert "expects Qwen/Qwen2.5-14B-Instruct-AWQ" in text
    assert "profile qwen2.5-14b" in text


def test_without_a_profile_the_message_says_so() -> None:
    with (
        FakeLlmServer(demo_policy, model="other") as server,
        pytest.raises(ModelMismatchError, match=r"no profile \(agents.yaml\)"),
    ):
        check(server.url, "Qwen/Qwen3-14B-AWQ", None)


def test_a_server_that_is_down_is_reported_clearly() -> None:
    with socket.socket() as s:  # puerto libre: nadie escucha
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(ModelMismatchError, match="does not answer GET /models"):
        check(f"http://127.0.0.1:{port}/v1", "Qwen/Qwen3-14B-AWQ", "actual")


def test_the_module_does_not_start_with_the_wrong_model() -> None:
    with (
        FakeLlmServer(demo_policy, model="another-model") as server,
        pytest.raises(SystemExit, match="another-model"),
    ):
        asyncio.run(run_module("http://127.0.0.1:1", llm_url=server.url, profile="qwen2.5-14b"))


def test_detector_only_does_not_check_the_llm() -> None:
    """Sin agentes no hace falta LLM: con la URL caída no se para por la comprobación."""

    async def scenario() -> BaseException | None:
        task = asyncio.create_task(
            run_module("http://127.0.0.1:1", detector_only=True, llm_url="http://127.0.0.1:1/v1")
        )
        await asyncio.sleep(0.3)
        error = task.exception() if task.done() else None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return error

    assert not isinstance(asyncio.run(scenario()), SystemExit)
