"""Proceso A del asistente (el del alumno): interpreta incidentes y propone hipótesis.

    uv run --project ai-module-py python -m ai_module.assistant --platform http://127.0.0.1:8100

Lee del bus solo lo que necesita (el mundo, los incidentes y el ciclo de vida de la ejecución):
**no se suscribe al dominio `sim` salvo a los tres eventos del ciclo de vida, ni al chat y los
topics del instructor**, y no habla HTTP con la plataforma. Del ciclo de vida solo guarda el
`run_id`: el nombre del escenario ya es una pista (`hijack`), así que lo descarta.
El vLLM local es lo único a lo que se conecta además del bus.
"""

import argparse
import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from poc_contracts.enums import ActivityState, AgentName, ConversationId, EventType, IncidentChange
from poc_contracts.envelope import Envelope
from poc_contracts.ws import EventMessage, StateMessage

from ..bus_client import DEFAULT_PLATFORM, BusClient
from ..ids import IdAllocator
from ..outbox import EventFactory, format_t
from ..situation.features import load_assets
from . import freeze
from .chat import Chat
from .config import DEFAULT_CONFIG, AssistantConfig, load_config
from .interpret import Interpreter, Outcome, is_interpreted
from .llm import LlmError, LlmPort, VllmClient
from .llm_queue import (
    PRIORITY_CHAT,
    PRIORITY_CLOSE,
    PRIORITY_OPEN,
    PRIORITY_RECOVERY,
    PRIORITY_REPORT,
    Job,
    LlmQueue,
)
from .replying import activity, publish_reply
from .report import Reporter
from .store import Store
from .trace import Trace

log = logging.getLogger("ai_module.assistant")

# Lo único que recibe este proceso. Nada de `sim.instructor`, `sim.player.Fault*`, el modo
# interactivo ni `ops.instructor` / `ai.instructor` (la verdad y el chat del instructor).
PATTERNS = (
    "citadel.pub.evt.air.>",
    "citadel.pub.evt.env.>",
    "citadel.pub.evt.ai.d1.IncidentUpdated.v1",
    "citadel.pub.evt.ops.monitor.OperatorMessage.v1",
    "citadel.pub.evt.ops.report.OperatorMessage.v1",
    "citadel.pub.evt.sim.player.SimulationStarted.v1",
    "citadel.pub.evt.sim.player.SimulationReset.v1",
    "citadel.pub.evt.sim.player.SimulationFinished.v1",
)
RESET_TYPES = {EventType.SIMULATION_STARTED, EventType.SIMULATION_RESET}
CHAT_AGENTS = {
    ConversationId.MONITOR: AgentName.CHAT_MONITOR,
    ConversationId.REPORT: AgentName.CHAT_REPORT,
}
PRIORITY = {
    IncidentChange.OPENED: PRIORITY_OPEN,
    IncidentChange.RENAMED: PRIORITY_OPEN,
    IncidentChange.STATE: PRIORITY_RECOVERY,
    IncidentChange.CLOSED: PRIORITY_CLOSE,
}


class AssistantProcess:
    def __init__(
        self, platform_url: str, config: AssistantConfig, llm: LlmPort, runs_dir: Path | None = None
    ) -> None:
        self.config = config
        self.ids = IdAllocator("a")
        self.factory = EventFactory(self.ids)
        assets = load_assets()
        self.store = Store(assets.cn0_nominal_dbhz, assets.agc_nominal_db)
        self.queue = LlmQueue()
        self.interpreter = Interpreter(config, llm)
        self.chat = Chat(config, llm)
        self.reporter = Reporter(config, llm)
        self._report_task: asyncio.Task[None] | None = None
        self.bus = BusClient(platform_url, patterns=PATTERNS)
        self.runs_dir = runs_dir
        self.run_id = ""
        self.trace = Trace()

    def _reset(self, run_id: str = "") -> None:
        self.ids.reset()
        self.store.reset()
        self.queue.reset()
        if self._report_task is not None:
            self._report_task.cancel()
            self._report_task = None
        self.run_id = run_id
        path = None
        if self.runs_dir and run_id:
            path = self.runs_dir / "_assistant" / run_id / "assistant.jsonl"
        self.trace = Trace(path)

    async def handle(self, event: Envelope) -> None:
        if event.type in RESET_TYPES:
            self._reset(str(event.payload.get("run_id", "")))
            return
        if event.type == EventType.SIMULATION_FINISHED:
            self._report_task = asyncio.ensure_future(self._schedule_report(event.event_id))
            return
        if event.type == EventType.OPERATOR_MESSAGE:
            self._question(event)
            return
        raw = event.model_dump(mode="json")
        self.factory.observe(event)
        if not self.store.observe(raw) or event.type != EventType.INCIDENT_UPDATED:
            return
        update = event.payload
        if not is_interpreted(update):
            return
        change = IncidentChange(update["change"])
        received = time.monotonic()
        key = f"incident:{update['incident_id']}"
        self.queue.submit(
            Job(
                priority=PRIORITY[change],
                key=key,
                expire_s=self.config.queue.expire_s,
                run=lambda: self._interpret(event.event_id, update, received),
                on_drop=lambda why, u=update: self.trace.write(
                    {"incident_id": u["incident_id"], "revision": u["revision"], "dropped": why}
                ),
            )
        )

    async def _schedule_report(self, finished_id: str) -> None:
        """Al terminar el ejercicio: espera a los últimos incidentes (el monitor cierra el último
        segundo después del fin) y pone el informe en la cola, detrás de todo lo demás."""
        await asyncio.sleep(self.config.queue.report_settle_s)
        self.queue.submit(Job(priority=PRIORITY_REPORT, run=lambda: self._report(finished_id)))

    async def _report(self, finished_id: str) -> None:
        invocation = self.ids.next("inv")
        await activity(self._send, AgentName.REPORT, invocation, finished_id, ActivityState.STARTED)
        started = time.monotonic()
        out = await self.reporter.write(self.store)
        self.store.report = out.markdown
        payload = {
            "run_id": self.run_id,
            "markdown": out.markdown,
            "alerts_count": out.alerts_count,
        }
        await self._send(EventType.REPORT_GENERATED, payload, causation_id=finished_id)
        await activity(
            self._send, AgentName.REPORT, invocation, finished_id, ActivityState.FINISHED
        )
        self.trace.write(
            {"report": True, "written": out.written, "reasons": out.reasons,
             "attempts": out.attempts, "latency_s": round(out.latency_s, 2),
             "since_finish_s": round(time.monotonic() - started, 2), "input": out.input_text,
             "markdown": out.markdown}
        )  # fmt: skip

    def _question(self, event: Envelope) -> None:
        """Una pregunta del operador (solo `monitor` e `informe`: el chat del instructor no llega
        a este proceso). Se contesta en la cola, detrás de las aperturas de incidentes."""
        conversation = ConversationId(event.payload["conversation_id"])
        if conversation not in CHAT_AGENTS:
            return
        self.factory.observe(event)
        snapshot = self.store.snapshot()  # la situación de cuando se pregunta
        self.queue.submit(
            Job(
                priority=PRIORITY_CHAT,
                expire_s=self.config.queue.chat_expire_s,
                run=lambda: self._answer(
                    event.event_id, conversation, event.payload["text"], snapshot
                ),
            )
        )

    async def _send(self, event_type: EventType, payload: dict[str, Any], **kw: Any) -> None:
        draft = self.factory.make(event_type, payload, sim_time=max(self.store.now, 0.0), **kw)
        try:
            await self.bus.publish(draft)
        except ConnectionError as exc:
            log.warning("cannot publish %s: %s", event_type.value, exc)

    async def _answer(
        self, reply_to: str, conversation: ConversationId, question: str, situation: Store
    ) -> None:
        agent = CHAT_AGENTS[conversation]
        invocation = self.ids.next("inv")
        await activity(self._send, agent, invocation, reply_to, ActivityState.STARTED)
        started = time.monotonic()
        history = self.store.history[conversation.value]
        out = await self.chat.answer(situation, conversation.value, question, history)
        await publish_reply(self._send, conversation, reply_to, out.text)
        await activity(self._send, agent, invocation, reply_to, ActivityState.FINISHED)
        self.store.history[conversation.value].append((question, out.text))
        self.trace.write(
            {"chat": conversation.value, "reply_to": reply_to, "question": question,
             "text": out.text, "answered": out.answered, "reasons": out.reasons,
             "attempts": out.attempts, "latency_s": round(out.latency_s, 2),
             "since_question_s": round(time.monotonic() - started, 2),
             "input": out.input_text}
        )  # fmt: skip

    async def _interpret(self, event_id: str, update: dict[str, Any], received: float) -> None:
        retry = time.monotonic() - received < self.config.queue.retry_before_s
        out = await self.interpreter.interpret(update, self.store, retry=retry)
        if out is None:
            return
        self._trace(update, out, time.monotonic() - received)
        if not out.published:
            log.info("%s %s: no text (%s)", update["incident_id"], update["revision"], out.error
                     or out.reasons)  # fmt: skip
            return
        draft = self.factory.make(
            EventType.INCIDENT_ENRICHED,
            self.interpreter.payload(update, out),
            sim_time=max(self.store.now, update["as_of_sim_time"]),
            causation_id=event_id,
        )
        try:
            await self.bus.publish(draft)
        except ConnectionError as exc:
            log.warning("cannot publish the text: %s", exc)
            return
        self.store.texts[update["incident_id"]] = out.text
        log.info("%s %s %s: %s", format_t(update["as_of_sim_time"]), update["incident_id"],
                 out.role, out.text)  # fmt: skip

    def _trace(self, update: dict[str, Any], out: Outcome, since_event_s: float) -> None:
        self.trace.write(
            {
                "incident_id": out.incident_id, "revision": out.revision, "role": out.role,
                "input": out.input_text, "text": out.text, "hypothesis": out.hypothesis,
                "error": out.error, "reasons": out.reasons,
                "attempts": [a.__dict__ for a in out.attempts],
                "latency_s": round(out.latency_s, 2), "since_event_s": round(since_event_s, 2),
            }
        )  # fmt: skip

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
    parser = argparse.ArgumentParser(description="Student-side assistant (LLM)")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    config = load_config(args.config)
    try:
        log.info(freeze.verify(config.assets))
    except freeze.FreezeError as exc:
        raise SystemExit(f"assistant stopped: {exc}") from exc
    log.info("assistant, model=%s, platform=%s", config.llm.model, args.platform)
    try:
        asyncio.run(
            AssistantProcess(args.platform, config, VllmClient(config.llm), args.runs_dir).run()
        )
    except LlmError as exc:
        raise SystemExit(f"assistant stopped: {exc}") from exc


if __name__ == "__main__":
    main()
