"""Informe de misión del alumno (papel `report`), al terminar el ejercicio.

**Los hechos los escribe el código** (cabecera, historia de cada incidente con sus horas,
severidad, confianza y la mayor distancia del radar a la ruta mientras estuvo abierto); el LLM solo
escribe frases sobre ellos (resumen, qué se vio en cada incidente y recomendaciones), que pasan por
las mismas comprobaciones que todo texto del asistente. Si no se puede escribir, el informe sale
con los hechos y esos apartados marcados como no disponibles. Sin incidentes no hay llamada al LLM.
"""

from dataclasses import dataclass, field
from typing import Any

from poc_contracts.enums import IncidentKind

from ..outbox import format_t
from .chat import SEVERITY_ORDER, path_text
from .checks import check_text
from .config import AssistantConfig
from .facts import PromptInput, distance_to_route, evidence_lines
from .llm import LlmError, LlmPort
from .store import Store

END_WORDS = {
    "returned_to_base": "the drone returned to base",
    "timeout": "the flight reached its time limit",
    "landed": "the drone landed after a failsafe",
}
NOT_AVAILABLE = "_Not available: the assistant could not write this part._"


@dataclass
class ReportOutcome:
    markdown: str
    alerts_count: int
    written: bool  # `False` = sin las frases del LLM (sin incidentes o no se pudo escribir)
    reasons: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    latency_s: float = 0.0
    input_text: str = ""


def max_radar_deviation(store: Store, since: float, until: float) -> float | None:
    """La mayor distancia del radar a la ruta planificada entre dos instantes."""
    values = [
        d
        for t, x, y in store.radar_track
        if since <= t <= until and (d := distance_to_route((x, y), store.route)) is not None
    ]
    return max(values) if values else None


def ordered_incidents(store: Store) -> list[list[dict[str, Any]]]:
    return sorted(store.revisions.values(), key=lambda revs: revs[0]["opened_at"])


def end_line(store: Store) -> str:
    end = store.mission_end
    if end is None:
        return "The exercise has finished."
    reason = END_WORDS.get(str(end.get("reason")), "the flight ended")
    return f"The flight ended at {format_t(end['t'])}: {reason}."


def incident_facts(store: Store, number: int, revisions: list[dict[str, Any]]) -> list[str]:
    """Los hechos de un incidente, escritos por el código (van al informe y al prompt)."""
    last = revisions[-1]
    peak = max((r["severity"] for r in revisions), key=SEVERITY_ORDER.index)
    lines = [
        f"- History: {path_text(revisions)}",
        f"- Severity: {last['severity']} (highest it reached: {peak}); "
        f"confidence {last['confidence']}",
    ]
    deviation = max_radar_deviation(store, revisions[0]["opened_at"], last["as_of_sim_time"])
    if deviation is not None:
        lines.append(
            f"- Largest radar distance from the planned route while it was open: {deviation:.0f} m"
        )
    return lines


def report_input(store: Store) -> PromptInput:
    parts = [end_line(store)]
    kinds: set[IncidentKind] = set()
    for number, revisions in enumerate(ordered_incidents(store), 1):
        last = revisions[-1]
        block = [f"Incident {number}: {last['name']}", *incident_facts(store, number, revisions)]
        why = evidence_lines(revisions[0], for_chat=True)
        if why:
            block.append("- Evidence when it opened:\n" + "\n".join("  " + w for w in why))
        if last["checks"]:
            block.append("- What to check: " + "; ".join(last["checks"]))
        parts.append("\n".join(block))
        kinds |= {IncidentKind(r["kind"]) for r in revisions}
    text = "\n\n".join(parts)
    return PromptInput(text=text, current=text, opening="", allowed_kinds=kinds)


def assemble(store: Store, summary: str | None, notes: dict[int, str], recs: list[str]) -> str:
    lines = [
        "# Mission report",
        "",
        end_line(store),
        "",
        "## Summary",
        "",
        summary or NOT_AVAILABLE,
    ]
    lines += ["", "## Incidents"]
    for number, revisions in enumerate(ordered_incidents(store), 1):
        last = revisions[-1]
        peak = max((r["severity"] for r in revisions), key=SEVERITY_ORDER.index)
        lines += ["", f"### {number} · {last['name']} ({peak} at most)", ""]
        lines += [f"- **History:** {path_text(revisions)}"]
        lines += [f"- **Confidence:** {last['confidence']}"]
        deviation = max_radar_deviation(store, revisions[0]["opened_at"], last["as_of_sim_time"])
        if deviation is not None:
            lines += [f"- **Largest radar distance from the planned route:** {deviation:.0f} m"]
        lines += ["", notes.get(number, NOT_AVAILABLE)]
    lines += ["", "## Recommendations", ""]
    lines += [f"- {r}" for r in recs] or [NOT_AVAILABLE]
    return "\n".join(lines) + "\n"


class Reporter:
    def __init__(self, config: AssistantConfig, llm: LlmPort) -> None:
        self.config = config
        self.llm = llm

    async def write(self, store: Store) -> ReportOutcome:
        incidents = ordered_incidents(store)
        if not incidents:
            text = "\n".join(
                ["# Mission report", "", end_line(store), "", "No incidents were opened."]
            )
            return ReportOutcome(text + "\n", 0, False)
        inp = report_input(store)
        out = ReportOutcome("", len(incidents), False, input_text=inp.text)
        cfg = self.config.role("report")
        user = inp.text
        for _attempt in range(2):
            try:
                result = await self.llm.complete(
                    cfg,
                    cfg.system_prompt(self.config.assets),
                    user,
                    cfg.tool_schemas(self.config.assets),
                )
            except LlmError as exc:
                out.reasons = [f"llm: {exc}"]
                break
            out.latency_s += result.latency_s
            args = result.tool_args or {}
            reasons, parts = self._judge(args, inp, len(incidents))
            out.attempts.append({"args": args, "reasons": reasons})
            if not reasons:
                out.written = True
                out.markdown = assemble(store, *parts)
                return out
            out.reasons = reasons
            user = (
                f"{inp.text}\n\nYour previous answer was rejected:\n"
                + "\n".join(f"- {r}" for r in reasons)
                + "\nWrite it again fixing all of that."
            )
        out.markdown = assemble(store, None, {}, [])
        return out

    def _judge(
        self, args: dict[str, Any], inp: PromptInput, count: int
    ) -> tuple[list[str], tuple[str, dict[int, str], list[str]]]:
        now_rule = self.config.now_rule
        reasons: list[str] = []

        def clean(piece: Any) -> str:
            verdict = check_text(str(piece), inp, "report_piece", now_rule=now_rule)
            reasons.extend(verdict.reasons)
            return verdict.text

        summary = clean(args.get("summary", ""))
        notes: dict[int, str] = {}
        for item in args.get("incidents") or []:
            try:
                number = int(item["number"])
            except (KeyError, TypeError, ValueError):
                reasons.append("format: each incident note needs its number")
                continue
            if not 1 <= number <= count:
                reasons.append(f"format: there is no incident {number}")
                continue
            notes[number] = clean(item.get("note", ""))
        recs = [clean(r) for r in (args.get("recommendations") or [])][:3]
        if not args:
            reasons.append("format: call the tool write_report")
        return list(dict.fromkeys(reasons)), (summary, notes, recs)
