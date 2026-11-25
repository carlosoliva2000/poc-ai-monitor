"""Las tablas del monitor como un JSON para la web (ventana «Rules» de las evidencias).

La web no tiene una copia a mano: `tools/video/export_tables.py` escribe
`web/lib/situation-tables.json` con esto, a partir del mismo `tables.yaml` que ejecuta el monitor,
y un test comprueba que el fichero está sincronizado.
"""

from typing import Any

from ..decision.table import DecisionTable, DecisionTables, load_tables
from .monitor import CAUSE_FACET, FACET_TABLES
from .policy import HERE

CAUSE_TABLE = "incident_kind"


def build(tables: DecisionTables | None = None) -> dict[str, Any]:
    """Cada faceta de las evidencias con su tabla completa, con las filas en orden de evaluación."""
    tables = tables or load_tables(HERE / "tables.yaml")
    names = {**FACET_TABLES, CAUSE_FACET: CAUSE_TABLE}
    facets: dict[str, Any] = {}
    for facet, name in names.items():
        facets[facet] = table_json(name, tables[name])
    return {"facets": facets}


def table_json(name: str, table: DecisionTable) -> dict[str, Any]:
    """Una tabla como el JSON de la web: entradas, salidas y filas en orden de evaluación."""
    return {
        "table": name,
        "description": table.description,
        "hit_policy": table.hit_policy,
        "inputs": table.inputs,
        "outputs": table.outputs,
        "rules": [
            {
                "id": rule.rule_id,
                "note": rule.note,
                "when": {
                    key: str(cell).lower() if isinstance(cell, bool) else str(cell)
                    for key, cell in rule.when.items()
                },
                "then": {key: str(value) for key, value in rule.then.items()},
            }
            for rule in table.rules
        ],
    }


def build_frozen() -> dict[str, Any]:
    """Las tablas congeladas (E7b): las 13 aprendidas de `tables_learned.yaml` y la regla
    determinista de `drone.situation`, cada una con el nombre de su faceta."""
    learned = load_tables(HERE / "tables_learned.yaml")
    rule = load_tables(HERE / "situation_rule.yaml")
    facets = {name.replace("_", ".", 1): table_json(name, t) for name, t in learned.tables.items()}
    facets["drone.situation"] = table_json("drone_situation_rule", rule["drone_situation_rule"])
    return {"facets": dict(sorted(facets.items()))}
