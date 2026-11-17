"""E6: la evaluación de una ejecución del híbrido (`AlertEnriched` y trazas `enrich`)."""

from pathlib import Path

from test_evaluate import Builder, trace_record

from ai_module.evaluate import evaluate, render_markdown, to_json

WIND_CHECKS = {"gps_alert_recent": False, "gps_radar_disagreed": False, "wind_notable": True,
               "wind_with_drift": True, "link_checked": True, "link_anomalous": False}  # fmt: skip


def hybrid_run(tmp_path: Path, text: str) -> Builder:
    b = Builder(tmp_path, "wind")
    r = b.raised("det-0001", 106.0, "ROUTE_DEVIATION")
    b.alert("ai-0002", 106.0, "WIND", r, ["det-0001"], checks=WIND_CHECKS)
    payload = {"alert_id": "ai-0002", "text": text, "hypothesis": None, "decided_by": "llm",
               "as_of_sim_time": 106.0, "alert_status": "open"}  # fmt: skip
    b.ev("AlertEnriched", 130.0, payload, "ai-enricher", id="ai-0003", causation="ai-0002")
    b.trace += [
        trace_record("enrich", invocation_id="inv-2", causation_ids=["ai-0002"],
                     enrich={"alert_id": "ai-0002", "rule_id": "C17", "published": "ai-0003",
                             "enrich_latency_wall_s": 1.5, "enrich_latency_sim_s": 24.0}),
        trace_record("enrich", invocation_id="inv-3", causation_ids=["ai-0004"],
                     enrich={"alert_id": "ai-0004", "rule_id": "C20",
                             "rejected": ["figures not in the facts: 57 m"]}),
        trace_record("enrich", invocation_id="inv-4", causation_ids=["ai-0005"],
                     enrich={"alert_id": "ai-0005", "rule_id": "C17", "skipped": "closed"}),
        trace_record("report", invocation_id="inv-5",
                     enrich={"waited_s": 2.1, "complete": True}),
    ]  # fmt: skip
    return b


def test_the_enrichment_is_counted_apart_and_does_not_change_the_verdicts(tmp_path: Path) -> None:
    ev = evaluate(hybrid_run(tmp_path, "The wind pushes the drone the way it drifts.").write())
    assert [r.verdict for r in ev.results] == ["✅"]
    assert ev.unanswered == [] and not ev.stray_alerts  # no es una respuesta ni una alerta
    e = ev.enrichment
    assert (e["alerts"], e["published"], len(e["rejected"]), len(e["skipped"])) == (3, 1, 1, 1)
    assert e["latency_wall_s"] == {"median": 1.5, "max": 1.5, "n": 1}
    md = render_markdown(ev)
    assert "## Enriquecimiento" in md and "❌ ai-0004 (C20): figures not in the facts: 57 m" in md
    assert "El informe esperó 2.1 s a la cola: completa" in md
    assert to_json(ev)["enrichment"]["published"] == 1


def test_an_interpretation_against_its_alert_checks_is_a_contradiction(tmp_path: Path) -> None:
    ev = evaluate(hybrid_run(tmp_path, "The wind blows against the drift.").write())
    [c] = ev.contradictions
    assert (c.alert_id, c.field) == ("ai-0002", "interpretación (LLM)")


def test_a_run_without_enrichment_has_no_section(tmp_path: Path) -> None:
    b = Builder(tmp_path, "wind")
    r = b.raised("det-0001", 106.0, "ROUTE_DEVIATION")
    b.alert("ai-0002", 106.0, "WIND", r, ["det-0001"], checks=WIND_CHECKS)
    ev = evaluate(b.write())
    assert ev.enrichment is None and "enrichment" not in to_json(ev)
    assert "Enriquecimiento" not in render_markdown(ev)
