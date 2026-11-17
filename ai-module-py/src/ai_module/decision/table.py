"""Tablas de decisión con forma de DMN y un evaluador pequeño (E6).

La tabla es un **dato** (`config/decision_table.yaml`), no código: entradas con nombre, salidas y
reglas con política *FIRST* (gana la primera que encaja, como el «para en el primer paso que
encaje» de las skills). Las celdas solo admiten *unary tests* de FEEL, el lenguaje de expresiones
de DMN, para que la misma tabla se pueda ejecutar en un motor de reglas (Drools/Kogito):

- `-` (cualquier valor), `true`, `false`, `null`;
- un número (`30`) o una cadena entre comillas (`"WIND"`): igualdad;
- comparaciones: `> 30`, `>= 30`, `< 0.5`, `<= 2`;
- intervalos: `[10..25]`, `(10..25]`, `[10..25)`, `(10..25)`;
- listas de tests separadas por comas (`"gps","radar"`): basta con que pase uno;
- `not(test, …)`: ninguno de los tests de dentro.

Nada de Python dentro de una celda: lo complejo se calcula antes como entrada (`features.py`).
Las salidas son literales (cadenas o números).
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TABLE = Path(__file__).resolve().parents[1] / "config" / "decision_table.yaml"
HIT_POLICIES = ("FIRST",)

_NUMBER = r"-?\d+(?:\.\d+)?"
_COMPARISON = re.compile(rf"^(<=|>=|<|>)\s*({_NUMBER})$")
_RANGE = re.compile(rf"^([\[(])\s*({_NUMBER})\s*\.\.\s*({_NUMBER})\s*([\])])$")
_STRING = re.compile(r'^"([^"]*)"$')
_NUMBER_RE = re.compile(rf"^{_NUMBER}$")


class TableError(Exception):
    """La tabla está mal formada o una celda no es un unary test válido (mensaje en inglés)."""


def _split(text: str) -> list[str]:
    """Separa por comas de primer nivel (no dentro de comillas, corchetes ni paréntesis)."""
    parts, depth, quoted, current = [], 0, False, ""
    for char in text:
        if char == '"':
            quoted = not quoted
        elif not quoted and char in "([":
            depth += 1
        elif not quoted and char in ")]":
            depth -= 1
        if char == "," and depth == 0 and not quoted:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    parts.append(current.strip())
    return parts


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _single(test: str, value: Any) -> bool:
    """Un unary test simple (sin comas)."""
    if test == "-":
        return True
    if test == "true":
        return value is True
    if test == "false":
        return value is False
    if test == "null":
        return value is None
    if test.startswith("not(") and test.endswith(")"):
        return not any(_single(t, value) for t in _split(test[4:-1]))
    if match := _STRING.match(test):
        return isinstance(value, str) and value == match.group(1)
    if _NUMBER_RE.match(test):
        number = _number(value)
        return number is not None and number == float(test)
    if match := _COMPARISON.match(test):
        number = _number(value)
        if number is None:
            return False
        op, limit = match.group(1), float(match.group(2))
        return {
            "<": number < limit,
            "<=": number <= limit,
            ">": number > limit,
            ">=": number >= limit,
        }[op]
    if match := _RANGE.match(test):
        number = _number(value)
        if number is None:
            return False
        low, high = float(match.group(2)), float(match.group(3))
        above = number >= low if match.group(1) == "[" else number > low
        below = number <= high if match.group(4) == "]" else number < high
        return above and below
    raise TableError(f"not a supported unary test: {test!r}")


def check_cell(test: str) -> None:
    """Falla si la celda no es un unary test del subconjunto admitido."""
    for part in _split(str(test).strip()):
        _single(part, None)  # solo valida la forma; el valor da igual


def matches(test: str | bool | int | float, value: Any) -> bool:
    """Si `value` pasa el unary test `test` (una celda de la tabla)."""
    if isinstance(test, bool):  # YAML convierte `true` sin comillas en booleano
        test = "true" if test else "false"
    elif isinstance(test, int | float):
        test = repr(test)
    return any(_single(part, value) for part in _split(str(test).strip()))


@dataclass(frozen=True)
class Rule:
    rule_id: str
    when: dict[str, str]
    then: dict[str, Any]
    note: str = ""


@dataclass(frozen=True)
class DecisionTable:
    name: str
    inputs: list[str]
    outputs: list[str]
    rules: list[Rule]
    hit_policy: str = "FIRST"
    description: str = ""

    def evaluate(self, inputs: dict[str, Any]) -> Rule:
        """La primera regla que encaja (política *FIRST*). Falla si falta una entrada o si no
        encaja ninguna (toda tabla termina con una regla por defecto)."""
        missing = [name for name in self.inputs if name not in inputs]
        if missing:
            raise TableError(f"table {self.name}: missing inputs {', '.join(missing)}")
        for rule in self.rules:
            if all(matches(test, inputs[name]) for name, test in rule.when.items()):
                return rule
        raise TableError(f"table {self.name}: no rule matches {inputs}")


@dataclass(frozen=True)
class DecisionTables:
    tables: dict[str, DecisionTable]
    path: Path
    sha256: str
    version: int = 1
    notes: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, name: str) -> DecisionTable:
        return self.tables[name]


def _rule(table: str, raw: dict[str, Any], inputs: list[str], outputs: list[str]) -> Rule:
    rule_id = str(raw.get("id") or "")
    if not rule_id:
        raise TableError(f"table {table}: a rule has no id")
    when = {str(k): v for k, v in (raw.get("when") or {}).items()}
    then = dict(raw.get("then") or {})
    unknown = sorted(set(when) - set(inputs))
    if unknown:
        raise TableError(f"table {table}, rule {rule_id}: unknown inputs {', '.join(unknown)}")
    if sorted(then) != sorted(outputs):
        raise TableError(f"table {table}, rule {rule_id}: outputs must be {', '.join(outputs)}")
    for test in when.values():
        check_cell(test if not isinstance(test, bool | int | float) else str(test).lower())
    return Rule(rule_id, when, then, str(raw.get("note") or ""))


def load_tables(path: Path = DEFAULT_TABLE) -> DecisionTables:
    data = path.read_bytes()
    raw = yaml.safe_load(data)
    tables: dict[str, DecisionTable] = {}
    seen_ids: set[str] = set()
    for name, spec in (raw.get("tables") or {}).items():
        policy = str(spec.get("hit_policy", "FIRST"))
        if policy not in HIT_POLICIES:
            raise TableError(f"table {name}: hit policy {policy!r} is not supported")
        inputs = [str(i) for i in spec["inputs"]]
        outputs = [str(o) for o in spec["outputs"]]
        rules = [_rule(name, r, inputs, outputs) for r in spec["rules"]]
        for rule in rules:
            if rule.rule_id in seen_ids:
                raise TableError(f"duplicated rule id {rule.rule_id}")
            seen_ids.add(rule.rule_id)
        if rules and rules[-1].when:
            raise TableError(f"table {name}: the last rule must be the default (no conditions)")
        tables[name] = DecisionTable(
            name, inputs, outputs, rules, policy, str(spec.get("description") or "")
        )
    return DecisionTables(
        tables, path, hashlib.sha256(data).hexdigest(), int(raw.get("version", 1))
    )
