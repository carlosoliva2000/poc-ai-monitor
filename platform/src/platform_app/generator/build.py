"""Construye `runs/<escenario>/` a partir de un escenario: plan, verdad, eventos y etiquetas.

Un único `random.Random(seed)` da todo el ruido. Se genera **todo** (también lo que un fallo
programado va a silenciar) y después se filtra: así `fallos` tiene exactamente los mismos
eventos que `nominal` menos los silenciados.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from poc_contracts.enums import Cause, EventType, LabelType, Rule, SensorSource
from poc_contracts.envelope import EventDraft
from poc_contracts.run_files import (
    Label,
    LabelsFile,
    PlanFile,
    PlanSample,
    TruthFile,
    TruthSample,
    TruthWind,
)
from poc_contracts.scenario import ScenarioConfig
from poc_contracts.topics import EVENT_SPECS, asset_for, routing_for, source_for, topic_for

from ..paths import RUNS_DIR
from . import sensors
from .controller import STEP_S, Flight, fly
from .disturbances import wind_at

EVAL_MARGIN_S = 60.0  # la ventana de evaluación acaba 60 s después de la anomalía

# Tipo de evento que reporta cada fuente (para silenciarla)
SOURCE_EVENT: dict[SensorSource, EventType] = {
    SensorSource.GPS: EventType.POSITION_UPDATED,
    SensorSource.RADAR: EventType.TRACK_UPDATED,
    SensorSource.METEO: EventType.WIND_REPORTED,
    SensorSource.LINK: EventType.LINK_STATUS,
    SensorSource.BATTERY: EventType.BATTERY_STATUS,
}

# Orden de los eventos con el mismo `sim_time`: misión, fallos y después cada fuente
_RANK: dict[EventType, int] = {
    **dict.fromkeys(
        [
            EventType.MISSION_PLANNED,
            EventType.MISSION_STARTED,
            EventType.WAYPOINT_REACHED,
            EventType.MISSION_COMPLETED,
        ],
        0,
    ),
    **dict.fromkeys([EventType.FAULT_INJECTED, EventType.FAULT_CLEARED], 1),
    EventType.POSITION_UPDATED: 2,
    EventType.TRACK_UPDATED: 3,
    EventType.WIND_REPORTED: 4,
    EventType.LINK_STATUS: 5,
    EventType.BATTERY_STATUS: 6,
}

# Anchura mínima del número del id: gps-000061, rad-000042, met-0008…
_ID_WIDTH = {"gps": 6, "rad": 6}


@dataclass(frozen=True)
class Run:
    """Todo lo que escribe el generador para un escenario."""

    name: str
    plan: PlanFile
    truth: TruthFile
    events: list[EventDraft]
    labels: LabelsFile


def event_time(t0: str, sim_time: float) -> str:
    """`t0 + sim_time` en ISO 8601 UTC; con milisegundos solo si hacen falta."""
    base = datetime.fromisoformat(t0).astimezone(UTC) + timedelta(seconds=sim_time)
    if base.microsecond == 0:
        return base.strftime("%Y-%m-%dT%H:%M:%SZ")
    return base.strftime("%Y-%m-%dT%H:%M:%S.") + f"{base.microsecond // 1000:03d}Z"


def make_event(
    config: ScenarioConfig, event_type: EventType, sim_time: float, number: int, payload: dict
) -> EventDraft:
    """Evento del generador (sin `seq` ni `ingestion_time`), validado."""
    spec = EVENT_SPECS[event_type]
    width = _ID_WIDTH.get(spec.id_prefix, 4)
    return EventDraft(
        event_id=f"{spec.id_prefix}-{number:0{width}d}",
        topic=topic_for(event_type),
        type=event_type,
        source=source_for(event_type),
        asset=asset_for(spec.domain, routing_for(event_type)),
        sim_time=sim_time,
        event_time=event_time(config.t0, sim_time),
        payload=payload,
    )


def _plan_flight(config: ScenarioConfig) -> tuple[Flight, list[float]]:
    """Vuelo sin perturbaciones y `eta_s` de cada punto de la ruta."""
    plan = fly(config, perturbed=False)
    if not plan.completed:
        raise ValueError("el plan no se completa dentro de max_duration_s")
    etas = [0.0] * len(plan.route)
    for n, i in plan.reached:
        etas[i] = round(n * STEP_S, 6)
    return plan, etas


def _mission_events(config: ScenarioConfig, flight: Flight, etas: list[float]) -> list[EventDraft]:
    m, d = config.mission, config.drone
    waypoints = [
        {"id": wid, "x": round(x, 1), "y": round(y, 1), "eta_s": eta}
        for wid, (x, y), eta in zip(flight.route_ids, flight.route, etas, strict=True)
    ]
    steps: list[tuple[EventType, float, dict]] = [
        (
            EventType.MISSION_PLANNED,
            0.0,
            {
                "mission_id": m.id,
                "cruise_speed_mps": d.cruise_speed_mps,
                "altitude_m": d.altitude_m,
                "acceptance_radius_m": d.acceptance_radius_m,
                "waypoints": waypoints,
            },
        ),
        (EventType.MISSION_STARTED, 0.0, {"mission_id": m.id}),
    ]
    for n, i in flight.reached:
        steps.append(
            (
                EventType.WAYPOINT_REACHED,
                round(n * STEP_S, 6),
                {"waypoint_id": flight.route_ids[i], "index": i},
            )
        )
    reason = "returned_to_base" if flight.completed else "timeout"
    steps.append(
        (
            EventType.MISSION_COMPLETED,
            flight.samples[-1].t,
            {"mission_id": m.id, "completed": flight.completed, "reason": reason},
        )
    )
    return [make_event(config, et, t, k, p) for k, (et, t, p) in enumerate(steps, start=1)]


def _sensor_events(config: ScenarioConfig, flight: Flight, rng: random.Random) -> list[EventDraft]:
    """Eventos de las cinco fuentes hasta el fin de la misión, con el ruido de la semilla."""
    end_s = flight.samples[-1].t
    readings = [
        sensors.gps_readings(config, flight.samples, rng, end_s),
        sensors.radar_readings(config, flight.samples, rng, end_s),
        sensors.meteo_readings(config, rng, end_s),
        sensors.link_readings(config, rng, end_s),
        sensors.battery_readings(config, rng, end_s),
    ]
    events: list[EventDraft] = []
    for source_readings in readings:
        for k, (et, t, payload) in enumerate(source_readings, start=1):
            events.append(make_event(config, et, t, k, payload))
    return events


def _fault_events(config: ScenarioConfig, end_s: float) -> list[EventDraft]:
    """`FaultInjected` / `FaultCleared` de los fallos programados (`origin: scenario`)."""
    pending: list[tuple[float, EventType, dict]] = []
    for f in config.faults:
        if f.start_s >= end_s:
            continue
        payload = {"source": f.source.value, "origin": "scenario"}
        pending.append((f.start_s, EventType.FAULT_INJECTED, payload))
        pending.append((min(f.end_s, end_s), EventType.FAULT_CLEARED, payload))
    pending.sort(key=lambda p: p[0])
    return [make_event(config, et, t, k, p) for k, (t, et, p) in enumerate(pending, start=1)]


def _silence(config: ScenarioConfig, events: list[EventDraft]) -> list[EventDraft]:
    """Quita los eventos de cada fuente silenciada en `[start_s, end_s)`."""
    windows = [(SOURCE_EVENT[f.source], f.start_s, f.end_s) for f in config.faults]
    return [
        e for e in events if not any(et == e.type and a <= e.sim_time < b for et, a, b in windows)
    ]


def _labels(config: ScenarioConfig, end_s: float) -> LabelsFile:
    """Una etiqueta por anomalía (`A1…`, por inicio) y por fallo programado (`F1…`)."""
    anomalies: list[tuple[float, float, LabelType, list[Rule], Cause]] = [
        (e.start_s, min(e.end_s, end_s), LabelType.WIND, [Rule.ROUTE_DEVIATION], Cause.WIND)
        for e in config.wind.episodes
    ]
    if config.spoofing:
        s = config.spoofing
        # tras `end_s` el GPS salta a la verdad, lejos de la ruta: puede saltar ROUTE_DEVIATION
        rules = [Rule.SOURCE_DISCREPANCY, Rule.ROUTE_DEVIATION]
        end = min(s.end_s, end_s)
        anomalies.append((s.start_s, end, LabelType.GPS_SPOOFING, rules, Cause.GPS_SPOOFING))
    if config.hijack:
        h = config.hijack
        end = min(h.end_s, end_s) if h.end_s is not None else end_s
        anomalies.append((h.start_s, end, LabelType.HIJACK, [Rule.ROUTE_DEVIATION], Cause.HIJACK))
    labels = [
        Label(
            id=f"A{i}",
            type=lt,
            source=None,
            start_s=a,
            end_s=b,
            expected_rules=rules,
            expected_cause=cause,
            eval_window=(a, b + EVAL_MARGIN_S),
        )
        for i, (a, b, lt, rules, cause) in enumerate(sorted(anomalies, key=lambda x: x[0]), 1)
    ]
    labels += [
        Label(
            id=f"F{i}",
            type=LabelType.SOURCE_SILENT,
            source=f.source,
            start_s=f.start_s,
            end_s=min(f.end_s, end_s),
            expected_rules=[Rule.SOURCE_SILENT],
            expected_cause=Cause.SENSOR_FAULT,
            eval_window=(f.start_s, min(f.end_s, end_s) + EVAL_MARGIN_S),
        )
        for i, f in enumerate(sorted(config.faults, key=lambda f: f.start_s), 1)
        if f.start_s < end_s
    ]
    return LabelsFile(labels=labels)


def _whole_seconds(flight: Flight) -> list:
    """Muestras de cada segundo entero y la última."""
    chosen = [s for s in flight.samples if s.n % round(1 / STEP_S) == 0]
    if chosen[-1].n != flight.samples[-1].n:
        chosen.append(flight.samples[-1])
    return chosen


def generate(config: ScenarioConfig) -> Run:
    """Genera el escenario completo en memoria (determinista con `config.seed`)."""
    rng = random.Random(config.seed)
    flight = fly(config, perturbed=True)
    end_s = flight.samples[-1].t
    plan_flight, etas = _plan_flight(config)
    plan = PlanFile(
        mission_id=config.mission.id,
        cruise_speed_mps=config.drone.cruise_speed_mps,
        altitude_m=config.drone.altitude_m,
        acceptance_radius_m=config.drone.acceptance_radius_m,
        duration_s=plan_flight.samples[-1].t,
        waypoints=[
            {"id": wid, "x": round(x, 1), "y": round(y, 1), "eta_s": eta}
            for wid, (x, y), eta in zip(plan_flight.route_ids, plan_flight.route, etas, strict=True)
        ],
        trajectory=[
            PlanSample(
                t=s.t,
                x=round(s.x, 2),
                y=round(s.y, 2),
                speed_mps=round(s.speed_mps, 2),
                heading_deg=round(s.heading_deg, 2),
            )
            for s in _whole_seconds(plan_flight)
        ],
    )
    chosen = _whole_seconds(flight)
    truth = TruthFile(
        duration_s=end_s,
        trajectory=[
            TruthSample(
                t=s.t,
                x=round(s.x, 2),
                y=round(s.y, 2),
                speed_mps=round(s.speed_mps, 2),
                heading_deg=round(s.heading_deg, 2),
                course_deg=round(s.course_deg, 2),
            )
            for s in chosen
        ],
        wind=[
            TruthWind(
                t=s.t,
                speed_mps=round((w := wind_at(s.t, config.wind)).speed_mps, 2),
                gust_mps=round(w.gust_mps, 2),
                from_deg=round(w.from_deg, 2),
            )
            for s in chosen
        ],
    )

    mission = _mission_events(config, flight, etas)
    faults = _fault_events(config, end_s)
    readings = _silence(config, _sensor_events(config, flight, rng))
    events = sorted(
        [*mission, *faults, *readings],
        key=lambda e: (e.sim_time, _RANK[e.type]),
    )
    return Run(config.name, plan, truth, events, _labels(config, end_s))


def write_run(run: Run, out_dir: Path | None = None) -> Path:
    """Escribe `plan.json`, `truth.json`, `events.jsonl` y `labels.json`."""
    out = out_dir if out_dir is not None else RUNS_DIR / run.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(run.plan.model_dump_json() + "\n", encoding="utf-8")
    (out / "truth.json").write_text(run.truth.model_dump_json() + "\n", encoding="utf-8")
    (out / "labels.json").write_text(run.labels.model_dump_json(indent=2) + "\n", encoding="utf-8")
    lines = "".join(e.model_dump_json() + "\n" for e in run.events)
    (out / "events.jsonl").write_text(lines, encoding="utf-8")
    return out
