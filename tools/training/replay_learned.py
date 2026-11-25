"""E7b, paso 4: `runs/demo` y `runs/nominal` pasados por el monitor con las tablas aprendidas.

Las cuatro facetas que tienen tabla a mano (GPS, enlace, viento y situación del dron) salen de las
tablas aprendidas; la tabla del tipo de incidente, el seguidor y la política son los del vídeo,
sin tocar (son de la E7c). Devuelve las transiciones de incidente para compararlas con las del
vídeo (`ai_module.situation.replay`).
"""

from pathlib import Path
from typing import Any

from tree_to_table import table_name

from ai_module.decision.table import DecisionTables, load_tables
from ai_module.ids import IdAllocator
from ai_module.situation.features import FeatureExtractor
from ai_module.situation.policy import HERE, load_policy
from ai_module.situation.replay import is_world, read_events
from ai_module.situation.situation_rule import rule_inputs
from ai_module.situation.tracker import Tracker
from poc_contracts.enums import IncidentKind

FACETS = ("gps.integrity", "link.availability", "environment.wind", "drone.situation")
CAUSE_FACETS = ("gps.availability", "drone.mode")  # las otras dos que usa la regla de la situación


def replay(
    events_path: Path, learned: DecisionTables, rule: bool = False, margin_k: float = 0.5
) -> list[tuple[float, str, str, str]]:
    """Transiciones `(t, cambio, tipo, estado)` con las facetas de `learned`. Con `rule`, la
    situación del dron sale de la regla determinista (`situation_rule.yaml`), no de la aprendida."""
    hand = load_tables(HERE / "tables.yaml")
    policy = load_policy()
    tracker = Tracker(IdAllocator(), policy.base_severity, policy.rank)
    fx = FeatureExtractor()
    situation_table = load_tables(HERE / "situation_rule.yaml")["drone_situation_rule"]
    previous = {"situation": "on_route"}
    out: list[tuple[float, str, str, str]] = []

    def step(row: Any) -> None:
        wanted = [f for f in FACETS if not (rule and f == "drone.situation")]
        state = {f: str(learned[table_name(f)].evaluate(row.values).then["state"]) for f in wanted}
        if rule:
            states = {f: state[f] for f in wanted} | {
                f: str(learned[table_name(f)].evaluate(row.values).then["state"])
                for f in CAUSE_FACETS
            }
            inputs = rule_inputs(row.values, states, previous["situation"], margin_k)
            previous["situation"] = state["drone.situation"] = str(
                situation_table.evaluate(inputs).then["state"]
            )
        cause = hand["incident_kind"].evaluate({
            "link": state["link.availability"], "radar_route_dev_m": row.radar_route_dev_m,
            "gps_integrity": state["gps.integrity"], "situation": state["drone.situation"],
            "wind": state["environment.wind"],
        })  # fmt: skip
        kind = cause.then["kind"]
        candidate = None if kind == "none" else IncidentKind(kind)
        for inc in tracker.step(row.t, candidate, state["drone.situation"] == "on_route"):
            out.append((inc.as_of, inc.change.value, inc.kind.value, inc.state.value))

    for event in read_events(events_path):
        if is_world(event):
            for row in fx.push(event):
                step(row)
    for row in fx.flush():
        step(row)
    return out
