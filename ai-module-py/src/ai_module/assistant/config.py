"""Configuración del asistente: `agent-assets/assistant.yaml` (servidor y una entrada por papel)."""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# agent-assets/ junto al código del repositorio (ai-module-py/src/ai_module/assistant/config.py)
REPO_ROOT = Path(__file__).resolve().parents[4]
ASSETS_DIR = REPO_ROOT / "agent-assets"
DEFAULT_CONFIG = ASSETS_DIR / "assistant.yaml"


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    reasoning: bool
    top_k: int
    repetition_penalty: float


@dataclass(frozen=True)
class RoleConfig:
    name: str
    enabled: bool
    prompt: str  # ruta relativa a agent-assets/
    temperature: float
    top_p: float
    max_tokens: int
    timeout_s: float
    tools: str | None = None  # fichero de esquemas de tools (relativo a agent-assets/)

    def system_prompt(self, assets: Path = ASSETS_DIR) -> str:
        return (assets / self.prompt).read_text(encoding="utf-8").strip()

    def tool_schemas(self, assets: Path = ASSETS_DIR) -> list[dict[str, Any]]:
        if not self.tools:
            return []
        return list(json.loads((assets / self.tools).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class QueueConfig:
    expire_s: float
    retry_before_s: float
    web_deadline_s: float
    chat_expire_s: float = 30.0  # una pregunta que no ha empezado a contestarse en este tiempo
    report_settle_s: float = 3.0  # espera tras el fin para que lleguen los últimos incidentes


@dataclass(frozen=True)
class AssistantConfig:
    llm: LlmConfig
    queue: QueueConfig
    now_rule: str
    roles: dict[str, RoleConfig]
    assets: Path = ASSETS_DIR

    def role(self, name: str) -> RoleConfig:
        return self.roles[name]


def load_config(path: Path = DEFAULT_CONFIG) -> AssistantConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    roles = {name: RoleConfig(name=name, **body) for name, body in raw["roles"].items()}
    now_rule = str(raw.get("now_rule", "loose"))
    if now_rule not in ("strict", "loose"):
        raise ValueError(f"now_rule must be strict or loose, not {now_rule!r}")
    llm = dict(raw["llm"])
    llm["model"] = os.environ.get("POC_LLM_MODEL") or llm["model"]  # otro modelo sin tocar el YAML
    return AssistantConfig(
        llm=LlmConfig(**llm),
        queue=QueueConfig(**raw["queue"]),
        now_rule=now_rule,
        roles=roles,
        assets=path.parent,
    )


def prompt_fingerprint(config: AssistantConfig, role: str) -> str:
    """Huella (sha256, 12 hex) del prompt, de las tools y del glosario de un papel."""
    digest = hashlib.sha256()
    cfg = config.role(role)
    parts = [cfg.prompt, cfg.tools, "glossary.yaml"]
    for rel in filter(None, parts):
        path = config.assets / rel
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
