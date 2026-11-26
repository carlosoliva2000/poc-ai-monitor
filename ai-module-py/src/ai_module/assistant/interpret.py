"""Interpretación de los incidentes y hipótesis en «sin determinar» (papeles `explain` e
`hypothesis`). El LLM solo escribe texto: no toca el incidente. Núcleo sin bus ni cola
(`Interpreter.interpret`), para usarlo igual en directo y fuera de línea.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from poc_contracts.enums import IncidentChange, IncidentKind
from poc_contracts.payloads import IncidentHypothesis

from .checks import check_text
from .config import AssistantConfig, prompt_fingerprint
from .facts import PromptInput, build_input
from .llm import LlmError, LlmPort, LlmResult
from .store import Store

log = logging.getLogger(__name__)

# Cambios de un incidente que se interpretan: `severity` es política y `evidence` ya se ve en la
# tarjeta.
INTERPRETED = frozenset(
    {IncidentChange.OPENED, IncidentChange.STATE, IncidentChange.RENAMED, IncidentChange.CLOSED}
)
ROLE_FOR_TEXT = {"explain": "explain", "hypothesis": "hypothesis"}


@dataclass
class Attempt:
    reasons: list[str]
    latency_s: float
    raw: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class Outcome:
    """Qué salió de interpretar una revisión (publicado o no, y por qué)."""

    incident_id: str
    revision: int
    role: str  # `explain` | `hypothesis`
    text: str | None = None
    hypothesis: dict[str, Any] | None = None
    attempts: list[Attempt] = field(default_factory=list)
    error: str | None = None
    input_text: str = ""

    @property
    def published(self) -> bool:
        return self.text is not None

    @property
    def reasons(self) -> list[str]:
        return [r for a in self.attempts for r in a.reasons]

    @property
    def latency_s(self) -> float:
        return sum(a.latency_s for a in self.attempts)


def is_interpreted(update: dict[str, Any]) -> bool:
    return IncidentChange(update["change"]) in INTERPRETED


def role_for(update: dict[str, Any], config: AssistantConfig) -> str | None:
    """`hypothesis` para un `UNDETERMINED` que se abre, `explain` para el resto; `None` si el
    papel está apagado."""
    undetermined = update["kind"] == IncidentKind.UNDETERMINED.value
    if (
        undetermined
        and update["change"] == IncidentChange.OPENED.value
        and config.role("hypothesis").enabled
    ):
        return "hypothesis"
    return "explain" if config.role("explain").enabled else None


class Interpreter:
    def __init__(self, config: AssistantConfig, llm: LlmPort) -> None:
        self.config = config
        self.llm = llm

    def fingerprint(self, role: str) -> str:
        return prompt_fingerprint(self.config, role)

    async def interpret(
        self, update: dict[str, Any], store: Store, *, retry: bool = True
    ) -> Outcome | None:
        """Escribe el texto de una revisión; hasta dos intentos (el segundo con los motivos)."""
        role = role_for(update, self.config)
        if role is None:
            return None
        inp = build_input(update, store)
        if role == "hypothesis" and not inp.event_ids:
            role = "explain"  # sin eventos que citar no hay hipótesis publicable
        out = Outcome(update["incident_id"], update["revision"], role, input_text=inp.text)
        cfg = self.config.role(role)
        user = inp.text
        for _attempt in range(2 if retry else 1):
            try:
                result = await self.llm.complete(
                    cfg,
                    cfg.system_prompt(self.config.assets),
                    user,
                    cfg.tool_schemas(self.config.assets) or None,
                )
            except LlmError as exc:
                out.error = str(exc)
                return out
            reasons, text, hyp = self._judge(role, result, inp)
            out.attempts.append(
                Attempt(reasons, result.latency_s, result.text or str(result.tool_args),
                        result.tokens_in, result.tokens_out)
            )  # fmt: skip
            if not reasons:
                out.text, out.hypothesis = text, hyp
                if role == "hypothesis" and hyp is None:
                    out.role = "explain"  # ninguna causa encaja: solo el texto
                return out
            user = (
                f"{inp.text}\n\nYour previous answer was rejected:\n"
                + "\n".join(f"- {r}" for r in reasons)
                + "\nWrite it again fixing all of that."
            )
        return out

    def _judge(
        self, role: str, result: LlmResult, inp: PromptInput
    ) -> tuple[list[str], str | None, dict[str, Any] | None]:
        now_rule = self.config.now_rule
        if role == "explain":
            verdict = check_text(result.text, inp, "explain", now_rule=now_rule)
            return verdict.reasons, (verdict.text if verdict.ok else None), None
        if result.tool_name != "propose_hypothesis" or result.tool_args is None:
            return ["format: call the tool propose_hypothesis"], None, None
        args = result.tool_args
        ranked = args.get("ranked") or []
        try:
            kinds = {IncidentKind(c["kind"]) for c in ranked}
        except (KeyError, ValueError, TypeError):
            return ["format: each cause needs a kind from the allowed list"], None, None
        pieces = [str(args.get("summary", ""))]
        for cause in ranked:
            pieces += [str(x) for x in cause.get("supports", []) + cause.get("missing", [])]
        pieces += [str(c.get("text", "")) for c in args.get("checks", [])]
        reasons: list[str] = []
        texts: list[str] = []
        for piece in pieces:
            verdict = check_text(piece, inp, "hypothesis", kinds, now_rule)
            reasons += verdict.reasons
            texts.append(verdict.text)
        if reasons:
            return list(dict.fromkeys(reasons)), None, None
        summary = texts[0]
        if not ranked:
            return [], summary, None
        # el código, no el modelo, pone la confianza y las evidencias (las de la revisión)
        i = 1
        built_ranked = []
        for cause in ranked:
            n_s, n_m = len(cause.get("supports", [])), len(cause.get("missing", []))
            built_ranked.append(
                {"kind": cause["kind"], "supports": texts[i : i + n_s],
                 "missing": texts[i + n_s : i + n_s + n_m]}
            )  # fmt: skip
            i += n_s + n_m
        built_checks = [
            {"target": c["target"], "text": texts[i + j]} for j, c in enumerate(args["checks"])
        ]
        try:
            hyp = IncidentHypothesis(
                kind=built_ranked[0]["kind"],
                confidence="possible",
                evidence_event_ids=inp.event_ids,
                ranked=built_ranked,
                checks=built_checks,
            )
        except ValidationError as exc:
            return [f"format: {exc.errors()[0]['msg']}"], None, None
        return [], summary, hyp.model_dump(mode="json")

    def payload(self, update: dict[str, Any], out: Outcome) -> dict[str, Any]:
        """El `IncidentEnriched` de un resultado publicable (marcado como del LLM)."""
        assert out.text is not None
        return {
            "incident_id": update["incident_id"],
            "revision": update["revision"],
            "state": update["state"],
            "text": out.text,
            "hypothesis": out.hypothesis,
            "role": "hypothesis" if out.hypothesis else "explain",
            "decided_by": "llm",
            "as_of_sim_time": update["as_of_sim_time"],
            "model": self.config.llm.model,
            "prompt_sha": self.fingerprint(out.role),
        }
