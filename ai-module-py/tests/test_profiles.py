"""Perfiles de modelo: validación, mezcla sobre `agents.yaml`, huellas y `profile.json`."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from agent_helpers import FakeLlm, FakePlatform, Script, text_response

from ai_module.agent.assets import Assets
from ai_module.agent.profiles import (
    DEFAULT_PROFILES,
    ProfileError,
    assets_fingerprint,
    list_profiles,
    load_profile,
)
from ai_module.runtime import Runtime

REPO = Path(__file__).resolve().parents[2]
NAMES = [
    "actual",
    "qwen3-14b-t0",
    "qwen3-14b-qwen",
    "qwen3-14b-think",
    "qwen3-30b-a3b-t0",
    "qwen3-30b-a3b-qwen",
    "qwen3-30b-a3b-think",
]
AGENTS = ("monitor", "chat_monitor", "report", "chat_report")


def write_profile(tmp_path: Path, name: str, content: dict) -> Path:
    (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump(content), encoding="utf-8")
    return tmp_path


def test_the_seven_initial_profiles_exist_and_load() -> None:
    assert set(NAMES) <= set(list_profiles())
    for name in NAMES:
        profile = load_profile(name)
        assets = Assets(profile=profile)
        assert assets.llm.model == profile.server["model"]
        for agent in AGENTS:
            assets.agent(agent)  # no falla


def test_unknown_sections_and_keys_are_errors(tmp_path: Path) -> None:
    for bad in (
        {"prompts": {"monitor": "x"}},
        {"sampling": {"system_prompt": "x"}},
        {"agents": {"monitor": {"tools": []}}},
        {"agents": {"nobody": {"temperature": 1}}},
        {"server": {"model": "m"}},  # sin tool_call_parser
    ):
        directory = write_profile(tmp_path, "bad", bad)
        with pytest.raises(ProfileError):
            load_profile("bad", directory)
    with pytest.raises(ProfileError):
        load_profile("does-not-exist", tmp_path)


@pytest.mark.parametrize("model", ["Qwen/Qwen3.5-27B-GPTQ-Int4", "amd/Qwen3.8-27B-Quark-AWQ-INT4"])
def test_hybrid_27b_models_are_forbidden(tmp_path: Path, model: str) -> None:
    server = {"model": model, "tool_call_parser": "hermes"}
    with pytest.raises(ProfileError, match="forbidden"):
        load_profile("x", write_profile(tmp_path, "x", {"server": server}))


def test_monitor_invocation_must_fit_in_the_platform_wait(tmp_path: Path) -> None:
    content = {
        "server": {"model": "Qwen/Qwen3-14B-AWQ", "tool_call_parser": "hermes"},
        "agents": {"monitor": {"max_invocation_s": 320}},
        "platform": {"wait_agent_timeout_s": 330},
    }
    profile = load_profile("p", write_profile(tmp_path, "p", content))
    with pytest.raises(ProfileError, match="platform wait"):
        Assets(profile=profile)  # 320 + 15 >= 330


def test_actual_changes_nothing_and_sends_no_thinking_switch() -> None:
    plain = Assets()
    actual = Assets(profile=load_profile("actual"))
    for name in AGENTS:
        assert actual.agent(name) == plain.agent(name)
    assert "chat_template_kwargs" not in actual.agent("monitor").sampling()["extra_body"]


@pytest.mark.parametrize("size", ["14b", "30b-a3b"])
def test_t0_profiles_keep_temperature_zero_and_ask_for_no_reasoning(size: str) -> None:
    assets = Assets(profile=load_profile(f"qwen3-{size}-t0"))
    monitor = assets.agent("monitor").sampling()
    assert monitor["temperature"] == 0 and monitor["extra_body"]["repetition_penalty"] == 1.05
    assert monitor["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert assets.agent("report").temperature == 0.7  # el informe, como hoy


@pytest.mark.parametrize("size", ["14b", "30b-a3b"])
def test_qwen_and_think_profiles_use_the_official_sampling_in_every_agent(size: str) -> None:
    for kind, (temperature, top_p, thinking) in {
        "qwen": (0.7, 0.8, False),
        "think": (0.6, 0.95, True),
    }.items():
        assets = Assets(profile=load_profile(f"qwen3-{size}-{kind}"))
        for name in AGENTS:
            s = assets.agent(name).sampling()
            assert (s["temperature"], s["top_p"], s["presence_penalty"]) == (
                temperature,
                top_p,
                1.5,
            )
            assert s["extra_body"]["top_k"] == 20 and s["extra_body"]["repetition_penalty"] == 1.0
            assert s["extra_body"]["chat_template_kwargs"] == {"enable_thinking": thinking}


def test_think_profiles_raise_max_tokens_and_times() -> None:
    assets = Assets(profile=load_profile("qwen3-14b-think"))
    assert assets.agent("monitor").max_tokens == 4000 and assets.agent("report").max_tokens == 6000
    # Lo que importa: los tiempos del perfil cumplen la condición con la espera de la plataforma.
    monitor = assets.agent("monitor")
    assert monitor.max_invocation_s + 15 < load_profile("qwen3-14b-think").wait_agent_timeout_s


def test_aids_and_chat_switches_can_come_from_a_profile(tmp_path: Path) -> None:
    content = {
        "server": {"model": "Qwen/Qwen3-14B-AWQ", "tool_call_parser": "hermes"},
        "agents": {"monitor": {"coherence_guardrail": False, "tool_choice": "auto"}},
        "chat": {"tools_enabled": True},
    }
    profile = load_profile("p", write_profile(tmp_path, "p", content))
    assets = Assets(profile=profile)
    monitor = assets.agent("monitor")
    assert monitor.coherence_guardrail is False and monitor.tool_choice == "auto"
    assert assets.chat_tools_enabled is True


def test_a_profile_never_touches_the_files_of_agent_assets() -> None:
    before = assets_fingerprint()
    Assets(profile=load_profile("qwen3-14b-think"))
    assert assets_fingerprint() == before


def test_assets_fingerprint_matches_the_shell_command() -> None:
    out = subprocess.run(
        "find agent-assets -type f | sort | xargs sha256sum | sha256sum",
        shell=True, cwd=REPO, capture_output=True, text=True, check=True,
        env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
    ).stdout.split()[0]  # fmt: skip
    assert assets_fingerprint() == out


def test_profile_fingerprint_is_the_hash_of_the_file() -> None:
    profile = load_profile("qwen3-14b-t0")
    data = (DEFAULT_PROFILES / "qwen3-14b-t0.yaml").read_bytes()
    assert profile.fingerprint == hashlib.sha256(data).hexdigest()


def test_serve_args_keep_reasoning_on_in_the_server() -> None:
    args = load_profile("qwen3-14b-think").serve_args(8000)
    assert args[:2] == ["serve", "Qwen/Qwen3-14B-AWQ"]
    assert args[args.index("--reasoning-parser") + 1] == "qwen3"
    assert "--default-chat-template-kwargs" not in args  # cada petición decide
    assert "--enable-auto-tool-choice" in args and "hermes" in args
    assert "--reasoning-parser" not in load_profile("actual").serve_args()
    assert load_profile("qwen3-14b-t0").server_signature() == (
        load_profile("qwen3-14b-think").server_signature()
    )  # los Qwen3 comparten servidor
    assert load_profile("qwen3-14b-t0").server_signature() != (
        load_profile("qwen3-30b-a3b-t0").server_signature()
    )


def test_profile_json_is_written_with_the_effective_parameters(tmp_path: Path) -> None:
    profile = load_profile("qwen3-14b-qwen")
    rt = Runtime(
        Assets(profile=profile), FakeLlm(Script(text_response("x"))), "http://p", _noop,
        tmp_path, platform_call=FakePlatform(),
    )  # fmt: skip
    assert rt.set_run("nominal", "20261023-000000")
    info = json.loads((tmp_path / "nominal" / "20261023-000000" / "profile.json").read_text())
    assert info["profile"] == "qwen3-14b-qwen"
    assert info["profile_fingerprint"] == profile.short
    assert info["assets_fingerprint"] == assets_fingerprint()[:16]
    assert info["agents"]["monitor"]["presence_penalty"] == 1.5
    assert info["agents"]["monitor"]["reasoning"] is False
    assert info["agents"]["monitor"]["aids"]["tool_choice"] == "required"
    assert info["wait_agent_timeout_s"] == 90.0


async def _noop(event: object) -> None:
    return None
