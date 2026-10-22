"""Los seis `events.jsonl` por el detector y el monitor, con LLM falsos de todo tipo: cada aviso
(Raised/Updated/Cleared) recibe al menos una respuesta con su `causation_id`, dentro del tope."""

import asyncio
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from agent_helpers import (
    NO_CHECKS,
    FakeLlm,
    call,
    make_runtime,
    reset_ids,
    run,
    text_response,
    tool_response,
)

from ai_module.detect_file import read_events
from ai_module.detector import Detector
from ai_module.monitor import Monitor
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope

RUNS = Path(__file__).resolve().parents[2] / "runs"
SCENARIOS = ["nominal", "viento", "spoofing", "secuestro", "fallos", "demo"]
DETECTIONS = (
    EventType.DETECTION_RAISED,
    EventType.DETECTION_UPDATED,
    EventType.DETECTION_CLEARED,
)
RESPONSES = (EventType.ANOMALY_DETECTED, EventType.ALERT_CLOSED, EventType.DETECTION_ACKNOWLEDGED)


def publisher(messages: list, tools: list, sampling: dict) -> Any:
    """LLM falso que siempre responde bien según lo que dice el estado del prompt."""
    user = messages[1]["content"]
    detections = re.findall(r"detección (det-\d+)", user)
    pending = list(
        dict.fromkeys(
            re.findall(r"(?:Nueva detección|ha empeorado:?|La detección) (det-\d+)", user)
        )
    )
    pending = list(dict.fromkeys(detections)) or pending
    open_alert = re.search(r"Alertas abiertas: (ai-\d+)", user)
    last_open = re.search(r"de la alerta (ai-\d+)", user)
    if last_open:
        return tool_response(call("close_alert", alert_id=last_open.group(1), reason="normalizada"))
    if open_alert:
        return tool_response(
            call(
                "acknowledge_detection",
                detection_ids=pending,
                alert_id=open_alert.group(1),
                reason="sigue igual",
            )  # fmt: skip
        )
    evidence = re.findall(r'"trigger_event_ids":\[([^\]]*)\]', user)[0]
    ids = re.findall(r'"([^"]+)"', evidence) or ["gps-000001"]
    return tool_response(
        call(
            "publish_alert",
            detection_ids=pending,
            checks=NO_CHECKS,
            cause="UNKNOWN",
            severity="medium",
            confidence=0.4,
            summary="prueba",
            explanation="e",
            recommendation="r",
            evidence_event_ids=ids[:2],
        )  # fmt: skip
    )


def texter(messages: list, tools: list, sampling: dict) -> Any:
    return text_response("Creo que es viento, pero no llamo a nada.")


def garbage(messages: list, tools: list, sampling: dict) -> Any:
    bad = tool_response(call("get_events"))
    bad.tool_calls[0] = type(bad.tool_calls[0])("c", "publish_alert", "{no json")
    return bad if len(messages) % 2 else tool_response(call("hackear"))


def exploding(messages: list, tools: list, sampling: dict) -> Any:
    return RuntimeError("vLLM caído")


class Sleeper(FakeLlm):
    async def complete(self, *args: Any, **kwargs: Any):
        await asyncio.sleep(10)


def to_envelope(draft: Any, seq: int) -> Envelope:
    return Envelope(**draft.model_dump(), seq=seq, ingestion_time="2026-10-20T10:00:00.000Z")


def drive(tmp_path: Path, name: str, llm: FakeLlm, *, fast_timeout: bool = False):
    """Detector + monitor sobre un escenario. Cada aviso se atiende en cuanto sale."""
    reset_ids()
    rt, published = make_runtime(tmp_path, llm)
    monitor = Monitor(rt)
    if fast_timeout:
        monitor.config = replace(monitor.config, max_invocation_s=0.05, llm_timeout_s=0.05)
    detector = Detector()
    detection_events: list[Envelope] = []
    seq = 0
    for event in read_events(RUNS / name / "events.jsonl"):
        seq += 1
        envelope = to_envelope(event, seq)
        rt.factory.observe(envelope)
        rt.clock.observe(envelope.sim_time)
        rt.index.add(envelope)
        for detection in detector.feed(event):
            seq += 1
            det = to_envelope(detection, seq)
            detection_events.append(det)
            rt.index.add(det)
            run(monitor.handle_batch([det]))
    return rt, published, monitor, detection_events


def check_everything_is_answered(rt, published, detection_events, monitor) -> None:
    answered: dict[str, list] = {}
    for e in published:
        if e.type in RESPONSES and e.causation_id:
            answered.setdefault(e.causation_id, []).append(e)
    for det in detection_events:
        assert det.event_id in answered, f"{det.type.value} {det.event_id} sin respuesta"
    cap = monitor.config.max_iterations
    assert all(r["iterations"] <= cap for r in rt.trace.records)
    # en la traza, lo publicado coincide con lo que salió al bus
    traced = {p["event_id"] for r in rt.trace.records for p in r["published"]}
    assert traced == {e.event_id for e in published if e.type in RESPONSES}


@pytest.mark.parametrize("name", SCENARIOS)
@pytest.mark.parametrize(
    "policy",
    [publisher, texter, garbage, exploding],
    ids=["publisher", "texter", "garbage", "error"],
)
def test_every_detection_gets_a_response(tmp_path: Path, name: str, policy: Any) -> None:
    rt, published, monitor, dets = drive(tmp_path, name, FakeLlm(policy))
    assert (name == "nominal") == (not dets)
    check_everything_is_answered(rt, published, dets, monitor)


@pytest.mark.parametrize("name", ["viento", "fallos"])
def test_every_detection_gets_a_response_when_the_llm_times_out(tmp_path: Path, name: str) -> None:
    rt, published, monitor, dets = drive(tmp_path, name, Sleeper(texter), fast_timeout=True)
    check_everything_is_answered(rt, published, dets, monitor)


def test_the_publisher_policy_gives_one_alert_per_episode_in_fallos(tmp_path: Path) -> None:
    """Con un LLM que responde bien al estado, `fallos` acaba sin alertas abiertas y sin
    UNKNOWN de fallback."""
    rt, published, monitor, dets = drive(tmp_path, "fallos", FakeLlm(publisher))
    assert rt.state.open_alerts() == []
    assert not any(r["fallback"] for r in rt.trace.records)
    alerts = [e for e in published if e.type == EventType.ANOMALY_DETECTED]
    assert len(alerts) >= 2
    assert json.dumps(sorted(e.event_id for e in alerts))  # ids únicos y serializables
    assert len({e.event_id for e in published if e.type in RESPONSES}) == len(
        [e for e in published if e.type in RESPONSES]
    )
