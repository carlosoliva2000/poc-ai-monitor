"""E6 (`monitor.engine: hybrid`): la interpretación del LLM de cada alerta que decide la tabla.

La tabla de decisión publica la alerta (causa, severidad, confianza, fase y ciclo de vida) y el
monitor pasa por `Monitor.enrich_hook` la fila, sus entradas y los hechos. Aquí, en una cola FIFO
con **un solo trabajador** y sin esperar a nada (el reproductor no espera el enriquecimiento):

1. si la alerta ya está sustituida o cerrada al empezar, no se llama al LLM (`skipped`);
2. el módulo escribe en frases lo que vio la tabla (sin nombres de campos) y el LLM, sin tools y
   en una sola llamada, devuelve un JSON con una frase y, solo si la causa es `UNKNOWN`, una
   hipótesis opcional (causa de la lista, confianza ≤ 0,4 y evidencias consultadas);
3. el texto pasa por `text_checks.enrichment_problems` y la hipótesis por el contrato; si algo no
   pasa, no se publica y queda en la traza (`rejected`);
4. se publica `AlertEnriched` (fuente `ai-enricher`, `causation_id` = la alerta) con el estado de
   la alerta en ese momento.

La traza (`agent: enrich`) guarda en `enrich` lo que pasó y las latencias de reloj y simuladas
desde que se publicó la alerta. Los chats no reciben la interpretación; el informe sí, comprobada.
"""

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from poc_contracts.enums import AlertStatus, Cause, DecidedBy, EventType
from poc_contracts.payloads import EnrichHypothesis

from .agent.assets import render, sections
from .agent.engine import AgentEngine
from .agent.llm import Messages
from .agent.trace import InvocationTrace
from .outbox import format_t
from .report_facts import cause_name, severity_name
from .runtime import Runtime
from .text_checks import enrichment_problems

log = logging.getLogger(__name__)

REPORT_WAIT_S = 30.0
"""Lo que espera el informe a que se vacíe la cola del enriquecimiento (lo que no llegue, no
entra)."""
MAX_SEEN_IDS = 40
JSON_RE = re.compile(r"\{.*\}", re.S)
TRENDS = {
    "moving_away": "moving away from the route",
    "approaching": "getting back to the route",
    "steady": "keeping its distance to the route",
}


class Enricher:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.config = rt.assets.agent("enrich")
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.texts: dict[str, str] = {}
        """Por alerta, la interpretación publicada (la usa el informe)."""
        self._busy = False
        self._idle = asyncio.Event()
        self._idle.set()
        self._current: asyncio.Task[None] | None = None

    # --- Cola -----------------------------------------------------------------------------

    def submit(self, item: dict[str, Any]) -> None:
        """El gancho del monitor: encola una alerta recién publicada por la tabla."""
        self.queue.put_nowait({**item, "_wall": time.monotonic(), "_sim": self.rt.clock.now()})
        self._idle.clear()

    def reset(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
        if self._current is not None and not self._current.done():
            self._current.cancel()
        self.texts.clear()
        if not self._busy:
            self._idle.set()

    async def wait_idle(self, timeout_s: float = REPORT_WAIT_S) -> bool:
        """Espera a que la cola esté vacía, como mucho `timeout_s`. `False` si no dio tiempo."""
        try:
            await asyncio.wait_for(self._idle.wait(), timeout_s)
        except TimeoutError:
            return False
        return True

    async def run_forever(self) -> None:
        while True:
            item = await self.queue.get()
            self._busy = True
            self._current = asyncio.create_task(self.enrich(item))
            await asyncio.wait({self._current})
            if not self._current.cancelled() and self._current.exception() is not None:
                log.error("enrichment failed", exc_info=self._current.exception())
            self._busy = False
            if self.queue.empty():
                self._idle.set()

    # --- Una alerta -----------------------------------------------------------------------

    async def enrich(self, item: dict[str, Any]) -> None:
        rt, cfg = self.rt, self.config
        alert_id = item["alert_id"]
        args = item["args"]
        trace = InvocationTrace(
            invocation_id=rt.ids.next("inv"),
            agent="enrich",
            causation_ids=[alert_id],
            as_of=item["as_of"],
            wall_start=_wall_iso(),
        )
        record: dict[str, Any] = {
            "alert_id": alert_id,
            "rule_id": item["rows"].get("cause"),
            "cause": args["cause"],
            "queue_wait_s": round(time.monotonic() - item["_wall"], 3),
        }
        started = time.monotonic()
        try:
            alert = rt.state.alerts.get(alert_id)
            status = _status(alert)
            if status != AlertStatus.OPEN:
                record["skipped"] = status.value if status else "unknown alert"
                trace.end_reason = "skipped"
                return
            prompt, messages = self.messages(item)
            result = await AgentEngine(rt.llm, cfg, [], _no_tools).run(messages, trace)
            if result.end_reason != "final":
                record["rejected"] = [f"no answer ({result.end_reason})"]
                return
            text, hypothesis, problems = check_answer(
                result.text, item, prompt, set(item.get("seen_ids") or [])
            )
            record["text"] = text
            record["hypothesis"] = hypothesis
            if problems:
                record["rejected"] = problems
                trace.end_reason = "rejected"
                return
            status = _status(rt.state.alerts.get(alert_id)) or AlertStatus.OPEN
            payload = {
                "alert_id": alert_id,
                "text": text,
                "hypothesis": hypothesis,
                "decided_by": DecidedBy.LLM.value,
                "as_of_sim_time": item["as_of"],
                "alert_status": status.value,
            }
            event = await rt.emit(EventType.ALERT_ENRICHED, payload, causation_id=alert_id)
            self.texts[alert_id] = text
            trace.published.append(
                {"event_id": event.event_id, "type": "AlertEnriched", "causation_id": alert_id}
            )
            record["published"] = event.event_id
            record["alert_status"] = status.value
            record["enrich_latency_wall_s"] = round(time.monotonic() - item["_wall"], 3)
            record["enrich_latency_sim_s"] = round(rt.clock.now() - item["as_of"], 1)
            trace.end_reason = "done"
        except asyncio.CancelledError:
            record["skipped"] = "reset"
            trace.end_reason = "cancelled"
            raise
        except Exception as exc:
            log.exception("enrichment of %s failed", alert_id)
            record["rejected"] = [f"error: {exc}"]
            trace.end_reason = "error"
        finally:
            record["llm_s"] = round(time.monotonic() - started, 3)
            trace.enrich = record
            trace.sim_time_end = rt.clock.now()
            trace.wall_end = _wall_iso()
            trace.duration_s = time.monotonic() - started
            rt.trace.write(trace)

    def messages(self, item: dict[str, Any]) -> tuple[str, Messages]:
        """El prompt de usuario (con los hechos en frases) y los mensajes de la llamada."""
        assets = self.rt.assets
        template = assets.prompt(self.config.objective_prompt or "")
        common, parts = sections(template)
        unknown = item["args"]["cause"] == Cause.UNKNOWN.value
        seen = sorted(item.get("seen_ids") or [])[-MAX_SEEN_IDS:]
        hypothesis = render(
            parts["hypothesis" if unknown else "no_hypothesis"],
            **({"seen_ids": ", ".join(seen) or "none"} if unknown else {}),
        )
        prompt = render(
            common,
            alert=alert_text(item),
            facts=facts_text(item),
            hypothesis_section=hypothesis,
        )
        system = assets.prompt(self.config.system_prompt)
        return prompt, [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]


# --- Lo que recibe el LLM ---------------------------------------------------------------------


def alert_text(item: dict[str, Any]) -> str:
    a = item["args"]
    phase = " (recovering: the problem has ended and the situation is going back to normal)"
    return "\n".join(
        [
            f"- Cause: {cause_name(a['cause'])}; severity: {severity_name(a['severity'])}; "
            f"confidence {a['confidence']:g}" + (phase if a.get("phase") == "recovering" else ""),
            f"- Time of the alert: {format_t(item['as_of'])}",
            f"- Summary: {a.get('summary', '')}",
            f"- Explanation: {a.get('explanation', '')}",
            f"- Recommendation: {a.get('recommendation', '')}",
        ]
    )


def facts_text(item: dict[str, Any]) -> str:
    """Los hechos de la tabla en frases cortas, con las cifras tal como las dieron las tools."""
    d = item["detection"]
    m = item.get("metrics") or {}
    inputs = item.get("inputs") or {}
    lines = [f"- Warning from the detector: {d.get('message', '')}"]
    now = m.get("now") or {}
    if now:
        parts = []
        gps_dev, radar_dev = (
            now.get("gps_deviation_from_plan_m"),
            now.get("radar_deviation_from_plan_m"),
        )
        if gps_dev is not None or radar_dev is not None:
            parts.append(
                "distance from the planned route: "
                + ", ".join(
                    f"{name} {value} m"
                    for name, value in (("GPS", gps_dev), ("radar", radar_dev))
                    if value is not None
                )
            )
        if now.get("gps_radar_agree") is not None:
            agree = "agree" if now["gps_radar_agree"] else "disagree"
            parts.append(f"GPS and radar {agree} ({now.get('gps_radar_distance_m')} m apart)")
        if now.get("route_trend") in TRENDS:
            parts.append(f"the drone is {TRENDS[now['route_trend']]}")
        if now.get("gps_fix") and now["gps_fix"] != "3d":
            parts.append(f"the GPS has no 3D fix ({now['gps_fix']})")
        if parts:
            lines.append(f"- At {format_t(item['as_of'])}: " + "; ".join(parts) + ".")
    gps_dev = m.get("gps_deviation_from_plan_m") or {}
    radar_dev = m.get("radar_deviation_from_plan_m") or {}
    dist = m.get("gps_radar_distance_m") or {}
    if gps_dev or radar_dev:
        window = []
        if gps_dev:
            window.append(f"GPS {gps_dev.get('mean')} m from the route on average (up to "
                          f"{gps_dev.get('max')} m)")  # fmt: skip
        if radar_dev:
            window.append(f"radar {radar_dev.get('mean')} m (up to {radar_dev.get('max')} m)")
        if dist:
            disagreed = (m.get("gps_radar") or {}).get("disagreed")
            verb = "disagreed" if disagreed else "did not disagree"
            window.append(f"GPS and radar {verb} (up to {dist.get('max')} m apart)")
        since, until = m.get("since"), m.get("until")
        span = f" from {format_t(since)} to {format_t(until)}" if since is not None else ""
        lines.append(f"- Over the window{span}: " + "; ".join(window) + ".")
    step = m.get("gps_max_step_m")
    if step is not None and inputs.get("gps_step_m") is not None and step >= 30:
        lines.append(f"- The GPS position jumped {step} m.")
    wind = m.get("wind") or {}
    if wind.get("samples"):
        notable = "strong enough to push the drone" if wind.get("notable") else "light"
        drift = (
            "it pushes the drone the way it is drifting"
            if wind.get("with_drift")
            else "it does not push the drone the way it is drifting"
        )
        lines.append(
            f"- Weather station: wind from {wind.get('from_deg')}° at {wind.get('mean_speed_mps')} "
            f"m/s, gusts up to {wind.get('max_gust_mps')} m/s; {notable}; {drift}."
        )
    elif m:
        lines.append("- Weather station: no data in the window.")
    gps = (item.get("gps") or [])[-1:] or None
    if gps:
        g = gps[0]
        lines.append(
            f"- Last GPS reading ({g.get('event_id')}): fix {g.get('fix')}, {g.get('sats')} "
            f"satellites, hdop {g.get('hdop')}."
        )
    link = (item.get("link") or [])[-1:] or None
    if link:
        k = link[0]
        other = " (not the mission's controller)" if inputs.get("link_controller_changed") else ""
        lines.append(
            f"- Command link ({k.get('event_id')}): controller {k.get('controller_id')}{other}, "
            f"latency {k.get('latency_ms')} ms, signal {k.get('rssi_dbm')} dBm."
        )
    if inputs.get("radar_silent"):
        lines.append("- Radar: no recent data.")
    return "\n".join(lines)


# --- Lo que devuelve el LLM -------------------------------------------------------------------


def check_answer(
    raw: str, item: dict[str, Any], prompt: str, seen_ids: set[str]
) -> tuple[str, dict[str, Any] | None, list[str]]:
    """(texto, hipótesis, problemas). Sin problemas, se publica."""
    match = JSON_RE.search(raw or "")
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        return "", None, ["the answer is not a JSON object with a text"]
    text = data["text"].strip()
    problems = enrichment_problems(text, prompt=prompt, seen_ids=seen_ids)
    hypothesis = data.get("hypothesis")
    if hypothesis is None:
        return text, None, problems
    if item["args"]["cause"] != Cause.UNKNOWN.value:
        return text, None, [*problems, "a hypothesis is only allowed when the cause is UNKNOWN"]
    try:
        checked = EnrichHypothesis.model_validate(hypothesis).model_dump(mode="json")
    except ValidationError as exc:
        reasons = "; ".join(e["msg"] for e in exc.errors())
        return text, None, [*problems, f"invalid hypothesis: {reasons}"]
    unseen = [i for i in checked["evidence_event_ids"] if i not in seen_ids]
    if unseen:
        problems = [*problems, f"hypothesis evidence not seen: {', '.join(unseen)}"]
    return text, checked, problems


def _status(alert: Any) -> AlertStatus | None:
    if alert is None:
        return None
    if alert.superseded_by is not None:
        return AlertStatus.SUPERSEDED
    return AlertStatus(alert.status)


async def _no_tools(name: str, args: dict[str, Any]) -> Any:
    raise RuntimeError("the enrichment has no tools")


def _wall_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
