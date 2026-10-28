"""Agente monitor: un solo trabajador que atiende las detecciones del detector.

Cada `DetectionRaised`, `DetectionUpdated` y `DetectionCleared` recibe **siempre** respuesta: un
evento de `ai-monitor` cuyo `causation_id` es el `event_id` de la detección (con «esperar al
agente», el reproductor se reanuda con él). Las respuestas son `AnomalyDetected`,
`DetectionAcknowledged` o `AlertClosed` (`contracts/eventos.md` §4).

- Una invocación a la vez; las detecciones que llegan mientras trabaja se agrupan en la siguiente.
- Los `DetectionCleared` que no cambian nada se responden sin LLM (determinista).
- Memoria de la opción B: cada invocación empieza de cero con el estado de `MonitorState`.
- Garantía: al terminar la invocación, lo que siga sin respuesta se responde en código (fallback).
"""

import asyncio
import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from poc_contracts.enums import ActivityState, AgentName, EventType
from poc_contracts.envelope import Envelope

from .agent.assets import AgentConfig, render, sections
from .agent.engine import AbortInvocation, AgentEngine, EngineResult, compact_json
from .agent.guardrails import (
    InvocationFacts,
    Verdict,
    check_acknowledge,
    check_close_alert,
    check_publish_alert,
)
from .agent.llm import Messages
from .agent.tools import Toolbox, strip_computed_facts
from .agent.trace import InvocationTrace
from .outbox import format_t
from .runtime import Runtime

log = logging.getLogger(__name__)

Kind = Literal["raised", "updated", "cleared"]
KIND_OF_TYPE: dict[EventType, Kind] = {
    EventType.DETECTION_RAISED: "raised",
    EventType.DETECTION_UPDATED: "updated",
    EventType.DETECTION_CLEARED: "cleared",
}
ID_RE = re.compile(r"\b(?:gps|rad|met|lnk|bat|mis|det|ai|ops)-\d+\b")
MAX_FALLBACK_EVIDENCE = 6


@dataclass
class Pending:
    """Un evento de detección que espera respuesta."""

    event: Envelope
    kind: Kind
    detection_id: str
    answered: bool = False
    last_open_of: str | None = None
    """Para un `cleared` que ha ido al LLM: la alerta cuya última detección abierta era."""

    @property
    def event_id(self) -> str:
        return self.event.event_id


@dataclass
class Invocation:
    """Lo que lleva una invocación del monitor: sus eventos pendientes y lo que ya ha publicado."""

    invocation_id: str
    as_of: float
    pending: list[Pending]
    trace: InvocationTrace
    seen_ids: set[str] = field(default_factory=set)
    repeats: dict[str, int] = field(default_factory=dict)
    """Cuántas veces ha repetido el modelo cada llamada ya rechazada."""
    rejected: dict[str, list[str]] = field(default_factory=dict)
    """Llamadas ya rechazadas (herramienta + argumentos) y sus errores."""
    facts: InvocationFacts = field(default_factory=InvocationFacts)
    """Lo que han devuelto las tools de datos en esta invocación (para contrastar los `checks`)."""
    alerts: dict[str, list[str]] = field(default_factory=dict)
    """`alert_id` -> `detection_ids` de las alertas publicadas en esta invocación."""

    def unanswered(self) -> list[Pending]:
        return [p for p in self.pending if not p.answered]

    def take(self, detection_ids: list[str]) -> list[Pending]:
        """Los eventos sin respuesta de esas detecciones, en orden."""
        wanted = set(detection_ids)
        return [p for p in self.unanswered() if p.detection_id in wanted]

    @property
    def all_answered(self) -> bool:
        return not self.unanswered()


def _wall_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Monitor:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.config: AgentConfig = rt.assets.agent("monitor")
        self.queue: deque[Envelope] = deque()
        self._busy = False
        self._current: asyncio.Task[None] | None = None
        self._wakeup = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._skills_by_model = 0

    # --- Cola -----------------------------------------------------------------------------

    def submit(self, event: Envelope) -> None:
        """Encola un evento de detección recibido del bus."""
        if event.type not in KIND_OF_TYPE:
            return
        self.queue.append(event)
        self._idle.clear()
        self._wakeup.set()

    def reset(self) -> None:
        """Nueva simulación o reinicio: se descarta la cola y se cancela la invocación en curso
        (sus respuestas irían a una ejecución que ya no existe)."""
        self.queue.clear()
        if self._current is not None and not self._current.done():
            self._current.cancel()
        if not self._busy:
            self._idle.set()

    async def wait_idle(self) -> None:
        """Espera a que la cola esté vacía y no haya ninguna invocación en curso."""
        await self._idle.wait()

    async def run_forever(self) -> None:
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            while self.queue:
                batch = self._take_batch()
                self._busy = True
                self._current = asyncio.create_task(self.handle_batch(batch))
                await asyncio.wait({self._current})  # no propaga la cancelación de `reset`
                if not self._current.cancelled() and self._current.exception() is not None:
                    log.error("monitor invocation failed", exc_info=self._current.exception())
                self._busy = False
            self._idle.set()

    def _take_batch(self) -> list[Envelope]:
        """Todo lo que hay en la cola, salvo un `Cleared` que va detrás de un aviso de la misma
        detección que aún no se ha respondido (se atiende en la siguiente invocación, ya con la
        alerta publicada)."""
        batch: list[Envelope] = []
        awaiting: set[str] = set()
        while self.queue:
            event = self.queue[0]
            detection_id = event.payload["detection_id"]
            if event.type == EventType.DETECTION_CLEARED and detection_id in awaiting:
                break
            if event.type != EventType.DETECTION_CLEARED:
                awaiting.add(detection_id)
            batch.append(self.queue.popleft())
        return batch

    # --- Una invocación -------------------------------------------------------------------

    async def handle_batch(self, batch: list[Envelope]) -> None:
        rt = self.rt
        invocation_id = rt.ids.next("inv")
        as_of = max([rt.clock.now(), *(e.sim_time for e in batch)])
        trace = InvocationTrace(
            invocation_id=invocation_id,
            agent="monitor",
            causation_ids=[e.event_id for e in batch],
            as_of=as_of,
            queue_at_start=len(self.queue),
            wall_start=_wall_iso(),
            guided_mode=self.config.guided_mode,
            aids=self.config.aids(),
        )
        started = time.monotonic()
        pending = await self._triage(batch, as_of, trace)
        inv = Invocation(invocation_id, as_of, pending, trace)
        if not pending:
            trace.deterministic = True
            trace.end_reason = "deterministic"
        else:
            await self._invoke_llm(inv)
        trace.sim_time_end = rt.clock.now()
        trace.wall_end = _wall_iso()
        trace.duration_s = time.monotonic() - started
        rt.trace.write(trace)

    async def _triage(
        self, batch: list[Envelope], as_of: float, trace: InvocationTrace
    ) -> list[Pending]:
        """Aplica los eventos al estado, en orden, y responde sin LLM a los `Cleared` que no
        cambian nada. Devuelve lo que necesita al LLM."""
        state = self.rt.state
        for_llm: list[Pending] = []
        for event in batch:
            state.apply(event)
            kind = KIND_OF_TYPE[event.type]
            detection_id = event.payload["detection_id"]
            if kind != "cleared":
                for_llm.append(Pending(event, kind, detection_id))
                continue
            alert = state.alert_of(detection_id)
            if alert is None:
                reason = f"Detection {detection_id} was cleared and had no associated alert."
            elif alert.status.value != "open":
                reason = (
                    f"Detection {detection_id} was cleared; its alert {alert.alert_id} "
                    "was already closed."
                )
            elif remaining := state.open_detections_of(alert.alert_id):
                ids = ", ".join(d.detection_id for d in remaining)
                reason = (
                    f"Detection {detection_id} was cleared; alert {alert.alert_id} "
                    f"stays open because it still has open detections ({ids})."
                )
            else:
                for_llm.append(Pending(event, kind, detection_id, last_open_of=alert.alert_id))
                continue
            await self._acknowledge(
                trace, event.event_id, detection_id,
                alert.alert_id if alert and alert.status.value == "open" else None, reason,
                as_of, fallback=False,
            )  # fmt: skip
        return for_llm

    async def _invoke_llm(self, inv: Invocation) -> None:
        rt, cfg = self.rt, self.config
        trace = inv.trace
        objective = self._objective(inv)
        inv.seen_ids |= set(ID_RE.findall(objective))
        system = rt.assets.system_prompt(cfg)
        messages: Messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": objective},
        ]
        if cfg.guided_mode:
            self._preload_skill(inv, messages)

        toolbox = Toolbox(
            rt.assets,
            cfg.skills,
            rt.platform_url,
            as_of=inv.as_of,
            local={
                "publish_alert": self._resolving(inv, "publish_alert", self._publish_alert),
                "acknowledge_detection": self._resolving(
                    inv, "acknowledge_detection", self._ack_tool
                ),
                "close_alert": self._resolving(inv, "close_alert", self._close_tool),
            },
            platform_call=rt.platform_call,
            on_skill=lambda name: trace.skills_loaded.append({"name": name, "by": "model"}),
        )

        async def execute(name: str, args: dict[str, Any]) -> Any:
            result = await toolbox(name, args)
            self._record_facts(inv, name, args, result)
            if name == "get_track_metrics" and isinstance(result, dict):
                rt.last_metrics = result
                rt.last_metrics_note = (
                    f"monitor query at {format_t(inv.as_of)} (window {result['since']:g}"
                    f"–{result['until']:g} s)"
                )
            if name == "get_events" and args.get("source") == "link" and isinstance(result, dict):
                rt.last_link = list(result.get("events", []))
                rt.last_link_note = f"looked at by the monitor at {format_t(inv.as_of)}"
            if name == "get_track_metrics" and not cfg.computed_facts:
                result = strip_computed_facts(result)  # el módulo los conserva para los checks
            inv.seen_ids |= set(ID_RE.findall(compact_json(result)))
            return result

        schemas = rt.assets.tool_schemas(cfg.active_tools)
        if not cfg.require_checks:
            schemas = rt.assets.with_optional_checks(schemas)
        engine = AgentEngine(rt.llm, cfg, schemas, execute)
        first = inv.pending[0].event_id
        await rt.activity(AgentName.MONITOR, ActivityState.STARTED, inv.invocation_id, first)
        result: EngineResult | None = None
        try:
            result = await engine.run(
                messages,
                trace,
                is_done=lambda: inv.all_answered,
                reminder=lambda: self._reminder(inv),
            )
        except Exception as exc:  # el motor ya recoge los errores del LLM; esto es un seguro
            log.exception("engine failed")
            trace.end_reason = "error"
            trace.messages = messages
            trace.guardrail_rejections.append({"tool": "engine", "errors": [str(exc)]})
        try:
            await self._guarantee(inv, result)
        finally:
            await rt.activity(AgentName.MONITOR, ActivityState.FINISHED, inv.invocation_id, first)

    # --- Prompts --------------------------------------------------------------------------

    def _objective(self, inv: Invocation) -> str:
        rt, cfg = self.rt, self.config
        common, secs = sections(rt.assets.prompt(cfg.objective_prompt or ""))
        parts = [
            render(
                common,
                t_label=format_t(inv.as_of),
                sim_time=f"{inv.as_of:g}",
                open_alerts=rt.state.describe_open_alerts(),
                open_detections=rt.state.describe_open_detections(),
                last_decisions=rt.state.describe_decisions(),
                gps_alert_recent=rt.state.describe_gps_alert(inv.as_of),
            )
        ]
        ids = list(dict.fromkeys(p.detection_id for p in inv.pending))
        if len(inv.pending) > 1:
            parts.append(
                render(secs["batch"], count=len(inv.pending), detection_ids=", ".join(ids))
            )
        for p in inv.pending:
            # al modelo solo se le enseña el `detection_id`, nunca el `event_id` del aviso: la
            # correspondencia con los eventos la hace el módulo (`Invocation.take`)
            payload = {"t": format_t(p.event.sim_time), **p.event.payload}
            record = rt.state.detections.get(p.detection_id)
            parts.append(
                render(
                    secs[p.kind],
                    detection_id=p.detection_id,
                    detection_json=compact_json(payload),
                    related_alerts=rt.state.describe_related_alerts(p.detection_id),
                    last_open_alert=p.last_open_of or "",
                    detection_since=f"{record.since:g}" if record else f"{p.event.sim_time:g}",
                    sim_time=f"{inv.as_of:g}",
                )
            )
        return "\n\n".join(parts)

    def _reminder(self, inv: Invocation) -> str:
        _, secs = sections(self.rt.assets.prompt(self.config.objective_prompt or ""))
        ids = ", ".join(dict.fromkeys(p.detection_id for p in inv.unanswered()))
        return render(secs["reminder"], pending=ids)

    def _preload_skill(self, inv: Invocation, messages: Messages) -> None:
        """Modo guiado: la skill de la regla de la primera detección se precarga como si el
        modelo hubiera llamado a `load_skill`."""
        first = next((p for p in inv.pending if p.kind != "cleared"), inv.pending[0])
        rule = first.event.payload.get("rule")
        name = self.config.guided_skill_by_rule.get(rule or "")
        if name is None:
            return
        call_id = f"guided-{inv.invocation_id}"
        arguments = json.dumps({"name": name})
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": "load_skill", "arguments": arguments},
                    }
                ],
            }
        )
        content = self.rt.assets.skills[name].content
        messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
        inv.trace.skills_loaded.append({"name": name, "by": "guided"})

    # --- Tools que publican ---------------------------------------------------------------

    @staticmethod
    def _record_facts(inv: Invocation, name: str, args: dict[str, Any], result: Any) -> None:
        """Guarda lo que devuelven `get_track_metrics` y `get_events` de enlace: con ello el
        guardrail contrasta los `checks` del modelo."""
        if name == "get_track_metrics" and isinstance(result, dict):
            inv.facts.metrics = result
        elif name == "get_events" and args.get("source") == "link" and isinstance(result, dict):
            inv.facts.link_events = list(result.get("events", []))

    def _resolving(self, inv: Invocation, tool: str, handler: Any) -> Any:
        """Envuelve una tool que responde: antes de validarla, el módulo rellena los ids que no
        hace falta elegir y rechaza, indicando el correcto, los que se equivocan."""

        async def run_tool(raw: dict[str, Any]) -> dict[str, Any]:
            filled, errors = self._resolve_ids(inv, tool, raw)
            if errors:
                return self._reject(inv, tool, raw, Verdict(errors=errors))
            return await handler(inv, filled)

        return run_tool

    @staticmethod
    def _resolve_ids(
        inv: Invocation, tool: str, raw: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """- `detection_ids` (publish_alert, acknowledge_detection): con una sola detección en el
        lote, el módulo la pone si falta y rechaza otra indicando la correcta.
        - `alert_id` (close_alert, acknowledge_detection): en un aviso de cierre (el
        `DetectionCleared` de la última detección abierta de una alerta) lo pone el módulo si falta
        y rechaza otro indicando el correcto."""
        raw = dict(raw)
        batch = list(dict.fromkeys(p.detection_id for p in inv.pending))
        if tool in ("publish_alert", "acknowledge_detection") and len(batch) == 1:
            given = raw.get("detection_ids")
            if not given:
                raw["detection_ids"] = batch
            elif list(given) != batch:
                return raw, [
                    f"This invocation handles {batch[0]}, not {', '.join(map(str, given))}: use "
                    f"{batch[0]} (or leave out detection_ids)"
                ]
        closure = {p.last_open_of for p in inv.pending if p.kind == "cleared" and p.last_open_of}
        only_closures = all(p.kind == "cleared" and p.last_open_of for p in inv.pending)
        if tool in ("close_alert", "acknowledge_detection") and only_closures and len(closure) == 1:
            expected = next(iter(closure))
            given_alert = raw.get("alert_id")
            if not given_alert:
                raw["alert_id"] = expected
            elif given_alert != expected:
                return raw, [
                    f"In this closing warning the alert is {expected}, not {given_alert}: use "
                    f"{expected} (or leave out alert_id)"
                ]
        return raw, []

    def _reject(
        self, inv: Invocation, tool: str, raw: dict[str, Any], verdict: Verdict
    ) -> dict[str, Any]:
        """Devuelve el rechazo al modelo. Si repite una llamada idéntica a otra ya rechazada, el
        rechazo lo dice (el 14B repetía la misma llamada hasta agotar las iteraciones)."""
        key = tool + json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
        errors = verdict.errors
        if key in inv.rejected:
            inv.repeats[key] = inv.repeats.get(key, 0) + 1
            if inv.repeats[key] >= 2:
                # segunda repetición: no se gastan más iteraciones, fallback
                inv.trace.guardrail_rejections.append(
                    {"tool": tool, "errors": ["repeats a rejected call for the second time"]}
                )
                raise AbortInvocation(f"{tool}: rejected call repeated for the second time")
            errors = [
                "This is the same call as before; change what I told you.",
                *inv.rejected[key],
            ]
        else:
            inv.rejected[key] = verdict.errors
        inv.trace.guardrail_rejections.append({"tool": tool, "errors": errors})
        return {"ok": False, "errors": errors}

    async def _publish_alert(self, inv: Invocation, raw: dict[str, Any]) -> dict[str, Any]:
        rt = self.rt
        verdict = check_publish_alert(
            raw,
            as_of=inv.as_of,
            state=rt.state,
            index=rt.index,
            seen_ids=inv.seen_ids,
            facts=inv.facts,
            coherence=self.config.coherence_guardrail,
            require_checks=self.config.require_checks,
            pending={p.detection_id for p in inv.pending},
            unanswered={p.detection_id for p in inv.unanswered()},
            source_silent_own_alert=self.config.source_silent_own_alert,
        )
        if not verdict.ok:
            return self._reject(inv, "publish_alert", raw, verdict)
        args = verdict.args
        inv.trace.unseen_evidence += len(verdict.unseen_evidence)
        covered = inv.take(args.detection_ids)
        alert_id = await self._emit_alert(
            inv, args.model_dump(mode="json"), covered[0].event_id if covered else None
        )
        inv.alerts[alert_id] = list(args.detection_ids)
        for index, pending in enumerate(covered):
            pending.answered = True
            if index > 0:  # el resto de avisos de esas detecciones: respuesta enlazada a la alerta
                await self._acknowledge(
                    inv.trace, pending.event_id, pending.detection_id, alert_id,
                    f"Included in alert {alert_id}.", inv.as_of, fallback=False,
                )  # fmt: skip
        return {"ok": True, "alert_id": alert_id}

    async def _emit_alert(
        self, inv: Invocation, fields: dict[str, Any], causation_id: str | None,
        *, fallback: bool = False,
    ) -> str:  # fmt: skip
        rt = self.rt
        alert_id = rt.ids.next("ai")
        payload = {**fields, "alert_id": alert_id, "as_of_sim_time": inv.as_of,
                   "fallback": fallback, "supersedes": fields.get("supersedes")}  # fmt: skip
        event = await rt.emit(
            EventType.ANOMALY_DETECTED,
            payload,
            causation_id=causation_id,
            sim_time=max(rt.clock.now(), inv.as_of),
            event_id=alert_id,
        )
        inv.trace.published.append(_published(event))
        return alert_id

    async def _ack_tool(self, inv: Invocation, raw: dict[str, Any]) -> dict[str, Any]:
        unanswered = {p.detection_id for p in inv.unanswered()}
        pending = {p.detection_id for p in inv.pending}
        verdict = check_acknowledge(
            raw,
            state=self.rt.state,
            unanswered=unanswered,
            pending=pending,
            source_silent_own_alert=self.config.source_silent_own_alert,
        )
        if not verdict.ok:
            return self._reject(inv, "acknowledge_detection", raw, verdict)
        args = verdict.args
        for p in inv.take(args.detection_ids):
            await self._acknowledge(
                inv.trace, p.event_id, p.detection_id, args.alert_id, args.reason, inv.as_of,
                fallback=False,
            )  # fmt: skip
            p.answered = True
        return {"ok": True, "acknowledged": list(args.detection_ids)}

    async def _close_tool(self, inv: Invocation, raw: dict[str, Any]) -> dict[str, Any]:
        state = self.rt.state
        verdict = check_close_alert(raw, state=state)
        if not verdict.ok:
            return self._reject(inv, "close_alert", raw, verdict)
        args = verdict.args
        covered = [
            p for p in inv.unanswered()
            if (alert := state.alert_of(p.detection_id)) and alert.alert_id == args.alert_id
        ]  # fmt: skip
        await self._close(inv, args.alert_id, args.reason, covered[0] if covered else None)
        for p in covered:
            p.answered = True
        for p in covered[1:]:
            await self._acknowledge(
                inv.trace, p.event_id, p.detection_id, args.alert_id,
                f"Alert {args.alert_id} was closed.", inv.as_of, fallback=False,
            )  # fmt: skip
        return {"ok": True, "alert_id": args.alert_id}

    async def _close(
        self, inv: Invocation, alert_id: str, reason: str, answering: Pending | None
    ) -> None:
        rt = self.rt
        event = await rt.emit(
            EventType.ALERT_CLOSED,
            {"alert_id": alert_id, "reason": reason, "as_of_sim_time": inv.as_of},
            causation_id=answering.event_id if answering else None,
            sim_time=max(rt.clock.now(), inv.as_of),
        )
        inv.trace.published.append(_published(event))

    async def _acknowledge(
        self, trace: InvocationTrace, causation_id: str, detection_id: str, alert_id: str | None,
        reason: str, as_of: float, *, fallback: bool,
    ) -> None:  # fmt: skip
        rt = self.rt
        event = await rt.emit(
            EventType.DETECTION_ACKNOWLEDGED,
            {
                "detection_id": detection_id,
                "alert_id": alert_id,
                "reason": reason,
                "as_of_sim_time": as_of,
                "fallback": fallback,
            },
            causation_id=causation_id,
            sim_time=max(rt.clock.now(), as_of),
        )
        trace.published.append(_published(event))

    # --- Garantía de respuesta ------------------------------------------------------------

    async def _guarantee(self, inv: Invocation, result: EngineResult | None) -> None:
        """Responde en código a lo que el agente no haya respondido (tabla de fallbacks de
        `contracts/eventos.md` §4)."""
        left = inv.unanswered()
        if not left:
            return
        state, trace = self.rt.state, inv.trace
        trace.fallback = True
        no_open_alert = not state.open_alerts()  # foto previa a los fallbacks
        why = f"the agent did not conclude ({trace.end_reason})"
        for p in left:
            if p.kind == "raised" and no_open_alert:
                evidence = list(p.event.payload.get("trigger_event_ids", []))[
                    -MAX_FALLBACK_EVIDENCE:
                ]
                rule = p.event.payload.get("rule", "")
                alert_id = await self._emit_alert(
                    inv,
                    {
                        "detection_ids": [p.detection_id],
                        "cause": "UNKNOWN",
                        "severity": p.event.payload.get("severity", "medium"),
                        "confidence": 0.1,
                        "summary": f"No automatic diagnosis for {rule} ({p.detection_id}): "
                        "needs operator review",
                        "explanation": f"The detector warned of {p.event.payload.get('message')}. "
                        f"There is no diagnosis: {why}.",
                        "recommendation": "Review by the operator.",
                        "evidence_event_ids": evidence or [p.event_id],
                        "supersedes": None,
                    },
                    p.event_id,
                    fallback=True,
                )
                inv.alerts[alert_id] = [p.detection_id]
            elif p.kind == "cleared" and p.last_open_of is not None:
                alert = state.alerts.get(p.last_open_of)
                if alert is not None and alert.status.value == "open":
                    trace.fallback_close = True
                    await self._close(
                        inv, alert.alert_id, "all its detections have been cleared", p
                    )
                else:
                    await self._acknowledge(
                        trace, p.event_id, p.detection_id, None, why, inv.as_of, fallback=True
                    )
            else:
                await self._acknowledge(
                    trace, p.event_id, p.detection_id, None, why, inv.as_of, fallback=True
                )
            p.answered = True


def _published(event: Any) -> dict[str, str]:
    return {
        "event_id": event.event_id,
        "type": event.type.value,
        "causation_id": event.causation_id or "",
    }
