"""Eventos sintéticos para probar el detector sin ficheros."""

from collections import defaultdict
from typing import Any

from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.topics import EVENT_SPECS, asset_for, routing_for, source_for, topic_for

ROUTE = [(0.0, 0.0), (1000.0, 0.0), (0.0, 0.0)]


def _event_time(sim_time: float) -> str:
    total = int(sim_time)
    return f"2026-10-20T10:{total // 60:02d}:{total % 60:02d}Z"


class Maker:
    """Fabrica eventos con ids secuenciales por prefijo, como el generador."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def event(self, event_type: EventType, t: float, payload: dict[str, Any]) -> EventDraft:
        spec = EVENT_SPECS[event_type]
        self._counts[spec.id_prefix] += 1
        return EventDraft(
            event_id=f"{spec.id_prefix}-{self._counts[spec.id_prefix]:06d}",
            topic=topic_for(event_type),
            type=event_type,
            source=source_for(event_type),
            asset=asset_for(spec.domain, routing_for(event_type)),
            sim_time=t,
            event_time=_event_time(t),
            payload=payload,
        )

    def plan(self, route: list[tuple[float, float]] = ROUTE) -> EventDraft:
        waypoints = [
            {"id": f"P{i}", "x": x, "y": y, "eta_s": float(i)} for i, (x, y) in enumerate(route)
        ]
        return self.event(
            EventType.MISSION_PLANNED,
            0.0,
            {
                "mission_id": "TEST",
                "cruise_speed_mps": 15.0,
                "altitude_m": 60.0,
                "acceptance_radius_m": 20.0,
                "waypoints": waypoints,
            },
        )

    def gps(
        self, t: float, x: float, y: float, fix: str = "3d", sats: int = 14, hdop: float = 0.8
    ) -> EventDraft:
        payload = {
            "x": x,
            "y": y,
            "alt_m": 60.0,
            "speed_mps": 15.0,
            "heading_deg": 90.0,
            "fix": fix,
            "sats": sats,
            "hdop": hdop,
        }
        return self.event(EventType.POSITION_UPDATED, t, payload)

    def radar(self, t: float, x: float, y: float) -> EventDraft:
        payload = {
            "radar_id": "radar-1",
            "x": x,
            "y": y,
            "speed_mps": 15.0,
            "course_deg": 90.0,
            "quality": 0.9,
        }
        return self.event(EventType.TRACK_UPDATED, t, payload)

    def wind(self, t: float) -> EventDraft:
        payload = {"station_id": "meteo-1", "speed_mps": 3.0, "gust_mps": 4.0, "from_deg": 300.0}
        return self.event(EventType.WIND_REPORTED, t, payload)

    def link(self, t: float) -> EventDraft:
        payload = {"controller_id": "GCS-1", "rssi_dbm": -62.0, "latency_ms": 45.0}
        return self.event(EventType.LINK_STATUS, t, payload)

    def battery(self, t: float) -> EventDraft:
        return self.event(EventType.BATTERY_STATUS, t, {"battery_pct": 90.0, "voltage_v": 22.9})

    def started(self, t: float = 0.0) -> EventDraft:
        payload = {"scenario": "test", "run_id": "r1", "duration_s": 100.0, "total_events": 10}
        return self.event(EventType.SIMULATION_STARTED, t, payload)

    def reset(self, t: float = 0.0) -> EventDraft:
        return self.event(EventType.SIMULATION_RESET, t, {})

    def finished(self, t: float) -> EventDraft:
        return self.event(EventType.SIMULATION_FINISHED, t, {"scenario": "test", "run_id": "r1"})

    def completed(self, t: float) -> EventDraft:
        payload = {"mission_id": "TEST", "completed": True, "reason": "returned_to_base"}
        return self.event(EventType.MISSION_COMPLETED, t, payload)

    def fault(self, t: float, source: str = "gps", mode: str = "mute") -> EventDraft:
        payload = {"source": source, "mode": mode, "origin": "manual"}
        return self.event(EventType.FAULT_INJECTED, t, payload)


def envelope(draft: EventDraft, seq: int = 1) -> Envelope:
    """El mismo evento ya publicado por el bus."""
    return Envelope(**draft.model_dump(), seq=seq, ingestion_time="2026-10-20T08:00:00.000Z")


def steady(maker: Maker, t: float, skip: tuple[str, ...] = ()) -> list[EventDraft]:
    """Los eventos de un vuelo normal en el instante entero `t` (sobre la ruta, sin ruido).

    `skip`: nombres de tipo que se omiten, p. ej. `"TrackUpdated"`.
    """
    x = float(t)
    events = [maker.gps(t, x, 0.0)]
    if t % 2 == 0:
        events.append(maker.radar(t, x, 0.0))
    if t % 5 == 0:
        events.append(maker.link(t))
    if t % 10 == 0:
        events += [maker.wind(t), maker.battery(t)]
    return [e for e in events if e.type.value not in skip]
