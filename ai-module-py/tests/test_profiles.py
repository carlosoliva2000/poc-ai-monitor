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


def test_actual_changes_nothing_and_turns_the_reasoning_off_per_request() -> None:
    """`actual` es «agents.yaml sin cambios»: Qwen3-14B sin razonamiento (desde la Fase 10)."""
    plain = Assets()
    actual = Assets(profile=load_profile("actual"))
    for name in AGENTS:
        assert actual.agent(name) == plain.agent(name)
    extra = actual.agent("monitor").sampling()["extra_body"]
    assert extra["chat_template_kwargs"] == {"enable_thinking": False}
    assert actual.llm.model == "Qwen/Qwen3-14B-AWQ"


def test_actual_is_the_old_t0_profile_and_qwen25_is_the_old_reference() -> None:
    """Antes de la Fase 10: `actual` = Qwen2.5 y `qwen3-14b-t0` = Qwen3 sin razonamiento."""
    t0 = Assets(profile=load_profile("qwen3-14b-t0"))
    actual = Assets(profile=load_profile("actual"))
    for name in AGENTS:
        assert actual.agent(name) == t0.agent(name)
    assert (
        load_profile("actual").server_signature() == load_profile("qwen3-14b-t0").server_signature()
    )
    old = load_profile("qwen2.5-14b")
    assert old.server_signature()["model"] == "Qwen/Qwen2.5-14B-Instruct-AWQ"
    assert "--reasoning-parser" not in old.serve_args()


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
    assert "--reasoning-parser" not in load_profile("qwen2.5-14b").serve_args()
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


def test_existing_profiles_send_the_same_requests_as_before_reasoning_effort() -> None:
    """`reasoning_effort` y `reasoning_field` no cambian nada con su valor por defecto: la petición
    de `actual` es exactamente la de antes y ningún otro perfil añade claves nuevas."""
    sampling = Assets(profile=load_profile("actual")).agent("monitor").sampling()
    assert set(sampling) == {
        "temperature",
        "top_p",
        "presence_penalty",
        "max_tokens",
        "tool_choice",
        "extra_body",
    }
    assert sampling["extra_body"] == {
        "top_k": sampling["extra_body"]["top_k"],
        "repetition_penalty": 1.05,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    for name in list_profiles():
        # gpt-oss fija el esfuerzo; un cliente alternativo (`llm.adapter`) envía otras claves
        if name in ("gpt-oss-20b-low",) or load_profile(name).raw.get("llm", {}).get("adapter"):
            continue
        for agent in AGENTS:
            config = Assets(profile=load_profile(name)).agent(agent)
            assert set(config.sampling()["extra_body"]) <= {
                "top_k",
                "repetition_penalty",
                "chat_template_kwargs",
            }, (name, agent)
            assert config.reasoning_effort is None and config.reasoning_field == "reasoning_content"
            assert "reasoning_effort" not in config.effective()
            assert "reasoning_field" not in config.effective()


def test_a_profile_can_set_the_reasoning_effort_and_the_returned_reasoning_field(
    tmp_path: Path,
) -> None:
    directory = write_profile(
        tmp_path,
        "harmony",
        {
            "server": {"model": "openai/gpt-oss-20b", "tool_call_parser": "openai"},
            "sampling": {
                "reasoning": None,
                "reasoning_effort": "low",
                "reasoning_field": "reasoning",
            },
        },
    )
    config = Assets(profile=load_profile("harmony", directory)).agent("monitor")
    extra = config.sampling()["extra_body"]
    assert extra["reasoning_effort"] == "low" and "chat_template_kwargs" not in extra
    assert config.effective()["reasoning_effort"] == "low"
    assert config.reasoning_field == "reasoning"


def test_the_assistant_message_returns_the_reasoning_in_the_configured_field() -> None:
    from ai_module.agent.llm import LlmResponse

    response = LlmResponse(content="", reasoning="because")
    assert response.assistant_message()["reasoning_content"] == "because"
    message = response.assistant_message("reasoning")
    assert message["reasoning"] == "because" and "reasoning_content" not in message


def test_server_env_is_validated_and_part_of_the_server_signature(tmp_path: Path) -> None:
    server = {"model": "m/x", "tool_call_parser": "hermes"}
    ok = write_profile(tmp_path, "ok", {"server": {**server, "env": {"VLLM_USE_DEEP_GEMM": "0"}}})
    profile = load_profile("ok", ok)
    assert profile.server_env() == {"VLLM_USE_DEEP_GEMM": "0"}
    assert profile.server_signature()["env"] == {"VLLM_USE_DEEP_GEMM": "0"}
    assert load_profile("qwen3-14b-fp8").server_env() == {"VLLM_USE_DEEP_GEMM": "0"}
    assert load_profile("actual").server_env() == {}
    for bad in ({"lower": "1"}, {"VAR": 0}, ["VAR"], {"A B": "1"}):
        folder = write_profile(tmp_path, "bad", {"server": {**server, "env": bad}})
        with pytest.raises(ProfileError):
            load_profile("bad", folder)


def test_assets_key_picks_a_frozen_copy_and_keeps_its_fingerprint() -> None:
    """`assets: agent-assets-v13` (Fase 14.1): textos de la Fase 13 con su huella de entonces."""
    profile = load_profile("actual-textos-v13")
    assert profile.assets_dir == REPO / "agent-assets-v13"
    assert assets_fingerprint(profile.assets_dir)[:16] == "293927dd0c038af5"
    assets = Assets(profile.assets_dir, profile)
    assert assets.profile_info()["assets"] == "agent-assets-v13"
    # la copia congelada no lleva la clave nueva: sin ella el bloque `now` no llega al modelo
    assert assets.agent("monitor").now_facts is False
    assert Assets().agent("monitor").now_facts is True
    assert load_profile("actual").assets_dir == REPO / "agent-assets"


@pytest.mark.parametrize("value", ["../agent-assets", "other", "agent-assets/x", 3])
def test_assets_key_only_accepts_agent_assets_folders(tmp_path: Path, value: object) -> None:
    directory = write_profile(tmp_path, "p", {"assets": value})
    with pytest.raises(ProfileError, match="assets"):
        load_profile("p", directory)


def test_assets_key_needs_an_existing_folder(tmp_path: Path) -> None:
    directory = write_profile(tmp_path, "p", {"assets": "agent-assets-does-not-exist"})
    with pytest.raises(ProfileError, match="does not exist"):
        load_profile("p", directory)


def test_the_now_block_is_stripped_when_now_facts_is_off() -> None:
    from ai_module.agent.tools import strip_computed_facts, strip_now_facts

    result = {
        "since": 0,
        "wind": {"notable": True},
        "gps_radar": {"disagreed": False},
        "now": {"x": 1},
    }
    assert "now" not in strip_now_facts(result) and "gps_radar" in strip_now_facts(result)
    assert "now" not in strip_computed_facts(result)  # sin hechos calculados tampoco hay `now`
    assert strip_now_facts("text") == "text"
