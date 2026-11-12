"""Tools `get_events`, `get_mission_plan` y `get_my_alerts`."""

from poc_contracts.enums import AlertStatus, EventSource, EventType, ToolSource
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

from .context import ToolContext, ToolFailure, format_t, resolve_window


def compact(event: Envelope, feed: ToolSource | None = None) -> CompactEvent:
    """Id, tipo, `sim_time`, `t` y los campos del payload (sin el resto del sobre); en
    `source: all`, además `feed` (la fuente del evento, v0.17: `source` es del payload)."""
    extra = {"feed": feed.value} if feed is not None else {}
    return CompactEvent(
        event_id=event.event_id,
        type=event.type,
        sim_time=event.sim_time,
        t=format_t(event.sim_time),
        **event.payload,
        **extra,
    )


ALL_DEFAULT_PER_SOURCE = 3
MAX_ALL_EVENTS = (
    60  # tope de `source: all`: el módulo recorta a ~4000 caracteres lo que se devuelve
)
SOURCE_ORDER = {source: index for index, source in enumerate(ToolSource)}


def get_events(ctx: ToolContext, args: GetEventsArgs) -> GetEventsResult:
    since, until, clipped = resolve_window(ctx, args.since, args.until, args.last_s)
    notes: list[str] = []
    if clipped is not None:
        notes.append(
            f"until was later than the current time: it was clipped to {format_t(clipped)}"
        )
    if args.source in (None, EventSource.ALL):
        events, truncated = _all_sources(ctx, args, since, until)
        if truncated:
            notes.append(
                "showing only the most recent events of each source (use one source or a "
                "narrower window to see more)"
            )
    else:
        found, truncated = ctx.events(
            source=TOOL_SOURCE_TO_ENVELOPE_SOURCE[ToolSource(args.source)],
            type=args.type,
            since=since,
            until=until,
            limit=args.last_n,
        )
        events = [compact(e) for e in found]
    return GetEventsResult(
        events=events,
        truncated=truncated,
        until_clipped_to=clipped,
        note="; ".join(notes) or None,
    )


def _all_sources(
    ctx: ToolContext, args: GetEventsArgs, since: float | None, until: float | None
) -> tuple[list[CompactEvent], bool]:
    """Los eventos de todas las fuentes de la ventana (v0.17), por tiempo y cada uno con su
    fuente (`feed`): hasta `last_n` por fuente (3 si no se pidió) y `MAX_ALL_EVENTS` en total."""
    per_source = args.last_n if "last_n" in args.model_fields_set else ALL_DEFAULT_PER_SOURCE
    collected: list[tuple[float, int, int, Envelope, ToolSource]] = []
    truncated = False
    for source in ToolSource:
        found, cut = ctx.events(
            source=TOOL_SOURCE_TO_ENVELOPE_SOURCE[source],
            type=args.type,
            since=since,
            until=until,
            limit=per_source,
        )
        truncated = truncated or cut
        collected += [(e.sim_time, SOURCE_ORDER[source], e.seq, e, source) for e in found]
    collected.sort(key=lambda row: row[:3])
    if len(collected) > MAX_ALL_EVENTS:
        collected, truncated = collected[len(collected) - MAX_ALL_EVENTS :], True
    return [compact(e, feed=source) for *_, e, source in collected], truncated


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
                phase=p.phase,
            )
        )
    return MyAlertsResult(alerts=alerts)
