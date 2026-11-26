"""Asistente LLM del alumno (E7d): lo importante es que el LLM no cambia el incidente, lo que se
rechaza de su salida, que el proceso del alumno no recibe la verdad y la cola del LLM."""

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_module.assistant import __main__ as proc
from ai_module.assistant.checks import check_text, normalize
from ai_module.assistant.config import AssistantConfig, RoleConfig, load_config
from ai_module.assistant.facts import build_input, glossary
from ai_module.assistant.interpret import Interpreter, is_interpreted, role_for
from ai_module.assistant.llm import LlmError, LlmResult
from ai_module.assistant.llm_queue import Job, LlmQueue
from ai_module.assistant.store import Store
from ai_module.ids import IdAllocator
from ai_module.outbox import EventFactory
from ai_module.situation.monitor import SituationMonitor
from ai_module.situation.replay import is_world, read_events
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.topics import topic_matches

REPO = Path(__file__).resolve().parents[2]
CONFIG = load_config()


def update(**over: Any) -> dict[str, Any]:
    base = {
        "incident_id": "inc-0001", "revision": 1, "kind": "GPS_SPOOFING", "subject": None,
        "name": "GPS spoofing", "state": "open", "severity": "high", "confidence": "confirmed",
        "opened_at": 200.0, "as_of_sim_time": 202.0, "change": "opened",
        "evidence": [{"facet": "gps.integrity", "state": "spoofed", "rule_id": "GI-02",
                      "conditions": [{"feature": "cn0_vs_nominal_db", "op": ">", "threshold": 4.0,
                                      "value": 7.2}]}],
        "context": [{"feature": "wind_est_mps", "value": 2.6}],
        "checks": ["Compare the GPS position with the radar track"],
        "evidence_event_ids": ["gns-000202", "rad-000101"], "decided_by": "table", "table": "t",
    }  # fmt: skip
    return {**base, **over}


def store_with_facts() -> Store:
    store = Store()
    store.observe({"type": "MissionPlanned", "sim_time": 0.0, "event_id": "mis-0001",
                   "payload": {"waypoints": [{"x": 0, "y": 0}, {"x": 1000, "y": 0}]}})  # fmt: skip
    store.observe({"type": "PositionUpdated", "sim_time": 202.0, "event_id": "gps-000202",
                   "payload": {"x": 500.0, "y": 5.0, "fix": "3d"}})  # fmt: skip
    store.observe({"type": "TrackUpdated", "sim_time": 202.0, "event_id": "rad-000101",
                   "payload": {"x": 500.0, "y": 37.0}})  # fmt: skip
    return store


class FakeLlm:
    """Un LLM falso que guarda cada entrada y contesta con lo que se le dé."""

    def __init__(self, *answers: LlmResult | str | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, str]] = []

    async def complete(self, role: RoleConfig, system: str, user: str, tools: Any = None) -> Any:
        self.calls.append((role.name, system, user))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, str):
            return LlmResult(answer, None, None, 0.1)
        return answer


def tool(**args: Any) -> LlmResult:
    return LlmResult("", "propose_hypothesis", args, 0.2)


# --- salida del LLM: lo que se rechaza ----------------------------------------------------------


def verdict(text: str, upd: dict[str, Any] | None = None, role: str = "explain") -> list[str]:
    upd = upd or update()
    return check_text(text, build_input(upd, store_with_facts()), role).reasons


def test_a_text_with_only_given_facts_passes() -> None:
    text = (
        "The GPS shows a spoofing signature and the radar is 32 m from it. Follow it on the radar."
    )
    assert verdict(text) == []


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("The GPS is 45 m off the radar.", "number"),  # cifra que no estaba
        ("At T+09:59 the GPS jumped.", "time"),  # hora que no estaba
        ("See gps-000202 for details.", "id"),  # id en el texto
        ("This is GPS_SPOOFING.", "internal"),  # nombre interno
        ("The drone is being hijacked.", "cause"),  # causa que el incidente no dice
        ("The wind is pushing the drone south.", "cause"),
        ("El dron está fuera de la ruta y la señal es falsa.", "language"),
        ("Check it. Check it again. Then check it a third time. Then stop.", "length"),
    ],
)
def test_rejected_outputs(text: str, code: str) -> None:
    assert any(r.startswith(code) for r in verdict(text)), verdict(text)


def test_a_contrary_cause_is_rejected_even_when_the_evidence_says_it() -> None:
    """Un secuestro cuya evidencia lee «spoofed GPS position»: el texto no puede decir spoofing."""
    hijack = update(
        kind="HIJACK", name="Hijack",
        evidence=[{"facet": "drone.cause", "state": "spoofed_position", "rule_id": "DC-01",
                   "conditions": []}],
        context=[],
    )  # fmt: skip
    reasons = verdict("The drone was misled by a spoofed GPS position.", hijack)
    assert any(r.startswith("cause") for r in reasons)
    assert verdict("Someone else is controlling the drone.", hijack) == []


def test_non_breaking_hyphen_is_normalised_not_rejected() -> None:
    assert normalize("GPS‑radar gap is small") == "GPS-radar gap is small"


def test_now_versus_opening_is_counted_by_its_trigger_word() -> None:
    first = update()
    second = update(
        revision=2, change="state", state="recovering", as_of_sim_time=252.0,
        evidence=[{"facet": "gps.integrity", "state": "reliable", "rule_id": "GI-01",
                   "conditions": [{"feature": "cn0_vs_nominal_db", "op": "<=", "threshold": 4.0,
                                   "value": -0.7}]}],
    )  # fmt: skip
    store = store_with_facts()
    store.revisions["inc-0001"].append(first)
    inp = build_input(second, store)
    # 7.2 solo existe en la apertura: «is» lo rechaza en `loose`, no en `strict`
    text = "The signal strength is 7.2 dB above nominal."
    loose = check_text(text, inp, "explain", now_rule="loose").reasons
    strict = check_text(text, inp, "explain", now_rule="strict").reasons
    assert any(r.startswith("now:is") for r in loose)
    assert not any(r.startswith("now") for r in strict)
    assert check_text("At opening it was 7.2 dB above nominal.", inp, "explain").ok


# --- el LLM no cambia el incidente --------------------------------------------------------------


def test_the_interpreter_only_produces_text_marked_as_the_llms() -> None:
    llm = FakeLlm("The GPS shows a spoofing signature. Follow the drone on the radar.")
    interpreter = Interpreter(CONFIG, llm)
    upd = update()
    out = asyncio.run(interpreter.interpret(upd, store_with_facts()))
    assert out is not None and out.published
    payload = interpreter.payload(upd, out)
    assert payload["decided_by"] == "llm" and payload["role"] == "explain"
    assert payload["hypothesis"] is None
    # el incidente que entra no se toca
    assert upd == update()
    # y el evento resultante es un IncidentEnriched válido (no un IncidentUpdated)
    draft = EventFactory(IdAllocator()).make(EventType.INCIDENT_ENRICHED, payload, sim_time=202.0)
    assert draft.source == "ai-enricher"


def test_a_rejected_text_gets_one_retry_with_the_reasons_and_then_nothing() -> None:
    bad = "The GPS is 45 m off."
    llm = FakeLlm(bad, bad)
    out = asyncio.run(Interpreter(CONFIG, llm).interpret(update(), store_with_facts()))
    assert out is not None and not out.published and len(out.attempts) == 2
    assert "rejected" in llm.calls[1][2] and "number" in llm.calls[1][2]
    # un texto bueno en el segundo intento sí se publica
    llm = FakeLlm(bad, "The GPS shows a spoofing signature.")
    out = asyncio.run(Interpreter(CONFIG, llm).interpret(update(), store_with_facts()))
    assert out is not None and out.published and len(out.attempts) == 2


def test_an_llm_error_publishes_nothing() -> None:
    out = asyncio.run(
        Interpreter(CONFIG, FakeLlm(LlmError("timeout"))).interpret(update(), store_with_facts())
    )
    assert out is not None and not out.published and out.error == "timeout"


def test_severity_and_evidence_revisions_are_not_interpreted() -> None:
    assert is_interpreted(update(change="opened")) and is_interpreted(update(change="closed"))
    assert not is_interpreted(update(change="severity"))
    assert not is_interpreted(update(change="evidence"))


# --- hipótesis -----------------------------------------------------------------------------------


def undetermined(**over: Any) -> dict[str, Any]:
    return update(
        kind="UNDETERMINED", name="Undetermined deviation", severity="medium",
        confidence="possible",
        evidence=[{"facet": "drone.situation", "state": "deviated", "rule_id": "DS-04",
                   "conditions": [{"feature": "radar_dev_sigma", "op": ">", "threshold": 3.0,
                                   "value": 6.5}]}],
        context=[{"feature": "possible_cause", "value": "WIND (possible)"}],
        **over,
    )  # fmt: skip


GOOD_HYPOTHESIS = {
    "summary": "The drone is off the route and the data do not settle why; this is not confirmed.",
    "ranked": [
        {"kind": "WIND", "supports": ["The drone drifts away from the route"],
         "missing": ["The station reports calm wind"]},
        {"kind": "GPS_SPOOFING", "supports": [], "missing": ["The signal strength has not risen"]},
    ],
    "checks": [{"target": "meteo", "text": "Check the weather station wind"},
               {"target": "receiver", "text": "Check the receiver signal strength"}],
}  # fmt: skip


def test_hypothesis_only_for_an_undetermined_incident_that_opens() -> None:
    assert role_for(undetermined(), CONFIG) == "hypothesis"
    assert role_for(undetermined(change="state", state="recovering"), CONFIG) == "explain"
    assert role_for(update(), CONFIG) == "explain"


def test_hypothesis_is_structured_possible_and_cites_the_revisions_events() -> None:
    llm = FakeLlm(tool(**GOOD_HYPOTHESIS))
    interpreter = Interpreter(CONFIG, llm)
    out = asyncio.run(interpreter.interpret(undetermined(), store_with_facts()))
    assert out is not None and out.published and out.hypothesis is not None
    hyp = out.hypothesis
    assert hyp["kind"] == hyp["ranked"][0]["kind"] == "WIND" and hyp["confidence"] == "possible"
    assert hyp["evidence_event_ids"] == ["gns-000202", "rad-000101"]  # los pone el código
    assert [c["target"] for c in hyp["checks"]] == ["meteo", "receiver"]
    payload = interpreter.payload(undetermined(), out)
    assert payload["role"] == "hypothesis"
    EventFactory(IdAllocator()).make(EventType.INCIDENT_ENRICHED, payload, sim_time=202.0)


def test_hypothesis_naming_a_cause_outside_its_list_or_a_bad_target_is_rejected() -> None:
    bad_text = {**GOOD_HYPOTHESIS, "summary": "Someone has hijacked it, probably."}
    out = asyncio.run(Interpreter(CONFIG, FakeLlm(tool(**bad_text))).interpret(
        undetermined(), store_with_facts()))  # fmt: skip
    assert out is not None and not out.published and any(r.startswith("cause") for r in out.reasons)
    bad_target = {**GOOD_HYPOTHESIS, "checks": [{"target": "wifi", "text": "Check it"}]}
    out = asyncio.run(Interpreter(CONFIG, FakeLlm(tool(**bad_target))).interpret(
        undetermined(), store_with_facts()))  # fmt: skip
    assert (
        out is not None and not out.published and any(r.startswith("format") for r in out.reasons)
    )


def test_empty_ranking_gives_only_the_text() -> None:
    args = {"summary": "The data do not point to any known cause.", "ranked": [], "checks": []}
    out = asyncio.run(Interpreter(CONFIG, FakeLlm(tool(**args))).interpret(
        undetermined(), store_with_facts()))  # fmt: skip
    assert out is not None and out.published and out.hypothesis is None and out.role == "explain"


# --- el proceso del alumno no recibe la verdad ---------------------------------------------------

TRUTH = ("TRUTHMARK1", "TRUTHMARK2", "TRUTHMARK3", "TRUTHMARK4")


def test_the_student_process_does_not_subscribe_to_the_instructors_topics() -> None:
    forbidden = [
        "citadel.pub.evt.sim.instructor.ExerciseInjects.v1",
        "citadel.pub.evt.sim.instructor.InstructorCommand.v1",
        "citadel.pub.evt.sim.player.FaultInjected.v1",
        "citadel.pub.evt.sim.player.FaultCleared.v1",
        "citadel.pub.evt.sim.player.InteractiveModeChanged.v1",
        "citadel.pub.evt.ops.instructor.OperatorMessage.v1",
        "citadel.pub.evt.ai.instructor.AgentReply.v1",
        "citadel.pub.evt.ai.instructor.DebriefGenerated.v1",
    ]
    for topic in forbidden:
        assert not any(topic_matches(p, topic) for p in proc.PATTERNS), topic


def test_the_assistant_package_has_no_http_client_towards_the_platform() -> None:
    banned = {"httpx", "requests", "urllib", "aiohttp", "http"}
    for path in (REPO / "ai-module-py/src/ai_module/assistant").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            assert not banned & set(names), f"{path.name} imports {names}"
            assert "platform_app" not in names


def make_env(event: dict[str, Any], seq: int) -> Envelope:
    return Envelope.model_validate({**event, "seq": seq, "ingestion_time": "2026-10-20T10:00:00Z"})


def build_flow() -> list[Envelope]:
    """`demo` con sus incidentes y, mezclado, todo lo que es del instructor y de la verdad."""
    events = read_events(REPO / "runs/demo/events.jsonl")
    monitor = SituationMonitor(tables="learned")
    factory = EventFactory(IdAllocator())
    t0 = events[0]["event_time"]
    base = {"asset": None, "event_time": t0, "causation_id": None, "ephemeral": False}
    flow: list[dict[str, Any]] = [
        {**base, "event_id": "plr-0001", "type": "SimulationStarted", "source": "platform-player",
         "topic": "citadel.pub.evt.sim.player.SimulationStarted.v1", "sim_time": 0.0,
         "payload": {"scenario": TRUTH[3], "run_id": "r1", "duration_s": 500.0,
                     "total_events": 1}},
        {**base, "event_id": "inj-0001", "type": "ExerciseInjects", "source": "platform-player",
         "topic": "citadel.pub.evt.sim.instructor.ExerciseInjects.v1", "sim_time": 0.0,
         "payload": {"injects": [{"id": TRUTH[0], "type": "hijack", "source": None,
                                  "start_s": 360.0, "end_s": 420.0}]}},
    ]  # fmt: skip
    for event in events:
        flow.append(event)
        if not is_world(event):
            continue
        for _, payload in monitor.push(event):
            draft = factory.make(
                EventType.INCIDENT_UPDATED, payload, sim_time=payload["as_of_sim_time"]
            )
            flow.append(draft.model_dump(mode="json"))
        if event["sim_time"] == 100.0 and event["type"] == "PositionUpdated":
            flow.append({**base, "event_id": "cmd-0001", "type": "InstructorCommand",
                         "source": "platform-player", "sim_time": 100.0,
                         "topic": "citadel.pub.evt.sim.instructor.InstructorCommand.v1",
                         "payload": {"command": "set_wind", "issued_by": "llm", "text": TRUTH[2],
                                     "params": {"from_deg": 0.0, "speed_mps": 19.0,
                                                "ramp_s": 10.0, "duration_s": None}}})  # fmt: skip
            flow.append({**base, "event_id": "ops-0001", "type": "OperatorMessage",
                         "source": "web-instructor", "sim_time": 100.0,
                         "topic": "citadel.pub.evt.ops.instructor.OperatorMessage.v1",
                         "payload": {"conversation_id": "instructor", "text": TRUTH[1],
                                     "context": None}})  # fmt: skip
    return [make_env(e, i + 1) for i, e in enumerate(flow)]


class FakeBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    async def publish(self, draft: Any) -> None:
        self.published.append(draft)


def run_flow(llm: FakeLlm) -> tuple[FakeBus, proc.AssistantProcess]:
    async def main() -> tuple[FakeBus, proc.AssistantProcess]:
        process = proc.AssistantProcess("http://127.0.0.1:1", CONFIG, llm)
        bus = FakeBus()
        process.bus = bus  # type: ignore[assignment]
        for event in build_flow():
            await process.handle(event)
        await process.queue.idle()
        return bus, process

    return asyncio.run(main())


def test_no_truth_reaches_a_prompt_and_only_its_own_texts_are_published() -> None:
    llm = FakeLlm("The drone is off the route. Follow it on the radar.")
    bus, process = run_flow(llm)
    assert llm.calls, "the assistant interpreted nothing"
    everything = " ".join(system + user for _, system, user in llm.calls)
    for mark in TRUTH:
        assert mark not in everything
    # tampoco en lo que guarda en su proceso
    stored = repr((process.store.last, dict(process.store.revisions)))
    assert not any(mark in stored for mark in TRUTH)
    # y solo publica textos suyos: ni IncidentUpdated ni nada del monitor
    assert {d.type for d in bus.published} == {EventType.INCIDENT_ENRICHED}
    assert all(
        d.source == "ai-enricher" and d.payload["decided_by"] == "llm" for d in bus.published
    )


# --- cola del LLM --------------------------------------------------------------------------------


def test_queue_runs_by_priority_and_a_newer_revision_replaces_the_pending_one() -> None:
    order: list[str] = []

    def job(name: str, priority: int, key: str | None = None, expire_s: float | None = None) -> Job:
        async def run() -> None:
            order.append(name)
            await asyncio.sleep(0.01)

        return Job(priority=priority, run=run, key=key, expire_s=expire_s)

    async def main() -> LlmQueue:
        queue = LlmQueue()
        queue.submit(job("first", 3))  # empieza ya
        await asyncio.sleep(0.001)
        queue.submit(job("close", 3, key="a"))
        queue.submit(job("open", 0, key="b"))
        queue.submit(job("close-newer", 3, key="a"))  # sustituye a «close»
        await queue.idle()
        return queue

    queue = asyncio.run(main())
    assert order == ["first", "open", "close-newer"]
    assert ("a", "superseded") in queue.dropped


def test_queue_cancels_the_running_job_when_a_newer_revision_arrives_and_drops_the_expired() -> (
    None
):
    done: list[str] = []

    async def slow() -> None:
        await asyncio.sleep(5)
        done.append("slow")

    async def quick() -> None:
        done.append("quick")

    async def main() -> LlmQueue:
        queue = LlmQueue()
        queue.submit(Job(priority=1, run=slow, key="inc"))
        await asyncio.sleep(0.01)
        queue.submit(Job(priority=1, run=quick, key="inc"))  # la de curso queda vieja
        queue.submit(Job(priority=2, run=quick, key="late", expire_s=0.0))
        await queue.idle()
        return queue

    queue = asyncio.run(main())
    assert done == ["quick"]
    assert ("inc", "cancelled") in queue.dropped and ("late", "expired") in queue.dropped


# --- configuración y glosario ---------------------------------------------------------------------


def test_every_role_has_temperature_zero_and_explicit_sampling() -> None:
    assert isinstance(CONFIG, AssistantConfig)
    for role in CONFIG.roles.values():
        assert role.temperature == 0 and role.top_p == 1.0 and role.max_tokens > 0
        assert role.system_prompt()  # el prompt existe y no está vacío


def test_the_glossary_covers_every_input_of_the_frozen_tables_and_every_facet_state() -> None:
    tables = yaml.safe_load(
        (REPO / "ai-module-py/src/ai_module/situation/tables_learned.yaml").read_text()
    )
    inputs: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "inputs" and isinstance(value, list):
                    inputs.update(x if isinstance(x, str) else x["name"] for x in value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(tables)
    assert inputs and not inputs - set(glossary()["features"])


def test_link_facts_carry_their_age_and_do_not_contradict_the_evidence_in_demo() -> None:
    """En `demo`, al pasar el secuestro a recuperación la evidencia dice «conectado» (lee la
    telemetría) y el último `LinkStatus` aún es de enlace perdido: los hechos dicen de cuándo es
    y que la telemetría ha llegado después."""

    def recovering_link_lines() -> list[str]:
        store = Store()
        monitor = SituationMonitor(tables="learned")
        for event in read_events(REPO / "runs/demo/events.jsonl"):
            if not is_world(event):
                continue
            store.observe(event)
            for _, payload in monitor.push(event):
                store.observe({"type": "IncidentUpdated", "event_id": "ai-9", "payload": payload,
                               "sim_time": payload["as_of_sim_time"]})  # fmt: skip
                if payload["kind"] == "HIJACK" and payload["state"] == "recovering":
                    text = build_input(payload, store).text
                    return [x for x in text.splitlines() if x.startswith("- Command link at")]
        return []

    seen = recovering_link_lines()
    assert len(seen) == 1 and " s ago)" in seen[0]
    assert "telemetry has arrived since" in seen[0]


# --- chats del alumno ---------------------------------------------------------------------------


def question_event(text: str, conversation: str = "monitor", n: int = 5) -> Envelope:
    source = "web-instructor" if conversation == "instructor" else "web-operator"
    return make_env(
        {
            "event_id": f"ops-{n:04d}", "type": "OperatorMessage", "source": source,
            "topic": f"citadel.pub.evt.ops.{conversation}.OperatorMessage.v1", "asset": None,
            "sim_time": 300.0, "event_time": "2026-10-20T10:05:00Z", "causation_id": None,
            "ephemeral": False,
            "payload": {"conversation_id": conversation, "text": text, "context": None},
        },
        900 + n,
    )  # fmt: skip


def chat_flow(questions: list[Envelope], llm: FakeLlm) -> tuple[FakeBus, proc.AssistantProcess]:
    async def main() -> tuple[FakeBus, proc.AssistantProcess]:
        process = proc.AssistantProcess("http://127.0.0.1:1", CONFIG, llm)
        bus = FakeBus()
        process.bus = bus  # type: ignore[assignment]
        for event in build_flow():
            await process.handle(event)
        await process.queue.idle()
        llm.calls.clear()
        bus.published.clear()
        for question in questions:
            await process.handle(question)
        await process.queue.idle()
        return bus, process

    return asyncio.run(main())


def test_a_chat_answer_is_checked_then_streamed_then_published_as_the_chats_reply() -> None:
    llm = FakeLlm(
        "The drone is off the route and the command link is lost. Follow it on the radar."
    )
    bus, _ = chat_flow([question_event("What is happening?")], llm)
    chat = [d for d in bus.published if d.type != EventType.INCIDENT_ENRICHED]
    kinds = [d.type for d in chat]
    assert kinds[0] == EventType.AGENT_ACTIVITY and kinds[-1] == EventType.AGENT_ACTIVITY
    reply = next(d for d in chat if d.type == EventType.AGENT_REPLY)
    assert reply.source == "ai-chat-monitor" and reply.payload["reply_to"] == "ops-0005"
    deltas = [d.payload["delta"] for d in chat if d.type == EventType.AGENT_REPLY_CHUNK]
    assert deltas and "".join(deltas) == reply.payload["text"]  # lo enseñado es lo comprobado
    assert all(d.ephemeral for d in chat if d.type == EventType.AGENT_REPLY_CHUNK)


def test_chat_answers_rejected_twice_get_a_fixed_text_and_llm_errors_say_so() -> None:
    bad = "The GPS is 4567 m off."  # una cifra que no estaba
    bus, _ = chat_flow([question_event("Where is the drone?")], FakeLlm(bad, bad))
    reply = next(d for d in bus.published if d.type == EventType.AGENT_REPLY)
    assert "could not give a reliable answer" in reply.payload["text"]
    bus, _ = chat_flow([question_event("Where is the drone?")], FakeLlm(LlmError("timeout")))
    reply = next(d for d in bus.published if d.type == EventType.AGENT_REPLY)
    assert "not available" in reply.payload["text"]


def test_a_chat_answer_can_deny_a_cause_the_operator_asked_about() -> None:
    # sin la pregunta, nombrar la estima se rechazaría: en `demo` no hubo ninguna
    llm = FakeLlm("No incident points to dead reckoning; the GPS has a fix.")
    bus, _ = chat_flow([question_event("Is the drone using dead reckoning?")], llm)
    reply = next(d for d in bus.published if d.type == EventType.AGENT_REPLY)
    assert "dead reckoning" in reply.payload["text"]
    assert len(llm.calls) == 1  # pasó a la primera


def test_the_chat_prompt_has_the_incidents_the_notes_the_facts_and_the_conversation() -> None:
    llm = FakeLlm("Some answer about the incidents.")
    chat_flow([question_event("What happened?", n=5), question_event("And then?", n=6)], llm)
    first, second = llm.calls[0][2], llm.calls[1][2]
    assert "It is now T+" in first and "Incident 1:" in first and "History:" in first
    assert "Facts now:" in first and "Question from the operator: What happened?" in first
    assert "Note already written for the operator" in first
    # la historia con sus horas, escrita por el código (el nombre nuevo y el inicio, separados)
    assert "opened as Command link lost at T+06:12" in first or "opened as Wind" in first
    assert "renamed to Hijack at T+06:28" in first or "closed at" in first
    assert "Operator: What happened?" in second and "Some answer" in second  # la conversación


def test_the_instructors_chat_never_reaches_the_students_assistant() -> None:
    llm = FakeLlm("An answer.")
    bus, process = chat_flow([question_event("TRUTHMARK2 ask", "instructor")], llm)
    assert not llm.calls and not bus.published
    assert "instructor" not in process.store.history


def test_a_question_is_answered_with_the_situation_of_when_it_was_asked() -> None:
    store = store_with_facts()
    snapshot = store.snapshot()
    store.observe({"type": "TrackUpdated", "sim_time": 400.0, "event_id": "rad-000200",
                   "payload": {"x": 900.0, "y": 900.0}})  # fmt: skip
    store.texts["inc-0001"] = "A text published later."
    assert snapshot.now == 202.0 and "inc-0001" not in snapshot.texts
    assert snapshot.last["TrackUpdated"][1]["y"] == 37.0


def test_the_incident_history_has_each_change_with_its_own_time() -> None:
    from ai_module.assistant.chat import path_text

    revisions = [
        update(change="opened", name="Command link lost", as_of_sim_time=372.0),
        update(change="renamed", name="Hijack", as_of_sim_time=388.0, revision=2),
        update(change="state", state="recovering", as_of_sim_time=413.0, revision=3),
        update(change="closed", state="closed", as_of_sim_time=478.0, revision=4),
    ]
    assert path_text(revisions) == (
        "opened as Command link lost at T+06:12; renamed to Hijack at T+06:28; "
        "recovering at T+06:53; closed at T+07:58"
    )


def test_a_stated_cause_is_rejected_and_the_incidents_own_check_wording_is_allowed() -> None:
    hijack = update(kind="HIJACK", name="Hijack", evidence=[], context=[])
    for said in ("Wind was the cause of the deviation.", "The cause was the wind."):
        assert any(r.startswith("cause") for r in verdict(said, hijack)), said
    no_fix = update(
        kind="GPS_NO_FIX", name="GPS position lost", evidence=[], context=[],
        checks=["Watch the drift: the drone navigates by dead reckoning"],
    )  # fmt: skip
    assert verdict("The drone now navigates by dead reckoning, so watch the drift.", no_fix) == []
    # sin esa frase en su «qué comprobar», nombrar la estima sí se rechaza
    other = update(kind="GPS_NO_FIX", name="GPS position lost", evidence=[], context=[])
    assert any(r.startswith("cause") for r in verdict("It is using dead reckoning.", other))


def test_process_tags_keep_ids_apart_however_many_events_each_process_publishes() -> None:
    """Los procesos comparten `ai-`, `act-` y `chk-` en un bus que rechaza un id repetido: con la
    etiqueta de cada uno no se pisan aunque pasen de mil eventos (los rangos de antes sí)."""
    from poc_contracts.envelope import EventDraft  # noqa: F401  (el formato lo valida el contrato)
    from poc_contracts.topics import matches_id_prefix

    monitor, alumno, instructor = IdAllocator("m"), IdAllocator("a"), IdAllocator("i")
    ids: list[str] = []
    for allocator in (monitor, alumno, instructor):
        for prefix in ("ai", "act", "chk"):
            ids += [allocator.next(prefix) for _ in range(2500)]
    assert len(ids) == len(set(ids))
    assert monitor.next("ai") == "ai-m-2501" and alumno.next("act") == "act-a-2501"
    # el formato lo admite el contrato; una etiqueta mal formada, no
    assert matches_id_prefix("ai-a-0001", EventType.INCIDENT_ENRICHED)
    assert matches_id_prefix("ai-0001", EventType.INCIDENT_ENRICHED)  # sin etiqueta sigue valiendo
    assert matches_id_prefix("act-i-12345", EventType.AGENT_ACTIVITY)
    for bad in ("ai-aa-0001", "ai-A-0001", "ai-a-", "gps-a-0001"):
        assert not matches_id_prefix(bad, EventType.INCIDENT_ENRICHED), bad
    # `inc-` e `inv-` no se comparten: no llevan etiqueta
    assert monitor.next("inc") == "inc-0001" and alumno.next("inv") == "inv-0001"
    with pytest.raises(ValueError, match="one lowercase letter"):
        IdAllocator("ab")
