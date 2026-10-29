"""Piezas compartidas por el monitor, el informe y los chats: el reloj del módulo, la
publicación de eventos (que también actualiza el estado y el índice locales) y la actividad.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from poc_contracts.enums import ActivityState, AgentName, ConversationId, EventType
from poc_contracts.envelope import EventDraft

from .agent.assets import Assets
from .agent.engine import ToolCallListener, ToolCallRecord
from .agent.guardrails import EventIndex
from .agent.llm import LlmClient
from .agent.tools import PlatformCall
from .agent.trace import TraceWriter
from .bus_client import call_platform_tool
from .chat_facts import describe_link, describe_metrics
from .ids import IdAllocator
from .monitor_state import MonitorState
from .outbox import EventFactory

log = logging.getLogger(__name__)

Publish = Callable[[EventDraft], Awaitable[None]]

TOOL_CALL_ARGUMENTS_CHARS = 1000
TOOL_CALL_RESULT_CHARS = 2000


def _cut(text: str, limit: int) -> tuple[str, bool]:
    """Recorta para la web; devuelve también si se recortó."""
    return (text, False) if len(text) <= limit else (text[:limit], True)


class Clock:
    """Reloj simulado del módulo: el mayor `sim_time` visto (eventos y mensajes `state`)."""

    def __init__(self) -> None:
        self._value = 0.0

    def observe(self, sim_time: float) -> None:
        self._value = max(self._value, sim_time)

    def now(self) -> float:
        return self._value

    def reset(self) -> None:
        self._value = 0.0


@dataclass
class Runtime:
    assets: Assets
    llm: LlmClient
    platform_url: str
    publish: Publish
    runs_dir: Path
    clock: Clock = field(default_factory=Clock)
    ids: IdAllocator = field(default_factory=IdAllocator)
    index: EventIndex = field(default_factory=EventIndex)
    trace: TraceWriter = field(default_factory=TraceWriter)
    platform_call: PlatformCall = call_platform_tool
    tool_call_events: bool = True
    """Publica `AgentToolCall` (solo para la web); se apaga con `--no-tool-call-events`."""
    scenario: str | None = None
    run_id: str | None = None
    last_metrics: dict[str, Any] | None = None
    """Último resultado de `get_track_metrics` del monitor (para los chats sin tools)."""
    last_metrics_note: str = ""
    last_link: list[dict[str, Any]] | None = None
    """Últimos eventos de enlace que miró el monitor (para los chats sin tools)."""
    last_link_note: str = ""

    def __post_init__(self) -> None:
        self.factory = EventFactory(self.ids)
        self.state = MonitorState(self.assets.agent("monitor").last_decisions_in_state)

    # --- Ejecución actual -----------------------------------------------------------------

    @property
    def run_dir(self) -> Path | None:
        if self.scenario is None or self.run_id is None:
            return None
        return self.runs_dir / self.scenario / self.run_id

    def set_run(self, scenario: str, run_id: str) -> bool:
        """Registra la ejecución en curso; devuelve `True` si es nueva (y apunta las trazas a su
        carpeta)."""
        if (scenario, run_id) == (self.scenario, self.run_id):
            return False
        self.scenario, self.run_id = scenario, run_id
        self.trace.path = self.runs_dir / scenario / run_id / "llm_trace.jsonl"
        self._write_profile_info()
        return True

    def _write_profile_info(self) -> None:
        """`profile.json` de la ejecución: perfil, huellas y parámetros efectivos de cada agente."""
        folder = self.run_dir
        if folder is None:
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)
            text = json.dumps(self.assets.profile_info(), ensure_ascii=False, indent=2)
            (folder / "profile.json").write_text(text + "\n", encoding="utf-8")
        except OSError:
            log.exception("could not write profile.json")

    def reset_run(self) -> None:
        """Nueva simulación o reinicio: todo el estado de la ejecución vuelve a cero."""
        self.ids.reset()
        self.state.reset()
        self.index.clear()
        self.clock.reset()
        self.scenario = self.run_id = None
        self.last_metrics = None
        self.last_link = None
        self.trace.path = None
        self.trace.records.clear()

    def describe_last_facts(self) -> str:
        """Los últimos hechos que consultó el monitor (trayectoria y enlace), cada uno con su
        interpretación (sí/no), para el sistema de un chat sin tools."""
        text = describe_metrics(self.last_metrics, self.last_metrics_note)
        link = describe_link(self.last_link, self.last_link_note)
        return f"{text}\n{link}" if link else text

    # --- Publicación ----------------------------------------------------------------------

    async def emit(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        causation_id: str | None = None,
        sim_time: float | None = None,
        conversation: ConversationId | None = None,
        event_id: str | None = None,
    ) -> EventDraft:
        """Construye, publica y aplica al estado local un evento del módulo. Un fallo de
        publicación (bus caído) se registra y no se propaga: el evento se da por perdido."""
        event = self.factory.make(
            event_type,
            payload,
            sim_time=self.clock.now() if sim_time is None else sim_time,
            causation_id=causation_id,
            conversation=conversation,
            event_id=event_id,
        )
        self.state.apply(event)
        self.index.add(event)
        try:
            await self.publish(event)
        except Exception as exc:
            log.error("cannot publish %s %s: %s", event.type.value, event.event_id, exc)
        return event

    def tool_call_listener(
        self, agent: AgentName, invocation_id: str, causation: str | None
    ) -> ToolCallListener | None:
        """Escucha de las llamadas a tool de una invocación, o `None` si está apagado."""
        if not self.tool_call_events:
            return None

        async def listener(record: ToolCallRecord) -> None:
            await self.tool_call(agent, invocation_id, causation, record)

        return listener

    async def tool_call(
        self,
        agent: AgentName,
        invocation_id: str,
        causation: str | None,
        record: ToolCallRecord,
    ) -> None:
        """Publica un `AgentToolCall` (recortado). **Solo se publica**: no pasa por `emit`, así
        que no entra en el estado ni en el índice de eventos del módulo (no puede ser evidencia),
        y `AiModule.handle_event` lo descarta al recibirlo de vuelta."""
        arguments, cut_args = _cut(record.arguments, TOOL_CALL_ARGUMENTS_CHARS)
        result, cut_result = (
            (None, False)
            if record.content is None
            else _cut(record.content, TOOL_CALL_RESULT_CHARS)
        )
        payload = {
            "agent": agent.value,
            "invocation_id": invocation_id,
            "index": record.index,
            "iteration": record.iteration,
            "tool": record.name,
            "arguments": arguments,
            "status": record.status,
            "result": result,
            "error": record.error,
            "truncated": cut_args or cut_result,
        }
        try:
            event = self.factory.make(
                EventType.AGENT_TOOL_CALL,
                payload,
                sim_time=self.clock.now(),
                causation_id=causation,
            )
            await self.publish(event)
        except Exception as exc:
            log.error("cannot publish AgentToolCall: %s", exc)

    async def activity(
        self, agent: AgentName, state: ActivityState, invocation_id: str, causation: str | None
    ) -> None:
        await self.emit(
            EventType.AGENT_ACTIVITY,
            {
                "agent": agent.value,
                "state": state.value,
                "invocation_id": invocation_id,
                "causation_id": causation,
            },
        )
