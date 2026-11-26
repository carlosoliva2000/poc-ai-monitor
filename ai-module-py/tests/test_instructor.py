"""Proceso del instructor (E7d): el traductor solo propone, la verdad solo vive aquí y lo suyo sale
por topics que el alumno no recibe."""

import asyncio
from typing import Any

import pytest
from test_assistant import FakeBus, FakeLlm, build_flow, question_event

from ai_module.assistant import __main__ as student
from ai_module.assistant.config import load_config
from ai_module.assistant.llm import LlmError, LlmResult
from ai_module.assistant.store import Store
from ai_module.instructor import __main__ as instr
from ai_module.instructor.store import InstructorStore
from ai_module.instructor.translator import (
    Translator,
    build_proposal,
    convert_units,
    describe_proposal,
    parse_direction,
)
from ai_module.instructor.truth import pairing
from poc_contracts.enums import EventType
from poc_contracts.topics import topic_matches

CONFIG = load_config()


def call(name: str, **args: Any) -> LlmResult:
    return LlmResult("", name, args, 0.1)


def translate(answer: LlmResult | Exception, text: str = "x", active: Any = None) -> Any:
    llm = FakeLlm(answer)
    return asyncio.run(Translator(CONFIG, llm).translate(text, active)), llm


# --- el traductor: de la frase a una orden del catálogo ------------------------------------------


@pytest.mark.parametrize(
    ("said", "degrees"),
    [("NE", 45.0), ("north-east", 45.0), ("from the north", 0.0), ("225", 225.0),
     ("225°", 225.0), ("west", 270.0), ("360", 0.0), ("north north east", 22.5)],
)  # fmt: skip
def test_directions_are_converted_by_the_code(said: str, degrees: float) -> None:
    assert parse_direction(said) == degrees


def test_an_unreadable_or_out_of_range_direction_is_an_error() -> None:
    for bad in ("sideways", "400"):
        with pytest.raises(ValueError):
            parse_direction(bad)


def test_a_proposal_fills_defaults_says_so_and_validates_the_ranges() -> None:
    ok = build_proposal({"from_direction": "NE", "speed": "8", "unit": "m/s"}, "NE at 8 m/s")
    assert ok["ok"] and ok["proposal"]["defaults_used"] == ["duration_s", "ramp_s"]
    assert ok["proposal"]["params"] == {"from_deg": 45.0, "speed_mps": 8.0, "ramp_s": 10.0,
                                        "duration_s": 60.0}  # fmt: skip
    text = describe_proposal(ok["proposal"])
    assert "Wind from NE (45°), 8 m/s, 60 s, ramp 10 s." in text and "Filled in by default" in text
    forever = build_proposal(
        {"from_direction": "N", "speed": "19", "until_cancelled": True, "ramp_s": 5}, "N 19 m/s"
    )  # fmt: skip
    assert forever["proposal"]["params"]["duration_s"] is None
    assert forever["proposal"]["defaults_used"] == []
    assert not build_proposal({"from_direction": "N", "speed": "45"}, "N 45 m/s")["ok"]
    assert not build_proposal({"from_direction": "N", "speed": "10", "duration_s": 99999}, "N 10")[
        "ok"
    ]
    assert not build_proposal({"from_direction": "N"}, "N")["ok"]


def test_a_wind_order_becomes_a_proposal_and_nothing_else() -> None:
    result, llm = translate(call("propose_wind", from_direction="north", speed="19", unit="m/s",
                                 until_cancelled=True),
        "wind from the north at 19 m/s until I cancel it",
    )  # fmt: skip
    assert result.proposal["command"] == "set_wind" and result.proposal["params"]["speed_mps"] == 19
    assert "Confirm it, edit it or discard it" in result.text
    assert len(llm.calls) == 1


def test_an_out_of_range_order_gets_one_retry_and_then_the_limit_without_a_proposal() -> None:
    bad = call("propose_wind", from_direction="north", speed="forty five", unit="m/s")
    result, llm = translate(bad, "wind from the north at forty five")
    assert result.proposal is None and "at most 40 m/s" in result.text
    assert len(llm.calls) == 2 and "rejected" in llm.calls[1][2]


def test_cancel_needs_an_active_wind_from_the_bus() -> None:
    result, _ = translate(call("propose_cancel_wind"), "Remove the wind", None)
    assert result.proposal is None and "no instructor wind" in result.text
    active = {"from_deg": 0.0, "speed_mps": 19.0, "remaining_s": None}
    result, _ = translate(call("propose_cancel_wind"), "Remove the wind", active)
    assert result.proposal == {"command": "cancel_wind", "params": None, "defaults_used": []}


def test_ambiguous_missing_speed_other_commands_and_questions_propose_nothing() -> None:
    active = {"from_deg": 0.0, "speed_mps": 12.0, "remaining_s": 30}
    result, _ = translate(call("not_an_order", reason="missing_speed"), "Stronger", active)
    assert result.proposal is None and result.text == "What speed, in m/s? The wind now is 12 m/s."
    result, _ = translate(call("not_an_order", reason="other_command"), "Hijack the drone")
    assert result.proposal is None and "only propose wind" in result.text
    result, _ = translate(call("not_an_order", reason="wrong_unit"), "20 knots")
    assert "m/s" in result.text and result.proposal is None
    result, _ = translate(call("not_an_order", reason="question"), "What happened?")
    assert result.to_chat and result.proposal is None
    result, _ = translate(
        call("not_an_order", reason="ambiguous", ask="Do you want the wind to start now?")
    )
    assert result.text == "Do you want the wind to start now?"
    # una pregunta con cifras inventadas se sustituye por la fija
    result, _ = translate(call("not_an_order", reason="ambiguous", ask="Do you mean 77 m/s?"))
    assert "direction and the speed" in result.text


def test_an_llm_error_is_said_and_proposes_nothing() -> None:
    result, _ = translate(LlmError("down"))
    assert result.proposal is None and "not available" in result.text


# --- la verdad vive solo aquí -----------------------------------------------------------------


def instructor_events() -> list[Any]:
    """`demo` con lo del instructor: lo programado, un fallo y un comando."""
    return [e for e in build_flow() if e.type != EventType.OPERATOR_MESSAGE]


def run_instructor(questions: list[Any], llm: FakeLlm) -> tuple[FakeBus, instr.InstructorProcess]:
    async def main() -> tuple[FakeBus, instr.InstructorProcess]:
        process = instr.InstructorProcess("http://127.0.0.1:1", CONFIG, llm)
        bus = FakeBus()
        process.bus = bus  # type: ignore[assignment]
        for event in instructor_events():
            await process.handle(event)
        for question in questions:
            await process.handle(question)
        await process.queue.idle()
        return bus, process

    return asyncio.run(main())


def test_the_instructors_replies_go_to_topics_the_student_does_not_receive() -> None:
    llm = FakeLlm(call("propose_wind", from_direction="NE", speed="8", unit="m/s"))
    bus, _ = run_instructor(
        [question_event("Wind from the north-east at 8 m/s", "instructor")], llm
    )
    assert bus.published
    for draft in bus.published:
        # la actividad va por el topic común (`ai.agent`), que el alumno tampoco recibe
        assert ".ai.instructor." in draft.topic or draft.type == EventType.AGENT_ACTIVITY
        assert not any(topic_matches(p, draft.topic) for p in student.PATTERNS)
    reply = next(d for d in bus.published if d.type == EventType.AGENT_REPLY)
    assert reply.source == "ai-chat-instructor"
    assert reply.payload["proposal"]["params"]["from_deg"] == 45.0
    assert reply.payload["tool_calls"] == ["propose_wind"]


def test_the_translator_never_publishes_a_command_or_touches_the_exercise() -> None:
    llm = FakeLlm(call("propose_wind", from_direction="NE", speed="8", unit="m/s"))
    bus, process = run_instructor([question_event("NE 8 m/s", "instructor")], llm)
    sent = {d.type for d in bus.published}
    assert EventType.INSTRUCTOR_COMMAND not in sent and EventType.INCIDENT_UPDATED not in sent
    assert sent <= {EventType.AGENT_ACTIVITY, EventType.AGENT_REPLY_CHUNK, EventType.AGENT_REPLY}
    assert (
        process.store.commands and len(process.store.commands) == 1
    )  # solo el de la frase de prueba


def test_the_active_wind_comes_from_the_bus_commands_not_from_the_web() -> None:
    store = InstructorStore()
    store.observe({"type": "InstructorCommand", "sim_time": 100.0, "event_id": "cmd-0001",
                   "payload": {"command": "set_wind", "issued_by": "panel", "text": None,
                               "params": {"from_deg": 0.0, "speed_mps": 12.0, "ramp_s": 10.0,
                                          "duration_s": 60.0}}})  # fmt: skip
    store.now = 130.0
    assert store.active_wind() == {"from_deg": 0.0, "speed_mps": 12.0, "remaining_s": 30}
    store.now = 170.0
    assert store.active_wind() is None  # terminó por duración
    store.now = 110.0
    store.observe({"type": "InstructorCommand", "sim_time": 110.0, "event_id": "cmd-0002",
                   "payload": {"command": "cancel_wind", "issued_by": "panel", "text": None,
                               "params": None}})  # fmt: skip
    assert store.active_wind() is None


def test_the_chat_with_the_truth_gets_it_and_the_pairing_but_not_the_students_chat() -> None:
    llm = FakeLlm(call("not_an_order", reason="question"), "The wind was detected.")
    bus, _ = run_instructor([question_event("What was programmed?", "instructor")], llm)
    prompt = next(user for _, _, user in llm.calls if "programmed or injected" in user)
    assert any(d.type == EventType.AGENT_REPLY for d in bus.published)
    assert "the truth" in prompt and "Detected as" in prompt
    assert "hijack of the drone" in prompt  # lo programado, en palabras


def test_pairing_says_what_was_seen_and_what_was_not() -> None:
    async def main() -> list[str]:
        process = instr.InstructorProcess("http://127.0.0.1:1", CONFIG, FakeLlm("x"))
        process.bus = FakeBus()  # type: ignore[assignment]
        for event in instructor_events():
            await process.handle(event)
        process.store.injects.append({"id": "F9", "type": "source_silent", "source": "battery",
                                      "start_s": 10.0, "end_s": 30.0})  # fmt: skip
        return pairing(process.store)

    lines = asyncio.run(main())
    hijack = next(line for line in lines if line.startswith("- hijack of the drone"))
    assert "Detected as Command link lost, later Hijack" in hijack
    assert any("battery silenced" in line and line.endswith("Not detected") for line in lines)


def test_the_students_store_drops_the_truth_even_if_it_arrived() -> None:
    store = Store()
    for kind in ("ExerciseInjects", "FaultInjected", "InstructorCommand"):
        assert not store.observe({"type": kind, "sim_time": 1.0, "event_id": "x", "payload": {}})


def test_a_speed_the_instructor_did_not_say_is_not_proposed_and_one_over_the_limit_is_refused() -> (
    None
):
    """Con «wind from the south» el modelo rellenaba un 0: la velocidad tiene que estar en la
    frase. Y una por encima del límite se contesta sin llamar al modelo."""
    made_up = call("propose_wind", from_direction="south", speed="0", unit="m/s")
    result, _ = translate(made_up, "wind from the south")
    assert result.proposal is None and result.text == "What speed, in m/s?"
    said = call("propose_wind", from_direction="east", speed="12", unit="m/s")
    result, _ = translate(said, "wind from the east, twelve metres per second")
    assert result.proposal is not None  # en palabras también vale
    result, llm = translate(said, "wind at 60 m/s from the east")
    assert result.proposal is None and "at most 40 m/s" in result.text and not llm.calls


def test_pairing_does_not_count_the_future_as_missed() -> None:
    store = InstructorStore()
    store.observe({"type": "ExerciseInjects", "sim_time": 0.0, "event_id": "inj-0001",
                   "payload": {"injects": [{"id": "A1", "type": "wind", "source": None,
                                            "start_s": 125.0, "end_s": 160.0}]}})  # fmt: skip
    store.now = 100.0
    assert pairing(store)[0].endswith("Has not started yet")
    store.now = 140.0
    assert pairing(store)[0].endswith("Not detected yet (it is still in progress)")
    store.now = 400.0
    assert pairing(store)[0].endswith("Not detected")


def test_units_are_converted_by_the_code_from_what_was_said_and_the_proposal_says_so() -> None:
    assert convert_units("wind from the west at 20 knots") == (
        "wind from the west at 10.3 m/s", ["20 knots = 10.3 m/s"]
    )  # fmt: skip
    assert convert_units("50 km/h and 30 mph")[1] == ["50 km/h = 13.9 m/s", "30 mph = 13.4 m/s"]
    assert convert_units("12 m/s from the north") == ("12 m/s from the north", [])
    # el modelo devuelve cifra o palabra y unidad tal como se dijeron; convierte el código
    for said, text in (("20", "wind from the west at 20 knots"),
                       ("twenty", "wind from the west at twenty knots")):  # fmt: skip
        result, llm = translate(
            call("propose_wind", from_direction="west", speed=said, unit="knots"), text
        )
        assert text in llm.calls[0][2]  # el modelo ve la frase tal cual, sin convertir
        assert result.proposal["params"]["speed_mps"] == 10.3
        assert "Converted by the assistant: 20 knots = 10.3 m/s." in result.text
        assert result.text.endswith("Confirm it, edit it or discard it.")
    result, _ = translate(
        call("propose_wind", from_direction="north", speed="fifty", unit="km/h"),
        "north wind, fifty km/h",
    )
    assert result.proposal["params"]["speed_mps"] == 13.9
    result, _ = translate(
        call("propose_wind", from_direction="east", speed="twenty five", unit="mph"),
        "east wind twenty-five mph",
    )
    assert result.proposal["params"]["speed_mps"] == 11.2
    # por encima del límite tras convertir: se rechaza (cifras: sin llamar al modelo)
    result, llm = translate(
        call("propose_wind", from_direction="west", speed="100", unit="knots"), "100 knots west"
    )
    assert result.proposal is None and "at most 40 m/s" in result.text
    assert "100 knots = 51.4 m/s" in result.text and not llm.calls
    result, _ = translate(
        call("propose_wind", from_direction="west", speed="eighty", unit="knots"),
        "wind from the west at eighty knots",
    )
    assert result.proposal is None and "at most 40 m/s" in result.text
    # una unidad que el instructor no dijo, o una velocidad que no dijo, no se aceptan
    result, _ = translate(
        call("propose_wind", from_direction="west", speed="20", unit="knots"), "wind west 20"
    )
    assert result.proposal is None and result.text == "What speed, in m/s?"
