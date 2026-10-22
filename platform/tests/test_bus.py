"""Bus y timeline: comodines, `seq`, efímeros, orden de entrega y handlers asíncronos."""

import asyncio

import pytest

from helpers import scenario_config
from platform_app.bus import Bus
from platform_app.generator.events import make_event
from platform_app.timeline import Timeline
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.topics import topic_for

CONFIG = scenario_config()


def gps(number: int, sim_time: float = 1.0) -> EventDraft:
    payload = {
        "x": 1.0,
        "y": 2.0,
        "alt_m": 60.0,
        "speed_mps": 15.0,
        "heading_deg": 10.0,
        "fix": "3d",
        "sats": 14,
        "hdop": 0.8,
    }
    return make_event(CONFIG, EventType.POSITION_UPDATED, sim_time, number, payload)


def wind(number: int, sim_time: float = 10.0) -> EventDraft:
    payload = {"station_id": "meteo-1", "speed_mps": 2.0, "gust_mps": 3.0, "from_deg": 300.0}
    return make_event(CONFIG, EventType.WIND_REPORTED, sim_time, number, payload)


def activity(number: int) -> EventDraft:
    """Efímero (`AgentActivity`)."""
    payload = {
        "agent": "monitor",
        "state": "started",
        "invocation_id": "inv-0001",
        "causation_id": None,
    }
    return EventDraft(
        event_id=f"act-{number:04d}",
        topic=topic_for(EventType.AGENT_ACTIVITY),
        type=EventType.AGENT_ACTIVITY,
        source="ai-module",
        asset=None,
        sim_time=1.0,
        event_time="2026-10-20T10:00:01Z",
        ephemeral=True,
        payload=payload,
    )


def test_seq_and_ingestion_time_are_set_by_the_bus() -> None:
    bus = Bus()
    first, second = bus.publish(gps(1)), bus.publish(wind(1))
    assert (first.seq, second.seq) == (1, 2)
    assert first.ingestion_time.endswith("Z") and "." in first.ingestion_time
    assert len(first.ingestion_time.split(".")[1]) == 4  # milisegundos + Z


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("citadel.pub.evt.air.d1.>", ["gps"]),
        ("citadel.pub.evt.>", ["gps", "wind"]),
        ("citadel.pub.evt.*.*.*.v1", ["gps", "wind"]),
        ("citadel.pub.evt.env.zone1.WindReported.v1", ["wind"]),
        ("citadel.pub.evt.air.d1.*", []),  # los topics tienen siete segmentos
        ("citadel.pub.evt.ai.>", []),
    ],
)
def test_wildcards(pattern: str, expected: list[str]) -> None:
    bus = Bus()
    got: list[str] = []
    bus.subscribe(pattern, lambda e: got.append("gps" if e.type == "PositionUpdated" else "wind"))
    bus.publish(gps(1))
    bus.publish(wind(1))
    assert got == expected


def test_invalid_pattern_is_rejected() -> None:
    with pytest.raises(ValueError):
        Bus().subscribe("citadel.pub.>.x", lambda e: None)


def test_unsubscribe_stops_delivery() -> None:
    bus = Bus()
    got: list[Envelope] = []
    sub = bus.subscribe("citadel.>", got.append)
    bus.publish(gps(1))
    bus.unsubscribe(sub)
    bus.publish(gps(2))
    assert len(got) == 1


def test_ephemeral_events_are_delivered_but_not_stored() -> None:
    bus = Bus()
    got: list[Envelope] = []
    bus.subscribe("citadel.>", got.append)
    bus.publish(activity(1))
    bus.publish(gps(1))
    assert [e.type for e in got] == ["AgentActivity", "PositionUpdated"]
    assert [e.type for e in bus.timeline.all()] == ["PositionUpdated"]


def test_reentrant_publish_keeps_seq_order_for_every_subscriber() -> None:
    bus = Bus()
    seen_a: list[int] = []
    seen_b: list[int] = []

    def reply(event: Envelope) -> None:
        seen_a.append(event.seq)
        if event.type == "PositionUpdated":
            bus.publish(wind(1))

    bus.subscribe("citadel.>", reply)
    bus.subscribe("citadel.>", lambda e: seen_b.append(e.seq))
    bus.publish(gps(1))
    assert seen_a == seen_b == [1, 2]


def test_failing_handler_does_not_break_the_publisher() -> None:
    bus = Bus()
    got: list[Envelope] = []

    def boom(event: Envelope) -> None:
        raise RuntimeError("boom")

    bus.subscribe("citadel.>", boom)
    bus.subscribe("citadel.>", got.append)
    bus.publish(gps(1))
    assert len(got) == 1


def test_reset_clears_timeline_and_restarts_seq_but_keeps_subscriptions() -> None:
    bus = Bus()
    got: list[Envelope] = []
    bus.subscribe("citadel.>", got.append)
    bus.publish(gps(1))
    bus.reset()
    assert len(bus.timeline) == 0
    assert bus.publish(gps(1)).seq == 1
    assert len(got) == 2


def test_async_handlers_receive_events_in_order() -> None:
    async def scenario() -> list[int]:
        bus = Bus()
        got: list[int] = []

        async def handler(event: Envelope) -> None:
            await asyncio.sleep(0)
            got.append(event.seq)

        bus.subscribe("citadel.>", handler)
        for n in range(5):
            bus.publish(gps(n + 1))
        await asyncio.sleep(0.05)
        return got

    assert asyncio.run(scenario()) == [1, 2, 3, 4, 5]


def test_timeline_queries_by_source_type_and_time(tmp_path) -> None:
    timeline = Timeline()
    bus = Bus(timeline)
    for n in range(1, 6):
        bus.publish(gps(n, sim_time=float(n)))
    bus.publish(wind(1, sim_time=3.0))
    found, truncated = timeline.query(source="d1-gps", since=2.0, until=4.0)
    assert [e.sim_time for e in found] == [2.0, 3.0, 4.0] and not truncated
    found, truncated = timeline.query(type=EventType.WIND_REPORTED)
    assert [e.event_id for e in found] == ["met-0001"]
    found, truncated = timeline.query(source="d1-gps", limit=2)
    assert [e.sim_time for e in found] == [4.0, 5.0] and truncated
    path = timeline.dump(tmp_path / "a" / "timeline.jsonl")
    lines = path.read_text().splitlines()
    assert len(lines) == 6 and Envelope.model_validate_json(lines[0]).seq == 1
