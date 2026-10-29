"""`tools/vllm/serve.sh` con un `vllm` y un `nvidia-smi` falsos: sin GPU ni modelos."""

import contextlib
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SERVE = REPO / "tools" / "vllm" / "serve.sh"

FAKE_VLLM = """#!/usr/bin/env bash
# vllm falso: `serve --help=all` lista flags; `serve MODEL --port N` abre /health y /version
if [ "$2" = "--help=all" ]; then
  echo "--tool-call-parser {hermes,mistral} --max-model-len --enable-auto-tool-choice"
  echo "--reasoning-parser"
  exit 0
fi
while [ $# -gt 0 ]; do [ "$1" = "--port" ] && PORT="$2"; shift; done
exec python3 -c "
import http.server  # vllm falso
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{\\"version\\":\\"0.0-fake\\"}'
        self.send_response(200); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(('127.0.0.1', $PORT), H).serve_forever()
"
"""
FAKE_SMI = """#!/usr/bin/env bash
case "$*" in
  *query-gpu*) cat "$FAKE_GPU_FILE";;
  *) echo "";;
esac
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.port = free_port()
        self.state = tmp_path / "state"
        self.cache = tmp_path / "hf"
        (self.cache / "models--Qwen--Qwen3-14B-AWQ" / "snapshots" / "abc").mkdir(parents=True)
        self.gpu = tmp_path / "gpu"
        self.gpu.write_text("100\n")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name, content in (("vllm", FAKE_VLLM), ("nvidia-smi", FAKE_SMI)):
            (bin_dir / name).write_text(content)
            (bin_dir / name).chmod(0o755)
        self.vars = {
            **os.environ,
            "VLLM_BIN": str(bin_dir / "vllm"),
            "NVIDIA_SMI": str(bin_dir / "nvidia-smi"),
            "FAKE_GPU_FILE": str(self.gpu),
            "SERVE_PORT": str(self.port),
            "SERVE_STATE_DIR": str(self.state),
            "HF_CACHE": str(self.cache),
            "GPU_TIMEOUT_S": "4",
            "START_TIMEOUT_S": "60",
        }

    def serve(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SERVE), *args], cwd=REPO, text=True, capture_output=True, check=False,
            env={**self.vars, **env}, timeout=120,
        )  # fmt: skip

    def pid(self) -> int | None:
        path = self.state / "vllm.pid"
        return int(path.read_text()) if path.exists() else None


@pytest.fixture
def env(tmp_path: Path):
    e = Env(tmp_path)
    yield e
    pid = e.pid()
    if pid:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"


def test_dry_run_prints_the_command_and_starts_nothing(env: Env) -> None:
    result = env.serve("start", "qwen3-14b-think", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "--reasoning-parser qwen3" in result.stdout and "HF_HUB_OFFLINE=1" in result.stdout
    assert "--default-chat-template-kwargs" not in result.stdout
    assert env.pid() is None


def test_a_forbidden_model_is_refused(env: Env, tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    server = {"model": "Qwen/Qwen3.5-27B-GPTQ-Int4", "tool_call_parser": "hermes"}
    (profiles / "big.yaml").write_text(yaml.safe_dump({"server": server}))
    result = env.serve("start", "big", MODEL_PROFILES_DIR=str(profiles))
    assert result.returncode == 2 and "forbidden" in result.stderr


def test_a_model_not_in_the_cache_is_not_downloaded(env: Env) -> None:
    result = env.serve("start", "qwen3-30b-a3b-t0")
    assert result.returncode == 4 and "not in the Hugging Face cache" in result.stderr
    assert env.pid() is None


def test_a_server_that_i_did_not_launch_is_never_touched(env: Env) -> None:
    foreign = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(env.port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        time.sleep(1)
        start = env.serve("start", "qwen3-14b-t0")
        assert start.returncode == 3 and "did not launch" in start.stderr
        stop = env.serve("stop")
        assert stop.returncode == 3
        assert foreign.poll() is None  # sigue vivo
    finally:
        foreign.kill()


def test_start_reuse_refuse_a_second_one_and_stop(env: Env) -> None:
    started = env.serve("start", "qwen3-14b-t0")
    assert started.returncode == 0, started.stdout + started.stderr
    pid = env.pid()
    assert pid and alive(pid)
    assert (env.state / "vllm.profile").read_text().strip() == "qwen3-14b-t0"
    assert list(env.state.glob("*_qwen3-14b-t0.json"))  # versión y tiempo hasta /health
    assert "0.0-fake" in next(env.state.glob("*_qwen3-14b-t0.json")).read_text()
    again = env.serve("start", "qwen3-14b-t0")
    assert again.returncode == 0 and "already running" in again.stdout
    other = env.serve("start", "qwen3-14b-think")  # mismo modelo, pero un servidor cada vez
    assert other.returncode == 3 and "stop it first" in other.stderr
    assert "my server is running" in env.serve("status").stdout
    stopped = env.serve("stop")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert env.pid() is None and not alive(pid)
    assert "no server running" in env.serve("status").stdout


def test_stop_waits_for_the_gpu_and_fails_when_it_is_not_released(env: Env) -> None:
    env.gpu.write_text("100\n")
    assert env.serve("gpu-idle").returncode == 0
    assert (env.state / "gpu_idle_mib").read_text().strip() == "100"
    assert env.serve("start", "qwen3-14b-t0").returncode == 0
    env.gpu.write_text("20000\n")  # la GPU no se libera
    stopped = env.serve("stop")
    assert stopped.returncode == 7 and "GPU is not free" in stopped.stderr
    env.gpu.write_text("300\n")  # reposo (100) + margen (512): libre
    assert env.serve("stop").returncode == 0  # ya no hay servidor: nada que parar
    again = env.serve("start", "qwen3-14b-t0")
    assert again.returncode == 0
    env.gpu.write_text("200\n")
    assert (
        env.serve("stop").returncode == 0 and "GPU free" in env.serve("status").stdout + "GPU free"
    )


def test_the_server_that_dies_while_starting_is_reported(env: Env, tmp_path: Path) -> None:
    broken = tmp_path / "bin" / "vllm"
    broken.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            if [ "$2" = "--help=all" ]; then
              echo "--tool-call-parser {hermes} --max-model-len --enable-auto-tool-choice"
              echo "--reasoning-parser"
              exit 0
            fi
            echo "CUDA out of memory"; exit 1
            """
        )
    )
    result = env.serve("start", "qwen3-14b-t0")
    assert result.returncode == 5 and "CUDA out of memory" in result.stdout + result.stderr
    assert env.pid() is None


def test_start_without_a_profile_uses_actual(env: Env) -> None:
    result = env.serve("start", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "profile: actual" in result.stdout and "Qwen/Qwen3-14B-AWQ" in result.stdout


def test_the_idle_memory_is_measured_at_every_start(env: Env) -> None:
    """La segunda pantalla se enchufa entre dos arranques: el reposo se vuelve a medir."""
    env.gpu.write_text("0\n")
    assert env.serve("start", "actual").returncode == 0
    assert (env.state / "gpu_idle_mib").read_text().strip() == "0"
    env.gpu.write_text("0\n")
    assert env.serve("stop").returncode == 0
    env.gpu.write_text("340\n")  # pantalla enchufada con vLLM parado
    assert env.serve("start", "actual").returncode == 0
    assert (env.state / "gpu_idle_mib").read_text().strip() == "340"
    stopped = env.serve("stop")  # no espera 0 MiB: 340 es el reposo
    assert stopped.returncode == 0 and "GPU free: 340 MiB" in stopped.stdout


def test_stop_fails_while_a_vllm_process_survives(env: Env, tmp_path: Path) -> None:
    """Aunque la memoria esté en el reposo, un proceso vivo del grupo de vLLM no es «libre»."""
    vllm = tmp_path / "bin" / "vllm"
    text = FAKE_VLLM.replace("exec python3", "(trap '' TERM; exec sleep 300) &\nexec python3", 1)
    vllm.write_text(text)
    assert env.serve("start", "actual").returncode == 0
    pid = env.pid()
    assert pid
    try:
        stopped = env.serve("stop")
        assert stopped.returncode == 7 and "vLLM processes are still alive" in stopped.stderr
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)
