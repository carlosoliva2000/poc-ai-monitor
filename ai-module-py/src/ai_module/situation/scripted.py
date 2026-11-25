"""Asistente con textos preparados (`assistant: scripted`), en lugar del LLM (E7d).

PROVISIONAL para el vídeo del 19/11/2026. Publica lo mismo que publicaría el asistente LLM, con
el mismo aspecto en la web:
- una interpretación (`IncidentEnriched`) tras cada transición de un incidente, con un retraso de
  reloj de pared (la web muestra «pending…» mientras tanto);
- las respuestas de los chats del monitor y del instructor (`AgentActivity` → `AgentReplyChunk`
  → `AgentReply`), por coincidencia exacta de la pregunta normalizada;
- el informe final (`ReportGenerated`) de los escenarios que tienen uno.

Todo lo preparado vive aquí y en `scripted_texts.yaml`; nada más del paquete sabe de ellos.
"""

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from poc_contracts.enums import (
    ActivityState,
    AgentName,
    ConversationId,
    DecidedBy,
    EnrichRole,
    EventType,
    IncidentChange,
)
from poc_contracts.envelope import EventDraft

from ..outbox import EventFactory
from .policy import HERE

log = logging.getLogger(__name__)
ENRICH_CHANGES = {IncidentChange.OPENED, IncidentChange.STATE, IncidentChange.RENAMED,
                  IncidentChange.CLOSED}  # fmt: skip
CHAT_AGENTS = {
    ConversationId.MONITOR: AgentName.CHAT_MONITOR,
    ConversationId.REPORT: AgentName.CHAT_REPORT,
    ConversationId.INSTRUCTOR: AgentName.CHAT_INSTRUCTOR,
}


def normalize(text: str) -> str:
    """Minúsculas, sin puntuación y sin espacios repetidos."""
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def load_texts(path: Path = HERE / "scripted_texts.yaml") -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Reply:
    text: str
    proposal: dict[str, Any] | None = None


class Script:
    """Los textos preparados, sin red ni tiempo (lo que prueban los tests)."""

    def __init__(self, texts: dict[str, Any] | None = None) -> None:
        self.texts = texts or load_texts()

    def enrichment(self, kind: str, state: str) -> str | None:
        return self.texts["enrich"].get(kind, {}).get(state)

    def monitor(self, question: str) -> Reply:
        chat = self.texts["chat"]
        for item in chat["monitor"]:
            if normalize(item["question"]) == normalize(question):
                return Reply(str(item["answer"]).strip())
        return Reply(chat["fallback"])

    def instructor(self, question: str, active_wind: dict[str, Any] | None) -> Reply:
        chat = self.texts["chat"]
        for item in chat["instructor"]:
            if normalize(item["question"]) != normalize(question):
                continue
            if item.get("requires_active_wind") and not active_wind:
                return Reply(chat["instructor_no_wind"])
            return Reply(str(item["answer"]), dict(item["proposal"]))
        return Reply(chat["instructor_fallback"])

    def report(self, scenario: str | None) -> str | None:
        text = (self.texts.get("report") or {}).get(scenario or "")
        return str(text).strip() if text else None


Publish = Callable[[EventDraft], Awaitable[None]]


class ScriptedAssistant:
    """Publica los textos preparados en el bus con el mismo ritmo que un LLM."""

    def __init__(
        self, factory: EventFactory, publish: Publish, now: Callable[[], float],
        script: Script | None = None, seed: int = 19,
    ) -> None:  # fmt: skip
        self.factory = factory
        self.publish = publish
        self.now = now
        self.script = script or Script()
        self.rng = random.Random(seed)
        self._tasks: set[asyncio.Task[None]] = set()
        self._queue: asyncio.Queue[tuple[float, EventDraft]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def reset(self) -> None:
        """Nueva ejecución: se descarta lo pendiente."""
        for task in list(self._tasks):
            task.cancel()
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        while not self._queue.empty():
            self._queue.get_nowait()

    # --- Interpretación de los incidentes -------------------------------------------------------
    def on_incident(self, draft: EventDraft) -> None:
        if IncidentChange(draft.payload["change"]) not in ENRICH_CHANGES:
            return
        if self._worker is None or self._worker.done():
            self._worker = asyncio.ensure_future(self._enrich_worker())
        low, high = self.script.texts["delay_s"]
        # cada texto sale a su hora (publicación + retraso), no uno tras otro: a velocidad alta
        # la cola no se retrasa
        due = asyncio.get_running_loop().time() + self.rng.uniform(low, high)
        self._queue.put_nowait((due, draft))

    async def _enrich_worker(self) -> None:
        """Un solo trabajador, en orden (como la cola del híbrido)."""
        while True:
            due, draft = await self._queue.get()
            await asyncio.sleep(max(0.0, due - asyncio.get_running_loop().time()))
            p = draft.payload
            text = self.script.enrichment(p["kind"], p["state"])
            if text is None:
                continue
            payload = {
                "incident_id": p["incident_id"], "revision": p["revision"], "state": p["state"],
                "text": text, "hypothesis": None, "role": EnrichRole.EXPLAIN.value,
                "decided_by": DecidedBy.LLM.value, "as_of_sim_time": p["as_of_sim_time"],
            }  # fmt: skip
            await self._send(EventType.INCIDENT_ENRICHED, payload, causation_id=draft.event_id)

    async def _send(self, event_type: EventType, payload: dict[str, Any], **kw: Any) -> str:
        draft = self.factory.make(event_type, payload, sim_time=max(self.now(), 0.0), **kw)
        try:
            await self.publish(draft)
        except ConnectionError as exc:
            log.warning("cannot publish %s: %s", event_type.value, exc)
        return draft.event_id

    # --- Chats ------------------------------------------------------------------------------
    def on_operator_message(self, event_id: str, payload: dict[str, Any]) -> None:
        conversation = ConversationId(payload["conversation_id"])
        if conversation == ConversationId.MONITOR:
            reply = self.script.monitor(payload["text"])
        elif conversation == ConversationId.INSTRUCTOR:
            wind = (payload.get("context") or {}).get("active_wind")
            reply = self.script.instructor(payload["text"], wind)
        else:
            reply = Reply(self.script.texts["chat"]["fallback"])
        self._spawn(self._answer(conversation, event_id, reply))

    async def _activity(self, agent: AgentName, state: ActivityState, inv: str, cause: str) -> None:
        payload = {"agent": agent.value, "state": state.value, "invocation_id": inv,
                   "causation_id": cause}  # fmt: skip
        await self._send(EventType.AGENT_ACTIVITY, payload, causation_id=cause)

    async def _answer(self, conversation: ConversationId, reply_to: str, reply: Reply) -> None:
        agent = CHAT_AGENTS[conversation]
        inv = self.factory.ids.next("inv")
        await self._activity(agent, ActivityState.STARTED, inv, reply_to)
        await asyncio.sleep(float(self.script.texts["thinking_s"]))
        chunk = self.script.texts["chunk"]
        words = re.split(r"(?<=\s)", reply.text)  # conserva los espacios y saltos de línea
        for i in range(0, len(words), int(chunk["words"])):
            delta = "".join(words[i : i + int(chunk["words"])])
            payload = {"conversation_id": conversation.value, "reply_to": reply_to, "delta": delta}
            await self._send(
                EventType.AGENT_REPLY_CHUNK, payload, causation_id=reply_to,
                conversation=conversation,
            )  # fmt: skip
            await asyncio.sleep(float(chunk["interval_s"]))
        final: dict[str, Any] = {"conversation_id": conversation.value, "reply_to": reply_to,
                                 "text": reply.text, "tool_calls": []}  # fmt: skip
        if conversation == ConversationId.INSTRUCTOR:
            final["proposal"] = reply.proposal
        await self._send(
            EventType.AGENT_REPLY, final, causation_id=reply_to, conversation=conversation
        )
        await self._activity(agent, ActivityState.FINISHED, inv, reply_to)

    # --- Informe ----------------------------------------------------------------------------
    def on_finished(self, scenario: str | None, run_id: str, incidents: int) -> None:
        markdown = self.script.report(scenario)
        if markdown is not None:
            self._spawn(self._report(run_id, markdown, incidents))

    async def _report(self, run_id: str, markdown: str, incidents: int) -> None:
        inv = self.factory.ids.next("inv")
        payload = {"agent": AgentName.REPORT.value, "state": ActivityState.STARTED.value,
                   "invocation_id": inv, "causation_id": None}  # fmt: skip
        await self._send(EventType.AGENT_ACTIVITY, payload)
        await asyncio.sleep(float(self.script.texts["report_delay_s"]))
        report = {"run_id": run_id, "markdown": markdown, "alerts_count": incidents}
        await self._send(EventType.REPORT_GENERATED, report)
        await self._send(EventType.AGENT_ACTIVITY, {**payload, "state": "finished"})
