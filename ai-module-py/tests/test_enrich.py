"""E6: el enriquecimiento del híbrido (`enrich.py`): la tabla decide y el LLM añade después una
frase que el módulo comprueba antes de publicar (`AlertEnriched`)."""

import json
from pathlib import Path
from typing import Any

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    detection_event,
    make_runtime,
    reset_ids,
    run,
)
from test_table_engine import IDS, events, metrics

from ai_module.agent.assets import Assets
from ai_module.agent.profiles import load_profile
from ai_module.detector import Detector, load_config
from ai_module.enrich import Enricher, check_answer
from ai_module.module import AiModule
from ai_module.monitor import Monitor
from ai_module.report_facts import anomalies_for_llm, build_facts
from ai_module.text_checks import enrichment_problems
from poc_contracts.enums import EventType

WIND_TEXT = (
    "The northerly wind at 11.0 m/s is pushing the drone the way it drifts; GPS and radar agree, "
    "so this is wind and not a fault."
)


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def setup(tmp_path: Path, *answers: str, engine: str = "hybrid", track: dict | None = None):
    llm = FakeLlm(Script(*answers) if answers else Script("{}"))
    platform = FakePlatform({"get_track_metrics": track or metrics(), "get_events": events})
    profile = load_profile(engine)
    rt, published = make_runtime(tmp_path, llm, platform, Assets(profile.assets_dir, profile))
    for event_id in IDS:
        rt.index._times[event_id] = 1.0
    rt.clock.observe(20.0)
    monitor = Monitor(rt)
    enricher = Enricher(rt)
    monitor.enrich_hook = enricher.submit
    return rt, published, monitor, enricher, llm


def answer(text: str = WIND_TEXT, hypothesis: Any = None) -> str:
    return json.dumps({"text": text, "hypothesis": hypothesis})


def drain(enricher: Enricher) -> None:
    while not enricher.queue.empty():
        run(enricher.enrich(enricher.queue.get_nowait()))


def enriched(published: list) -> list:
    return [e for e in published if e.type == EventType.ALERT_ENRICHED]


def enrich_record(rt: Any) -> dict[str, Any]:
    [record] = [r for r in rt.trace.records if r["agent"] == "enrich"]
    return record


def test_the_table_alert_gets_a_checked_interpretation(tmp_path: Path) -> None:
    rt, published, monitor, enricher, llm = setup(tmp_path, answer())
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    [alert] = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert llm.requests == []  # la alerta no espera al LLM
    drain(enricher)
    [event] = enriched(published)
    p = event.payload
    assert event.source == "ai-enricher" and event.causation_id == alert.payload["alert_id"]
    assert p["text"] == WIND_TEXT and p["hypothesis"] is None
    assert (p["decided_by"], p["alert_status"], p["as_of_sim_time"]) == ("llm", "open", 20.0)
    [request] = llm.requests
    assert request["tools"] == [] and request["sampling"]["temperature"] == 0
    system, user = (m["content"] for m in request["messages"])
    assert "Do not change them" in system and "wind from 350.0°" in user
    assert "gps_radar" not in user and 'Leave "hypothesis": null.' in user
    record = enrich_record(rt)["enrich"]
    assert record["published"] == event.event_id and record["rule_id"] == "C17"
    assert record["enrich_latency_wall_s"] >= 0 and record["enrich_latency_sim_s"] == 0.0
    assert enricher.texts == {alert.payload["alert_id"]: WIND_TEXT}
    # la alerta de la tabla no cambia
    assert alert.payload["cause"] == "WIND" and alert.payload["decided_by"] == "table"


def test_a_text_that_does_not_pass_the_checks_is_not_published(tmp_path: Path) -> None:
    bad = "The gps_radar_disagreed flag is false and the drone is 57 m off at T+09:59 (gps-000999)."
    rt, published, monitor, enricher, _ = setup(tmp_path, answer(bad))
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    drain(enricher)
    assert enriched(published) == []
    reasons = " | ".join(enrich_record(rt)["enrich"]["rejected"])
    for part in ("internal names", "figures not in the facts: 57 m", "times not in the facts",
                 "event ids not seen: gps-000999"):  # fmt: skip
        assert part in reasons, part
    assert enricher.texts == {}


@pytest.mark.parametrize("raw", ["not json at all", '```json\n{"hypothesis": null}\n```', "[1, 2]"])
def test_an_answer_that_is_not_the_json_is_rejected(tmp_path: Path, raw: str) -> None:
    rt, published, monitor, enricher, _ = setup(tmp_path, raw)
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    drain(enricher)
    assert enriched(published) == []
    assert enrich_record(rt)["enrich"]["rejected"] == [
        "the answer is not a JSON object with a text"
    ]


def test_a_json_in_a_code_block_is_accepted(tmp_path: Path) -> None:
    _, published, monitor, enricher, _ = setup(tmp_path, f"```json\n{answer()}\n```")
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    drain(enricher)
    assert len(enriched(published)) == 1


def test_a_hypothesis_is_only_allowed_on_unknown(tmp_path: Path) -> None:
    hyp = {"cause": "GPS_SPOOFING", "confidence": 0.3, "evidence_event_ids": ["rad-000002"]}
    rt, published, monitor, enricher, _ = setup(tmp_path, answer(hypothesis=hyp))
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    drain(enricher)
    assert enriched(published) == []
    assert "only allowed when the cause is UNKNOWN" in enrich_record(rt)["enrich"]["rejected"][-1]


def unknown_track() -> dict[str, Any]:
    """Una desviación que no encaja con nada: sin viento notable, GPS y radar de acuerdo, rumbo
    hacia el waypoint (la tabla dice UNKNOWN, fila por defecto)."""
    wind = {**metrics()["wind"], "notable": False, "with_drift": False, "mean_speed_mps": 2.0}
    return metrics(wind=wind, bearing_to_next_waypoint_deg=95.0)


def test_unknown_can_carry_a_hypothesis_with_seen_evidence(tmp_path: Path) -> None:
    text = "The drone left the route while GPS and radar agree and the wind is light."
    hyp = {"cause": "HIJACK", "confidence": 0.3, "evidence_event_ids": ["gps-000003"]}
    rt, published, monitor, enricher, llm = setup(
        tmp_path, answer(text, hyp), track=unknown_track()
    )
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    [alert] = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert alert.payload["cause"] == "UNKNOWN"
    drain(enricher)
    [event] = enriched(published)
    assert event.payload["hypothesis"] == hyp
    user = llm.requests[0]["messages"][1]["content"]
    assert "Event ids you may cite:" in user and "gps-000003" in user


def test_a_hypothesis_with_unseen_evidence_or_too_confident_is_rejected(tmp_path: Path) -> None:
    for hyp, reason in (
        ({"cause": "HIJACK", "confidence": 0.3, "evidence_event_ids": ["lnk-9999"]}, "not seen"),
        ({"cause": "HIJACK", "confidence": 0.7, "evidence_event_ids": ["gps-000003"]}, "0.4"),
        ({"cause": "UNKNOWN", "confidence": 0.2, "evidence_event_ids": ["gps-000003"]}, "UNKNOWN"),
    ):
        reset_ids()
        folder = tmp_path / reason.replace(" ", "-")
        rt, published, monitor, enricher, _ = setup(
            folder, answer("The drone left the route.", hyp), track=unknown_track()
        )
        run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
        drain(enricher)
        assert enriched(published) == [], reason
        assert reason in " ".join(enrich_record(rt)["enrich"]["rejected"]), reason


def test_an_alert_closed_before_the_call_is_skipped(tmp_path: Path) -> None:
    rt, published, monitor, enricher, llm = setup(tmp_path, answer())
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    run(monitor.handle_batch([detection_event("cleared", "det-0001", 20.0)]))
    assert any(e.type == EventType.ALERT_CLOSED for e in published)
    drain(enricher)
    assert enriched(published) == [] and llm.requests == []  # sin llamada al LLM
    assert enrich_record(rt)["enrich"]["skipped"] == "closed"


def test_the_module_only_enriches_with_hybrid(tmp_path: Path) -> None:
    for engine, expected in (("table", False), ("hybrid", True), ("actual", False)):
        profile = load_profile(engine)
        rt, _ = make_runtime(tmp_path, FakeLlm(Script("{}")), FakePlatform(),
                             Assets(profile.assets_dir, profile))  # fmt: skip
        module = AiModule(rt, Detector(load_config()))
        assert (module.enricher is not None) is expected, engine
        assert (module.monitor.enrich_hook is not None) is expected, engine
        if expected:
            assert module.report.enricher is module.enricher


def test_profile_json_only_lists_the_enrich_agent_with_hybrid() -> None:
    for engine, expected in (("actual", False), ("table", False), ("hybrid", True)):
        profile = load_profile(engine)
        info = Assets(profile.assets_dir, profile).profile_info()
        assert ("enrich" in info["agents"]) is expected, engine


def test_the_report_gets_the_published_interpretation(tmp_path: Path) -> None:
    rt, _, monitor, enricher, _ = setup(tmp_path, answer())
    run(monitor.handle_batch([detection_event("raised", "det-0001", 20.0)]))
    drain(enricher)
    text = anomalies_for_llm(build_facts(rt.state), interpretations=enricher.texts)
    assert f'Interpretation (written by a language model, checked): "{WIND_TEXT}"' in text
    assert "Interpretation" not in anomalies_for_llm(build_facts(rt.state))


def test_wait_idle_has_a_ceiling(tmp_path: Path) -> None:
    rt, _, _, enricher, _ = setup(tmp_path)
    assert run(enricher.wait_idle(0.01)) is True  # cola vacía
    enricher.submit({"alert_id": "ai-0001", "as_of": 20.0, "args": {"cause": "WIND"}, "rows": {}})
    assert run(enricher.wait_idle(0.01)) is False  # nadie la vacía: se rinde al tope


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("", "empty text"),
        ("The cause is GPS_SPOOFING.", "names in capitals: GPS_SPOOFING"),
        ("It looks like LINK_ANOMALY.", "names in capitals: LINK_ANOMALY"),
        ("wind_notable is true", "internal names"),
        ("The value is: true", "bare booleans"),
        ("It is 12.5 m off.", "figures not in the facts: 12.5 m"),
        ("Since T+01:00.", "times not in the facts: T+01:00"),
        ("See met-0042.", "event ids not seen: met-0042"),
        ("x" * 401, "too long"),
    ],
)
def test_enrichment_text_checks(text: str, problem: str) -> None:
    problems = enrichment_problems(
        text, prompt="drift 11.0 m/s at T+00:20, met-0001", seen_ids=set()
    )
    assert any(problem in p for p in problems), problems


def test_a_text_with_only_known_figures_times_and_ids_passes() -> None:
    prompt = "wind 11.0 m/s, distance 35.0 m at T+00:20 (met-0001)"
    text = "The wind at 11.0 m/s moved the drone about 35 m from the route at T+00:20 (met-0001)."
    assert enrichment_problems(text, prompt=prompt, seen_ids=set()) == []
    assert check_answer(json.dumps({"text": text, "hypothesis": None}),
                        {"args": {"cause": "WIND"}}, prompt, set())[2] == []  # fmt: skip
