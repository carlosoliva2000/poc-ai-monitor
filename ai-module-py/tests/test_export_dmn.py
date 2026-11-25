"""E6: el exportador de la tabla de decisión a DMN 1.5 (`tools/decision/export_dmn.py`)."""

import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET

from ai_module.decision.table import load_tables

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "decision" / "export_dmn.py"
E6_TABLE = Path(__file__).parent / "data" / "decision_table_e6.yaml"
LEARNED = Path(__file__).resolve().parents[1] / "src" / "ai_module" / "situation"
NS = {"dmn": "https://www.omg.org/spec/DMN/20230324/MODEL/"}


def _module():
    spec = importlib.util.spec_from_file_location("export_dmn", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_rule_and_cell_goes_to_the_dmn(tmp_path: Path) -> None:
    out = tmp_path / "t.dmn"
    assert _module().main(["--table", str(E6_TABLE), "--out", str(out)]) == 0
    root = ET.parse(out).getroot()
    assert root.tag == "{https://www.omg.org/spec/DMN/20230324/MODEL/}definitions"
    tables = load_tables(E6_TABLE)
    for name, table in tables.tables.items():
        dt = root.find(f"dmn:decision[@name='{name}']/dmn:decisionTable", NS)
        assert dt is not None and dt.get("hitPolicy") == "FIRST"
        rules = dt.findall("dmn:rule", NS)
        assert len(rules) == len(table.rules)
        for node in rules:
            assert len(node.findall("dmn:inputEntry", NS)) == len(table.inputs)
            assert len(node.findall("dmn:outputEntry", NS)) == len(table.outputs)
    wind = root.find(".//dmn:rule[@id='cause_C17']", NS)
    texts = [e.text for e in wind.findall("dmn:outputEntry/dmn:text", NS)]  # type: ignore[union-attr]
    assert texts == ['"WIND"', '"active"', '"same_cause"']


def test_the_export_is_deterministic(tmp_path: Path) -> None:
    module = _module()
    a, b = tmp_path / "a.dmn", tmp_path / "b.dmn"
    module.main(["--table", str(E6_TABLE), "--out", str(a)])
    module.main(["--table", str(E6_TABLE), "--out", str(b)])
    assert a.read_bytes() == b.read_bytes()


def test_the_frozen_learned_tables_and_the_situation_rule_export_unchanged(tmp_path: Path) -> None:
    """Las reglas congeladas se pueden llevar a un motor de reglas: cada fila sale con sus celdas
    tal cual (`, null`, `(a..b]`, `not(null)`) y sus salidas. No se valida con un motor DMN real."""
    module = _module()
    for name, decisions in (("tables_learned.yaml", 13), ("situation_rule.yaml", 1)):
        source = load_tables(LEARNED / name)
        out = tmp_path / f"{name}.dmn"
        assert module.main(["--table", str(LEARNED / name), "--out", str(out)]) == 0
        root = ET.parse(out).getroot()
        assert len(root.findall("dmn:decision", NS)) == len(source.tables) == decisions
        for table_name, table in source.tables.items():
            rules = root.findall(f"dmn:decision[@name='{table_name}']//dmn:rule", NS)
            assert len(rules) == len(table.rules)
            for node, rule in zip(rules, table.rules, strict=True):
                cells = [e.text for e in node.findall("dmn:inputEntry/dmn:text", NS)]
                assert cells == [
                    str(rule.when.get(i, "-")).lower()
                    if isinstance(rule.when.get(i), bool)
                    else str(rule.when.get(i, "-"))
                    for i in table.inputs
                ]
