"""Núcleo del monitor de situación, sin red: características → tablas por faceta → tipo de
incidente → seguidor → payloads de `IncidentUpdated`. Determinista: lo usan el proceso en
directo (`__main__`) y la reproducción sobre `events.jsonl` (`replay.py`).

Los umbrales están en las tablas (`tables.yaml`), nunca en el código, y no hay disparos por tiempo
ni por el nombre del escenario.
"""

from dataclasses import dataclass, field
from typing import Any

from poc_contracts.enums import DecidedBy, IncidentChange, IncidentKind, IncidentState

from ..decision.table import DecisionTables, Rule, load_tables
from ..ids import IdAllocator
from .features import WIND_LIMIT_MPS, FeatureExtractor, FeatureRow, GnssReference
from .policy import HERE, Policy, evidence_item, load_policy
from .tracker import Incident, Tracker

TABLE_NAME = "handwritten-video"
FACET_TABLES = {
    "gps.integrity": "gps_integrity",
    "link.availability": "link_availability",
    "environment.wind": "environment_wind",
    "drone.situation": "drone_situation",
}
CAUSE_FACET = "drone.cause"
# Valores que crecen mientras dura un incidente (metros y segundos): una evidencia se refresca
# cuando uno se duplica respecto a lo publicado.
DRIFT_FEATURES = ("route_dev_m", "radar_route_dev_m", "tele_gap_s")
DRIFT_FACTOR = 2.0
# Fuente de las evidencias de cada faceta (la de la situación depende de quién mide la desviación)
FACET_EVIDENCE = {
    "gps.integrity": "gnss",
    "link.availability": "link",
    "environment.wind": "autopilot",
}


@dataclass
class Snapshot:
    """Estados y filas de un instante, para las evidencias."""

    states: dict[str, str] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    deviation_source: str | None = None
    wind_est_mps: float | None = None


class SituationMonitor:
    def __init__(
        self,
        ids: IdAllocator | None = None,
        tables: DecisionTables | None = None,
        policy: Policy | None = None,
    ) -> None:
        self.ids = ids or IdAllocator()
        self.tables = tables or load_tables(HERE / "tables.yaml")
        self.policy = policy or load_policy()
        self.features = FeatureExtractor()
        self.reference = GnssReference()
        self.tracker = Tracker(self.ids, self.policy.base_severity, self.policy.rank)
        self.reset()

    def reset(self) -> None:
        self.features.reset()
        self.reference.reset()
        self.tracker.reset()
        self._situation = "on_route"
        self._wind_high_s = 0
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

    def _evaluate(self, snap: Snapshot, facet: str, table: str, inputs: dict[str, Any]) -> str:
        rule = self.tables[table].evaluate(inputs)
        snap.rules[facet], snap.inputs[facet] = rule, inputs
        snap.states[facet] = str(rule.then["state"] if "state" in rule.then else rule.then["kind"])
        return snap.states[facet]

    def step(self, row: FeatureRow) -> list[tuple[float, dict[str, Any]]]:
        snap = Snapshot(wind_est_mps=row.wind_est_mps)
        telemetry = row.tele_gap_s < 3.0
        rise, drop = self.reference.deltas(row)
        gps = self._evaluate(
            snap, "gps.integrity", "gps_integrity",
            {"telemetry": telemetry, "cn0_rise_db": rise, "agc_drop_db": drop},
        )  # fmt: skip
        self.reference.update(row, gps == "reliable")
        link = self._evaluate(
            snap, "link.availability", "link_availability",
            {"tele_gap_s": row.tele_gap_s, "link_loss_pct": row.link_loss_pct},
        )  # fmt: skip
        high = row.wind_est_mps is not None and row.wind_est_mps >= WIND_LIMIT_MPS
        self._wind_high_s = self._wind_high_s + 1 if high else 0
        wind = self._evaluate(
            snap, "environment.wind", "environment_wind",
            {"wind_est_mps": row.wind_est_mps, "wind_high_s": self._wind_high_s},
        )  # fmt: skip
        use_gps = telemetry and gps == "reliable" and row.gps_route_dev_m is not None
        deviation = row.gps_route_dev_m if use_gps else row.radar_route_dev_m
        snap.deviation_source = "gps" if use_gps else "radar" if deviation is not None else None
        self._situation = self._evaluate(
            snap, "drone.situation", "drone_situation",
            {"route_dev_m": deviation, "previous": self._situation},
        )  # fmt: skip
        cause_inputs = {
            "link": link, "radar_route_dev_m": row.radar_route_dev_m, "gps_integrity": gps,
            "situation": self._situation, "wind": wind,
        }  # fmt: skip
        rule = self.tables["incident_kind"].evaluate(cause_inputs)
        snap.rules[CAUSE_FACET], snap.inputs[CAUSE_FACET] = rule, cause_inputs
        kind = rule.then["kind"]
        candidate = None if kind == "none" else IncidentKind(kind)
        snap.states[CAUSE_FACET] = str(kind)
        self.last = snap
        transitions = self.tracker.step(row.t, candidate, self._situation == "on_route")
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
        if inc.state == IncidentState.OPEN and snap.states.get(CAUSE_FACET) == inc.kind.value:
            item = evidence_item(CAUSE_FACET, snap.rules[CAUSE_FACET], snap.inputs[CAUSE_FACET])
            evidence.append(item)
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
            "table": TABLE_NAME,
        }

    def _confidence(self, inc: Incident) -> str:
        """Confianza fija por fila de la tabla del tipo (la primera fila de ese tipo)."""
        for rule in self.tables["incident_kind"].rules:
            if rule.then["kind"] == inc.kind.value:
                return str(rule.then["confidence"])
        return "possible"
