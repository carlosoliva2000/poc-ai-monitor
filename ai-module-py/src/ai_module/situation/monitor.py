"""Núcleo del monitor de situación, sin red: características → estado de cada faceta (tablas
aprendidas congeladas, o las escritas a mano como alternativa) → tipo de incidente → seguidor →
payloads de `IncidentUpdated`. Determinista: lo usan el proceso en directo (`__main__`) y la
reproducción sobre `events.jsonl` (`replay.py`).

Los umbrales están en las tablas, nunca en el código, y no hay disparos por tiempo ni por el nombre
del escenario. El tipo de incidente sale todavía de la tabla `incident_kind` del vídeo (provisional
hasta que el catálogo de incidentes la sustituya).
"""

from typing import Any

from poc_contracts.enums import DecidedBy, IncidentChange, IncidentKind, IncidentState

from ..decision.table import DecisionTables, load_tables
from ..ids import IdAllocator
from .facets import LEARNED, FacetEngine, Snapshot, make_engine
from .features import FeatureExtractor, FeatureRow
from .policy import HERE, Policy, evidence_item, load_policy
from .tracker import Incident, Tracker

CAUSE_FACET = "drone.cause"
# Valores que crecen mientras dura un incidente (metros y segundos): una evidencia se refresca
# cuando uno se duplica respecto a lo publicado.
DRIFT_FEATURES = ("route_dev_m", "radar_route_dev_m", "radar_dev_m", "gps_dev_m", "tele_gap_s")
DRIFT_FACTOR = 2.0
# Fuente de las evidencias de cada faceta (la de la situación depende de quién mide la desviación)
FACET_EVIDENCE = {
    "gps.integrity": "gnss",
    "link.availability": "link",
    "environment.wind": "autopilot",
}


class SituationMonitor:
    def __init__(
        self,
        ids: IdAllocator | None = None,
        tables: str = LEARNED,
        policy: Policy | None = None,
        kind_table: DecisionTables | None = None,
    ) -> None:
        self.ids = ids or IdAllocator()
        self.engine: FacetEngine = make_engine(tables)
        self.kind_tables = kind_table or load_tables(HERE / "tables.yaml")
        self.policy = policy or load_policy()
        self.features = FeatureExtractor()
        self.tracker = Tracker(self.ids, self.policy.base_severity, self.policy.rank)
        self.reset()

    def reset(self) -> None:
        self.features.reset()
        self.engine.reset()
        self.tracker.reset()
        self._published: dict[str, str] = {}  # estado de las facetas de las últimas evidencias
        self._published_values: dict[str, float] = {}  # distancias y huecos de esas evidencias
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
        snap = self.engine.evaluate(row)
        situation = snap.states["drone.situation"]
        kind_inputs = {
            "link": snap.states["link.availability"],
            "radar_route_dev_m": row.radar_route_dev_m,
            "gps_integrity": snap.states["gps.integrity"],
            "situation": situation,
            "wind": snap.states["environment.wind"],
        }
        rule = self.kind_tables["incident_kind"].evaluate(kind_inputs)
        snap.kind_rule, snap.kind_inputs, snap.kind = rule, kind_inputs, str(rule.then["kind"])
        candidate = None if snap.kind == "none" else IncidentKind(snap.kind)
        self.last = snap
        transitions = self.tracker.step(row.t, candidate, situation == "on_route")
        if not transitions and self.tracker.current is not None and self._evidence_changed(snap):
            transitions = [self.tracker.revise(row.t, IncidentChange.EVIDENCE)]
        if transitions:
            last = transitions[-1]
            closed = last.state == IncidentState.CLOSED
            self._published = {} if closed else self._facet_states(last, snap)
            self._published_values = {} if closed else self._drift_values(snap)
        return [(inc.as_of, self.payload(inc, snap, row)) for inc in transitions]

    def _evidence_changed(self, snap: Snapshot) -> bool:
        """Las evidencias de un incidente abierto se actualizan, no cada segundo, cuando:
        - cambia el estado de alguna de sus facetas (p. ej. situation on_route → deviated;
          `returning` cuenta como fuera de ruta: sin parpadeo entre 15 y 25 m), o
        - una distancia o un hueco de telemetría se duplica respecto a lo publicado (el secuestro
          sigue «deviated» mientras el dron pasa de 130 m a 600 m)."""
        incident = self.tracker.current
        assert incident is not None
        states = self._comparable(self._facet_states(incident, snap))
        if states != self._comparable(self._published):
            return True
        return any(
            before > 0 and now >= DRIFT_FACTOR * before
            for feature, before in self._published_values.items()
            if (now := self._drift_values(snap).get(feature)) is not None
        )

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

    @staticmethod
    def _comparable(states: dict[str, str]) -> dict[str, str]:
        return {f: "off_route" if s in ("deviated", "returning") else s for f, s in states.items()}

    def _facet_states(self, inc: Incident, snap: Snapshot) -> dict[str, str]:
        return {
            facet: snap.states[facet]
            for facet in self.policy.kinds[inc.kind].facets
            if facet in snap.states
        }

    def payload(self, inc: Incident, snap: Snapshot, row: FeatureRow) -> dict[str, Any]:
        kind_policy = self.policy.kinds[inc.kind]
        evidence = [
            evidence_item(facet, snap.rules[facet], snap.inputs[facet])
            for facet in kind_policy.facets
            if facet in snap.rules
        ]
        if inc.state == IncidentState.OPEN and snap.kind == inc.kind.value:
            assert snap.kind_rule is not None
            evidence.append(evidence_item(CAUSE_FACET, snap.kind_rule, snap.kind_inputs))
        ids: list[str] = []
        for facet in kind_policy.facets:
            source = FACET_EVIDENCE.get(facet) or snap.deviation_source
            event_id = row.evidence_ids.get(source or "")
            if event_id and event_id not in ids:
                ids.append(event_id)
        context: list[dict[str, Any]] = []
        if snap.deviation_source:
            context.append({"feature": "deviation_source", "value": snap.deviation_source})
        notable = snap.states.get("environment.wind") in ("notable", "beyond_limit")
        if inc.kind != IncidentKind.WIND and notable and snap.wind_est_mps is not None:
            context.append({"feature": "wind_est_mps", "value": round(snap.wind_est_mps, 1)})
        return {
            "incident_id": inc.incident_id,
            "revision": inc.revision,
            "kind": inc.kind.value,
            "name": kind_policy.name,
            "state": inc.state.value,
            "severity": inc.severity.value,
            "confidence": self._confidence(inc),
            "opened_at": inc.opened_at,
            "as_of_sim_time": inc.as_of,
            "change": inc.change.value,
            "evidence": evidence,
            "context": context,
            "checks": kind_policy.checks,
            "evidence_event_ids": ids,
            "decided_by": DecidedBy.TABLE.value,
            "table": self.engine.table_name,
        }

    def _confidence(self, inc: Incident) -> str:
        """Confianza fija por fila de la tabla del tipo (la primera fila de ese tipo)."""
        for rule in self.kind_tables["incident_kind"].rules:
            if rule.then["kind"] == inc.kind.value:
                return str(rule.then["confidence"])
        return "possible"
