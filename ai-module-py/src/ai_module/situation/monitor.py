"""Núcleo del monitor de situación, sin red: características → estado de cada faceta (tablas
aprendidas congeladas, o las escritas a mano como alternativa) → catálogo de incidentes → seguidor
→ payloads de `IncidentUpdated`. Determinista: lo usan el proceso en directo (`__main__`) y la
reproducción sobre `events.jsonl` (`replay.py`).

Los umbrales están en las tablas, nunca en el código, y no hay disparos por tiempo ni por el nombre
del escenario. Qué incidente abre cada combinación de estados es política (`catalog.py`,
`policy.yaml`).
"""

from typing import Any

from poc_contracts.enums import DecidedBy, IncidentChange, IncidentKind, IncidentState

from ..ids import IdAllocator
from .catalog import NOT_APPLICABLE, NOT_OBSERVABLE, hijack_level
from .engine import IncidentEngine, cause_kind
from .facets import LEARNED, FacetEngine, Snapshot, make_engine
from .features import FeatureExtractor, FeatureRow
from .policy import Policy, evidence_item, load_policy
from .tracker import Incident

# Valores que crecen mientras dura un incidente (metros y segundos): una evidencia se refresca
# cuando uno se duplica respecto a lo publicado.
DISTANCE_FEATURES = ("route_dev_m", "radar_route_dev_m", "radar_dev_m", "gps_dev_m")
DRIFT_FEATURES = (*DISTANCE_FEATURES, "tele_gap_s")
DRIFT_FLOOR = (
    20.0  # una distancia por debajo de esto (m) no cuenta como «se duplica»; un hueco, 3 s
)
GAP_FLOOR = 3.0
# Fuente de los eventos que sostienen cada faceta (la de la situación depende de quién mide)
FACET_SOURCE = {
    "gps.availability": "gps", "gps.quality": "gnss", "gps.integrity": "gnss",
    "link.availability": "link", "link.quality": "link", "radar.availability": "radar",
    "meteo.availability": "meteo", "battery.availability": "battery", "battery.level": "battery",
    "battery.endurance": "battery", "environment.wind": "autopilot", "drone.mode": "autopilot",
}  # fmt: skip
COMPARABLE = {"deviated": "off_route", "returning": "off_route"}


class SituationMonitor:
    def __init__(
        self, ids: IdAllocator | None = None, tables: str = LEARNED, policy: Policy | None = None
    ) -> None:
        self.ids = ids or IdAllocator()
        self.facets: FacetEngine = make_engine(tables)
        self.policy = policy or load_policy()
        self.features = FeatureExtractor()
        self.incidents = IncidentEngine(self.ids, self.policy)
        self.tracker = self.incidents.tracker
        self.reset()

    def reset(self) -> None:
        self.features.reset()
        self.facets.reset()
        self.incidents.reset()
        self._published: dict[str, dict[str, Any]] = {}  # lo último publicado de cada incidente
        self.last = Snapshot()

    def set_plan(self, waypoints: list[dict[str, Any]]) -> None:
        self.features.set_plan(waypoints)

    def push(self, event: dict[str, Any]) -> list[tuple[float, dict[str, Any]]]:
        """Un evento del mundo; devuelve los `IncidentUpdated` (instante, payload) que provoca."""
        out: list[tuple[float, dict[str, Any]]] = []
        for row in self.features.push(event):
            out.extend(self.step(row))
        return out

    def flush(self) -> list[tuple[float, dict[str, Any]]]:
        out: list[tuple[float, dict[str, Any]]] = []
        for row in self.features.flush():
            out.extend(self.step(row))
        return out

    def step(self, row: FeatureRow) -> list[tuple[float, dict[str, Any]]]:
        snap = self.facets.evaluate(row)
        self.last = snap
        transitions = self.incidents.step(row.t, snap.states, snap.confidence)
        done = {inc.family for inc in transitions}
        for family, inc in list(self.tracker.current.items()):
            if family in done or family in self.incidents.held:
                continue
            reason = self._refresh_reason(inc, snap)
            if reason == "drift":
                revised = self.tracker.escalate(family, row.t)
                transitions.append(
                    revised or self.tracker.revise(family, row.t, IncidentChange.EVIDENCE)
                )
            elif reason:  # facetas, confianza o hueco de telemetría
                transitions.append(self.tracker.revise(family, row.t, IncidentChange.EVIDENCE))
        payloads = [(inc.as_of, self.payload(inc, snap, row)) for inc in transitions]
        for inc in transitions:
            if inc.state == IncidentState.CLOSED:
                self._published.pop(inc.incident_id, None)
            else:
                self._published[inc.incident_id] = self._snapshot_of(inc, snap)
        return payloads

    # --- evidencias vivas --------------------------------------------------------------------

    def _facet_states(self, inc: Incident) -> dict[str, str]:
        states = self.incidents.view.states
        return {
            facet: COMPARABLE.get(states[facet], states[facet])
            for facet in self.policy.facets(inc.kind, inc.subject)
            if states.get(facet) not in (None, NOT_APPLICABLE, NOT_OBSERVABLE)
        }

    @staticmethod
    def _drift_values(snap: Snapshot) -> dict[str, float]:
        """Los valores de las condiciones que crecen mientras dura el incidente."""
        values: dict[str, float] = {}
        for inputs in snap.inputs.values():
            for feature in DRIFT_FEATURES:
                value = inputs.get(feature)
                if isinstance(value, int | float) and not isinstance(value, bool):
                    values[feature] = max(values.get(feature, 0.0), float(value))
        return values

    def _snapshot_of(self, inc: Incident, snap: Snapshot) -> dict[str, Any]:
        return {
            "states": self._facet_states(inc),
            "values": self._drift_values(snap),
            "confidence": inc.confidence,
        }

    def _refresh_reason(self, inc: Incident, snap: Snapshot) -> str | None:
        """Por qué hay que refrescar las evidencias de un incidente abierto (no cada segundo):
        cambia el estado de alguna de sus facetas (`returning` cuenta como fuera de ruta: sin
        parpadeo entre 15 y 25 m), cambia su confianza, o una distancia o un hueco de telemetría se
        duplica respecto a lo publicado (el secuestro sigue «deviated» de 130 m a 600 m)."""
        before = self._published.get(inc.incident_id)
        if before is None:
            return "facets"
        if self._facet_states(inc) != before["states"]:
            return "facets"
        if inc.confidence != before["confidence"]:
            return "confidence"
        if "drone.situation" not in self.policy.facets(inc.kind, inc.subject) and inc.kind not in (
            IncidentKind.LINK_LOSS,
            IncidentKind.HIJACK,
        ):
            return None
        now = self._drift_values(snap)
        factor = self.policy.defaults.drift_factor
        grown = [
            feature
            for feature, old in before["values"].items()
            if old >= (DRIFT_FLOOR if feature in DISTANCE_FEATURES else GAP_FLOOR)
            and now.get(feature, 0.0) >= factor * old
        ]
        if not grown:
            return None
        return "drift" if any(f in DISTANCE_FEATURES for f in grown) else "gap"

    # --- payload -----------------------------------------------------------------------------

    def payload(self, inc: Incident, snap: Snapshot, row: FeatureRow) -> dict[str, Any]:
        policy = self.policy.kinds[inc.kind]
        facets = self.policy.facets(inc.kind, inc.subject)
        states = self.incidents.view.states
        evidence = [
            evidence_item(facet, snap.rules[facet], snap.inputs[facet])
            for facet in facets
            if facet in snap.rules and states.get(facet) not in (NOT_APPLICABLE, NOT_OBSERVABLE)
        ]
        ids: list[str] = []
        for facet in facets:
            source = FACET_SOURCE.get(facet) or snap.deviation_source
            event_id = row.evidence_ids.get(source or "")
            if event_id and event_id not in ids:
                ids.append(event_id)
        return {
            "incident_id": inc.incident_id,
            "revision": inc.revision,
            "kind": inc.kind.value,
            "subject": inc.subject,
            "name": self.policy.name(inc.kind, inc.subject),
            "state": inc.state.value,
            "severity": inc.severity.value,
            "confidence": inc.confidence,
            "opened_at": inc.opened_at,
            "as_of_sim_time": inc.as_of,
            "change": inc.change.value,
            "evidence": evidence,
            "context": self._context(inc, snap, row),
            "checks": policy.checks,
            "evidence_event_ids": ids,
            "decided_by": DecidedBy.TABLE.value,
            "table": self.facets.table_name,
        }

    def _context(self, inc: Incident, snap: Snapshot, row: FeatureRow) -> list[dict[str, Any]]:
        """Lo que no decide pero ayuda a leer el incidente (la web lo enseña aparte)."""
        view = self.incidents.view
        facets = self.policy.facets(inc.kind, inc.subject)
        context: list[dict[str, Any]] = []
        if snap.deviation_source and "drone.situation" in facets:
            context.append({"feature": "deviation_source", "value": snap.deviation_source})
        notable = snap.states.get("environment.wind") in ("notable", "beyond_limit")
        if inc.kind != IncidentKind.WIND and notable and snap.wind_est_mps is not None:
            context.append({"feature": "wind_est_mps", "value": round(snap.wind_est_mps, 1)})
        if inc.kind == IncidentKind.LINK_LOSS and hijack_level(view) == 1:
            context.append({"feature": "suspected_cause", "value": "HIJACK (probable)"})
        if inc.kind == IncidentKind.UNDETERMINED:
            kind = cause_kind(view.state("drone.cause"))
            if kind is not None:
                context.append({"feature": "possible_cause", "value": f"{kind.value} (possible)"})
        if inc.kind in (IncidentKind.LINK_LOSS, IncidentKind.HIJACK):
            context.append({"feature": "telemetry_gap_s", "value": round(row.tele_gap_s)})
        pct = row.values.get("battery_pct")
        if inc.family == "battery" and pct is not None:
            context.append({"feature": "battery_pct", "value": round(pct, 1)})
        return context
