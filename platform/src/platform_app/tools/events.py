"""Tools `get_events`, `get_mission_plan` y `get_my_alerts`."""

from poc_contracts.enums import AlertStatus, EventType
from poc_contracts.envelope import Envelope
from poc_contracts.payloads import AlertClosed, AnomalyDetected, MissionPlanned
from poc_contracts.tools import (
    AlertSummary,
    CompactEvent,
    GetEventsArgs,
    GetEventsResult,
    GetMyAlertsArgs,
    MissionPlanResult,
    MyAlertsResult,
    NoArgs,
)
from poc_contracts.topics import TOOL_SOURCE_TO_ENVELOPE_SOURCE

from .context import ToolContext, ToolFailure, format_t


def compact(event: Envelope) -> CompactEvent:
    """Id, tipo, `sim_time`, `t` y los campos del payload (sin el resto del sobre)."""
    return CompactEvent(
        event_id=event.event_id,
        type=event.type,
        sim_time=event.sim_time,
        t=format_t(event.sim_time),
        **event.payload,
    )


def get_events(ctx: ToolContext, args: GetEventsArgs) -> GetEventsResult:
    found, truncated = ctx.events(
        source=TOOL_SOURCE_TO_ENVELOPE_SOURCE[args.source],
        type=args.type,
        since=args.since,
        until=args.until,
        limit=args.last_n,
    )
    return GetEventsResult(events=[compact(e) for e in found], truncated=truncated)


def mission_planned(ctx: ToolContext) -> MissionPlanned:
    event = ctx.latest(EventType.MISSION_PLANNED)
    if event is None:
        raise ToolFailure("there is no mission plan yet: the simulation has not started")
    return MissionPlanned.model_validate(event.payload)


def next_waypoint(ctx: ToolContext, plan: MissionPlanned, until: float | None = None) -> str | None:
    """Siguiente waypoint pendiente según los `WaypointReached` hasta `until` (o hasta ahora)."""
    reached, _ = ctx.events(type=EventType.WAYPOINT_REACHED, until=until)
    last = max((int(e.payload["index"]) for e in reached), default=0)
    return plan.waypoints[last + 1].id if last + 1 < len(plan.waypoints) else None


def get_mission_plan(ctx: ToolContext, args: NoArgs) -> MissionPlanResult:
    plan = mission_planned(ctx)
    return MissionPlanResult(**plan.model_dump(), next_waypoint=next_waypoint(ctx, plan))


def alert_statuses(ctx: ToolContext) -> list[tuple[Envelope, AlertStatus]]:
    """Alertas del monitor (`AnomalyDetected`) con su estado, reconstruido de los eventos:
    `superseded` si otra la sustituye, `closed` si hay un `AlertClosed`, `open` si no."""
    alerts, _ = ctx.events(type=EventType.ANOMALY_DETECTED)
    closed_events, _ = ctx.events(type=EventType.ALERT_CLOSED)
    closed = {AlertClosed.model_validate(e.payload).alert_id for e in closed_events}
    superseded = {
        s for e in alerts if (s := AnomalyDetected.model_validate(e.payload).supersedes) is not None
    }
    out: list[tuple[Envelope, AlertStatus]] = []
    for event in alerts:
        alert_id = event.payload["alert_id"]
        if alert_id in superseded:
            status = AlertStatus.SUPERSEDED
        elif alert_id in closed:
            status = AlertStatus.CLOSED
        else:
            status = AlertStatus.OPEN
        out.append((event, status))
    return out


def get_my_alerts(ctx: ToolContext, args: GetMyAlertsArgs) -> MyAlertsResult:
    alerts = []
    for event, status in alert_statuses(ctx):
        if args.only_open and status != AlertStatus.OPEN:
            continue
        p = AnomalyDetected.model_validate(event.payload)
        alerts.append(
            AlertSummary(
                alert_id=p.alert_id,
                cause=p.cause,
                severity=p.severity,
                confidence=p.confidence,
                summary=p.summary,
                status=status,
                sim_time=event.sim_time,
            )
        )
    return MyAlertsResult(alerts=alerts)
