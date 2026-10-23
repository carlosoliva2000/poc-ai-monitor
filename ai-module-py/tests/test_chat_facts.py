"""Hechos para los chats sin tools: cada juicio con su interpretación y sus cifras, sin nombres de
campos, y calculados con las mismas reglas que el guardrail del monitor. Sin LLM."""

import re
from pathlib import Path

from test_round9 import chat_runtime, operator_message, run

from ai_module.agent.guardrails import InvocationFacts, expected_checks, metric_facts
from ai_module.chat import Chat
from ai_module.chat_facts import describe_metrics
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import ConversationId

# los números de la ventana del viento de `demo` (T+01:46): viento a favor de la deriva
WIND_DEMO = {
    "since": 76.0, "until": 106.0,
    "gps_deviation_from_plan_m": {"mean": 20.1, "max": 30.5, "trend": "increasing"},
    "radar_deviation_from_plan_m": {"mean": 21.0, "max": 32.5, "trend": "increasing"},
    "gps_radar_distance_m": {"mean": 6.6, "max": 9.0, "trend": "stable"},
    "drift_direction_deg": 151.2,
    "wind": {"mean_speed_mps": 3.9, "max_gust_mps": 9.7, "from_deg": 326.3, "wind_to_deg": 146.3,
             "drift_vs_wind_deg": 4.9, "notable": True, "with_drift": True},
    "gps_radar": {"disagreed": False}, "gps_max_step_m": 14.8,
}  # fmt: skip
NOTE = "monitor query at T+01:46 (window 76–106 s)"


def test_the_injected_facts_carry_the_interpretation_next_to_the_figures() -> None:
    text = describe_metrics(WIND_DEMO, NOTE)
    assert text.startswith(NOTE)
    assert "The wind is notable: yes (mean 3.9 m/s, gust 9.7 m/s)" in text
    assert "The drift goes with the wind: yes (the wind pushes in the same direction" in text
    assert "difference of 4.9°" in text
    assert "GPS and radar disagree: no (mean distance of 6.6 m, maximum of 9.0 m)" in text
    assert "Sudden GPS jump" in text and ": no (" in text.split("Sudden GPS jump")[1].split("\n")[0]
    # sin ángulos de procedencia ni de deriva: puestos uno junto a otro, el 14B los compara él
    assert "326" not in text and "146" not in text and "151" not in text
    assert "GPS deviation from the planned route: mean 20.1 m, maximum 30.5 m" in text


def test_the_injected_facts_have_no_field_names() -> None:
    text = describe_metrics(WIND_DEMO, NOTE)
    assert not re.search(r"[a-z]+_[a-z_]+|\w+=\w+|[{}\"]", text), text


def test_the_judgement_changes_with_the_facts_not_with_the_model() -> None:
    other = {
        **WIND_DEMO,
        "wind": {**WIND_DEMO["wind"], "mean_speed_mps": 1.7, "max_gust_mps": 2.4,
                 "drift_vs_wind_deg": 140.0, "notable": False, "with_drift": False},
        "gps_radar": {"disagreed": True},
        "gps_radar_distance_m": {"mean": 41.0, "max": 73.0, "trend": "increasing"},
        "gps_max_step_m": 68.0,
    }  # fmt: skip
    text = describe_metrics(other, NOTE)
    assert "The wind is notable: no (mean 1.7 m/s, gust 2.4 m/s)" in text
    assert "The drift goes with the wind: no (the wind does not push in the direction" in text
    assert "difference of 140.0°" in text
    assert "GPS and radar disagree: yes (mean distance of 41.0 m, maximum of 73.0 m)" in text
    assert "recovery after a spoofing or a loss): yes (" in text


def test_missing_data_is_said_not_invented() -> None:
    text = describe_metrics({"wind": None, "gps_radar": None, "gps_max_step_m": None}, NOTE)
    assert "There is no wind data" in text
    assert "GPS and radar disagree: cannot be known" in text
    assert "Sudden GPS jump: cannot be known" in text
    no_drift = describe_metrics(
        {**WIND_DEMO, "wind": {**WIND_DEMO["wind"], "drift_vs_wind_deg": None}}, NOTE
    )
    assert "The drift goes with the wind: no (the drone is not moving off the route)" in no_drift
    assert (
        describe_metrics(None, NOTE) == "The monitor has not yet looked up the trajectory metrics."
    )


def test_the_chat_uses_the_same_rules_as_the_guardrail_checks() -> None:
    """Lo que dice el chat (sí/no) sale de `metric_facts`, que es también lo que espera el
    guardrail de los `checks` de la alerta."""
    for notable, drift, disagreed in [
        (True, True, False),
        (False, False, True),
        (True, False, True),
    ]:
        wind = {**WIND_DEMO["wind"], "notable": notable, "with_drift": drift}
        metrics = {**WIND_DEMO, "gps_radar": {"disagreed": disagreed}, "wind": wind}
        facts = metric_facts(metrics)
        expected = expected_checks(InvocationFacts(metrics=metrics), MonitorState(), 106.0)
        assert facts["wind_notable"] == expected["wind_notable"] == notable
        assert facts["wind_with_drift"] == expected["wind_with_drift"] == drift
        assert facts["gps_radar_disagreed"] == expected["gps_radar_disagreed"] == disagreed
        text = describe_metrics(metrics, NOTE)
        yes_no = lambda v: "yes" if v else "no"  # noqa: E731
        assert f"The wind is notable: {yes_no(notable)} (" in text
        assert f"The drift goes with the wind: {yes_no(drift)} (" in text
        assert f"GPS and radar disagree: {yes_no(disagreed)} (" in text


def test_the_system_of_both_chats_carries_the_interpreted_facts(tmp_path: Path) -> None:
    for conversation in (ConversationId.MONITOR, ConversationId.REPORT):
        rt, _, llm = chat_runtime(tmp_path, tools=False)
        rt.last_metrics, rt.last_metrics_note = WIND_DEMO, NOTE
        chat = Chat(
            rt, conversation, _report(rt) if conversation == ConversationId.REPORT else None
        )
        run(chat.answer(operator_message(conversation.value, "¿por qué crees que es viento?")))
        system = llm.requests[0]["messages"][0]["content"]
        assert "The wind is notable: yes (mean 3.9 m/s, gust 9.7 m/s)" in system
        assert "The drift goes with the wind: yes (the wind pushes in the same direction" in system
        assert "GPS and radar disagree: no (mean distance of 6.6 m" in system
        assert "wind_to_deg" not in system and '"notable"' not in system  # sin el JSON de antes


def _report(rt):  # noqa: ANN001, ANN202
    from ai_module.monitor import Monitor
    from ai_module.report import ReportAgent

    report = ReportAgent(rt, Monitor(rt))
    report.markdown = "# Informe de prueba"
    return report


LINK_OK = [
    {"event_id": f"lnk-{n:04d}", "sim_time": 5.0 * n, "controller_id": "GCS-1",
     "rssi_dbm": -62.0 - n % 3, "latency_ms": 44.0 + n}
    for n in range(1, 7)
]  # fmt: skip
LINK_HIJACKED = [
    *LINK_OK[:3],
    {"event_id": "lnk-0067", "sim_time": 335.0, "controller_id": "UNK-4F2A",
     "rssi_dbm": -79.0, "latency_ms": 122.0},
]  # fmt: skip


def test_the_link_fact_carries_the_verdict_and_the_figures() -> None:
    from ai_module.chat_facts import describe_link

    hijacked = describe_link(LINK_HIJACKED, "looked at by the monitor at T+05:42")
    assert (
        "The command link is anomalous: yes (the controller changes from GCS-1 to UNK-4F2A at "
        "T+05:35" in hijacked
    )
    assert (
        "signal between -79 and -62 dBm" in hijacked and "latency between 45 and 122 ms" in hijacked
    )
    assert "looked at by the monitor at T+05:42" in hijacked
    calm = describe_link(LINK_OK, "looked at by the monitor at T+01:46")
    assert "The command link is anomalous: no (a single controller, GCS-1" in calm
    assert describe_link(None, "") == "" and describe_link([], "") == ""


def test_alerts_for_the_chats_have_checks_and_evidence_but_not_the_prose_explanation() -> None:
    """La explicación en prosa del monitor puede contradecir sus propios checks (dijo que el viento
    empujaba «en dirección contraria» a una deriva que los checks daban a favor) y el chat la
    repetía: los chats reciben las comprobaciones, no esa prosa."""
    from test_monitor_state import alert

    state = MonitorState()
    state.apply(alert("ai-0002", ["det-1"], cause="WIND"))
    full = state.describe_alerts_detail()
    chat = state.describe_alerts_detail(explanation=False)
    assert "Explanation: x" in full and "Explanation" not in chat
    assert "Recommendation: y" in chat and "Evidence: gps-000001" in chat
