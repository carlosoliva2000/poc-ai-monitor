"""E6: el evaluador de la tabla de decisión (subconjunto de unary tests de FEEL, política FIRST)."""

from pathlib import Path

import pytest

from ai_module.decision.table import TableError, check_cell, load_tables, matches


@pytest.mark.parametrize(
    ("test", "value", "expected"),
    [
        ("-", None, True),
        ("-", "x", True),
        ("true", True, True),
        ("true", 1, False),
        ("false", False, True),
        ("null", None, True),
        ("null", False, False),
        ('"WIND"', "WIND", True),
        ('"WIND"', "HIJACK", False),
        ('"gps","radar"', "radar", True),
        ('"gps","radar"', "link", False),
        ("> 30", 30.1, True),
        ("> 30", 30, False),
        (">= 30", 30, True),
        ("< 0.5", 0.49, True),
        ("<= 2", 2, True),
        ("> 30", None, False),
        ("> 30", True, False),  # un booleano no es un número
        ("[10..25]", 10, True),
        ("[10..25]", 25, True),
        ("(10..25)", 10, False),
        ("[10..25)", 25, False),
        ("30", 30.0, True),
        ("not(false)", None, True),
        ("not(false)", True, True),
        ("not(false)", False, False),
        ('not("moving_away")', "steady", True),
        ('not("moving_away")', "moving_away", False),
        (True, True, True),  # YAML sin comillas
        (0, 0, True),
    ],
)
def test_unary_tests(test: object, value: object, expected: bool) -> None:
    assert matches(test, value) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize("cell", ["x == 1", "foo", "> abc", "[1..]", "len(x)"])
def test_python_or_unknown_cells_are_rejected(cell: str) -> None:
    with pytest.raises(TableError):
        check_cell(cell)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "t.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_first_hit_policy_and_default(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
tables:
  t:
    inputs: [a, b]
    outputs: [o]
    rules:
      - {id: R1, when: {a: '> 1'}, then: {o: one}}
      - {id: R2, when: {a: '> 0', b: 'true'}, then: {o: two}}
      - {id: R3, when: {}, then: {o: default}}
""",
    )
    table = load_tables(path)["t"]
    assert table.evaluate({"a": 2, "b": True}).rule_id == "R1"  # la primera, aunque R2 también
    assert table.evaluate({"a": 0.5, "b": True}).rule_id == "R2"
    assert table.evaluate({"a": 0, "b": False}).rule_id == "R3"
    with pytest.raises(TableError, match="missing inputs"):
        table.evaluate({"a": 1})


DEFAULT = "\n      - {id: R2, when: {}, then: {o: y}}"


DEFAULT = "\n      - {id: R2, when: {}, then: {o: y}}"


@pytest.mark.parametrize(
    ("rules", "error"),
    [
        ("- {id: R1, when: {zz: 'true'}, then: {o: x}}" + DEFAULT, "unknown inputs"),
        ("- {id: R1, when: {a: 'true'}, then: {o: x}}", "last rule must be the default"),
        ("- {id: R1, when: {a: 'a + 1'}, then: {o: x}}" + DEFAULT, "unary test"),
        ("- {id: R1, when: {}, then: {p: x}}", "outputs must be"),
        (
            "- {id: R1, when: {a: 'true'}, then: {o: x}}\n      - {id: R1, when: {}, then: {o: y}}",
            "duplicated",
        ),
    ],
)
def test_malformed_tables_fail(tmp_path: Path, rules: str, error: str) -> None:
    path = _write(
        tmp_path, f"tables:\n  t:\n    inputs: [a]\n    outputs: [o]\n    rules:\n      {rules}\n"
    )
    with pytest.raises(TableError, match=error):
        load_tables(path)


def test_the_hash_is_the_sha256_of_the_file(tmp_path: Path) -> None:
    import hashlib

    tables = load_tables()
    assert tables.sha256 == hashlib.sha256(tables.path.read_bytes()).hexdigest()
