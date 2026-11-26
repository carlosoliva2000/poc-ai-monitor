"""Debriefing del instructor (papel `debrief`), al terminar el ejercicio.

La lista de lo inyectado frente a lo detectado y los incidentes los escribe el código (`truth.py`);
el LLM solo escribe un resumen y hasta tres puntos para comentar con el alumno, que pasan por las
mismas comprobaciones que todo texto del asistente. Lleva la verdad: va por `ai.instructor`.
"""

from dataclasses import dataclass, field
from typing import Any

from poc_contracts.enums import IncidentKind

from ..assistant.chat import path_text
from ..assistant.checks import check_text
from ..assistant.config import AssistantConfig
from ..assistant.facts import PromptInput
from ..assistant.llm import LlmError, LlmPort
from ..assistant.report import NOT_AVAILABLE, end_line, ordered_incidents
from .store import InstructorStore
from .truth import episodes, pairing, truth_causes


@dataclass
class DebriefOutcome:
    markdown: str
    injects_count: int
    written: bool
    reasons: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    latency_s: float = 0.0
    input_text: str = ""


def incident_lines(store: InstructorStore) -> list[str]:
    return [f"- {revs[-1]['name']}: {path_text(revs)}" for revs in ordered_incidents(store)] or [
        "- The system opened no incidents."
    ]


def debrief_input(store: InstructorStore) -> PromptInput:
    text = "\n\n".join(
        [
            end_line(store),
            "Injected or programmed, compared with what was detected:\n"
            + ("\n".join(pairing(store)) or "- Nothing was injected."),
            "Incidents the system opened:\n" + "\n".join(incident_lines(store)),
        ]
    )
    kinds = truth_causes(store)
    for revisions in store.revisions.values():
        kinds |= {IncidentKind(r["kind"]) for r in revisions}
    return PromptInput(text=text, current=text, opening="", allowed_kinds=kinds)


def assemble(store: InstructorStore, summary: str | None, points: list[str]) -> str:
    lines = ["# Exercise debriefing", "", end_line(store), "", "## Injected and detected", ""]
    lines += pairing(store) or ["- Nothing was injected."]
    lines += ["", "## Incidents the system opened", ""] + incident_lines(store)
    lines += ["", "## Summary", "", summary or NOT_AVAILABLE, "", "## Points to discuss", ""]
    lines += [f"- {p}" for p in points] or [NOT_AVAILABLE]
    return "\n".join(lines) + "\n"


class Debriefer:
    def __init__(self, config: AssistantConfig, llm: LlmPort) -> None:
        self.config = config
        self.llm = llm

    def _clean(self, piece: Any, inp: PromptInput, reasons: list[str]) -> str:
        verdict = check_text(str(piece), inp, "report_piece", now_rule=self.config.now_rule)
        reasons.extend(verdict.reasons)
        return verdict.text

    async def write(self, store: InstructorStore) -> DebriefOutcome:
        count = len(episodes(store))
        inp = debrief_input(store)
        out = DebriefOutcome("", count, False, input_text=inp.text)
        cfg = self.config.role("debrief")
        user = inp.text
        for _attempt in range(2):
            try:
                result = await self.llm.complete(
                    cfg,
                    cfg.system_prompt(self.config.assets),
                    user,
                    cfg.tool_schemas(self.config.assets),
                )
            except LlmError as exc:
                out.reasons = [f"llm: {exc}"]
                break
            out.latency_s += result.latency_s
            args = result.tool_args or {}
            reasons: list[str] = []
            summary = self._clean(args.get("summary", ""), inp, reasons)
            points = [self._clean(p, inp, reasons) for p in (args.get("points") or [])][:3]
            if not args:
                reasons.append("format: call the tool write_debrief")
            reasons = list(dict.fromkeys(reasons))
            out.attempts.append({"args": args, "reasons": reasons})
            if not reasons:
                out.written, out.markdown = True, assemble(store, summary, points)
                return out
            out.reasons = reasons
            user = (
                f"{inp.text}\n\nYour previous answer was rejected:\n"
                + "\n".join(f"- {r}" for r in reasons)
                + "\nWrite it again fixing all of that."
            )
        out.markdown = assemble(store, None, [])
        return out
