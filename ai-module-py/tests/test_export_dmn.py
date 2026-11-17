"""E6: el exportador de la tabla de decisión a DMN 1.5 (`tools/decision/export_dmn.py`)."""

import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET

from ai_module.decision.table import load_tables

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "decision" / "export_dmn.py"
NS = {"dmn": "https://www.omg.org/spec/DMN/20230324/MODEL/"}


def _module():
    spec = importlib.util.spec_from_file_location("export_dmn", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_rule_and_cell_goes_to_the_dmn(tmp_path: Path) -> None:
    out = tmp_path / "t.dmn"
    assert _module().main(["--out", str(out)]) == 0
    root = ET.parse(out).getroot()
    assert root.tag == "{https://www.omg.org/spec/DMN/20230324/MODEL/}definitions"
    tables = load_tables()
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
    module.main(["--out", str(a)])
    module.main(["--out", str(b)])
    assert a.read_bytes() == b.read_bytes()
