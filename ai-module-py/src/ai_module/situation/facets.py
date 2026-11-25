"""Estado de cada faceta en un segundo: de dónde sale cada estado, con su fila y su confianza.

Dos motores producen lo mismo para el resto del monitor (`Snapshot`), así que el catálogo, el
seguidor y la política son idénticos y la evaluación compara solo las tablas:
- `LearnedFacets`: las 13 tablas aprendidas y la regla de la situación (congeladas, E7b);
- `HandwrittenFacets`: las tablas escritas a mano del vídeo (`tables.yaml`), alternativa
  seleccionable para comparar. No es el camino por defecto.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..decision.table import DecisionTables, Rule, load_tables
from . import freeze
from .features import FeatureRow
from .policy import HERE
from .situation_rule import position_used, rule_inputs

LEARNED = "learned"
HANDWRITTEN = "handwritten"
TABLE_NAMES = {LEARNED: "learned-e7b-v3", HANDWRITTEN: "handwritten-video"}

# Facetas de las tablas a mano y la tabla que decide cada una
HAND_FACET_TABLES = {
    "gps.integrity": "gps_integrity",
    "link.availability": "link_availability",
    "environment.wind": "environment_wind",
    "drone.situation": "drone_situation",
}
# Provisional (vídeo): viento por encima del cual la tabla a mano da «fuera de límites»
HAND_WIND_LIMIT_MPS = 12.0
HAND_REFERENCE_WINDOW = 60  # mediana de 60 s para la referencia de C/N0 y AGC


@dataclass
class Snapshot:
    """Estados, filas y entradas de un instante, para las evidencias."""

    states: dict[str, str] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    confidence: dict[str, str] = field(default_factory=dict)  # nivel de la fila (si la tiene)
    deviation_source: str | None = None
    wind_est_mps: float | None = None
    # Tipo de incidente que da la tabla `incident_kind` del vídeo (provisional, ver `monitor.py`)
    kind: str = "none"
    kind_rule: Rule | None = None
    kind_inputs: dict[str, Any] = field(default_factory=dict)

    def put(self, facet: str, rule: Rule, inputs: dict[str, Any]) -> str:
        self.rules[facet], self.inputs[facet] = rule, inputs
        self.states[facet] = str(rule.then["state"])
        if "confidence" in rule.then:
            self.confidence[facet] = str(rule.then["confidence"])
        return self.states[facet]


class FacetEngine(Protocol):
    table_name: str

    def reset(self) -> None: ...
    def evaluate(self, row: FeatureRow) -> Snapshot: ...


class LearnedFacets:
    """Las 13 tablas aprendidas (`tables_learned.yaml`) y la regla determinista de la situación
    (`situation_rule.yaml`, con el margen del fichero de congelación). Comprueba el hash al
    crearse."""

    table_name = TABLE_NAMES[LEARNED]

    def __init__(self) -> None:
        freeze.verify()
        self.tables = load_tables(HERE / "tables_learned.yaml")
        self.rule = load_tables(HERE / "situation_rule.yaml")["drone_situation_rule"]
        self.margin_k = freeze.margin_k()
        self.reset()

    def reset(self) -> None:
        self._situation = "on_route"

    def evaluate(self, row: FeatureRow) -> Snapshot:
        snap = Snapshot(wind_est_mps=row.wind_est_mps)
        for name, table in self.tables.tables.items():
            facet = name.replace("_", ".", 1)
            snap.put(facet, table.evaluate(row.values), row.values)
        source, _, _ = position_used(row.values, snap.states)
        snap.deviation_source = source
        inputs = rule_inputs(row.values, snap.states, self._situation, self.margin_k)
        self._situation = snap.put("drone.situation", self.rule.evaluate(inputs), inputs)
        return snap


def _median(values: deque[float]) -> float:
    return sorted(values)[len(values) // 2]


class GnssReference:
    """Referencia de C/N0 y AGC de las tablas a mano: la mediana de los últimos 60 s, **congelada
    mientras el GPS no es fiable** (una mediana que siguiera actualizándose subiría con el engaño y
    lo dejaría de ver). Depende de la salida de la tabla, así que no sirve para entrenar."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._cn0: deque[float] = deque(maxlen=HAND_REFERENCE_WINDOW)
        self._agc: deque[float] = deque(maxlen=HAND_REFERENCE_WINDOW)
        self.cn0: float | None = None
        self.agc: float | None = None

    def deltas(self, row: FeatureRow) -> tuple[float | None, float | None]:
        """C/N0 y AGC menos su referencia (la primera lectura es su propia referencia)."""
        if row.cn0_dbhz is None or row.agc_db is None:
            return None, None
        if self.cn0 is None or self.agc is None:
            self.cn0, self.agc = row.cn0_dbhz, row.agc_db
        return row.cn0_dbhz - self.cn0, row.agc_db - self.agc

    def update(self, row: FeatureRow, reliable: bool) -> None:
        if not reliable or row.cn0_dbhz is None or row.agc_db is None:
            return
        self._cn0.append(row.cn0_dbhz)
        self._agc.append(row.agc_db)
        self.cn0, self.agc = _median(self._cn0), _median(self._agc)


class HandwrittenFacets:
    """Las cuatro facetas de las tablas a mano del vídeo (`tables.yaml`): integridad del GPS,
    enlace, viento y situación. Con sus apaños (referencia de C/N0, 12 m/s fijos, telemetría
    < 3 s), que solo viven aquí."""

    table_name = TABLE_NAMES[HANDWRITTEN]

    def __init__(self, tables: DecisionTables | None = None) -> None:
        self.tables = tables or load_tables(HERE / "tables.yaml")
        self.reference = GnssReference()
        self.reset()

    def reset(self) -> None:
        self.reference.reset()
        self._situation = "on_route"
        self._wind_high_s = 0

    def evaluate(self, row: FeatureRow) -> Snapshot:
        snap = Snapshot(wind_est_mps=row.wind_est_mps)
        telemetry = row.tele_gap_s < 3.0
        rise, drop = self.reference.deltas(row)
        gps = self._put(snap, "gps.integrity", {
            "telemetry": telemetry, "cn0_rise_db": rise, "agc_drop_db": drop,
        })  # fmt: skip
        self.reference.update(row, gps == "reliable")
        self._put(snap, "link.availability", {
            "tele_gap_s": row.tele_gap_s, "link_loss_pct": row.link_loss_pct,
        })  # fmt: skip
        high = row.wind_est_mps is not None and row.wind_est_mps >= HAND_WIND_LIMIT_MPS
        self._wind_high_s = self._wind_high_s + 1 if high else 0
        self._put(snap, "environment.wind", {
            "wind_est_mps": row.wind_est_mps, "wind_high_s": self._wind_high_s,
        })  # fmt: skip
        use_gps = telemetry and gps == "reliable" and row.gps_route_dev_m is not None
        deviation = row.gps_route_dev_m if use_gps else row.radar_route_dev_m
        snap.deviation_source = "gps" if use_gps else "radar" if deviation is not None else None
        self._situation = self._put(snap, "drone.situation", {
            "route_dev_m": deviation, "previous": self._situation,
        })  # fmt: skip
        return snap

    def _put(self, snap: Snapshot, facet: str, inputs: dict[str, Any]) -> str:
        return snap.put(facet, self.tables[HAND_FACET_TABLES[facet]].evaluate(inputs), inputs)


def make_engine(tables: str) -> FacetEngine:
    if tables == LEARNED:
        return LearnedFacets()
    if tables == HANDWRITTEN:
        return HandwrittenFacets()
    raise ValueError(f"tables must be '{LEARNED}' or '{HANDWRITTEN}', not {tables!r}")
