"""Monitor de situación con las tablas a mano y reglas de la web. Deterministas: no hay LLM ni
plataforma."""

from pathlib import Path

from ai_module.situation.replay import replay as replay_tables
from poc_contracts.enums import EventType
from poc_contracts.payloads import PAYLOAD_MODELS

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def replay(path: Path) -> list[tuple[float, dict]]:
    return replay_tables(path)


def transitions(path: Path) -> list[tuple[str, str, str, str]]:
    out = []
    for _, p in replay(path):
        PAYLOAD_MODELS[EventType.INCIDENT_UPDATED].model_validate(p)  # cumple el contrato
        out.append((p["incident_id"], p["change"], p["kind"], p["state"]))
    return out


def test_nominal_with_the_two_instructor_orders_gives_wind() -> None:
    # tools/video/gen_nominal_cmd.py: 19 m/s del norte de T+110 a T+150
    changes = [
        t[1:]
        for t in transitions(FIXTURES / "nominal_cmd" / "events.jsonl.gz")
        if t[1] != "evidence"
    ]
    assert [c for c in changes if c[0] != "severity"] == [
        ("opened", "WIND", "open"),
        ("state", "WIND", "recovering"),
        ("closed", "WIND", "closed"),
    ]


def test_the_web_rules_come_from_the_tables_the_monitor_runs() -> None:
    """La ventana «Rules» de la web lee `web/lib/situation-tables.json`, generado desde
    `tables.yaml`: si se cambia una tabla hay que volver a generarlo."""
    import json

    from ai_module.situation.export_tables import build

    saved = json.loads((ROOT / "web" / "lib" / "situation-tables.json").read_text(encoding="utf-8"))
    assert saved == build(), (
        "run: uv run --project ai-module-py python tools/video/export_tables.py"
    )
    facets = saved["facets"]
    assert set(facets) == {"gps.integrity", "link.availability", "environment.wind",
                           "drone.situation"}  # fmt: skip
    for table in facets.values():
        assert (
            table["hit_policy"] == "FIRST" and table["rules"][-1]["when"] == {}
        )  # la última, por defecto
    # toda fila que puede decidir una evidencia está en la tabla que enseña la web
    ids = {rule["id"] for table in facets.values() for rule in table["rules"]}
    for _, update in replay_tables(ROOT / "runs" / "demo" / "events.jsonl", "handwritten"):
        for item in update["evidence"]:
            assert item["rule_id"] in {r["id"] for r in facets[item["facet"]]["rules"]} <= ids
