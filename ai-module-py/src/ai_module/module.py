"""El módulo de IA completo: reparte cada mensaje del bus entre el detector, el monitor, el
informe y los chats. Sin E/S propia: recibe mensajes y publica por la función `publish`.
"""

import asyncio
import logging
from collections.abc import Callable

from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import Envelope
from poc_contracts.ws import ErrorMessage, EventMessage, StateMessage

from .chat import Chat
from .detection_format import DetectionFormatter
from .detector import Detector
from .monitor import Monitor
from .report import ReportAgent
from .runtime import Runtime

log = logging.getLogger(__name__)

# Respuestas del monitor que pueden venir de otro proceso: se aplican al estado local.
_MONITOR_EVENTS = (
    EventType.ANOMALY_DETECTED,
    EventType.ALERT_CLOSED,
    EventType.DETECTION_ACKNOWLEDGED,
)


class AiModule:
    def __init__(
        self,
        rt: Runtime,
        detector: Detector,
        *,
        with_agents: bool = True,
        on_detection: Callable[[str], None] | None = None,
    ) -> None:
        self.rt = rt
        self.detector = detector
        self.with_agents = with_agents
        self.formatter = DetectionFormatter()
        self._on_detection = on_detection
        self.monitor = Monitor(rt) if with_agents else None
        self.report = ReportAgent(rt, self.monitor) if self.monitor else None
        self.chats = {c: Chat(rt, c, self.report) for c in ConversationId} if with_agents else {}
        self._tasks: list[asyncio.Task[None]] = []
        self._report_started = False

    # --- Ciclo de vida de las tareas ------------------------------------------------------

    def start(self) -> None:
        if self.monitor:
            self._tasks.append(asyncio.create_task(self.monitor.run_forever()))
        self._tasks += [asyncio.create_task(c.run_forever()) for c in self.chats.values()]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # --- Mensajes -------------------------------------------------------------------------

    async def handle(self, message: EventMessage | StateMessage | ErrorMessage) -> None:
        if isinstance(message, StateMessage):
            self.rt.clock.observe(message.sim_time)
            if (
                message.scenario
                and message.run_id
                and self.rt.set_run(message.scenario, message.run_id)
            ):
                log.info("run %s/%s", message.scenario, message.run_id)
        elif isinstance(message, EventMessage):
            await self.handle_event(message.event)

    async def handle_event(self, event: Envelope) -> None:
        rt = self.rt
        if event.type == EventType.AGENT_TOOL_CALL:
            return  # solo para la web: ni el detector, ni los agentes, ni el índice lo ven
        if event.type in (EventType.SIMULATION_STARTED, EventType.SIMULATION_RESET):
            self._new_run()
            if event.type == EventType.SIMULATION_STARTED:
                rt.set_run(event.payload["scenario"], event.payload["run_id"])
        rt.factory.observe(event)
        rt.clock.observe(event.sim_time)
        rt.index.add(event)

        if self.monitor and event.source == "ai-detector":
            self.monitor.submit(event)
        elif event.type in _MONITOR_EVENTS:
            rt.state.apply(event)
        elif event.type == EventType.OPERATOR_MESSAGE:
            chat = self.chats.get(ConversationId(event.payload["conversation_id"]))
            if chat is not None:
                chat.submit(event)
        elif event.type == EventType.SIMULATION_FINISHED and self.report:
            self._start_report(event)

        for detection in self.detector.feed(event):
            line = self.formatter.format(detection)
            if self._on_detection is not None:
                self._on_detection(line)
            await rt.publish(detection)

    def _new_run(self) -> None:
        self.rt.reset_run()
        self._report_started = False
        if self.monitor:
            self.monitor.reset()
        if self.report:
            self.report.reset()
        for chat in self.chats.values():
            chat.reset()

    def _start_report(self, finished: Envelope) -> None:
        if self._report_started or self.report is None:
            return
        self._report_started = True
        payload = finished.payload
        task = asyncio.create_task(
            self.report.generate(payload["scenario"], payload["run_id"], finished.event_id)
        )
        task.add_done_callback(_log_failure)
        self._tasks.append(task)


def _log_failure(task: asyncio.Task[object]) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("report failed", exc_info=task.exception())
