"""Proceso B del asistente (el del instructor): traductor de órdenes y chat con la verdad.

    uv run --project ai-module-py python -m ai_module.instructor --platform http://127.0.0.1:8100

Es **el único proceso que se suscribe a lo del instructor**: lo programado (`ExerciseInjects`), los
fallos inyectados, los comandos de viento y su chat (`ops.instructor`). Responde en `ai.instructor`,
que el alumno no recibe. **No publica `InstructorCommand` ni cambia nada**: propone y la web, con la
confirmación del instructor, manda el comando a la plataforma.
"""

import argparse
import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from poc_contracts.enums import ActivityState, AgentName, ConversationId, EventType
from poc_contracts.envelope import Envelope
from poc_contracts.ws import EventMessage, StateMessage

from ..assistant import freeze
from ..assistant.config import DEFAULT_CONFIG, AssistantConfig, load_config
from ..assistant.llm import LlmError, LlmPort, VllmClient
from ..assistant.llm_queue import PRIORITY_CHAT, PRIORITY_REPORT, Job, LlmQueue
from ..assistant.replying import activity, publish_reply
from ..assistant.trace import Trace
from ..bus_client import DEFAULT_PLATFORM, BusClient
from ..ids import IdAllocator
from ..outbox import EventFactory
from ..situation.features import load_assets
from .chat import InstructorChat
from .debrief import Debriefer
from .store import InstructorStore
from .translator import Translator

log = logging.getLogger("ai_module.instructor")

PATTERNS = (
    "citadel.pub.evt.air.>",
    "citadel.pub.evt.env.>",
    "citadel.pub.evt.ai.d1.IncidentUpdated.v1",
    "citadel.pub.evt.sim.instructor.>",
    "citadel.pub.evt.sim.player.FaultInjected.v1",
    "citadel.pub.evt.sim.player.FaultCleared.v1",
    "citadel.pub.evt.sim.player.SimulationStarted.v1",
    "citadel.pub.evt.sim.player.SimulationReset.v1",
    "citadel.pub.evt.sim.player.SimulationFinished.v1",
    "citadel.pub.evt.ops.instructor.OperatorMessage.v1",
)
RESET_TYPES = {EventType.SIMULATION_STARTED, EventType.SIMULATION_RESET}


class InstructorProcess:
    def __init__(
        self, platform_url: str, config: AssistantConfig, llm: LlmPort, runs_dir: Path | None = None
    ) -> None:
        self.config = config
        self.ids = IdAllocator("i")
        self.factory = EventFactory(self.ids)
        assets = load_assets()
        self.store = InstructorStore(assets.cn0_nominal_dbhz, assets.agc_nominal_db)
        self.queue = LlmQueue()
        self.translator = Translator(config, llm)
        self.chat = InstructorChat(config, llm)
        self.debriefer = Debriefer(config, llm)
        self._debrief_task: asyncio.Task[None] | None = None
        self.bus = BusClient(platform_url, patterns=PATTERNS)
        self.runs_dir = runs_dir
        self.history: list[tuple[str, str]] = []
        self.run_id = ""
        self.trace = Trace()

    def _reset(self, event: Envelope) -> None:
        run_id = str(event.payload.get("run_id", ""))
        self.ids.reset()
        self.store.reset()
        self.queue.reset()
        if self._debrief_task is not None:
            self._debrief_task.cancel()
            self._debrief_task = None
        self.history = []
        self.store.scenario = event.payload.get("scenario")
        self.run_id = run_id
        path = None
        if self.runs_dir and run_id:
            path = self.runs_dir / "_assistant" / run_id / "instructor.jsonl"
        self.trace = Trace(path)

    async def handle(self, event: Envelope) -> None:
        if event.type in RESET_TYPES:
            self._reset(event)
            return
        if event.type == EventType.SIMULATION_FINISHED:
            self.store.finished = True
            self._debrief_task = asyncio.ensure_future(self._schedule_debrief(event.event_id))
            return
        self.factory.observe(event)
        if event.type == EventType.OPERATOR_MESSAGE:
            self._question(event)
            return
        self.store.observe(event.model_dump(mode="json"))

    async def _schedule_debrief(self, finished_id: str) -> None:
        """Al terminar: espera a los últimos incidentes y pone el debriefing en la cola."""
        await asyncio.sleep(self.config.queue.report_settle_s)
        self.queue.submit(Job(priority=PRIORITY_REPORT, run=lambda: self._debrief(finished_id)))

    async def _debrief(self, finished_id: str) -> None:
        invocation = self.ids.next("inv")
        agent = AgentName.DEBRIEF
        await activity(self._send, agent, invocation, finished_id, ActivityState.STARTED)
        started = time.monotonic()
        out = await self.debriefer.write(self.store)
        payload = {
            "run_id": self.run_id,
            "markdown": out.markdown,
            "injects_count": out.injects_count,
        }
        await self._send(EventType.DEBRIEF_GENERATED, payload, causation_id=finished_id)
        await activity(self._send, agent, invocation, finished_id, ActivityState.FINISHED)
        self.trace.write(
            {"debrief": True, "written": out.written, "reasons": out.reasons,
             "attempts": out.attempts, "latency_s": round(out.latency_s, 2),
             "since_finish_s": round(time.monotonic() - started, 2), "input": out.input_text,
             "markdown": out.markdown}
        )  # fmt: skip

    def _question(self, event: Envelope) -> None:
        if event.payload["conversation_id"] != ConversationId.INSTRUCTOR.value:
            return
        snapshot = self.store.snapshot()
        self.queue.submit(
            Job(
                priority=PRIORITY_CHAT,
                expire_s=self.config.queue.chat_expire_s,
                run=lambda: self._answer(event.event_id, event.payload, snapshot),
            )
        )

    async def _send(self, event_type: EventType, payload: dict[str, Any], **kw: Any) -> None:
        draft = self.factory.make(event_type, payload, sim_time=max(self.store.now, 0.0), **kw)
        try:
            await self.bus.publish(draft)
        except ConnectionError as exc:
            log.warning("cannot publish %s: %s", event_type.value, exc)

    async def _answer(
        self, reply_to: str, message: dict[str, Any], situation: InstructorStore
    ) -> None:
        text = message["text"]
        agent = AgentName.CHAT_INSTRUCTOR
        invocation = self.ids.next("inv")
        await activity(self._send, agent, invocation, reply_to, ActivityState.STARTED)
        started = time.monotonic()
        translation = await self.translator.translate(text, situation.active_wind())
        record: dict[str, Any] = {
            "reply_to": reply_to, "question": text, "tool": translation.tool,
            "calls": translation.raw, "reasons": translation.reasons,
            "active_wind_from_bus": situation.active_wind(),
            "active_wind_from_web": (message.get("context") or {}).get("active_wind"),
            "translator_latency_s": round(translation.latency_s, 2),
        }  # fmt: skip
        proposal = translation.proposal
        reply = translation.text or ""
        tool_calls = [translation.tool] if translation.tool else []
        if translation.to_chat:
            out = await self.chat.answer_instructor(situation, text, self.history)
            reply, tool_calls = out.text, []
            record.update(chat_input=out.input_text, chat_reasons=out.reasons,
                          chat_attempts=out.attempts, chat_answered=out.answered)  # fmt: skip
        await publish_reply(
            self._send, ConversationId.INSTRUCTOR, reply_to, reply,
            tool_calls=tool_calls, proposal=proposal,
        )  # fmt: skip
        await activity(self._send, agent, invocation, reply_to, ActivityState.FINISHED)
        self.history.append((text, reply))
        record.update(reply=reply, proposal=proposal,
                      since_question_s=round(time.monotonic() - started, 2))  # fmt: skip
        self.trace.write(record)

    async def run(self) -> None:
        await VllmClient(self.config.llm).check_model()
        await self.serve()

    async def serve(self) -> None:
        """Escucha el bus (sin comprobar vLLM: las pruebas usan un LLM falso)."""
        async with self.bus:
            async for message in self.bus.messages():
                if isinstance(message, EventMessage):
                    await self.handle(message.event)
                elif isinstance(message, StateMessage):
                    self.store.now = max(self.store.now, message.sim_time)


def main() -> None:
    parser = argparse.ArgumentParser(description="Instructor-side assistant (translator and chat)")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    config = load_config(args.config)
    try:
        log.info(freeze.verify(config.assets))
    except freeze.FreezeError as exc:
        raise SystemExit(f"instructor assistant stopped: {exc}") from exc
    log.info("instructor assistant, model=%s, platform=%s", config.llm.model, args.platform)
    try:
        asyncio.run(
            InstructorProcess(args.platform, config, VllmClient(config.llm), args.runs_dir).run()
        )
    except LlmError as exc:
        raise SystemExit(f"instructor assistant stopped: {exc}") from exc


if __name__ == "__main__":
    main()
