"""Agente del instructor (Fase 16): rumbos, propuestas validadas y el chat con un LLM falso.
El chat propone y no publica ningún comando; la propuesta va en `AgentReply.proposal`."""

from pathlib import Path

import pytest
from agent_helpers import (
    FakeLlm,
    Script,
    call,
    make_runtime,
    reset_ids,
    run,
    text_response,
    tool_response,
)

from ai_module.instructor import (
    InstructorChat,
    build_proposal,
    describe_active_wind,
    parse_direction,
)
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import Envelope
from poc_contracts.topics import source_for, topic_for


@pytest.fixture(autouse=True)
def _ids() -> None:
    reset_ids()


@pytest.mark.parametrize(
    ("text", "degrees"),
    [
        ("N", 0.0), ("north", 0.0), ("NE", 45.0), ("north-east", 45.0), ("northeast", 45.0),
        ("from the north-east", 45.0), ("From the South", 180.0), ("WSW", 247.5),
        ("east north east", 67.5), ("225", 225.0), ("225 degrees", 225.0), ("225°", 225.0),
        ("360", 0.0), ("from 45 degrees", 45.0),
    ],
)  # fmt: skip
def test_direction_is_converted_by_the_code(text: str, degrees: float) -> None:
    assert parse_direction(text) == degrees


@pytest.mark.parametrize("bad", ["nowhere", "", "up", "361", "-10"])
def test_directions_that_cannot_be_read_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_direction(bad)


def test_proposal_fills_defaults_and_says_which() -> None:
    result = build_proposal({"from_direction": "NE", "speed_mps": 8})
    assert result == {
        "ok": True,
        "proposal": {
            "command": "set_wind",
            "params": {
                "from_deg": 45.0, "speed_mps": 8.0, "gust_mps": 10.4,
                "ramp_s": 10.0, "duration_s": 60.0,
            },
            "defaults_used": ["gust_mps", "duration_s", "ramp_s"],
        },
    }  # fmt: skip
    full = build_proposal(
        {"from_direction": "north", "speed_mps": 12, "gust_mps": 16, "duration_s": 60, "ramp_s": 10}
    )
    assert full["proposal"]["defaults_used"] == []
    forever = build_proposal({"from_direction": "N", "speed_mps": 5, "until_cancelled": True})
    assert forever["proposal"]["params"]["duration_s"] is None
    assert "duration_s" not in forever["proposal"]["defaults_used"]


def test_proposal_errors_are_for_the_model_to_correct() -> None:
    too_strong = build_proposal({"from_direction": "east", "speed_mps": 100})
    assert too_strong["ok"] is False and "at most 40 m/s" in too_strong["errors"][0]
    assert len(too_strong["errors"]) == 1  # no se queja también de la racha que rellenó él
    assert (
        "gust_mps"
        in build_proposal({"from_direction": "N", "speed_mps": 12, "gust_mps": 5})["errors"][0]
    )
    assert (
        "Cannot read the direction"
        in build_proposal({"from_direction": "x", "speed_mps": 3})["errors"][0]
    )
    assert build_proposal({"speed_mps": 3})["errors"] == ["from_direction is missing"]
    assert (
        "ramp_s"
        in build_proposal({"from_direction": "N", "speed_mps": 3, "ramp_s": 500})["errors"][0]
    )


def operator_message(text: str, active: dict | None = None, number: int = 1) -> Envelope:
    conv, kind = ConversationId.INSTRUCTOR, EventType.OPERATOR_MESSAGE
    payload: dict = {"conversation_id": "instructor", "text": text}
    if active is not None:
        payload["context"] = {"active_wind": active}
    return Envelope(
        event_id=f"ops-{number:04d}", topic=topic_for(kind, conv), type=kind,
        source=source_for(kind, conv), asset=None, seq=number, sim_time=10.0,
        event_time="2026-10-20T10:00:00Z", ingestion_time="2026-10-20T10:00:00.000Z",
        payload=payload,
    )  # fmt: skip


def replies(published: list) -> list:
    return [e for e in published if e.type == EventType.AGENT_REPLY]


def test_the_chat_proposes_and_never_publishes_a_command(tmp_path: Path) -> None:
    llm = FakeLlm(
        Script(
            tool_response(call("propose_wind", from_direction="north-east", speed_mps=8)),
            text_response(
                "Proposed: wind from the north-east at 8 m/s. Defaults: gust, duration, ramp."
            ),
        )
    )
    rt, published = make_runtime(tmp_path, llm)
    chat = InstructorChat(rt)
    run(chat.answer(operator_message("Wind from the north-east at 8 m/s")))
    [reply] = replies(published)
    assert (
        reply.topic.endswith("ai.instructor.AgentReply.v1") and reply.source == "ai-chat-instructor"
    )
    assert reply.payload["tool_calls"] == ["propose_wind"]
    assert reply.payload["proposal"]["params"]["from_deg"] == 45.0
    assert reply.payload["proposal"]["defaults_used"] == ["gust_mps", "duration_s", "ramp_s"]
    # el agente solo propone: no sale ningún comando ni evento de la simulación
    allowed = {
        EventType.AGENT_REPLY,
        EventType.AGENT_REPLY_CHUNK,
        EventType.AGENT_ACTIVITY,
        EventType.AGENT_TOOL_CALL,
    }
    assert {e.type for e in published} <= allowed
    tools = [t["function"]["name"] for t in llm.requests[0]["tools"]]
    assert tools == ["propose_wind", "propose_cancel_wind"]  # sin tools de datos
    assert llm.requests[0]["sampling"]["temperature"] == 0
    assert [e.payload["agent"] for e in published if e.type == EventType.AGENT_ACTIVITY] == [
        "chat-instructor", "chat-instructor",
    ]  # fmt: skip


def test_a_rejected_proposal_lets_the_model_correct_and_only_the_valid_one_is_proposed(
    tmp_path: Path,
) -> None:
    llm = FakeLlm(
        Script(
            tool_response(call("propose_wind", from_direction="east", speed_mps=100)),
            text_response("The limit is 40 m/s: I cannot propose 100 m/s."),
        )
    )
    rt, published = make_runtime(tmp_path, llm)
    run(InstructorChat(rt).answer(operator_message("East wind at 100 m/s")))
    [reply] = replies(published)
    assert "proposal" not in reply.payload
    calls = [e for e in published if e.type == EventType.AGENT_TOOL_CALL]
    assert [c.payload["status"] for c in calls] == ["rejected"]


def test_cancel_needs_an_active_wind_that_the_web_reports(tmp_path: Path) -> None:
    active = {"from_deg": 0.0, "speed_mps": 12.0, "gust_mps": 16.0, "remaining_s": 41.0}
    for context, has_proposal in ((active, True), (None, False)):
        llm = FakeLlm(Script(tool_response(call("propose_cancel_wind")), text_response("ok")))
        rt, published = make_runtime(tmp_path, llm)
        run(InstructorChat(rt).answer(operator_message("Remove the wind", context)))
        [reply] = replies(published)
        assert ("proposal" in reply.payload) is has_proposal
        if has_proposal:
            assert reply.payload["proposal"] == {
                "command": "cancel_wind",
                "params": None,
                "defaults_used": [],
            }
        system = llm.requests[0]["messages"][0]["content"]
        assert "<<" not in system
        assert ("Active: from 0°, 12 m/s" in system) is has_proposal


def test_active_wind_description() -> None:
    assert describe_active_wind(None) == "No wind from the instructor is active."
    text = describe_active_wind(
        {"from_deg": 45.0, "speed_mps": 8.0, "gust_mps": 10.4, "remaining_s": None}
    )
    assert "until it is cancelled" in text and "45°" in text


# --- Respuesta sin llamar a la tool (el historial hace imitar el texto) -------------------------

LIE = "I propose a wind from the east at 25 m/s. The gust was set to 32.5 m/s by default."


def test_a_reply_that_talks_about_a_proposal_without_the_tool_is_retried(tmp_path: Path) -> None:
    from ai_module.instructor import NO_TOOL_REMINDER

    llm = FakeLlm(
        Script(
            text_response(LIE),  # no llama a la tool…
            tool_response(call("propose_wind", from_direction="east", speed_mps=25, duration_s=20)),
            text_response("Done."),  # …y tras el recordatorio sí
        )
    )
    rt, published = make_runtime(tmp_path, llm)
    run(
        InstructorChat(rt).answer(operator_message("put a very strong wind 25 m/s from east, 20 s"))
    )
    [reply] = replies(published)
    assert reply.payload["proposal"]["params"]["speed_mps"] == 25.0
    assert reply.payload["tool_calls"] == ["propose_wind"]
    # el recordatorio se manda y la respuesta falsa no se le deja ver
    second = llm.requests[1]["messages"]
    assert second[-1] == {"role": "user", "content": NO_TOOL_REMINDER}
    assert all(m.get("content") != LIE for m in second)
    assert rt.trace.records[0]["aids"] == {"retried_without_tool": True}


def test_if_it_still_does_not_call_the_tool_the_reply_does_not_pretend(tmp_path: Path) -> None:
    from ai_module.instructor import NO_PROPOSAL_REPLY

    llm = FakeLlm(Script(text_response(LIE)))
    rt, published = make_runtime(tmp_path, llm)
    run(InstructorChat(rt).answer(operator_message("wind from the east 25 m/s")))
    [reply] = replies(published)
    assert "proposal" not in reply.payload and reply.payload["text"] == NO_PROPOSAL_REPLY
    assert len(llm.requests) == 2  # un solo reintento


def test_a_question_is_not_retried(tmp_path: Path) -> None:
    llm = FakeLlm(Script(text_response("Please provide the wind speed in m/s.")))
    rt, published = make_runtime(tmp_path, llm)
    run(InstructorChat(rt).answer(operator_message("Wind from the south")))
    [reply] = replies(published)
    assert (
        reply.payload["text"] == "Please provide the wind speed in m/s." and len(llm.requests) == 1
    )


def test_the_text_of_a_proposal_is_written_by_the_code(tmp_path: Path) -> None:
    llm = FakeLlm(
        Script(
            tool_response(call("propose_wind", from_direction="north", speed_mps=12, gust_mps=16,
                               duration_s=60, ramp_s=10)),
            text_response("I propose it; the gust was set by default."),  # miente: no hubo defecto
        )
    )  # fmt: skip
    rt, published = make_runtime(tmp_path, llm)
    run(InstructorChat(rt).answer(operator_message("12 m/s from the north, gusts 16, one minute")))
    [reply] = replies(published)
    assert reply.payload["text"] == (
        "Wind from N (0°), 12 m/s, gusts 16 m/s, 60 s, ramp 10 s. "
        "Confirm it, edit it or discard it."
    )


def test_describe_proposal_names_only_what_was_filled_in() -> None:
    from ai_module.instructor import describe_proposal

    p = build_proposal({"from_direction": "NE", "speed_mps": 8})["proposal"]
    assert describe_proposal(p) == (
        "Wind from NE (45°), 8 m/s, gusts 10.4 m/s, 60 s, ramp 10 s. "
        "Filled in by default: gust_mps, duration_s, ramp_s. Confirm it, edit it or discard it."
    )
    forever = build_proposal({"from_direction": "47", "speed_mps": 5, "until_cancelled": True})
    assert "47° (≈NE)" in describe_proposal(forever["proposal"])
    assert "until cancelled" in describe_proposal(forever["proposal"])
    cancel = {"command": "cancel_wind", "params": None, "defaults_used": []}
    assert describe_proposal(cancel).startswith("Cancel the wind")


def test_claims_a_proposal_even_with_a_new_wording_but_not_questions_or_refusals() -> None:
    from ai_module.instructor import claims_a_proposal

    assert claims_a_proposal("I propose a wind from the east.")
    assert claims_a_proposal(
        "Wind from E (90°), 25 m/s, gusts 32.5 m/s, 20 s, ramp 10 s. Confirm it."
    )
    assert not claims_a_proposal("Please provide the wind speed in m/s.")
    assert not claims_a_proposal("What is the new speed in m/s?")
    assert not claims_a_proposal(
        "The requested 100 m/s exceeds the maximum allowed limit of 40 m/s."
    )


def test_history_keeps_the_whole_exchange_with_the_tool_call(tmp_path: Path) -> None:
    llm = FakeLlm(
        Script(
            tool_response(call("propose_wind", from_direction="east", speed_mps=25, duration_s=20)),
            text_response("Done."),
            tool_response(call("propose_wind", from_direction="west", speed_mps=10)),
            text_response("Done."),
        )
    )
    rt, _ = make_runtime(tmp_path, llm)
    chat = InstructorChat(rt)
    run(chat.answer(operator_message("east 25 m/s 20 s")))
    assert [m["role"] for m in chat.history] == ["user", "assistant", "tool", "assistant"]
    assert chat.history[1]["tool_calls"][0]["function"]["name"] == "propose_wind"
    run(chat.answer(operator_message("west 10 m/s", number=2)))
    sent = llm.requests[2]["messages"]  # la segunda pregunta ve la primera con su llamada a la tool
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "assistant", "user"]


def test_a_history_cut_in_the_middle_never_starts_with_a_tool_result(tmp_path: Path) -> None:
    rt, _ = make_runtime(tmp_path, FakeLlm(Script(text_response("ok"))))
    chat = InstructorChat(rt)
    chat.history.extend(
        [{"role": "tool", "content": "{}"}, {"role": "assistant", "content": "x"},
         {"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    )  # fmt: skip
    assert [m["role"] for m in chat._usable_history()] == ["user", "assistant"]
