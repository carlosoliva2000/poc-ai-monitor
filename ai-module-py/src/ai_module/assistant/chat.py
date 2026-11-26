"""Chats del alumno (papel `chat`): el del monitor y el del informe.

El código pone en el prompt lo que el asistente sabe (incidentes, notas ya publicadas, hechos de
ahora y la conversación); el LLM solo redacta, sin tools. La respuesta se comprueba **antes** de
publicarla (como todo texto del asistente) y por eso no hay streaming real: se genera entera y se
escribe a la web en trozos rápidos. Nunca recibe la verdad ni el chat del instructor.
"""

from dataclasses import dataclass, field
from typing import Any

from poc_contracts.enums import IncidentKind

from ..outbox import format_t
from .checks import Verdict, check_text, kinds_named
from .config import AssistantConfig
from .facts import PromptInput, context_lines, evidence_lines, now_facts
from .llm import LlmError, LlmPort
from .store import Store

FALLBACK_REJECTED = "I could not give a reliable answer to that. Look at the incident cards."
FALLBACK_ERROR = "The assistant is not available right now. Look at the incident cards."
HISTORY_TURNS = 3  # últimos intercambios de la conversación que entran en el prompt
MAX_INCIDENTS = 6
SEVERITY_ORDER = ["low", "medium", "high"]


@dataclass
class ChatOutcome:
    text: str
    answered: bool  # `False` = respuesta fija (rechazada dos veces o error del LLM)
    reasons: list[str] = field(default_factory=list)
    latency_s: float = 0.0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    input_text: str = ""


def path_text(revisions: list[dict[str, Any]]) -> str:
    """La historia del incidente con sus horas, escrita por el código: «opened as Command link
    lost at T+06:12; renamed to Hijack at T+06:28; recovering at T+06:53; closed at T+07:58». Así
    el modelo no mezcla la hora de un cambio de nombre con la del inicio."""
    steps = []
    for r in revisions:
        at = format_t(r["as_of_sim_time"])
        if r["change"] == "opened":
            steps.append(f"opened as {r['name']} at {at}")
        elif r["change"] == "renamed":
            steps.append(f"renamed to {r['name']} at {at}")
        elif r["change"] == "state":
            steps.append(f"{r['state']} at {at}")
        elif r["change"] == "severity":
            steps.append(f"severity {r['severity']} at {at}")
        elif r["change"] == "closed":
            steps.append(f"closed at {at}")
    return "; ".join(steps)


def incident_blocks(store: Store) -> list[str]:
    """Un bloque por incidente: abiertos primero; los cerrados, solo su recorrido y su nota."""
    ordered = sorted(
        store.revisions.items(),
        key=lambda item: (item[1][-1]["state"] == "closed", item[1][0]["opened_at"]),
    )[:MAX_INCIDENTS]
    blocks = []
    for incident_id, revisions in ordered:
        last = revisions[-1]
        peak = max((r["severity"] for r in revisions), key=SEVERITY_ORDER.index)
        head = (
            f"{last['name']} — {last['state']}, severity {last['severity']} (highest it reached: "
            f"{peak}), confidence {last['confidence']}. History: {path_text(revisions)}."
        )
        lines = [head]
        if last["state"] != "closed":
            evidence = evidence_lines(last, for_chat=True)
            if evidence:
                lines.append(
                    f"Evidence at {format_t(last['as_of_sim_time'])}:\n" + "\n".join(evidence)
                )
            context = context_lines(last)
            if context:
                lines.append("Context:\n" + "\n".join(context))
            if last["checks"]:
                lines.append("What to check:\n" + "\n".join(f"- {c}" for c in last["checks"]))
        if incident_id in store.texts:
            lines.append(f'Note already written for the operator: "{store.texts[incident_id]}"')
        blocks.append("\n".join(lines))
    return blocks


def ranking_line(store: Store) -> str:
    """Los incidentes de más a menos grave según la máxima severidad que alcanzaron (lo calcula el
    código: el modelo se equivocaba al compararlas)."""
    peaks = [
        (max((r["severity"] for r in revs), key=SEVERITY_ORDER.index), revs[-1]["name"])
        for revs in store.revisions.values()
    ]
    peaks.sort(key=lambda p: -SEVERITY_ORDER.index(p[0]))
    return "Incidents by the highest severity they reached: " + "; ".join(
        f"{name} ({peak})" for peak, name in peaks
    )


def chat_input(
    store: Store, conversation: str, question: str, history: list[tuple[str, str]] | None = None
) -> PromptInput:
    parts = [f"It is now T+{int(store.now) // 60:02d}:{int(store.now) % 60:02d} in the exercise."]
    blocks = incident_blocks(store)
    if blocks:
        parts.append(
            "Incidents:\n\n" + "\n\n".join(f"Incident {i}: {b}" for i, b in enumerate(blocks, 1))
        )
    else:
        parts.append("There are no incidents so far.")
    if store.revisions:
        parts.append(ranking_line(store))
    facts = now_facts(store)
    if facts:
        parts.append("Facts now:\n" + "\n".join(facts))
    if conversation == "report":
        parts.append("Report:\n" + (store.report or "The report has not been written yet."))
    history = (history or [])[-HISTORY_TURNS:]
    if history:
        parts.append(
            "Conversation so far:\n" + "\n".join(f"Operator: {q}\nYou: {a}" for q, a in history)
        )
    parts.append(f"Question from the operator: {question}")
    text = "\n\n".join(parts)
    kinds: set[IncidentKind] = {IncidentKind(rev[-1]["kind"]) for rev in store.revisions.values()}
    for rev in store.revisions.values():
        for r in rev:
            kinds.add(IncidentKind(r["kind"]))
    return PromptInput(text=text, current=text, opening="", allowed_kinds=kinds | kinds_named(text))


class Chat:
    def __init__(self, config: AssistantConfig, llm: LlmPort) -> None:
        self.config = config
        self.llm = llm

    async def answer(
        self, store: Store, conversation: str, question: str, history: list[tuple[str, str]]
    ) -> ChatOutcome:
        """`store`: la situación de cuando se hizo la pregunta (`Store.snapshot`); `history`: la
        conversación hasta ahora, que sí es la de ahora."""
        inp = chat_input(store, conversation, question, history)
        cfg = self.config.role("chat")
        out = ChatOutcome("", False, input_text=inp.text)
        user = inp.text
        for _attempt in range(2):
            try:
                result = await self.llm.complete(cfg, cfg.system_prompt(self.config.assets), user)
            except LlmError as exc:
                out.text, out.reasons = FALLBACK_ERROR, [f"llm: {exc}"]
                return out
            verdict: Verdict = check_text(result.text, inp, "chat", now_rule=self.config.now_rule)
            out.latency_s += result.latency_s
            out.attempts.append({"raw": result.text, "reasons": verdict.reasons})
            if verdict.ok:
                out.text, out.answered, out.reasons = verdict.text, True, []
                return out
            out.reasons = verdict.reasons
            user = (
                f"{inp.text}\n\nYour previous answer was rejected:\n"
                + "\n".join(f"- {r}" for r in verdict.reasons)
                + "\nWrite it again fixing all of that."
            )
        out.text = FALLBACK_REJECTED
        return out
