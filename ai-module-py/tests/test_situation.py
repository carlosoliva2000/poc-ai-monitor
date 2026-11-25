"""Monitor de situación con las tablas a mano del vídeo (alternativa `handwritten`) y textos
preparados. Deterministas: no hay LLM ni plataforma."""

import asyncio
import subprocess
import sys
from pathlib import Path

from ai_module.ids import IdAllocator
from ai_module.outbox import EventFactory
from ai_module.situation.replay import replay as replay_tables
from ai_module.situation.scripted import Script, ScriptedAssistant, load_texts, normalize
from poc_contracts.enums import EventType
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import PAYLOAD_MODELS

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def replay(path: Path) -> list[tuple[float, dict]]:
    """Estas pruebas son del vídeo (tablas a mano, instantes del guion): las tablas aprendidas
    congeladas se prueban en `test_situation_learned.py`."""
    return replay_tables(path, "handwritten")


def transitions(path: Path) -> list[tuple[str, str, str, str]]:
    out = []
    for _, p in replay(path):
        PAYLOAD_MODELS[EventType.INCIDENT_UPDATED].model_validate(p)  # cumple el contrato
        out.append((p["incident_id"], p["change"], p["kind"], p["state"]))
    return out


def test_demo_gives_the_three_incidents_with_their_transitions() -> None:
    changes = [
        t for t in transitions(ROOT / "runs" / "demo" / "events.jsonl") if t[1] != "evidence"
    ]
    assert changes == [
        ("inc-0001", "opened", "WIND", "open"),
        ("inc-0001", "state", "WIND", "recovering"),
        ("inc-0001", "closed", "WIND", "closed"),
        ("inc-0002", "opened", "GPS_SPOOFING", "open"),
        ("inc-0002", "state", "GPS_SPOOFING", "recovering"),
        ("inc-0002", "closed", "GPS_SPOOFING", "closed"),
        ("inc-0003", "opened", "LINK_LOSS", "open"),
        ("inc-0003", "renamed", "HIJACK", "open"),  # mismo incidente, otro nombre
        ("inc-0003", "state", "HIJACK", "recovering"),
        ("inc-0003", "closed", "HIJACK", "closed"),
    ]


def test_evidence_is_refreshed_when_a_facet_changes_state() -> None:
    """El engaño empieza con el dron en ruta; la tarjeta tiene que reflejar la desviación que el
    radar ve al pasar de 25 m (sin una revisión por segundo)."""
    updates = [p for _, p in replay(ROOT / "runs" / "demo" / "events.jsonl")]
    spoof = [p for p in updates if p["incident_id"] == "inc-0002"]
    assert [p["revision"] for p in spoof] == list(range(1, len(spoof) + 1))
    refreshed = next(p for p in spoof if p["change"] == "evidence" and p["state"] == "open")
    situation = next(e for e in refreshed["evidence"] if e["facet"] == "drone.situation")
    assert situation["state"] == "deviated"
    (condition,) = situation["conditions"]
    assert condition["feature"] == "route_dev_m" and 25.0 < condition["value"] < 30.0
    assert len(spoof) <= 8  # no una revisión por segundo
    # una revisión de evidencias no cambia el incidente (su interpretación no se repite)
    opened = spoof[0]
    for key in ("kind", "name", "state", "severity", "opened_at"):
        assert refreshed[key] == opened[key]


def test_the_hijack_card_follows_the_drone_while_it_flies_away() -> None:
    """El secuestro sigue `deviated` mientras el dron pasa de 130 m a unos 600 m: la tarjeta tiene
    que enseñar la distancia de ahora (una revisión cuando se duplica, no cada segundo)."""
    hijack = [p for _, p in replay(ROOT / "runs" / "demo" / "events.jsonl")
              if p["incident_id"] == "inc-0003" and p["state"] == "open"]  # fmt: skip

    def radar(p: dict) -> float:
        cause = next(e for e in p["evidence"] if e["facet"] == "drone.cause")
        return next(c["value"] for c in cause["conditions"] if c["feature"] == "radar_route_dev_m")

    distances = [radar(p) for p in hijack if p["kind"] == "HIJACK"]
    assert distances[0] < 150 and distances[-1] > 400 and distances[-1] > 3 * distances[0]
    assert all(b >= 1.9 * a for a, b in zip(distances, distances[1:], strict=False))
    assert len(distances) <= 4


def test_spoofing_is_seen_before_the_drone_leaves_the_route() -> None:
    opened = next(p for _, p in replay(ROOT / "runs" / "demo" / "events.jsonl")
                  if p["kind"] == "GPS_SPOOFING")  # fmt: skip
    situation = next(e for e in opened["evidence"] if e["facet"] == "drone.situation")
    assert situation["state"] == "on_route"
    integrity = next(e for e in opened["evidence"] if e["facet"] == "gps.integrity")
    assert (integrity["state"], integrity["rule_id"]) == ("spoofed", "GI-02")


def test_nominal_gives_no_incident() -> None:
    assert transitions(ROOT / "runs" / "nominal" / "events.jsonl") == []


def test_nominal_with_the_two_instructor_orders_gives_wind() -> None:
    # tools/video/gen_nominal_cmd.py: 19 m/s del norte de T+110 a T+150
    changes = [
        t[1:]
        for t in transitions(FIXTURES / "nominal_cmd" / "events.jsonl.gz")
        if t[1] != "evidence"
    ]
    assert changes == [
        ("opened", "WIND", "open"),
        ("state", "WIND", "recovering"),
        ("closed", "WIND", "closed"),
    ]


def test_instructor_script_gives_its_two_proposals() -> None:
    script = Script()
    wind = script.instructor("put a strong wind from the North, 19 m/s, until I cancel it!", None)
    assert wind.proposal == {
        "command": "set_wind",
        "params": {"from_deg": 0.0, "speed_mps": 19.0, "ramp_s": 10.0, "duration_s": None},
        "defaults_used": ["ramp_s"],
    }
    active = {"from_deg": 0.0, "speed_mps": 19.0, "remaining_s": None}
    cancel = script.instructor("Remove the wind.", active)
    assert cancel.proposal == {"command": "cancel_wind", "params": None, "defaults_used": []}
    assert script.instructor("Remove the wind", None).proposal is None  # sin viento activo
    assert script.instructor("Make it rain", active).proposal is None
    for item in load_texts()["chat"]["instructor"]:  # la propuesta cumple el contrato
        PAYLOAD_MODELS[EventType.AGENT_REPLY].model_validate(
            {
                "conversation_id": "instructor",
                "reply_to": "ops-0001",
                "text": "t",
                "tool_calls": [],
                "proposal": item["proposal"],
            }  # fmt: skip
        )


def test_monitor_chat_and_report_texts() -> None:
    script = Script()
    texts = load_texts()
    assert normalize("  Why do you think the drone is being HIJACKED?? ") == normalize(
        texts["chat"]["monitor"][0]["question"]
    )
    assert "radar" in script.monitor("why do you think the drone is being hijacked").text
    assert script.monitor("What is the battery level?").text == texts["chat"]["fallback"]
    assert script.report("demo") is not None and script.report("nominal") is None
    for kind in ("WIND", "GPS_SPOOFING", "LINK_LOSS", "HIJACK"):
        for state in ("open", "recovering", "closed"):
            assert script.enrichment(kind, state)


def test_scripted_assistant_publishes_like_the_llm() -> None:
    """Chat: actividad, trozos, respuesta y fin; incidente: su interpretación tras el retraso."""
    texts = {**load_texts(), "delay_s": [0.0, 0.0], "thinking_s": 0.0, "report_delay_s": 0.0}
    texts["chunk"] = {"words": 3, "interval_s": 0.0}
    published: list[EventDraft] = []
    sent: list[EventDraft] = []

    async def publish(draft: EventDraft) -> None:
        published.append(draft)

    async def scenario() -> None:
        factory = EventFactory(IdAllocator())
        assistant = ScriptedAssistant(factory, publish, lambda: 390.0, Script(texts))
        question = "Why do you think the drone is being hijacked?"
        assistant.on_operator_message("ops-0001", {"conversation_id": "monitor", "text": question})
        update = next(p for _, p in replay(ROOT / "runs" / "demo" / "events.jsonl"))
        draft = factory.make(EventType.INCIDENT_UPDATED, update, sim_time=138.0)
        sent.append(draft)
        assistant.on_incident(draft)
        refreshed = factory.make(
            EventType.INCIDENT_UPDATED,
            {**update, "revision": 2, "change": "evidence"},
            sim_time=140.0,
        )
        assistant.on_incident(refreshed)  # change evidence: sin interpretación nueva
        assistant.on_finished("demo", "run-1", 3)
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    kinds = [d.type.value for d in published]
    assert kinds[0] == "AgentActivity" and "AgentReplyChunk" in kinds
    reply = next(d for d in published if d.type == EventType.AGENT_REPLY)
    chunks = "".join(d.payload["delta"] for d in published if d.type == EventType.AGENT_REPLY_CHUNK)
    assert chunks == reply.payload["text"] and reply.payload["tool_calls"] == []
    enriched = next(d for d in published if d.type == EventType.INCIDENT_ENRICHED)
    assert enriched.causation_id == sent[0].event_id
    assert enriched.payload["state"] == "open" and "17 m/s" in enriched.payload["text"]
    assert sum(d.type == EventType.INCIDENT_ENRICHED for d in published) == 1
    assert any(d.type == EventType.REPORT_GENERATED for d in published)


def test_the_package_does_not_import_the_frozen_module() -> None:
    code = (
        "import sys, ai_module.situation.__main__, ai_module.situation.replay\n"
        "frozen = ['module', 'monitor', 'detector', 'instructor', 'runtime', 'agent', 'chat',"
        " 'enrich', 'decision.decider', 'decision.features']\n"
        "print([f for f in frozen if 'ai_module.' + f in sys.modules])\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


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
                           "drone.situation", "drone.cause"}  # fmt: skip
    for table in facets.values():
        assert (
            table["hit_policy"] == "FIRST" and table["rules"][-1]["when"] == {}
        )  # la última, por defecto
    # toda fila que puede decidir una evidencia está en la tabla que enseña la web
    ids = {rule["id"] for table in facets.values() for rule in table["rules"]}
    for _, update in replay(ROOT / "runs" / "demo" / "events.jsonl"):
        for item in update["evidence"]:
            assert item["rule_id"] in {r["id"] for r in facets[item["facet"]]["rules"]} <= ids
