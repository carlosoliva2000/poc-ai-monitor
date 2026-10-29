"""Lanzador de experimentos: perfiles × escenarios × repeticiones, y su `compare.md`.

    uv run --project ai-module-py python tools/experiments/run_matrix.py \\
        --profiles qwen3-14b-t0,qwen3-30b-a3b-t0 --scenarios demo,wind --reps 3
    uv run --project ai-module-py python tools/experiments/run_matrix.py --fake \\
        --profiles qwen3-14b-t0,qwen3-30b-a3b-t0 --scenarios nominal --reps 2
    uv run --project ai-module-py python tools/experiments/run_matrix.py --resume <id>
    uv run --project ai-module-py python -m ai_module.compare experiments/<id>

Para cada perfil arranca el servidor con `tools/vllm/serve.sh` si hace falta (y para el anterior
si cambia de modelo o de configuración del servidor; los perfiles Qwen3 de un mismo modelo lo
comparten), ejecuta `platform_app.run` con «esperar al agente» a 16× y la evaluación, y deja todo
en `experiments/<id>/`: `manifest.json`, `runs/<perfil>/<escenario>/r<k>/` (con `eval.md`,
`eval.json`, `llm_trace.jsonl`, `timeline.jsonl`, `informe.md`, `run_meta.json` y `profile.json`),
`logs/` y `compare.md`. Si el servidor cae o no se libera la GPU, para la matriz sin reintentar.

`--fake` sustituye vLLM por el servidor LLM falso de las pruebas (sin GPU).
"""

import argparse
import importlib.metadata
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ai_module.agent.assets import DEFAULT_ASSETS, Assets
from ai_module.agent.profiles import Profile, assets_fingerprint, load_profile
from ai_module.compare import write_compare

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO / "experiments"
SERVE = REPO / "tools" / "vllm" / "serve.sh"
SPEED = "16"
COPY_FILES = (
    "eval.md", "eval.json", "llm_trace.jsonl", "timeline.jsonl", "informe.md", "run_meta.json",
    "profile.json",
)  # fmt: skip
EVAL_RE = re.compile(r"→ (.+)/eval\.md")
FINAL_QUESTION = "Which was the most serious anomaly and why?"
SCRIPT_QUESTIONS = (
    "monitor:110:Why do you think it is wind?",
    "monitor:342:What did you look at on the link?",
    f"report:end:{FINAL_QUESTION}",
)
DEFAULT_ASKS = {"demo": list(SCRIPT_QUESTIONS)}
OTHER_ASKS = [f"report:end:{FINAL_QUESTION}"]


class MatrixError(Exception):
    """La matriz se para (servidor caído, GPU sin liberar, servidor ajeno…); no se reintenta."""


class Backend(Protocol):
    """Servidor LLM de la matriz: vLLM por `serve.sh`, o el servidor falso."""

    llm_url: str | None

    def prepare(self) -> None: ...
    def start(self, profile: Profile) -> None: ...
    def stop(self) -> None: ...
    def healthy(self) -> bool: ...
    def version(self) -> str: ...


def http_ok(url: str, timeout: float = 3.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read().decode()
    except OSError:
        return None


def parse_version(text: str | None) -> str:
    """`{"version": "0.31.0"}` de `GET /version` de vLLM."""
    try:
        return str(json.loads(text or "{}").get("version", "n/d"))
    except ValueError:
        return "n/d"


class VllmBackend:
    """vLLM con `tools/vllm/serve.sh` (puerto 8000, URL de `agents.yaml`)."""

    llm_url = None
    port = 8000

    def _serve(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SERVE), *args], cwd=REPO, text=True, capture_output=True, check=False
        )

    def prepare(self) -> None:
        """Mide la memoria de GPU en reposo antes del primer arranque (si no hay servidor)."""
        result = self._serve("gpu-idle")
        print(result.stdout.strip() or result.stderr.strip(), flush=True)

    def start(self, profile: Profile) -> None:
        result = self._serve("start", profile.name)
        print(result.stdout.strip(), flush=True)
        if result.returncode != 0:
            raise MatrixError(f"serve.sh start {profile.name} failed ({result.returncode}): "
                              f"{result.stderr.strip()}")  # fmt: skip

    def stop(self) -> None:
        result = self._serve("stop")
        print(result.stdout.strip(), flush=True)
        if result.returncode != 0:
            raise MatrixError(
                f"serve.sh stop failed ({result.returncode}): {result.stderr.strip()}"
            )

    def healthy(self) -> bool:
        return http_ok(f"http://127.0.0.1:{self.port}/health") is not None

    def version(self) -> str:
        return parse_version(http_ok(f"http://127.0.0.1:{self.port}/version"))


class FakeBackend:
    """Servidor LLM falso de las pruebas (`ai_module.testing.fake_llm`), sin GPU."""

    port = 8190

    def __init__(self) -> None:
        self.llm_url = f"http://127.0.0.1:{self.port}/v1"
        self.proc: subprocess.Popen[bytes] | None = None

    def prepare(self) -> None:
        return None

    def start(self, profile: Profile) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ai_module.testing.fake_llm", "--port", str(self.port),
             "--model", str(profile.model)],
            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        deadline = time.monotonic() + 20
        while not self.healthy():
            if time.monotonic() > deadline or self.proc.poll() is not None:
                raise MatrixError("the fake LLM server did not start")
            time.sleep(0.2)

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait(10)
            self.proc = None

    def healthy(self) -> bool:
        return (
            self.proc is not None
            and self.proc.poll() is None
            and (http_ok(f"http://127.0.0.1:{self.port}/health") is not None)
        )

    def version(self) -> str:
        return parse_version(http_ok(f"http://127.0.0.1:{self.port}/version"))


class ServerManager:
    """Decide cuándo arrancar, reutilizar o cambiar el servidor."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self.current: Profile | None = None
        self.version = "n/d"
        self.prepared = False

    def ensure(self, profile: Profile) -> None:
        if self.current is not None and (
            self.current.server_signature() == profile.server_signature()
        ):
            if not self.backend.healthy():
                raise MatrixError("the LLM server is down: stopping the matrix (no retry)")
            self.current = profile
            return
        if self.current is not None:
            print(f"== changing server: {self.current.name} -> {profile.name}", flush=True)
            self.backend.stop()  # espera a que la GPU se libere
            self.current = None
        elif not self.prepared:
            self.backend.prepare()
        self.prepared = True
        self.backend.start(profile)
        self.current = profile
        self.version = self.backend.version()

    def check(self) -> None:
        if self.current is not None and not self.backend.healthy():
            raise MatrixError("the LLM server is down: stopping the matrix (no retry)")

    def close(self, keep: bool) -> None:
        if self.current is not None and not keep:
            self.backend.stop()
            self.current = None


@dataclass(frozen=True)
class RunSpec:
    profile: str
    scenario: str
    rep: int


def plan(profiles: list[str], scenarios: list[str], reps: int) -> list[RunSpec]:
    """Perfil por perfil, para cambiar de servidor lo menos posible."""
    return [
        RunSpec(p, s, k) for p in profiles for s in scenarios for k in range(1, reps + 1)
    ]  # fmt: skip


def git_info() -> dict[str, Any]:
    """Versión del repositorio (solo lectura)."""

    def git(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True, check=False)
        return done.stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def build_manifest(
    exp_id: str, args: argparse.Namespace, profiles: dict[str, Profile], runs: list[RunSpec]
) -> dict[str, Any]:
    return {
        "id": exp_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "fake": args.fake,
        "profiles": {
            name: {
                "fingerprint": p.fingerprint,
                "short": p.short,
                "model": p.server.get("model"),
                "server": p.server_signature(),
                "wait_agent_timeout_s": p.wait_agent_timeout_s,
            }
            for name, p in profiles.items()
        },
        "scenarios": args.scenario_list,
        "reps": args.reps,
        "assets_fingerprint": assets_fingerprint(DEFAULT_ASSETS),
        "vllm_version": "n/d",
        "openai_sdk": importlib.metadata.version("openai"),
        "git": git_info(),
        "speed": float(SPEED),
        "runs": [
            {"profile": r.profile, "scenario": r.scenario, "rep": r.rep, "status": "pending"}
            for r in runs
        ],
    }


def save(folder: Path, manifest: dict[str, Any]) -> None:
    (folder / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_command(spec: RunSpec, args: argparse.Namespace, llm_url: str | None) -> list[str]:
    asks = args.ask or ([] if args.no_ask else DEFAULT_ASKS.get(spec.scenario, OTHER_ASKS))
    command = [
        "uv", "run", "--project", "platform", "python", "-m", "platform_app.run",
        "--scenario", spec.scenario, "--speed", SPEED, "--wait-agent", "--evaluate",
        "--profile", spec.profile, "--port", str(args.platform_port),
        "--timeout", str(args.run_timeout),
    ]  # fmt: skip
    if llm_url:
        command += ["--llm-url", llm_url]
    for ask in asks:
        command += ["--ask", ask]
    return command


def execute(spec: RunSpec, args: argparse.Namespace, llm_url: str | None, folder: Path) -> dict:
    """Una ejecución: lanza `run.py`, copia sus ficheros y devuelve su entrada del manifiesto."""
    started = time.monotonic()
    log = folder / "logs" / f"{spec.profile}_{spec.scenario}_r{spec.rep}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run(
            run_command(spec, args, llm_url), cwd=REPO, text=True, capture_output=True,
            timeout=args.run_timeout + 300, check=False,
        )  # fmt: skip
        output = done.stdout + done.stderr
    except subprocess.TimeoutExpired as exc:
        output = f"TIMEOUT\n{exc.stdout or ''}{exc.stderr or ''}"
        done = None
    log.write_text(output, encoding="utf-8")
    entry: dict[str, Any] = {"wall_s": round(time.monotonic() - started, 1), "status": "failed"}
    found = EVAL_RE.search(output)
    if found is None or not (Path(found.group(1)) / "eval.json").exists():
        entry["error"] = (output.strip().splitlines() or ["no output"])[-1][:300]
        return entry
    source = Path(found.group(1))
    target = folder / "runs" / spec.profile / spec.scenario / f"r{spec.rep}"
    target.mkdir(parents=True, exist_ok=True)
    for name in COPY_FILES:
        if (source / name).exists():
            shutil.copy2(source / name, target / name)
    entry.update(status="ok", run_id=source.name, returncode=done.returncode if done else None)
    return entry


def run_matrix(args: argparse.Namespace, backend: Backend) -> Path:
    profiles = {name: load_profile(name) for name in args.profile_list}
    folder = EXPERIMENTS / args.id
    runs = plan(args.profile_list, args.scenario_list, args.reps)
    if args.resume:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    else:
        if folder.exists():
            raise MatrixError(f"{folder} already exists: use --resume {args.id} or another --id")
        folder.mkdir(parents=True)
        manifest = build_manifest(args.id, args, profiles, runs)
        save(folder, manifest)
    entries = {(e["profile"], e["scenario"], e["rep"]): e for e in manifest["runs"]}
    servers = ServerManager(backend)
    try:
        for spec in runs:
            entry = entries[(spec.profile, spec.scenario, spec.rep)]
            if entry["status"] == "ok":
                continue
            servers.ensure(profiles[spec.profile])
            manifest["vllm_version"] = servers.version
            print(f"== {spec.profile} · {spec.scenario} · r{spec.rep}", flush=True)
            entry.update(execute(spec, args, backend.llm_url, folder))
            save(folder, manifest)
            print(f"   {entry['status']} ({entry['wall_s']} s)", flush=True)
            servers.check()
    finally:
        try:
            servers.close(args.keep_server)
        finally:
            save(folder, manifest)
            print(f"→ {write_compare(folder)}", flush=True)
    return folder


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profiles", help="perfiles separados por comas (model-profiles/)")
    parser.add_argument("--scenarios", help="escenarios separados por comas")
    parser.add_argument("--reps", type=int, default=1, help="repeticiones por perfil y escenario")
    parser.add_argument("--id", help="identificador del experimento (por defecto, la fecha)")
    parser.add_argument("--resume", metavar="ID", help="continúa un experimento (salta las ok)")
    parser.add_argument("--fake", action="store_true", help="servidor LLM falso, sin GPU")
    parser.add_argument("--keep-server", action="store_true", help="no parar el servidor al final")
    parser.add_argument("--ask", action="append", help="pregunta CONVERSACIÓN:CUÁNDO:TEXTO")
    parser.add_argument("--no-ask", action="store_true", help="sin preguntas a los chats")
    parser.add_argument("--platform-port", type=int, help="puerto de la plataforma")
    parser.add_argument("--run-timeout", type=float, default=1800.0, help="segundos por ejecución")
    parser.add_argument("--dry-run", action="store_true", help="solo muestra el plan")
    args = parser.parse_args(argv)
    if args.resume:
        manifest = json.loads((EXPERIMENTS / args.resume / "manifest.json").read_text("utf-8"))
        args.id = args.resume
        args.profile_list = list(manifest["profiles"])
        args.scenario_list = list(manifest["scenarios"])
        args.reps = manifest["reps"]
        args.fake = manifest.get("fake", args.fake)
    else:
        if not (args.profiles and args.scenarios):
            parser.error("--profiles and --scenarios are needed (or --resume)")
        args.profile_list = [p for p in args.profiles.split(",") if p]
        args.scenario_list = [s for s in args.scenarios.split(",") if s]
        args.id = args.id or datetime.now().strftime("%Y%m%d-%H%M%S") + (
            "-fake" if args.fake else ""
        )
    args.platform_port = args.platform_port or (8199 if args.fake else 8100)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    if args.dry_run:
        profiles = {name: load_profile(name) for name in args.profile_list}
        server = None
        for spec in plan(args.profile_list, args.scenario_list, args.reps):
            signature = profiles[spec.profile].server_signature()
            if signature != server:
                profile = profiles[spec.profile]
                print(f"server: start {profile.server['model']}")
                print(f"  vllm {shlex.join(profile.serve_args())}")
                info = Assets(DEFAULT_ASSETS, profile).profile_info()
                print(f"  llm model: {info['model']} · wait {info['wait_agent_timeout_s']:g} s")
                for agent, effective in info["agents"].items():
                    print(f"  {agent}: {json.dumps(effective, sort_keys=True)}")
                server = signature
            print(f"  run {spec.profile} {spec.scenario} r{spec.rep}")
        return 0
    backend: Backend = FakeBackend() if args.fake else VllmBackend()
    try:
        folder = run_matrix(args, backend)
    except MatrixError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"experiment in {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
