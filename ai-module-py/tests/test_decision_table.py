"""E6: la tabla de decisión (`config/decision_table.yaml`): una prueba por fila, con los ejemplos de
`tests/data/decision_examples.yaml`, y que todas las celdas son unary tests de FEEL admitidos."""

from pathlib import Path

import pytest
import yaml

from ai_module.decision.table import load_tables

EXAMPLES = yaml.safe_load(
    (Path(__file__).parent / "data" / "decision_examples.yaml").read_text(encoding="utf-8")
)
TABLES = load_tables()
CASES = [(table, rule.rule_id) for table, spec in TABLES.tables.items() for rule in spec.rules]


def test_every_rule_has_an_example() -> None:
    for table, rule_id in CASES:
        assert rule_id in EXAMPLES["examples"][table], f"{table}.{rule_id} has no example"
    for table, examples in EXAMPLES["examples"].items():
        known = {r.rule_id for r in TABLES[table].rules}
        assert set(examples) <= known, f"examples for unknown rules in {table}"


@pytest.mark.parametrize(("table", "rule_id"), CASES)
def test_each_rule_fires_on_its_example(table: str, rule_id: str) -> None:
    inputs = {**EXAMPLES["defaults"][table], **(EXAMPLES["examples"][table][rule_id] or {})}
    assert TABLES[table].evaluate(inputs).rule_id == rule_id


def test_the_tables_have_the_expected_shape() -> None:
    assert set(TABLES.tables) == {"cause", "severity", "confidence"}
    assert TABLES["cause"].outputs == ["cause", "phase", "attach"]
    for spec in TABLES.tables.values():
        assert spec.hit_policy == "FIRST"
        assert not spec.rules[-1].when  # la última es la regla por defecto


def test_the_outputs_are_closed_lists() -> None:
    causes = {"WIND", "HIJACK", "GPS_SPOOFING", "SENSOR_FAULT", "GPS_JAMMING", "UNKNOWN",
              "SAME_AS_GPS_ALERT"}  # fmt: skip
    for rule in TABLES["cause"].rules:
        assert rule.then["cause"] in causes
        assert rule.then["phase"] in ("active", "recovering")
        assert rule.then["attach"] in ("none", "same_cause", "gps_alert", "hijack_alert")
    for rule in TABLES["severity"].rules:
        assert rule.then["severity"] in ("low", "medium", "high")
    for rule in TABLES["confidence"].rules:
        assert 0 <= rule.then["confidence"] <= 1
    unknown = [r for r in TABLES["confidence"].rules if r.when.get("cause") == '"UNKNOWN"']
    assert unknown and all(r.then["confidence"] <= 0.4 for r in unknown)  # skill: ≤ 0,4
