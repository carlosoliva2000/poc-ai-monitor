"""Cliente LLM alternativo de pago: configuración, coste, libro de cuentas y presupuesto de
`run_matrix` (sin red y sin ningún proveedor concreto)."""

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from ai_module.agent.assets import Assets
from ai_module.agent.llm import ModelMismatchError, load_adapter
from ai_module.agent.profiles import ProfileError, load_profile

REPO = Path(__file__).resolve().parents[2]


def load_tool(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        name, REPO / "tools" / "experiments" / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"paid_{name}"] = module
    spec.loader.exec_module(module)
    return module


cost = load_tool("cost")
run_matrix = load_tool("run_matrix")
PRICING = {"input": 1.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}


def write_profile(directory: Path, body: str) -> None:
    (directory / "paid.yaml").write_text(
        "llm:\n  model: some-model\n  adapter: 'pkg.mod:Client'\n  adapter_path: pkg-dir\n"
        "  api_key_file: ~/k\n"
        "  pricing: {input: 1.0, cache_write: 1.25, cache_read: 0.1, output: 5.0}\n" + body,
        encoding="utf-8",
    )


# --- configuración ---------------------------------------------------------------------------


def test_a_profile_without_server_carries_adapter_pricing_and_thinking(tmp_path: Path) -> None:
    write_profile(
        tmp_path,
        "sampling:\n  reasoning: null\n  reasoning_effort: medium\n  thinking: between_tools\n",
    )
    profile = load_profile("paid", tmp_path)
    assets = Assets(profile=profile)
    assert assets.llm.adapter == "pkg.mod:Client"
    assert assets.llm.pricing == PRICING and assets.llm.api_key_file == "~/k"
    config = assets.agent("monitor")
    assert config.thinking == "between_tools"
    assert config.sampling()["extra_body"]["thinking_mode"] == "between_tools"
    assert config.effective()["thinking"] == "between_tools"


def test_without_thinking_the_request_has_no_new_key() -> None:
    sampling = Assets(profile=load_profile("actual")).agent("monitor").sampling()
    assert "thinking_mode" not in sampling["extra_body"]


def test_a_profile_may_set_the_state_line(tmp_path: Path) -> None:
    write_profile(tmp_path, "agents:\n  monitor:\n    state_line: data\n")
    assert Assets(profile=load_profile("paid", tmp_path)).agent("monitor").state_line == "data"


def test_unknown_llm_keys_are_still_rejected(tmp_path: Path) -> None:
    write_profile(tmp_path, "")
    text = (tmp_path / "paid.yaml").read_text(encoding="utf-8")
    (tmp_path / "paid.yaml").write_text(text.replace("pricing:", "price:"), encoding="utf-8")
    with pytest.raises(ProfileError, match="unknown key llm.price"):
        load_profile("paid", tmp_path)


def test_a_bad_adapter_spec_or_module_is_a_clear_error() -> None:
    with pytest.raises(ModelMismatchError, match="module:Class"):
        load_adapter("nomodule")
    with pytest.raises(ModelMismatchError, match="cannot load"):
        load_adapter("no_such_module_xyz:Client")


# --- coste -----------------------------------------------------------------------------------


def trace_line(agent: str, calls: list[dict[str, Any]], max_tokens: int = 1000) -> str:
    return json.dumps({"agent": agent, "sampling": {"max_tokens": max_tokens}, "calls": calls})


def test_trace_cost_splits_cached_written_fresh_and_output(tmp_path: Path) -> None:
    trace = tmp_path / "t.jsonl"
    call = {
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "cached_tokens": 600,
        "cache_write_tokens": 200,
        "reasoning_tokens": 40,
    }
    trace.write_text(trace_line("monitor", [call]) + "\n", encoding="utf-8")
    total = cost.trace_cost(trace, PRICING)
    expected = (200 * 1.0 + 200 * 1.25 + 600 * 0.1 + 100 * 5.0) / 1e6
    assert total["cost_usd"] == pytest.approx(expected)
    assert (total["prompt"], total["cache_read"], total["reasoning"]) == (1000, 600, 40)
    assert total["estimated_calls"] == 0


def test_a_call_without_usage_is_counted_with_an_upper_bound(tmp_path: Path) -> None:
    ok = {"prompt_tokens": 2000, "completion_tokens": 10}
    lost = {"prompt_tokens": 0, "completion_tokens": 0, "content": "[TimeoutError] x"}
    trace = tmp_path / "t.jsonl"
    trace.write_text(trace_line("monitor", [ok, lost], max_tokens=500) + "\n", encoding="utf-8")
    total = cost.trace_cost(trace, PRICING)
    bound = (2000 * 1.0 + 500 * 5.0) / 1e6
    assert total["estimated_calls"] == 1
    assert total["cost_usd"] == pytest.approx((2000 * 1.0 + 10 * 5.0) / 1e6 + bound)


def test_estimate_uses_the_defaults_then_the_largest_measured_run() -> None:
    ledger: dict[str, Any] = {"budget_usd": 3.0, "entries": []}
    first = cost.estimate_usd(ledger, "model-sonnet-x", "demo", series_b=False)
    assert first == cost.DEFAULT_ESTIMATE[("sonnet", "demo")]
    assert cost.estimate_usd(ledger, "model-sonnet-x", "demo", series_b=True) == pytest.approx(
        first * cost.SERIES_B_FACTOR
    )
    ledger["entries"] += [
        {"kind": "run", "model": "model-sonnet-x", "scenario": "demo", "cost_usd": 0.2},
        {"kind": "run", "model": "model-sonnet-x", "scenario": "demo", "cost_usd": 0.3},
    ]
    assert cost.estimate_usd(ledger, "model-sonnet-x", "demo", False) == pytest.approx(0.36)
    assert cost.spent_usd(ledger) == pytest.approx(0.5)


# --- run_matrix ------------------------------------------------------------------------------


def paid_profile(tmp_path: Path) -> Any:
    write_profile(tmp_path, "")
    return load_profile("paid", tmp_path)


def args_for(tmp_path: Path, budget: float | None) -> Namespace:
    return Namespace(budget_usd=budget, ledger=tmp_path / "ledger.json", id="exp")


def test_a_paid_profile_needs_a_budget(tmp_path: Path) -> None:
    profiles = {"paid": paid_profile(tmp_path), "actual": load_profile("actual")}
    assert run_matrix.uses_adapter(profiles["paid"])
    assert not run_matrix.uses_adapter(profiles["actual"])
    with pytest.raises(run_matrix.MatrixError, match="--budget-usd"):
        run_matrix.require_budget(profiles, None)
    run_matrix.require_budget(profiles, 3.0)
    run_matrix.require_budget({"actual": profiles["actual"]}, None)


def test_the_run_is_not_launched_when_the_estimate_does_not_fit(tmp_path: Path) -> None:
    profile = paid_profile(tmp_path)
    spec = run_matrix.RunSpec("paid", "faults", 1)
    args = args_for(tmp_path, budget=0.29)
    ledger = {"budget_usd": 0.29, "entries": [{"kind": "run", "cost_usd": 0.25, "model": "m"}]}
    cost.save_ledger(ledger, args.ledger)
    with pytest.raises(run_matrix.MatrixError, match="not launched"):
        run_matrix.paid_environment(spec, profile, args)


def test_the_environment_carries_the_package_and_the_remaining_budget(tmp_path: Path) -> None:
    profile = paid_profile(tmp_path)
    spec = run_matrix.RunSpec("paid", "demo", 1)
    args = args_for(tmp_path, budget=3.0)
    cost.save_ledger({"budget_usd": 3.0, "entries": [{"kind": "x", "cost_usd": 1.0}]}, args.ledger)
    env = run_matrix.paid_environment(spec, profile, args)
    assert env["LLM_RUN_CAP_USD"] == "2.0000"
    assert env["AI_MODULE_UV_ARGS"].endswith("pkg-dir")


def test_a_fatal_error_in_the_trace_is_detected(tmp_path: Path) -> None:
    trace = tmp_path / "t.jsonl"
    fatal = {"prompt_tokens": 0, "completion_tokens": 0, "content": "[FatalLlmError] HTTP 400"}
    trace.write_text(trace_line("monitor", [fatal]) + "\n", encoding="utf-8")
    assert run_matrix.fatal_error(trace) == "[FatalLlmError] HTTP 400"
    clean = tmp_path / "c.jsonl"
    clean.write_text(trace_line("monitor", [{"prompt_tokens": 5, "completion_tokens": 1}]) + "\n")
    assert run_matrix.fatal_error(clean) is None
    with pytest.raises(run_matrix.MatrixError, match="fatal"):
        run_matrix.stop_if_paid_run_failed({"status": "ok", "fatal": "x"})
    with pytest.raises(run_matrix.MatrixError, match="failed"):
        run_matrix.stop_if_paid_run_failed({"status": "failed", "error": "boom"})
    run_matrix.stop_if_paid_run_failed({"status": "ok"})


def test_a_paid_profile_without_the_package_path_is_a_clear_error(tmp_path: Path) -> None:
    write_profile(tmp_path, "")
    text = (tmp_path / "paid.yaml").read_text(encoding="utf-8")
    (tmp_path / "paid.yaml").write_text(
        text.replace("  adapter_path: pkg-dir\n", ""), encoding="utf-8"
    )
    profile = load_profile("paid", tmp_path)
    args = args_for(tmp_path, budget=3.0)
    with pytest.raises(run_matrix.MatrixError, match="adapter_path"):
        run_matrix.paid_environment(run_matrix.RunSpec("paid", "demo", 1), profile, args)
