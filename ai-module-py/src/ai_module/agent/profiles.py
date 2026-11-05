"""Perfiles de modelo: `model-profiles/<nombre>.yaml`.

Un perfil se aplica **en memoria** sobre `agent-assets/agents.yaml` (que no se toca) y solo puede
cambiar el servidor y el modelo, el muestreo, el razonamiento, los tiempos máximos y los
interruptores de ayudas. Cualquier otra clave es un error: un perfil no puede cambiar prompts,
skills ni esquemas de tools. Una sola excepción (Fase 14.1): `assets: agent-assets-v13` elige otra
carpeta completa de la raíz del repositorio (`agent-assets*`), congelada, para repetir con los
textos antiguos; el perfil no edita nada dentro de ella.

    uv run --project ai-module-py python -m ai_module.agent.profiles serve-args <perfil>
    uv run --project ai-module-py python -m ai_module.agent.profiles show <perfil>
"""

import argparse
import copy
import hashlib
import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# model-profiles/ junto al código del repositorio (ai-module-py/src/ai_module/agent/profiles.py)
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROFILES = REPO_ROOT / "model-profiles"
ASSETS_DIR = REPO_ROOT / "agent-assets"

AGENT_NAMES = ("monitor", "chat_monitor", "report", "chat_report")
SAMPLING_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "presence_penalty",
    "max_tokens",
)
LIMIT_KEYS = ("max_invocation_s", "llm_timeout_s")
AID_KEYS = (
    "tool_choice",
    "final_iteration_response_tools_only",
    "require_checks",
    "coherence_guardrail",
    "computed_facts",
    "now_facts",
    "source_silent_own_alert",
    "no_duplicate_cause",
    "recovery_ack_veto",
    "fill_link_anomalous",
    "recovery_jump_from_module",
    "guided_skills",
)
# La memoria del monitor no es una ayuda: cambia lo que el modelo recuerda, no lo que se le quita.
MEMORY_KEYS = ("memory", "memory_budget_tokens", "memory_target_tokens")
REASONING_KEYS = ("reasoning", "reasoning_effort", "reasoning_field")
AGENT_KEYS = (*SAMPLING_KEYS, *REASONING_KEYS, *LIMIT_KEYS, *AID_KEYS, *MEMORY_KEYS)
ALLOWED = {
    "description": None,
    "assets": None,
    "server": (
        "model",
        "tool_call_parser",
        "reasoning_parser",
        "max_model_len",
        "extra_args",
        "env",
    ),
    "llm": ("model", "base_url", "api_key"),
    "sampling": (*SAMPLING_KEYS, *REASONING_KEYS),
    "agents": AGENT_NAMES,
    "chat": ("tools_enabled",),
    "platform": ("wait_agent_timeout_s",),
}
# Modelos híbridos de 27B que cuelgan vLLM y han tirado Windows: no se sirven.
FORBIDDEN_MODELS = ("qwen3.5-27b", "qwen3.8-27b")
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
ASSETS_NAME = re.compile(r"agent-assets[A-Za-z0-9._-]*")
ASSETS_LABEL = "agent-assets"  # nombre con el que se calcula la huella, sea cual sea la carpeta
MEMORY_GROWTH_TOKENS = 4000  # lo que puede crecer el contexto durante una invocación
PLATFORM_MARGIN_S = 15.0  # `max_invocation_s` + margen < espera de la plataforma
DEFAULT_WAIT_S = 90.0


class ProfileError(Exception):
    """Un perfil no existe o está mal formado (mensaje en inglés)."""


def digest(paths: list[tuple[str, Path]]) -> str:
    """Huella como `find … | sort | xargs sha256sum | sha256sum`: las líneas `hash  ruta`
    ordenadas por ruta (bytes) y el sha256 de todas."""
    lines = sorted(
        (f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n" for name, path in paths),
        key=lambda line: line.split("  ", 1)[1].encode(),
    )
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def assets_fingerprint(root: Path = ASSETS_DIR) -> str:
    """Huella completa de `agent-assets/` (con 16 caracteres es la huella de congelado). Se calcula
    con el nombre `agent-assets` aunque la carpeta sea una copia congelada (`agent-assets-v13`),
    así la copia tiene la huella que tenía el original."""
    files = [(f"{ASSETS_LABEL}/{p.relative_to(root).as_posix()}", p) for p in root.rglob("*")]
    return digest([(name, p) for name, p in files if p.is_file()])


@dataclass(frozen=True)
class Profile:
    name: str
    raw: dict[str, Any]
    fingerprint: str
    """Huella completa del fichero del perfil (sha256)."""
    path: Path | None = None
    overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def short(self) -> str:
        return self.fingerprint[:16]

    @property
    def server(self) -> dict[str, Any]:
        return self.raw.get("server", {})

    @property
    def assets_dir(self) -> Path:
        """Carpeta de assets del perfil: la del repositorio o la copia congelada que fije."""
        name = self.raw.get("assets")
        return REPO_ROOT / name if name else ASSETS_DIR

    @property
    def model(self) -> str | None:
        return self.raw.get("llm", {}).get("model") or self.server.get("model")

    @property
    def wait_agent_timeout_s(self) -> float:
        return float(self.raw.get("platform", {}).get("wait_agent_timeout_s", DEFAULT_WAIT_S))

    def server_signature(self) -> dict[str, Any]:
        """Lo que hace falta para decidir si dos perfiles pueden compartir servidor."""
        s = self.server
        return {
            "model": s.get("model"),
            "tool_call_parser": s.get("tool_call_parser"),
            "reasoning_parser": s.get("reasoning_parser"),
            "max_model_len": s.get("max_model_len"),
            "extra_args": list(s.get("extra_args", [])),
            "env": self.server_env(),
        }

    def server_env(self) -> dict[str, str]:
        """Variables de entorno que se exportan solo al servidor de este perfil."""
        return {k: str(v) for k, v in self.server.get("env", {}).items()}

    def serve_args(self, port: int = 8000) -> list[str]:
        """Argumentos de `vllm serve`. Con parser de razonamiento, el razonamiento queda activado
        en el servidor y cada petición lo enciende o apaga con `enable_thinking`."""
        s = self.server
        args = [
            "serve",
            s["model"],
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--max-model-len",
            str(s.get("max_model_len", 32768)),
            "--enable-auto-tool-choice",
            "--tool-call-parser",
            s["tool_call_parser"],
        ]
        if s.get("reasoning_parser"):
            args += ["--reasoning-parser", s["reasoning_parser"]]
        return args + [str(a) for a in s.get("extra_args", [])]

    def apply(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Copia de `agents.yaml` (ya leído) con el perfil aplicado."""
        out = copy.deepcopy(raw)
        server_model = self.server.get("model")
        if server_model:
            out["llm"]["model"] = server_model
        out["llm"].update(self.raw.get("llm", {}))
        sampling = self.raw.get("sampling", {})
        out["llm"].update(sampling)
        for name in AGENT_NAMES:
            spec = out["agents"][name]
            # el muestreo del perfil manda sobre el que fija cada agente en agents.yaml
            spec.update(sampling)
            spec.update(self.raw.get("agents", {}).get(name, {}))
        out.setdefault("chat", {}).update(self.raw.get("chat", {}))
        monitor = out["agents"]["monitor"]
        wait = self.wait_agent_timeout_s
        if float(monitor.get("max_invocation_s", 60)) + PLATFORM_MARGIN_S >= wait:
            raise ProfileError(
                f"profile {self.name}: monitor max_invocation_s {monitor['max_invocation_s']} + "
                f"{PLATFORM_MARGIN_S:g} must be below the platform wait {wait:g}"
            )
        self._check_memory(monitor)
        return out

    def _check_memory(self, monitor: dict[str, Any]) -> None:
        """Con la memoria A, el historial que se compacta más lo que crece una invocación y la
        respuesta tienen que caber en `max_model_len`."""
        if monitor.get("memory", "per_detection") != "per_run":
            return
        budget = int(monitor.get("memory_budget_tokens", 26000))
        target = int(monitor.get("memory_target_tokens", 18000))
        max_len = int(self.server.get("max_model_len", 32768))
        room = budget + int(monitor.get("max_tokens", 800)) + MEMORY_GROWTH_TOKENS
        if target >= budget or room > max_len:
            raise ProfileError(
                f"profile {self.name}: memory_budget_tokens {budget} (target {target}) + max_tokens"
                f" + {MEMORY_GROWTH_TOKENS} for one invocation must fit in max_model_len {max_len}"
            )


def _validate_env(name: str, env: Any) -> None:
    """`server.env`: nombres de variable válidos y valores de texto (los números y booleanos de
    YAML se rechazan: `"0"` no es `0`)."""
    if not isinstance(env, dict):
        raise ProfileError(f"profile {name}: server.env must be a mapping")
    for var, value in env.items():
        if not isinstance(var, str) or not ENV_NAME.fullmatch(var):
            raise ProfileError(f"profile {name}: server.env name {var!r} is not a valid variable")
        if not isinstance(value, str):
            raise ProfileError(f"profile {name}: server.env.{var} must be a string (quote it)")


def _validate(name: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProfileError(f"profile {name}: the file is not a mapping")
    for key, value in raw.items():
        if key not in ALLOWED:
            raise ProfileError(f"profile {name}: unknown section {key!r}")
        allowed = ALLOWED[key]
        if key == "assets":
            if not isinstance(value, str) or not ASSETS_NAME.fullmatch(value):
                raise ProfileError(f"profile {name}: assets must be a folder named agent-assets*")
            if not (REPO_ROOT / value).is_dir():
                raise ProfileError(f"profile {name}: the assets folder {value} does not exist")
        if allowed is None:
            continue
        if not isinstance(value, dict):
            raise ProfileError(f"profile {name}: {key} must be a mapping")
        for sub, subvalue in value.items():
            if sub not in allowed:
                raise ProfileError(f"profile {name}: unknown key {key}.{sub}")
            if key == "server" and sub == "env":
                _validate_env(name, subvalue)
            if key == "agents":
                if not isinstance(subvalue, dict):
                    raise ProfileError(f"profile {name}: agents.{sub} must be a mapping")
                for k in subvalue:
                    if k not in AGENT_KEYS:
                        raise ProfileError(f"profile {name}: unknown key agents.{sub}.{k}")
    server = raw.get("server")
    if server is not None:
        for required in ("model", "tool_call_parser"):
            if required not in server:
                raise ProfileError(f"profile {name}: server.{required} is missing")
        lowered = str(server["model"]).lower()
        if any(f in lowered for f in FORBIDDEN_MODELS):
            raise ProfileError(f"profile {name}: model {server['model']} is forbidden")
    return raw


def load_profile(name: str, directory: Path = DEFAULT_PROFILES) -> Profile:
    path = directory / f"{name}.yaml"
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ProfileError(f"cannot read profile {name}: {exc}") from exc
    raw = _validate(name, yaml.safe_load(data))
    return Profile(name, raw, hashlib.sha256(data).hexdigest(), path)


def list_profiles(directory: Path = DEFAULT_PROFILES) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", choices=["serve-args", "serve-env", "show", "model", "list"])
    parser.add_argument("profile", nargs="?")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dir", type=Path, default=DEFAULT_PROFILES)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            print("\n".join(list_profiles(args.dir)))
            return 0
        if not args.profile:
            parser.error("a profile name is needed")
        profile = load_profile(args.profile, args.dir)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "serve-args":
        print(shlex.join(profile.serve_args(args.port)))  # para `eval set -- …` en serve.sh
    elif args.command == "serve-env":
        for var, value in profile.server_env().items():
            print(f"{var}={value}")  # una por línea, para `env VAR=valor …` en serve.sh
    elif args.command == "model":
        print(profile.server["model"])
    else:
        print(json.dumps({**profile.raw, "fingerprint": profile.short}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
