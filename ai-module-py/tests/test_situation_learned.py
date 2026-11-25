"""Monitor de situación con las tablas aprendidas congeladas (E7b), el camino por defecto."""

from pathlib import Path

import pytest

from ai_module.situation import freeze
from ai_module.situation.export_tables import build_frozen
from ai_module.situation.facets import HANDWRITTEN, LEARNED, LearnedFacets
from ai_module.situation.monitor import SituationMonitor
from ai_module.situation.replay import replay
from poc_contracts.enums import EventType
from poc_contracts.payloads import PAYLOAD_MODELS

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "runs" / "demo" / "events.jsonl"


def changes(tables: str, path: Path = DEMO) -> list[tuple[str, str, str]]:
    out = []
    for _, p in replay(path, tables):
        PAYLOAD_MODELS[EventType.INCIDENT_UPDATED].model_validate(p)  # cumple el contrato
        if p["change"] in ("opened", "renamed", "closed"):
            out.append((p["incident_id"], p["change"], p["kind"]))
    return out


def test_the_monitor_checks_the_freeze_and_refuses_to_start_if_a_frozen_file_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert freeze.changed_files() == []
    LearnedFacets()  # arranca
    monkeypatch.setattr(freeze, "changed_files", lambda: ["ai-module-py/.../tables_learned.yaml"])
    with pytest.raises(freeze.FreezeError, match="tables_learned"):
        LearnedFacets()
    SituationMonitor(tables=HANDWRITTEN)  # la alternativa a mano no está congelada


def test_the_situation_rule_runs_with_the_margin_of_the_freeze_file() -> None:
    """El fichero congelado (`situation_rule.py`) dice 1,0 y la evaluación de la E7b usó 0,5."""
    assert LearnedFacets().margin_k == 0.5 == freeze.margin_k()


def test_demo_with_the_learned_tables_gives_the_three_incidents_like_with_the_hand_ones() -> None:
    expected = [
        ("inc-0001", "opened", "WIND"), ("inc-0001", "closed", "WIND"),
        ("inc-0002", "opened", "GPS_SPOOFING"), ("inc-0002", "closed", "GPS_SPOOFING"),
        ("inc-0003", "opened", "LINK_LOSS"), ("inc-0003", "renamed", "HIJACK"),
        ("inc-0003", "closed", "HIJACK"),
    ]  # fmt: skip
    assert changes(LEARNED) == expected == changes(HANDWRITTEN)


def test_demo_opens_within_a_few_seconds_of_the_hand_tables() -> None:
    def opens(tables: str) -> dict[str, float]:
        return {
            p["kind"]: t for t, p in replay(DEMO, tables) if p["change"] in ("opened", "renamed")
        }

    learned, hand = opens(LEARNED), opens(HANDWRITTEN)
    assert learned.keys() == hand.keys()
    assert all(abs(learned[k] - hand[k]) <= 4 for k in learned)


def test_nominal_gives_no_incident_with_the_learned_tables() -> None:
    assert replay(ROOT / "runs" / "nominal" / "events.jsonl", LEARNED) == []


def test_the_evidence_of_a_learned_row_is_readable_and_every_row_is_in_the_web_rules() -> None:
    frozen = build_frozen()["facets"]
    for _, update in replay(DEMO, LEARNED):
        for item in update["evidence"]:
            if item["facet"] == "drone.cause":  # la tabla del tipo de incidente (provisional)
                continue
            assert item["rule_id"] in {r["id"] for r in frozen[item["facet"]]["rules"]}
            for c in item["conditions"]:
                assert c["op"] in (">=", "<=", ">", "<", "==", "!=")
