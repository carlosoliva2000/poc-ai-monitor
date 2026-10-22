"""Lectura de `agent-assets/`: configuración de agentes, prompts, skills y esquemas de tools.

Nada de esto se escribe en el código: el módulo Java leerá los mismos ficheros. Los esquemas de
las tools se envían al modelo **tal cual** están en `tools.json` (filtrados por la lista del
agente, en el orden del fichero).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# agent-assets/ junto al código del repositorio (ai-module-py/src/ai_module/agent/assets.py)
DEFAULT_ASSETS = Path(__file__).resolve().parents[4] / "agent-assets"
MARKER_RE = re.compile(r"<<(\w+)>>")
SECTION_RE = re.compile(r"^## (\w+)\s*$", re.M)


class AssetError(Exception):
    """Un recurso falta o está mal formado (mensaje en español)."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    content: str
    """Texto completo del `SKILL.md`, tal como lo recibe el modelo con `load_skill`."""


@dataclass(frozen=True)
class AgentConfig:
    """Una instancia del motor (monitor, informe o chat), con el muestreo ya resuelto."""

    name: str
    system_prompt: str
    tools: list[str]
    skills: list[str]
    max_iterations: int
    max_invocation_s: float
    llm_timeout_s: float
    temperature: float
    top_p: float
    top_k: int
    repetition_penalty: float
    max_tokens: int
    tool_choice: str
    objective_prompt: str | None = None
    output_prompt: str | None = None
    system_prompt_notools: str | None = None
    """Prompt de sistema del chat cuando `chat.tools_enabled` es falso (sin tools)."""
    disabled_tools: list[str] = field(default_factory=list)
    final_tools: list[str] = field(default_factory=list)
    """Tools que se ofrecen en la última iteración permitida (vacío: las mismas de siempre)."""
    final_iteration_response_tools_only: bool = True
    """Interruptor: si es falso, la última iteración ofrece las mismas tools que las demás."""
    require_checks: bool = True
    """Interruptor del monitor: `checks` obligatorio en el esquema de `publish_alert`."""
    coherence_guardrail: bool = True
    """Interruptor del monitor: guardrail de coherencia de `publish_alert`."""
    computed_facts: bool = True
    """Interruptor del monitor: `get_track_metrics` entrega los campos calculados al modelo."""
    guided_mode: bool = False
    guided_skill_by_rule: dict[str, str] = field(default_factory=dict)
    last_decisions_in_state: int = 3
    max_history_messages: int = 12
    stream: bool = False
    no_report_reply: str = ""

    @property
    def active_tools(self) -> list[str]:
        return [t for t in self.tools if t not in self.disabled_tools]

    @property
    def last_iteration_tools(self) -> list[str]:
        """Tools de la última iteración: `final_tools` (las que sigan activas) o todas."""
        if not self.final_tools or not self.final_iteration_response_tools_only:
            return self.active_tools
        return [t for t in self.active_tools if t in self.final_tools]

    def aids(self) -> dict[str, Any]:
        """Las ayudas al modelo activas, para la traza y la cabecera de `eval.md`."""
        return {
            "tool_choice": self.tool_choice,
            "final_iteration_response_tools_only": bool(
                self.final_tools and self.final_iteration_response_tools_only
            ),
            "require_checks": self.require_checks,
            "coherence_guardrail": self.coherence_guardrail,
            "computed_facts": self.computed_facts,
        }

    def sampling(self) -> dict[str, Any]:
        """Parámetros de muestreo de **cada** petición (los no estándar, en `extra_body`)."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "tool_choice": self.tool_choice,
            "extra_body": {"top_k": self.top_k, "repetition_penalty": self.repetition_penalty},
        }


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    api_key: str
    model: str


def render(template: str, **values: object) -> str:
    """Sustituye los marcadores `<<nombre>>`. Falla si falta un valor o queda alguno sin sustituir
    (así un marcador mal escrito no llega al modelo)."""
    missing = sorted({m for m in MARKER_RE.findall(template) if m not in values})
    if missing:
        raise AssetError(f"faltan valores para los marcadores: {', '.join(missing)}")
    return MARKER_RE.sub(lambda m: str(values[m.group(1)]), template)


def sections(text: str) -> tuple[str, dict[str, str]]:
    """Divide una plantilla en su parte común (antes del primer `## nombre`) y sus secciones."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return text.strip(), {}
    common = text[: matches[0].start()].strip()
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match.group(1)] = text[match.end() : end].strip()
    return common, out


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.S)


class Assets:
    def __init__(self, root: Path = DEFAULT_ASSETS) -> None:
        self.root = root
        try:
            raw = yaml.safe_load((root / "agents.yaml").read_text(encoding="utf-8"))
        except OSError as exc:
            raise AssetError(f"no se puede leer {root / 'agents.yaml'}: {exc}") from exc
        self._raw: dict[str, Any] = raw
        self.llm = LlmSettings(
            base_url=raw["llm"]["base_url"],
            api_key=raw["llm"]["api_key"],
            model=raw["llm"]["model"],
        )
        self.tools_json: list[dict[str, Any]] = json.loads(
            (root / "tools.json").read_text(encoding="utf-8")
        )
        self.skills = self._load_skills()
        self._prompts: dict[str, str] = {}

    # --- Skills ---------------------------------------------------------------------------

    def _load_skills(self) -> dict[str, Skill]:
        skills: dict[str, Skill] = {}
        for path in sorted((self.root / "skills").glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            match = re.match(r"---\n(.*?)\n---\n", text, re.S)
            if not match:
                raise AssetError(f"{path}: falta la cabecera name/description")
            header = yaml.safe_load(match.group(1))
            skills[header["name"]] = Skill(header["name"], header["description"], text)
        return skills

    @staticmethod
    def with_optional_checks(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Copia de los esquemas con `checks` opcional en `publish_alert` (interruptor
        `require_checks` apagado). Los demás esquemas no se tocan."""
        out = []
        for schema in schemas:
            function = schema["function"]
            if function["name"] == "publish_alert":
                parameters = dict(function["parameters"])
                parameters["required"] = [r for r in parameters["required"] if r != "checks"]
                schema = {**schema, "function": {**function, "parameters": parameters}}
            out.append(schema)
        return out

    def skill_body(self, name: str) -> str:
        """Una skill sin su cabecera (para inyectarla en un prompt)."""
        text = self.skills[name].content
        return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()

    @property
    def chat_tools_enabled(self) -> bool:
        """Interruptor `chat.tools_enabled`: si los chats reciben tools (por defecto sí)."""
        return bool(self._raw.get("chat", {}).get("tools_enabled", True))

    def skills_index(self, names: list[str]) -> str:
        """Índice para el prompt de sistema: una línea por skill (nombre y descripción)."""
        lines = []
        for name in names:
            if name not in self.skills:
                raise AssetError(f"skill desconocida en agents.yaml: {name}")
            lines.append(f"- `{name}`: {self.skills[name].description}")
        return "\n".join(lines)

    # --- Tools ----------------------------------------------------------------------------

    def tool_schemas(self, names: list[str]) -> list[dict[str, Any]]:
        """Esquemas de `tools.json` tal cual, en el orden del fichero, solo los de `names`."""
        known = {t["function"]["name"] for t in self.tools_json}
        unknown = sorted(set(names) - known)
        if unknown:
            raise AssetError(f"tools desconocidas en agents.yaml: {', '.join(unknown)}")
        return [t for t in self.tools_json if t["function"]["name"] in names]

    # --- Prompts --------------------------------------------------------------------------

    def prompt(self, relative: str) -> str:
        if relative not in self._prompts:
            self._prompts[relative] = _strip_comments(
                (self.root / relative).read_text(encoding="utf-8")
            )
        return self._prompts[relative]

    # --- Agentes --------------------------------------------------------------------------

    def agent(self, name: str) -> AgentConfig:
        base = self._raw["llm"]
        spec = self._raw["agents"][name]

        def pick(key: str, default: Any = None) -> Any:
            return spec.get(key, base.get(key, default))

        return AgentConfig(
            name=name,
            system_prompt=spec["system_prompt"],
            objective_prompt=spec.get("objective_prompt"),
            output_prompt=spec.get("output_prompt"),
            system_prompt_notools=spec.get("system_prompt_notools"),
            tools=list(spec["tools"]),
            skills=list(spec.get("skills", [])),
            disabled_tools=list(spec.get("disabled_tools", [])),
            final_tools=list(spec.get("final_tools", [])),
            final_iteration_response_tools_only=bool(
                spec.get("final_iteration_response_tools_only", True)
            ),
            require_checks=bool(spec.get("require_checks", True)),
            coherence_guardrail=bool(spec.get("coherence_guardrail", True)),
            computed_facts=bool(spec.get("computed_facts", True)),
            max_iterations=int(spec["max_iterations"]),
            max_invocation_s=float(spec.get("max_invocation_s", 60)),
            llm_timeout_s=float(spec.get("llm_timeout_s", 40)),
            temperature=float(pick("temperature")),
            top_p=float(pick("top_p")),
            top_k=int(pick("top_k", -1)),
            repetition_penalty=float(pick("repetition_penalty", 1.0)),
            max_tokens=int(pick("max_tokens")),
            tool_choice=str(pick("tool_choice", "auto")),
            guided_mode=bool(spec.get("guided_mode", False)),
            guided_skill_by_rule=dict(spec.get("guided_skill_by_rule", {})),
            last_decisions_in_state=int(spec.get("last_decisions_in_state", 3)),
            max_history_messages=int(spec.get("max_history_messages", 12)),
            stream=bool(spec.get("stream", False)),
            no_report_reply=str(spec.get("no_report_reply", "")),
        )

    def system_prompt(self, agent: AgentConfig, *, notools: bool = False, **values: object) -> str:
        """Orquestación + salida (si la hay), con los marcadores sustituidos. Siempre se pasan
        `skills_index` y `max_iterations`. `notools`: la variante sin tools de un chat."""
        path = (agent.system_prompt_notools if notools else None) or agent.system_prompt
        parts = [self.prompt(path)]
        if agent.output_prompt:
            parts.append(self.prompt(agent.output_prompt))
        values = {
            "skills_index": self.skills_index(agent.skills),
            "max_iterations": agent.max_iterations,
            **values,
        }
        return render("\n\n".join(p.strip() for p in parts), **values)
