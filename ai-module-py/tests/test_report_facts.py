"""Hechos del informe: anomalías por cadena, cronología, valoración y lectura del LLM."""

from agent_helpers import detection_event, reset_ids
from test_monitor_state import ack, alert, closed

from ai_module.monitor_state import MonitorState
from ai_module.report_facts import (
    MISSING,
    Narrative,
    anomalies_for_llm,
    assemble,
    assessment_facts,
    build_facts,
    figures_line,
    monitor_stats,
    parse_narrative,
    timeline_table,
)

SUMMARY = {
    "mission_id": "MSN", "duration_s": 200.0, "mission_completed": True,
    "completion_reason": "returned_to_base", "waypoints_planned": ["WP1", "WP2"],
    "waypoints_reached": [{"waypoint_id": "WP1", "sim_time": 66.0}],
}  # fmt: skip


def spoofing_state() -> MonitorState:
    """Una cadena (spoofing alta → recuperación media, cerrada) y una alerta de viento abierta."""
    reset_ids()
    state = MonitorState()
    state.apply(detection_event("raised", "det-0001", 20.0))
    state.apply(alert("ai-0002", ["det-0001"], cause="WIND", t=21.0))
    state.apply(detection_event("raised", "det-0003", 100.0, rule="SOURCE_DISCREPANCY"))
    state.apply(alert("ai-0004", ["det-0003"], cause="GPS_SPOOFING", t=101.0))
    state.apply(detection_event("raised", "det-0005", 130.0))
    second = alert("ai-0006", ["det-0005"], cause="GPS_SPOOFING", supersedes="ai-0004", t=131.0)
    second.payload["severity"] = "medium"
    state.apply(second)
    state.apply(detection_event("cleared", "det-0003", 140.0))
    state.apply(closed("ai-0006", t=150.0))
    return state


def test_each_chain_is_one_anomaly_with_the_first_alert_and_the_last_if_it_changes() -> None:
    state = spoofing_state()
    facts = build_facts(state)
    assert [a.label for a in facts.anomalies] == ["A1", "A2"]
    wind, spoofing = facts.anomalies
    assert (wind.first.cause, wind.closed_at, wind.delay_s) == ("WIND", None, 1.0)
    assert [a.alert_id for a in spoofing.chain] == ["ai-0004", "ai-0006"]
    assert [d.detection_id for d in spoofing.detections] == ["det-0003", "det-0005"]
    assert spoofing.detected_at == 100.0 and spoofing.delay_s == 1.0 and spoofing.closed_at == 150.0
    assert facts.labels == {"ai-0002": "A1", "ai-0004": "A2", "ai-0006": "A2"}
    text = assemble("demo", SUMMARY, state, facts, Narrative(seen={"A2": "Saltó 68 m."}))
    assert "### A2 · Spoofing del GPS (alta, confianza 0.8)" in text  # la primera alerta
    assert (
        "detección a T+01:40 (SOURCE_DISCREPANCY, ROUTE_DEVIATION), primera alerta a T+01:41"
        in text
    )
    assert "**Última alerta:** ai-0006 a T+02:11 (severidad alta → media; 2 alertas" in text
    assert "- **Qué se vio:** Saltó 68 m." in text
    assert (
        "- **Estado:** cerrada por el monitor a T+02:30" in text
        and "- **Estado:** ABIERTA al final." in text
    )
    assert "(abiertas al final: 1)" in text and "**Waypoints alcanzados:** 1 de 2" in text


def test_timeline_is_in_time_order_with_every_t_of_the_state() -> None:
    state = spoofing_state()
    table = timeline_table(state, build_facts(state), SUMMARY)
    rows = table.splitlines()[2:]
    times = [row.split("|")[1].strip() for row in rows]
    assert times == sorted(times)
    assert "| T+00:00 | Misión | Inicio de la misión MSN |" in table
    assert (
        "| T+01:41 | Monitor | Alerta ai-0004 (A2): Spoofing del GPS (alta, confianza 0.8) |"
        in table
    )
    assert (
        "sustituye a ai-0004" in table
        and "| T+02:30 | Monitor | Cierre de la alerta ai-0006 (A2)" in table
    )
    assert "det-0003 SOURCE_DISCREPANCY cerrada (duró 40 s; máximo 40,0 m)" in table
    assert "| T+03:20 | Misión | Fin de la misión: regreso a base |" in table


def test_detections_without_alert_are_listed() -> None:
    reset_ids()
    state = MonitorState()
    state.apply(detection_event("raised", "det-0001", 10.0))
    state.apply(ack("ai-0002", "det-0001", None))
    facts = build_facts(state)
    text = assemble("v", None, state, facts, Narrative())
    assert facts.anomalies == [] and [d.detection_id for d in facts.without_alert] == ["det-0001"]
    assert "El monitor no publicó ninguna alerta." in text and "## Detecciones sin alerta" in text
    assert "datos del vuelo no disponibles" in text and text.count(MISSING) == 3


def test_assessment_facts_carry_delays_fallbacks_rejections_and_aids() -> None:
    state = spoofing_state()
    records = [
        {"agent": "monitor", "duration_s": 12.4, "fallback": False, "deterministic": False,
         "published": [{"event_id": "ai-0002"}],
         "guardrail_rejections": [{"tool": "publish_alert", "errors": ["Falta  `ids`"]}]},
        {"agent": "monitor", "duration_s": 0.0, "fallback": False, "deterministic": True,
         "published": [], "guardrail_rejections": []},
        {"agent": "monitor", "duration_s": 30.0, "fallback": True, "deterministic": False,
         "published": [], "guardrail_rejections": []},
        {"agent": "chat-monitor", "duration_s": 1.0,
         "guardrail_rejections": [{"tool": "x", "errors": ["no"]}]},
    ]  # fmt: skip
    aids = {"tool_choice": "required", "coherence_guardrail": True, "require_checks": False}
    text = assessment_facts(build_facts(state), records, aids)
    assert "A1: la primera alerta llegó 1,0 s de simulación después de la detección" in text
    assert "tardó 12 s de reloj" in text and "Invocaciones del monitor con LLM: 2" in text
    assert "Número de fallbacks (el módulo respondió por el monitor porque no concluyó): 1" in text
    assert "rechazadas por los guardrails: 1." in text and "publish_alert 1" in text
    assert "Motivo: «Falta `ids`»" in text
    assert "tool_choice «required»" in text and "guardrail de coherencia" in text
    assert "comprobaciones (`checks`) obligatorias" not in text  # apagada


LLM_TEXT = """Aquí va el informe:

## Resumen
Dos anomalías.

## Qué se vio
### A1
Viento de 9 m/s.
Con deriva a favor.
**A2:** El GPS saltó 68 m.

## Cronología
(el LLM se la inventa: se ignora)

## Valoración del monitor
Aceptable, con reservas.

## Recomendaciones
1. Uno.
2. Dos.
"""


def test_parse_narrative_reads_the_four_parts_and_ignores_the_rest() -> None:
    n = parse_narrative(LLM_TEXT, ["A1", "A2"])
    assert n.summary == "Dos anomalías."
    assert n.seen == {"A1": "Viento de 9 m/s. Con deriva a favor.", "A2": "El GPS saltó 68 m."}
    assert n.assessment == "Aceptable, con reservas."
    assert n.recommendations == "1. Uno.\n2. Dos."
    assert "inventa" not in n.summary + n.assessment + n.recommendations


def test_parse_narrative_tolerates_titles_and_missing_parts() -> None:
    n = parse_narrative("# Valoración del monitor\nBien.\n## Resumen:\nR", ["A1"])
    assert (n.summary, n.assessment, n.recommendations, n.seen) == ("R", "Bien.", "", {})
    assert not n.empty and parse_narrative("texto suelto sin títulos", ["A1"]).empty


def test_anomalies_for_llm_gives_detector_numbers_and_monitor_reasoning() -> None:
    text = anomalies_for_llm(build_facts(spoofing_state()))
    assert (
        "### A2 · Spoofing del GPS — detección a T+01:40, primera alerta a T+01:41, "
        "cerrada por el monitor a T+02:30" in text
    )
    assert (
        "- Detector det-0003 SOURCE_DISCREPANCY a T+01:40: «desviación de prueba» "
        "(valor 35,0 m, umbral 30,0 m, máximo 40,0 m)" in text
    )
    assert "- Monitor ai-0006 a T+02:11: Spoofing del GPS (media" in text


def test_parse_narrative_unwraps_a_code_block_and_drops_what_follows() -> None:
    text = "```markdown\n## Resumen\nR\n\n## Recomendaciones\n1. Uno\n```\n\nEste informe resume…"
    n = parse_narrative(text, [])
    assert (n.summary, n.recommendations) == ("R", "1. Uno")


def test_figures_line_is_written_by_the_module_and_status_says_when_detections_ended() -> None:
    state = spoofing_state()
    state.apply(detection_event("cleared", "det-0005", 135.0))
    facts = build_facts(state)
    records = [
        {"agent": "monitor", "duration_s": 10.0, "fallback": False, "deterministic": False,
         "guardrail_rejections": [{"tool": "publish_alert", "errors": ["x"]}]},
        {"agent": "monitor", "duration_s": 0.0, "fallback": True, "deterministic": True,
         "guardrail_rejections": []},
    ]  # fmt: skip
    line = figures_line(monitor_stats(records, {"coherence_guardrail": True}), facts)
    assert "2 invocaciones (1 con LLM y 1 deterministas)" in line and "media 10 s" in line
    assert "fallbacks: 1 · rechazos de los guardrails: 1 · alertas abiertas al final: 1" in line
    assert "ayudas activas: guardrail de coherencia" in line
    text = assemble("demo", SUMMARY, state, facts, Narrative(), figures=line)
    assert "## Valoración del monitor\n\n**Cifras del monitor**" in text
    assert (
        "cerrada por el monitor a T+02:30 (la última detección de la cadena terminó a T+02:20)"
        in text
    )


def test_status_only_explains_the_gap_when_the_closure_is_late() -> None:
    """Esperando al agente el cierre sale a la hora del fin de la detección: sin paréntesis."""
    state = spoofing_state()
    state.apply(detection_event("cleared", "det-0005", 135.0))
    state.alerts["ai-0006"].closed_at = 142.0  # 2 s después de que terminara det-0003 (T+02:20)
    spoofing = build_facts(state).anomalies[1]
    assert spoofing.status == "cerrada por el monitor a T+02:22"
    state.alerts["ai-0006"].closed_at = 150.0
    assert spoofing.status == (
        "cerrada por el monitor a T+02:30 (la última detección de la cadena terminó a T+02:20)"
    )


def test_detection_updates_show_as_a_severity_rise_and_keep_the_opening_values() -> None:
    reset_ids()
    state = MonitorState()
    state.apply(detection_event("raised", "det-0001", 10.0))
    updated = detection_event("updated", "det-0001", 15.0, severity="high")
    updated.payload["value"], updated.payload["message"] = 90.0, "ya 90 m"
    state.apply(updated)
    table = timeline_table(state, build_facts(state), None)
    assert (
        "| T+00:10 | Detector | det-0001 ROUTE_DEVIATION (media): desviación de prueba |" in table
    )
    assert "| T+00:15 | Detector | det-0001 ROUTE_DEVIATION sube a alta: ya 90 m |" in table
    assert state.detections["det-0001"].value == 35.0
