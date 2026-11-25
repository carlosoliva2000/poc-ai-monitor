"""Las tablas aprendidas congeladas de la E7b: son las que se ejecutan y salen de la candidata."""

import hashlib
import json
from pathlib import Path

import yaml

from ai_module.decision.table import load_tables
from ai_module.situation.export_tables import build, build_frozen
from ai_module.situation.policy import HERE
from poc_contracts.states import FACETS

ROOT = Path(__file__).resolve().parents[2]
FROZEN = HERE / "tables_learned.yaml"
REVIEW = ROOT / "tools" / "training" / "review" / "e7b-v3"
CANDIDATE = ROOT / "tools" / "training" / "candidates" / "e7b-v3.yaml"
WEB = ROOT / "web" / "lib"


def test_every_learned_facet_has_its_frozen_table_and_the_situation_is_the_rule() -> None:
    tables = load_tables(FROZEN)
    expected = {f.replace(".", "_") for f in FACETS if f != "drone.situation"}
    assert set(tables.tables) == expected  # la situación es la regla, no una tabla aprendida
    for table in tables.tables.values():
        assert (
            table.hit_policy == "FIRST" and table.rules[-1].when == {}
        )  # termina en el por defecto
        assert "probability" in table.outputs and "confidence" in table.outputs
    assert set(load_tables(HERE / "situation_rule.yaml").tables) == {"drone_situation_rule"}


def test_the_frozen_tables_are_the_candidate_minus_the_rejected_rows() -> None:
    """Se puede restaurar: la tabla congelada es la candidata sin las filas de `rejected.yaml`."""
    candidate = yaml.safe_load(CANDIDATE.read_text(encoding="utf-8"))["tables"]
    unreviewed = yaml.safe_load((REVIEW / "candidate-unreviewed.yaml").read_text(encoding="utf-8"))
    assert unreviewed["tables"] == candidate  # la copia sin revisar es la candidata
    rejected = yaml.safe_load((REVIEW / "rejected.yaml").read_text(encoding="utf-8"))["rows"]
    assert {r["id"] for r in rejected} == {"LQ-03", "BE-06", "DM-10"}
    frozen = yaml.safe_load(FROZEN.read_text(encoding="utf-8"))["tables"]
    for row in rejected:  # completas: condiciones, estado, probabilidad, soporte y aciertos
        assert (
            row["when"] and row["then"]["probability"] < 0.1 and row["validation"]["instants"] > 0
        )
        assert row["reason"] and "effect_in_validation" in row
        assert row["id"] not in {r["id"] for r in frozen[row["table"]]["rules"]}
        original = next(r for r in candidate[row["table"]]["rules"] if r["id"] == row["id"])
        assert original["when"] == row["when"] and original["then"] == row["then"]
    drop = {r["id"] for r in rejected}
    for name, table in frozen.items():
        kept = [r for r in candidate[name]["rules"] if r["id"] not in drop]
        assert [r["id"] for r in table["rules"]] == [r["id"] for r in kept]
        assert table["rules"] == kept


def test_the_freeze_file_matches_the_files_that_run() -> None:
    freeze = json.loads((HERE / "tables_freeze.json").read_text(encoding="utf-8"))
    assert freeze["dataset"] == "e7b-v3" and freeze["margin_k"] == 0.5
    for name, digest in freeze["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert "ai-module-py/src/ai_module/situation/tables_learned.yaml" in freeze["files"]


def test_the_web_rules_of_the_frozen_tables_come_from_the_tables_that_run() -> None:
    """`web/lib/situation-tables-frozen.json` no se desincroniza (se regenera con
    `uv run --project ai-module-py python tools/training/export_frozen.py`)."""
    on_disk = json.loads((WEB / "situation-tables-frozen.json").read_text(encoding="utf-8"))
    assert on_disk == build_frozen()
    assert set(on_disk["facets"]) == set(FACETS)
    assert build()["facets"]  # y las de a mano siguen exportándose igual
