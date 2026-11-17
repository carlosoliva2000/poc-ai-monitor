"""Exporta la tabla de decisión del monitor (E6) a DMN 1.5 (XML), para un motor de reglas.

    uv run --project ai-module-py python tools/decision/export_dmn.py [--out RUTA.dmn]

Una `decision` por tabla (`cause`, `severity`, `confidence`), cada una con su `decisionTable`
(política FIRST), sus entradas (`inputExpression` = el nombre de la entrada) y sus salidas. Las
celdas ya son unary tests de FEEL y se copian tal cual; las salidas se escriben como literales de
FEEL (cadenas entre comillas, números sin ellas). Espacio de nombres de DMN 1.5 tomado del XSD
oficial (https://www.omg.org/spec/DMN/20230324/DMN15.xsd). La salida es determinista.

No se valida aquí: no hay en Python un validador de DMN fiable (pyDMNrules solo lee Excel); se
validaría cargándola en Drools/Kogito.
"""

import argparse
import sys
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ai-module-py" / "src"))

from ai_module.decision.table import DEFAULT_TABLE, DecisionTables, load_tables  # noqa: E402

DMN_NS = "https://www.omg.org/spec/DMN/20230324/MODEL/"
FEEL_NS = "https://www.omg.org/spec/DMN/20230324/FEEL/"
MODEL_NS = "https://citadel.local/poc-ai-monitor/monitor-decision"
DEFAULT_OUT = REPO / "experiments" / "e6" / "decision_table.dmn"


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return f"{value:g}"
    return f'"{value}"'


def _cell(test: object) -> str:
    if isinstance(test, bool):
        return "true" if test else "false"
    return str(test)


def to_dmn(tables: DecisionTables) -> str:
    ET.register_namespace("", DMN_NS)
    q = lambda tag: f"{{{DMN_NS}}}{tag}"  # noqa: E731
    root = ET.Element(
        q("definitions"),
        {
            "id": "monitor_decision",
            "name": "Monitor decision table",
            "namespace": MODEL_NS,
            "expressionLanguage": FEEL_NS,
            "typeLanguage": FEEL_NS,
        },
    )
    for name, table in tables.tables.items():
        decision = ET.SubElement(root, q("decision"), {"id": f"decision_{name}", "name": name})
        if table.description:
            ET.SubElement(decision, q("description")).text = table.description
        dt = ET.SubElement(
            decision, q("decisionTable"), {"id": f"table_{name}", "hitPolicy": table.hit_policy}
        )
        for i, input_name in enumerate(table.inputs):
            node = ET.SubElement(dt, q("input"), {"id": f"{name}_in_{i}", "label": input_name})
            expression = ET.SubElement(node, q("inputExpression"), {"id": f"{name}_ie_{i}"})
            ET.SubElement(expression, q("text")).text = input_name
        for i, output in enumerate(table.outputs):
            ET.SubElement(dt, q("output"), {"id": f"{name}_out_{i}", "name": output})
        for rule in table.rules:
            node = ET.SubElement(dt, q("rule"), {"id": f"{name}_{rule.rule_id}"})
            if rule.note:
                ET.SubElement(node, q("description")).text = f"{rule.rule_id}: {rule.note}"
            for i, input_name in enumerate(table.inputs):
                entry = ET.SubElement(node, q("inputEntry"), {"id": f"{rule.rule_id}_i{i}"})
                ET.SubElement(entry, q("text")).text = _cell(rule.when.get(input_name, "-"))
            for i, output in enumerate(table.outputs):
                entry = ET.SubElement(node, q("outputEntry"), {"id": f"{rule.rule_id}_o{i}"})
                ET.SubElement(entry, q("text")).text = _literal(rule.then[output])
    text = ET.tostring(root, encoding="unicode")
    return minidom.parseString(text).toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the decision table to DMN 1.5 XML")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    tables = load_tables(args.table)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(to_dmn(tables), encoding="utf-8")
    rules = sum(len(t.rules) for t in tables.tables.values())
    count = f"{len(tables.tables)} decisions, {rules} rules"
    print(f"{args.out} · {count} · table {tables.sha256[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
