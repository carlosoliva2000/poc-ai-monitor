"""Ronda 8: `load_skill` repetido, línea de alerta del GPS, orden del esquema, rechazos en
español y accionables, llamada repetida, solo detecciones pendientes y estado en los chats."""

import json
from pathlib import Path

import pytest
from agent_helpers import (
    FakeLlm,
    FakePlatform,
    Script,
    alert_args,
    call,
    detection_event,
    make_runtime,
    reset_ids,
    run,
    seed_evidence,
    text_response,
    tool_response,
)
from test_monitor_state import alert, closed
from test_report_chat import operator_message

from ai_module.agent.assets import Assets
from ai_module.agent.tools import Toolbox
from ai_module.chat import Chat
from ai_module.monitor import Monitor
from ai_module.monitor_state import MonitorState
from poc_contracts.enums import ConversationId, EventType

ASSETS = Assets()


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


def setup(tmp_path: Path, policy, platform=None):
    llm = FakeLlm(policy)
    rt, published = make_runtime(tmp_path, llm, platform)
    seed_evidence(rt, "gps-000001", "gps-000002", sim_time=1.0)
    rt.clock.observe(20.0)
    return rt, published, Monitor(rt), llm


def raised(det="det-0001", t=20.0, **kw):
    return detection_event("raised", det, t, **kw)


# --- 1. load_skill repetido -----------------------------------------------------------------


def test_a_skill_already_loaded_is_not_sent_again() -> None:
    loaded: list[str] = []
    box = Toolbox(
        ASSETS, ["route-deviation", "source-discrepancy"], "http://p", on_skill=loaded.append
    )
    first = run(box("load_skill", {"name": "route-deviation"}))
    assert first.startswith("---\nname: route-deviation")
    again = run(box("load_skill", {"name": "route-deviation"}))
    assert again == (
        "Ya tienes cargada la skill route-deviation (más arriba): sigue con su siguiente paso."
    )
    other = run(box("load_skill", {"name": "source-discrepancy"}))
    assert other.startswith("---\nname: source-discrepancy")
    assert loaded == ["route-deviation", "source-discrepancy"]  # la traza cuenta cada una una vez


def test_each_invocation_has_its_own_loaded_skills(tmp_path: Path) -> None:
    script = Script(
        tool_response(call("load_skill", name="route-deviation")),
        tool_response(call("load_skill", name="route-deviation")),
        tool_response(call("publish_alert", **alert_args(["det-0001"]))),
    )
    rt, _, monitor, llm = setup(tmp_path, script)
    run(monitor.handle_batch([raised()]))
    tool_texts = [m["content"] for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert tool_texts[0].startswith("---") and tool_texts[1].startswith("Ya tienes cargada")
    assert rt.trace.records[0]["skills_loaded"] == [{"name": "route-deviation", "by": "model"}]
    reset_ids()
    rt2, _, monitor2, llm2 = setup(
        tmp_path,
        Script(tool_response(call("load_skill", name="route-deviation")), text_response("x")),
    )
    run(monitor2.handle_batch([raised()]))
    first_tool = next(m for m in llm2.requests[-1]["messages"] if m["role"] == "tool")["content"]
    assert first_tool.startswith("---")  # otra invocación: se vuelve a entregar


# --- 2. línea de alerta del GPS en el estado ---------------------------------------------------


def test_state_line_for_the_gps_alert() -> None:
    s = MonitorState()
    assert s.describe_gps_alert(10.0) == "no"
    s.apply(detection_event("raised", "det-1", 5.0, rule="SOURCE_DISCREPANCY"))
    s.apply(alert("ai-0008", ["det-1"], cause="GPS_SPOOFING"))
    assert s.describe_gps_alert(10.0) == (
        "sí — ai-0008 GPS_SPOOFING (abierta). Si este aviso es la recuperación del GPS: "
        "causa GPS_SPOOFING, supersedes ai-0008"
    )
    s.apply(detection_event("cleared", "det-1", 40.0))
    s.apply(closed("ai-0008", t=50.0))
    closed_line = s.describe_gps_alert(100.0)  # cerrada hace 50 s
    assert "ai-0008 GPS_SPOOFING (cerrada hace 50 s)" in closed_line
    assert closed_line.endswith("causa GPS_SPOOFING, sin supersedes (ya está cerrada)")
    assert s.describe_gps_alert(111.0) == "no"


def test_the_prompt_carries_the_gps_alert_line(tmp_path: Path) -> None:
    rt, _, monitor, llm = setup(tmp_path, Script("x"))
    rt.state.apply(raised("det-0001", 5.0, rule="SOURCE_DISCREPANCY"))
    rt.state.apply(alert("ai-0008", ["det-0001"], cause="GPS_SPOOFING"))
    run(monitor.handle_batch([raised("det-0002", 20.0)]))
    prompt = llm.requests[0]["messages"][1]["content"]
    assert (
        "- Alerta del GPS reciente (abierta o cerrada hace ≤ 60 s): sí — ai-0008 GPS_SPOOFING"
        in prompt
    )
    assert "causa GPS_SPOOFING, supersedes ai-0008" in prompt
    skill = ASSETS.skills["route-deviation"].content
    assert "«Alerta del GPS reciente» del estado dice **sí**" in skill


# --- 3. orden del esquema -----------------------------------------------------------------------


def test_publish_alert_schema_puts_the_evidence_right_after_the_confidence() -> None:
    [schema] = ASSETS.tool_schemas(["publish_alert"])
    parameters = schema["function"]["parameters"]
    props = list(parameters["properties"])
    assert props[:6] == [
        "detection_ids",
        "checks",
        "cause",
        "severity",
        "confidence",
        "evidence_event_ids",
    ]
    assert props[6:9] == ["summary", "explanation", "recommendation"]
    # los obligatorios, en el orden de las propiedades (`detection_ids` lo puede poner el módulo)
    assert parameters["required"] == props[1:9]


# --- 4. rechazos en español y accionables -------------------------------------------------------


def test_a_missing_evidence_field_is_explained_in_spanish(tmp_path: Path) -> None:
    bad = alert_args(["det-0001"])
    del bad["evidence_event_ids"]
    rt, _, monitor, llm = setup(tmp_path, Script(tool_response(call("publish_alert", **bad)), "x"))
    run(monitor.handle_batch([raised()]))
    [rejection] = rt.trace.records[0]["guardrail_rejections"]
    assert rejection["errors"] == [
        "Falta `evidence_event_ids`: pon ahí, no en la explicación, de 2 a 6 ids que hayas visto, "
        "como met-0010 o gps-000106"
    ]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"confidence": 1.7}, "`confidence` fuera de rango: un número entre 0 y 1"),
        (
            {"summary": "x" * 200},
            "`summary` es demasiado largo: una frase de menos de 160 caracteres",
        ),
        ({"cause": "ALIENS"}, "`cause` no es un valor permitido: usa una de WIND, HIJACK"),
        ({"evidence_event_ids": []}, "`evidence_event_ids` está vacío: pon ahí"),
        ({"sobra": 1}, "`sobra` sobra: quítalo"),
    ],
)
def test_validation_errors_are_spanish(change: dict, expected: str, tmp_path: Path) -> None:
    args = {**alert_args(["det-0001"]), **change}
    rt, _, monitor, _ = setup(tmp_path, Script(tool_response(call("publish_alert", **args)), "x"))
    run(monitor.handle_batch([raised()]))
    errors = rt.trace.records[0]["guardrail_rejections"][0]["errors"]
    assert any(e.startswith(expected) for e in errors), errors


def test_a_missing_nested_check_says_how_to_fix_it(tmp_path: Path) -> None:
    bad = alert_args(["det-0001"])
    del bad["checks"]["link_anomalous"]
    rt, _, monitor, _ = setup(tmp_path, Script(tool_response(call("publish_alert", **bad)), "x"))
    run(monitor.handle_batch([raised()]))
    assert rt.trace.records[0]["guardrail_rejections"][0]["errors"] == [
        "Falta `checks.link_anomalous`: true, false, o null si no has mirado el enlace"
    ]


def test_the_same_rejected_call_is_called_out(tmp_path: Path) -> None:
    bad = alert_args(["det-0001"], evidence_event_ids=["gps-999999"])
    fixed = alert_args(["det-0001"])
    script = Script(
        tool_response(call("publish_alert", **bad)),
        tool_response(call("publish_alert", **bad)),
        tool_response(call("publish_alert", **fixed)),
    )
    rt, published, monitor, llm = setup(tmp_path, script)
    run(monitor.handle_batch([raised()]))
    first, second = rt.trace.records[0]["guardrail_rejections"]
    assert "gps-999999" in first["errors"][0] and first["errors"][0].startswith("la evidencia")
    assert second["errors"][0] == "Es la misma llamada que antes; cambia lo que te indiqué."
    assert second["errors"][1:] == first["errors"]  # y repite qué había que cambiar
    assert any(e.type == EventType.ANOMALY_DETECTED for e in published)


# --- 5. iteraciones y tiempos -------------------------------------------------------------------


def test_the_monitor_has_twelve_iterations_and_the_timeouts_leave_room_for_the_platform() -> None:
    config = ASSETS.agent("monitor")
    assert config.max_iterations == 12
    assert config.max_invocation_s + 15 < 90  # WAIT_AGENT_TIMEOUT_S de la plataforma
    assert config.llm_timeout_s < config.max_invocation_s


# --- 7a. solo detecciones pendientes ------------------------------------------------------------


def test_publish_alert_only_accepts_pending_detections(tmp_path: Path) -> None:
    rt, published, monitor, llm = setup(tmp_path, Script("x"))
    rt.state.apply(raised("det-0001", 5.0))  # una detección anterior, ya atendida
    old = alert_args(["det-0001", "det-0002"])
    script = Script(
        tool_response(call("publish_alert", **old)),
        tool_response(call("publish_alert", **alert_args(["det-0002"]))),
    )
    llm.policy = script
    event = raised("det-0002", 20.0)
    run(monitor.handle_batch([event]))
    [rejection] = rt.trace.records[0]["guardrail_rejections"]
    assert "Esta invocación atiende det-0002, no det-0001, det-0002" in rejection["errors"][0]
    [alert_event] = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert alert_event.causation_id == event.event_id  # responde a la detección que atiende


def test_publish_alert_rejects_detections_that_already_have_a_response(tmp_path: Path) -> None:
    ack_then_alert = Script(
        tool_response(
            call("acknowledge_detection", detection_ids=["det-0001"], reason="sin alerta")
        ),
    )
    rt, published, monitor, _ = setup(tmp_path, ack_then_alert)
    run(monitor.handle_batch([raised("det-0001"), raised("det-0002", rule="SOURCE_DISCREPANCY")]))
    # la segunda llamada del modelo ya no llega (el lote tiene respuesta por el fallback);
    # comprobamos la regla directamente
    from ai_module.agent.guardrails import check_publish_alert

    verdict = check_publish_alert(
        alert_args(["det-0001"]),
        as_of=20.0,
        state=rt.state,
        index=rt.index,
        seen_ids={"gps-000001", "gps-000002"},
        pending={"det-0001", "det-0002"},
        unanswered={"det-0002"},
    )
    assert any("ya tienen respuesta" in e for e in verdict.errors)


# --- 6. informe y chats --------------------------------------------------------------------------


def test_chats_carry_the_current_state_in_every_question(tmp_path: Path) -> None:
    llm = FakeLlm(lambda m, t, s: text_response("ok"))
    rt, _ = make_runtime(tmp_path, llm, FakePlatform())
    rt.assets._raw.setdefault("chat", {})["tools_enabled"] = True  # esta prueba es con tools
    rt.state.apply(detection_event("raised", "det-1", 5.0))
    rt.state.apply(alert("ai-0003", ["det-1"], cause="WIND"))
    rt.clock.observe(50.0)
    chat = Chat(rt, ConversationId.MONITOR)
    run(chat.answer(operator_message("monitor", "¿qué hay abierto?")))
    system = llm.requests[0]["messages"][0]["content"]
    assert "T+00:50" in system and "ai-0003 WIND" in system and "det-1 ROUTE_DEVIATION" in system
    assert llm.requests[0]["tools"]  # y mantienen sus tools para los detalles
    # después de otra alerta, el sistema de la siguiente pregunta lo refleja
    rt.state.apply(closed("ai-0003", t=60.0))
    rt.clock.observe(70.0)
    run(chat.answer(operator_message("monitor", "¿y ahora?", 2)))
    assert "alertas abiertas: ninguna" in llm.requests[1]["messages"][0]["content"].lower()


def test_report_prompt_has_no_tools_and_carries_the_data() -> None:
    config = ASSETS.agent("report")
    assert config.tools == [] and config.skills == []
    assert json.dumps(ASSETS.skill_body("report-format")).startswith('"# Formato del informe final')
