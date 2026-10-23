"""Lanzador de experimentos: gestión del servidor (sin GPU) y una matriz completa con el LLM
falso de las pruebas (marca `e2e`)."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from ai_module.agent.profiles import Profile, load_profile

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "run_matrix", REPO / "tools" / "experiments" / "run_matrix.py"
)
assert spec and spec.loader
run_matrix = importlib.util.module_from_spec(spec)
sys.modules["run_matrix"] = run_matrix
spec.loader.exec_module(run_matrix)


class RecordingBackend:
    llm_url = None

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.up = False

    def prepare(self) -> None:
        self.calls.append("prepare")

    def start(self, profile: Profile) -> None:
        self.calls.append(f"start {profile.name}")
        self.up = True

    def stop(self) -> None:
        self.calls.append("stop")
        self.up = False

    def healthy(self) -> bool:
        return self.up

    def version(self) -> str:
        return "9.9"


def manager() -> tuple["run_matrix.ServerManager", RecordingBackend]:
    backend = RecordingBackend()
    return run_matrix.ServerManager(backend), backend


def test_qwen3_profiles_of_one_model_share_the_server_and_a_new_model_restarts_it() -> None:
    servers, backend = manager()
    for name in ("qwen3-14b-t0", "qwen3-14b-qwen", "qwen3-14b-think", "qwen3-30b-a3b-t0"):
        servers.ensure(load_profile(name))
    assert backend.calls == [
        "prepare", "start qwen3-14b-t0", "stop", "start qwen3-30b-a3b-t0",
    ]  # fmt: skip
    servers.close(keep=False)
    assert backend.calls[-1] == "stop" and not backend.up


def test_keep_server_leaves_it_running() -> None:
    servers, backend = manager()
    servers.ensure(load_profile("actual"))
    servers.close(keep=True)
    assert backend.up and backend.calls == ["prepare", "start actual"]


def test_a_server_that_went_down_stops_the_matrix_without_retry() -> None:
    servers, backend = manager()
    servers.ensure(load_profile("qwen3-14b-t0"))
    backend.up = False
    with pytest.raises(run_matrix.MatrixError, match="down"):
        servers.ensure(load_profile("qwen3-14b-think"))
    with pytest.raises(run_matrix.MatrixError, match="down"):
        servers.check()
    assert backend.calls == ["prepare", "start qwen3-14b-t0"]  # sin reintentos


def test_a_failure_to_start_or_to_free_the_gpu_propagates() -> None:
    servers, backend = manager()
    servers.ensure(load_profile("qwen3-14b-t0"))

    def stop_fails() -> None:
        raise run_matrix.MatrixError("the GPU is not free")

    backend.stop = stop_fails  # type: ignore[method-assign]
    with pytest.raises(run_matrix.MatrixError, match="GPU"):
        servers.ensure(load_profile("qwen3-30b-a3b-t0"))
    assert servers.current is None or servers.current.name == "qwen3-14b-t0"
    assert "start qwen3-30b-a3b-t0" not in backend.calls


def test_the_plan_goes_profile_by_profile() -> None:
    runs = run_matrix.plan(["a", "b"], ["s1", "s2"], 2)
    assert [(r.profile, r.scenario, r.rep) for r in runs][:5] == [
        ("a", "s1", 1), ("a", "s1", 2), ("a", "s2", 1), ("a", "s2", 2), ("b", "s1", 1),
    ]  # fmt: skip
    assert len(runs) == 8


def test_the_questions_are_the_script_in_demo_and_one_final_question_elsewhere() -> None:
    args = run_matrix.parse(["--profiles", "actual", "--scenarios", "demo", "--id", "t"])
    demo = run_matrix.run_command(run_matrix.RunSpec("actual", "demo", 1), args, None)
    asks = [demo[i + 1] for i, x in enumerate(demo) if x == "--ask"]
    assert (
        len(asks) == 3 and asks[0].startswith("monitor:110:") and asks[2].startswith("report:end:")
    )
    wind = run_matrix.run_command(run_matrix.RunSpec("actual", "wind", 1), args, None)
    assert [wind[i + 1] for i, x in enumerate(wind) if x == "--ask"] == [run_matrix.OTHER_ASKS[0]]
    assert "--wait-agent" in wind and wind[wind.index("--speed") + 1] == "16"
    assert wind[wind.index("--profile") + 1] == "actual"


@pytest.mark.e2e
def test_full_matrix_with_the_fake_llm_two_models_two_repetitions() -> None:
    folder = run_matrix.EXPERIMENTS / "pytest-fake"
    shutil.rmtree(folder, ignore_errors=True)
    code = run_matrix.main(
        ["--fake", "--id", "pytest-fake", "--profiles", "qwen3-14b-t0,qwen3-30b-a3b-t0",
         "--scenarios", "nominal", "--reps", "2"]
    )  # fmt: skip
    try:
        assert code == 0
        manifest = json.loads((folder / "manifest.json").read_text())
        assert [r["status"] for r in manifest["runs"]] == ["ok"] * 4
        assert set(manifest["profiles"]) == {"qwen3-14b-t0", "qwen3-30b-a3b-t0"}
        assert manifest["profiles"]["qwen3-14b-t0"]["fingerprint"]
        assert (
            manifest["assets_fingerprint"].startswith("e28d071e856efb09")
            or manifest["assets_fingerprint"]
        )
        assert manifest["vllm_version"] == "fake" and manifest["git"]["commit"]
        for profile in manifest["profiles"]:
            for rep in (1, 2):
                run = folder / "runs" / profile / "nominal" / f"r{rep}"
                assert (run / "eval.json").exists() and (run / "profile.json").exists()
                assert json.loads((run / "profile.json").read_text())["profile"] == profile
        text = (folder / "compare.md").read_text()
        assert "## nominal" in text and "`qwen3-30b-a3b-t0`" in text and "estable (2/2)" in text
    finally:
        shutil.rmtree(folder, ignore_errors=True)
