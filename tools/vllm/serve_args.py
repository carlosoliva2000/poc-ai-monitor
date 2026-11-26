"""Lee un perfil de `model-profiles/` y da lo que `serve.sh` necesita para arrancar vLLM.

    uv run --project ai-module-py python tools/vllm/serve_args.py serve-args <perfil> [--port 8000]
    uv run --project ai-module-py python tools/vllm/serve_args.py serve-env <perfil>
    uv run --project ai-module-py python tools/vllm/serve_args.py model <perfil>
    uv run --project ai-module-py python tools/vllm/serve_args.py list

Solo se lee la sección `server` del perfil: `model`, `tool_call_parser` (obligatorios),
`reasoning_parser`, `max_model_len`, `extra_args` y `env`. **Cualquier otra sección se ignora**
(muestreo, agentes, ayudas de formatos anteriores), así que un perfil archivado de
`~/poc-backups/model-profiles-archivo/` se puede copiar de vuelta a `model-profiles/` y arrancar
sin tocar código. El asistente usa el modelo de `agent-assets/assistant.yaml` (o de la variable
`POC_LLM_MODEL`); si no coincide con el que sirve vLLM, no arranca.
"""

import argparse
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PROFILES = Path(__file__).resolve().parents[2] / "model-profiles"
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Modelos híbridos de 27B que cuelgan vLLM y han tirado Windows: no se sirven.
FORBIDDEN_MODELS = ("qwen3.5-27b", "qwen3.8-27b")


class ProfileError(Exception):
    """Un perfil que no se puede leer o no es válido."""


def load_server(name: str, directory: Path = DEFAULT_PROFILES) -> dict[str, Any]:
    """La sección `server` del perfil, validada."""
    path = directory / f"{name}.yaml"
    try:
        raw = yaml.safe_load(path.read_bytes())
    except (OSError, yaml.YAMLError) as exc:
        raise ProfileError(f"cannot read profile {name}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("server"), dict):
        raise ProfileError(f"profile {name}: it needs a server section")
    server: dict[str, Any] = raw["server"]
    for required in ("model", "tool_call_parser"):
        if required not in server:
            raise ProfileError(f"profile {name}: server.{required} is missing")
    if any(f in str(server["model"]).lower() for f in FORBIDDEN_MODELS):
        raise ProfileError(f"profile {name}: model {server['model']} is forbidden")
    env = server.get("env", {})
    if not isinstance(env, dict):
        raise ProfileError(f"profile {name}: server.env must be a mapping")
    for var, value in env.items():
        if not isinstance(var, str) or not ENV_NAME.fullmatch(var):
            raise ProfileError(f"profile {name}: server.env name {var!r} is not a valid variable")
        if not isinstance(value, str):
            raise ProfileError(f"profile {name}: server.env.{var} must be a string (quote it)")
    return server


def serve_args(server: dict[str, Any], port: int = 8000) -> list[str]:
    """Argumentos de `vllm serve`. Con parser de razonamiento, el razonamiento queda activado en el
    servidor y cada petición lo apaga con `enable_thinking`."""
    args = [
        "serve", str(server["model"]), "--host", "127.0.0.1", "--port", str(port),
        "--max-model-len", str(server.get("max_model_len", 32768)),
        "--enable-auto-tool-choice", "--tool-call-parser", str(server["tool_call_parser"]),
    ]  # fmt: skip
    if server.get("reasoning_parser"):
        args += ["--reasoning-parser", str(server["reasoning_parser"])]
    return args + [str(a) for a in server.get("extra_args", [])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve-args", "serve-env", "model", "list"])
    parser.add_argument("profile", nargs="?")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dir", type=Path, default=DEFAULT_PROFILES)
    args = parser.parse_args(argv)
    if args.command == "list":
        print("\n".join(sorted(p.stem for p in args.dir.glob("*.yaml"))))
        return 0
    if not args.profile:
        parser.error("a profile name is needed")
    try:
        server = load_server(args.profile, args.dir)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "serve-args":
        print(shlex.join(serve_args(server, args.port)))  # para `eval set -- …` en serve.sh
    elif args.command == "serve-env":
        for var, value in server.get("env", {}).items():
            print(f"{var}={value}")  # una por línea, para `env VAR=valor …` en serve.sh
    else:
        print(server["model"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
