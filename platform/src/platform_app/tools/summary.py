"""Tool `get_flight_summary`: resumen del vuelo para el informe. Nunca incluye el dominio `sim`."""

import math

from poc_contracts.enums import AlertStatus, Cause, EventType, Rule
from poc_contracts.payloads import AnomalyDetected, MissionCompleted
from poc_contracts.tools import (
    AlertsByCause,
    DetectionsByRule,
    DistanceBySource,
    FlightSummary,
    NoArgs,
    ReachedWaypoint,
)

from ..generator.controller import BASE
from .context import ToolContext
from .events import alert_statuses, mission_planned
from .metrics import GPS_SOURCE, RADAR_SOURCE


def _path_length(ctx: ToolContext, source: str, event_type: EventType) -> float | None:
    events, _ = ctx.events(source=source, type=event_type)
    if not events:
        return None
    pts = [(e.payload["x"], e.payload["y"]) for e in events]
    return round(sum(math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False)), 1)


def get_flight_summary(ctx: ToolContext, args: NoArgs) -> FlightSummary:
    plan = mission_planned(ctx)
    completed_event = ctx.latest(EventType.MISSION_COMPLETED)
    completed = (
        MissionCompleted.model_validate(completed_event.payload) if completed_event else None
    )
    reached, _ = ctx.events(type=EventType.WAYPOINT_REACHED)
    raised, _ = ctx.events(type=EventType.DETECTION_RAISED)

    counts_rule = {rule.value: 0 for rule in Rule}
    for e in raised:
        counts_rule[e.payload["rule"]] += 1
    counts_cause = {cause.value: 0 for cause in Cause}
    # una cadena de `supersedes` es una sola alerta: se cuenta la que está en vigor
    in_force = [e for e, s in alert_statuses(ctx) if s != AlertStatus.SUPERSEDED]
    for e in in_force:
        counts_cause[AnomalyDetected.model_validate(e.payload).cause.value] += 1
    statuses = [s for _, s in alert_statuses(ctx)]

    return FlightSummary(
        mission_id=plan.mission_id,
        duration_s=completed_event.sim_time if completed_event else ctx.cutoff(),
        mission_completed=bool(completed and completed.completed),
        completion_reason=completed.reason if completed else None,
        distance_m=DistanceBySource(
            gps=_path_length(ctx, GPS_SOURCE, EventType.POSITION_UPDATED),
            radar=_path_length(ctx, RADAR_SOURCE, EventType.TRACK_UPDATED),
        ),
        waypoints_planned=[w.id for w in plan.waypoints if w.id != BASE],
        waypoints_reached=[
            ReachedWaypoint(waypoint_id=e.payload["waypoint_id"], sim_time=e.sim_time)
            for e in reached
            if e.payload["waypoint_id"] != BASE
        ],
        detections_by_rule=DetectionsByRule(**counts_rule),
        alerts_by_cause=AlertsByCause(**counts_cause),
        alerts_open=statuses.count(AlertStatus.OPEN),
        alerts_closed=statuses.count(AlertStatus.CLOSED),
    )
