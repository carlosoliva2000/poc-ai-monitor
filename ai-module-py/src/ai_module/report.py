"""Agente de informe: al terminar la simulación (y cuando el monitor ha vaciado su cola) escribe
el informe final, lo publica como `ReportGenerated` y lo guarda en
`runs/<escenario>/<run_id>/informe.md`.

Los hechos (cronología, T+ de detección, alerta y cierre, severidad, estado y evidencias de cada
anomalía) los escribe el módulo a partir del estado del monitor (`report_facts.py`). El LLM, sin
tools y en una sola llamada, solo redacta el resumen, «qué se vio» de cada anomalía, la valoración
del monitor y las recomendaciones; el módulo lo monta todo. Si el agente no concluye, el informe
sale con los hechos y esos apartados marcados como no disponibles.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from poc_contracts.enums import ActivityState, AgentName, EventType

from .agent.assets import render
from .agent.engine import AgentEngine, ToolError, compact_json
from .agent.llm import Messages
from .agent.trace import InvocationTrace
from .monitor import Monitor
from .outbox import format_t
from .report_facts import (
    Narrative,
    anomalies_for_llm,
    assemble,
    assessment_facts,
    build_facts,
    figures_line,
    monitor_stats,
    parse_narrative,
)
from .runtime import Runtime

log = logging.getLogger(__name__)


class ReportAgent:
    def __init__(self, rt: Runtime, monitor: Monitor) -> None:
        self.rt = rt
        self.monitor = monitor
        self.config = rt.assets.agent("report")
        self.markdown: str | None = None

    def reset(self) -> None:
        self.markdown = None

    async def generate(self, scenario: str, run_id: str, finished_id: str | None) -> str:
        """Espera a que el monitor termine y escribe el informe. Devuelve el Markdown."""
        rt, cfg = self.rt, self.config
        await self.monitor.wait_idle()
        invocation_id = rt.ids.next("inv")
        now = rt.clock.now()
        trace = InvocationTrace(
            invocation_id=invocation_id,
            agent="report",
            causation_ids=[finished_id] if finished_id else [],
            as_of=now,
            wall_start=_wall_iso(),
        )
        started = time.monotonic()
        await rt.activity(AgentName.REPORT, ActivityState.STARTED, invocation_id, finished_id)
        markdown = ""
        summary: dict[str, Any] | None = None
        facts = build_facts(rt.state)
        aids = rt.assets.agent("monitor").aids()
        narrative = Narrative()
        try:
            summary = await rt.platform_call(rt.platform_url, "get_flight_summary", {})
            if not summary or "mission_id" not in summary:
                summary = None
        except Exception as exc:
            log.error("cannot get the flight summary: %s", exc)
        try:
            # sin tools: el módulo entrega los datos en el prompt y hace una sola llamada
            labels = [a.label for a in facts.anomalies]
            objective = render(
                rt.assets.prompt(cfg.objective_prompt or ""),
                scenario=scenario,
                run_id=run_id,
                t_label=format_t(now),
                sim_time=f"{now:g}",
                flight_summary=compact_json(summary) if summary else "not available",
                labels=", ".join(labels) or "none",
                anomalies=anomalies_for_llm(facts),
                assessment_facts=assessment_facts(facts, rt.trace.records, aids),
            )
            system = rt.assets.system_prompt(
                cfg, report_format=rt.assets.skill_body("report-format")
            )
            messages: Messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": objective},
            ]
            engine = AgentEngine(rt.llm, cfg, [], _no_tools)
            result = await engine.run(messages, trace)
            if result.end_reason == "final":
                narrative = parse_narrative(result.text, labels)
        except Exception:
            log.exception("report agent failed")
            trace.end_reason = "error"
        note = ""
        if narrative.empty:
            trace.fallback = True
            note = (
                "Report with the module's facts and without narrative: the agent did not conclude "
                f"({trace.end_reason})."
            )
        figures = figures_line(monitor_stats(rt.trace.records, aids), facts)
        markdown = assemble(scenario, summary, rt.state, facts, narrative, note, figures)
        trace.sim_time_end = rt.clock.now()
        trace.wall_end = _wall_iso()
        trace.duration_s = time.monotonic() - started
        self.markdown = markdown
        run_dir = rt.run_dir
        if run_dir is not None:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "informe.md").write_text(markdown + "\n", encoding="utf-8")
        event = await rt.emit(
            EventType.REPORT_GENERATED,
            {"run_id": run_id, "markdown": markdown, "alerts_count": rt.state.chains_published},
            causation_id=finished_id,
        )
        trace.published.append(
            {
                "event_id": event.event_id,
                "type": "ReportGenerated",
                "causation_id": finished_id or "",
            }
        )
        rt.trace.write(trace)
        await rt.activity(AgentName.REPORT, ActivityState.FINISHED, invocation_id, finished_id)
        return markdown


async def _no_tools(name: str, args: dict[str, Any]) -> Any:
    raise ToolError("this agent has no tools")


def _wall_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
