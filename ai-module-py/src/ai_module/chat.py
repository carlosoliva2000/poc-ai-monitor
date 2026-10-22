"""Chats con los agentes: uno por conversación (`monitor` e `report`), cada uno en su propia
tarea, **sin pasar por la cola del monitor**: un chat lento no retrasa una detección.

- Historial de los últimos 12 mensajes (pregunta del operador y respuesta final).
- El prompt de sistema se rehace en cada pregunta (cambia el instante actual).
- Respuesta en streaming: `AgentReplyChunk` efímeros y, al final, `AgentReply`.
- El chat del informe, antes de que exista el informe, contesta con un texto fijo de
  `agents.yaml` (sin llamar al LLM).
"""

import asyncio
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from poc_contracts.enums import ActivityState, AgentName, ConversationId, EventType
from poc_contracts.envelope import Envelope

from .agent.engine import AgentEngine
from .agent.llm import Messages
from .agent.tools import Toolbox
from .agent.trace import InvocationTrace
from .outbox import format_t
from .report import ReportAgent
from .runtime import Runtime

log = logging.getLogger(__name__)

_AGENT = {
    ConversationId.MONITOR: (AgentName.CHAT_MONITOR, "chat_monitor"),
    ConversationId.REPORT: (AgentName.CHAT_REPORT, "chat_report"),
}


class Chat:
    def __init__(
        self, rt: Runtime, conversation: ConversationId, report: ReportAgent | None = None
    ) -> None:
        self.rt = rt
        self.conversation = conversation
        self.report = report
        self.agent_name, config_name = _AGENT[conversation]
        self.config = rt.assets.agent(config_name)
        self.history: deque[dict[str, str]] = deque(maxlen=self.config.max_history_messages)
        self._queue: asyncio.Queue[Envelope] = asyncio.Queue()
        self.busy = False

    def submit(self, event: Envelope) -> None:
        self._queue.put_nowait(event)

    def reset(self) -> None:
        self.history.clear()
        while not self._queue.empty():
            self._queue.get_nowait()

    async def run_forever(self) -> None:
        while True:
            event = await self._queue.get()
            self.busy = True
            try:
                await self.answer(event)
            except Exception:
                log.exception("chat %s failed", self.conversation.value)
            finally:
                self.busy = False

    async def answer(self, event: Envelope) -> None:
        rt, cfg = self.rt, self.config
        question = str(event.payload["text"])
        if self.conversation == ConversationId.REPORT and (
            self.report is None or self.report.markdown is None
        ):
            await self._reply(event, cfg.no_report_reply, [])
            return
        invocation_id = rt.ids.next("inv")
        now = rt.clock.now()
        trace = InvocationTrace(
            invocation_id=invocation_id,
            agent=self.agent_name.value,
            causation_ids=[event.event_id],
            as_of=now,
            wall_start=_wall_iso(),
            conversation_id=self.conversation.value,
        )
        started = time.monotonic()
        values: dict[str, Any] = {
            "t_label": format_t(now),
            "sim_time": f"{now:g}",
            # el estado actual va en el sistema de cada pregunta; los detalles, con las tools
            "open_alerts": rt.state.describe_open_alerts(),
            "open_detections": rt.state.describe_open_detections(),
        }
        if self.conversation == ConversationId.REPORT:
            values["report_markdown"] = self.report.markdown if self.report else ""
        tools_on = rt.assets.chat_tools_enabled
        if not tools_on:  # sin tools: el sistema lleva las alertas con su razonamiento y los hechos
            values["alerts_detail"] = rt.state.describe_alerts_detail(explanation=False)
            values["last_facts"] = rt.describe_last_facts()
        trace.aids = {"chat_tools_enabled": tools_on}
        system = rt.assets.system_prompt(cfg, notools=not tools_on, **values)
        messages: Messages = [
            {"role": "system", "content": system},
            *self.history,
            {"role": "user", "content": question},
        ]
        # el chat del monitor, como el monitor, no ve más allá de «ahora»
        capped = now if self.conversation == ConversationId.MONITOR else None
        toolbox = Toolbox(
            rt.assets,
            cfg.skills,
            rt.platform_url,
            as_of=capped,
            platform_call=rt.platform_call,
            on_skill=lambda name: trace.skills_loaded.append({"name": name, "by": "model"}),
        )
        schemas = rt.assets.tool_schemas(cfg.active_tools) if tools_on else []
        engine = AgentEngine(rt.llm, cfg, schemas, toolbox)

        async def chunk(delta: str) -> None:
            await rt.emit(
                EventType.AGENT_REPLY_CHUNK,
                {
                    "conversation_id": self.conversation.value,
                    "reply_to": event.event_id,
                    "delta": delta,
                },
                conversation=self.conversation,
            )

        await rt.activity(self.agent_name, ActivityState.STARTED, invocation_id, event.event_id)
        try:
            result = await engine.run(messages, trace, on_delta=chunk)
            text = result.streamed_text.strip() or result.text.strip()
            if not text:
                text = (
                    f"No he podido responder ({result.end_reason}). Prueba a repetir la pregunta."
                )
            tool_names = result.tool_names
        except Exception:
            log.exception("chat engine failed")
            text, tool_names, trace.end_reason = "No he podido responder por un error.", [], "error"
        reply = await self._reply(event, text, tool_names)
        trace.published.append(
            {"event_id": reply.event_id, "type": "AgentReply", "causation_id": event.event_id}
        )
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": text})
        trace.sim_time_end = rt.clock.now()
        trace.wall_end = _wall_iso()
        trace.duration_s = time.monotonic() - started
        rt.trace.write(trace)
        await rt.activity(self.agent_name, ActivityState.FINISHED, invocation_id, event.event_id)

    async def _reply(self, event: Envelope, text: str, tool_names: list[str]) -> Any:
        return await self.rt.emit(
            EventType.AGENT_REPLY,
            {
                "conversation_id": self.conversation.value,
                "reply_to": event.event_id,
                "text": text,
                "tool_calls": tool_names,
            },
            conversation=self.conversation,
        )


def _wall_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
