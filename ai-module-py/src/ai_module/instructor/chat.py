"""Chat del instructor (papel `chat_instructor`): como el del alumno, pero con la verdad del
ejercicio: lo programado, los fallos y los comandos, y cómo se comparan con lo detectado."""

from ..assistant.chat import Chat, ChatOutcome, chat_input
from ..assistant.checks import check_text, kinds_named
from ..assistant.facts import PromptInput
from ..assistant.llm import LlmError
from .store import InstructorStore
from .truth import episodes, pairing, truth_causes


def instructor_input(
    store: InstructorStore, question: str, history: list[tuple[str, str]]
) -> PromptInput:
    base = chat_input(store, "instructor", question, history)
    truth = [f"- {e.describe()}" for e in episodes(store)] or [
        "- Nothing was programmed or injected."
    ]
    section = (
        "What the exercise had programmed or injected (the truth):\n"
        + "\n".join(truth)
        + "\n\nProgrammed or injected, compared with what was detected:\n"
        + ("\n".join(pairing(store)) or "- Nothing to compare.")
    )
    # la verdad va antes de la pregunta, para que sea lo último que se lee con ella
    head, _, tail = base.text.rpartition("Question from the operator:")
    text = f"{head}{section}\n\nQuestion from the instructor:{tail}"
    allowed = base.allowed_kinds | truth_causes(store) | kinds_named(text)
    return PromptInput(text=text, current=text, opening="", allowed_kinds=allowed)


class InstructorChat(Chat):
    async def answer_instructor(
        self, store: InstructorStore, question: str, history: list[tuple[str, str]]
    ) -> ChatOutcome:
        inp = instructor_input(store, question, history)
        cfg = self.config.role("chat_instructor")
        out = ChatOutcome("", False, input_text=inp.text)
        user = inp.text
        for _attempt in range(2):
            try:
                result = await self.llm.complete(cfg, cfg.system_prompt(self.config.assets), user)
            except LlmError as exc:
                out.text, out.reasons = "The assistant is not available right now.", [f"llm: {exc}"]
                return out
            verdict = check_text(result.text, inp, "chat", now_rule=self.config.now_rule)
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
        out.text = "I could not give a reliable answer to that. Look at the exercise timeline."
        return out
