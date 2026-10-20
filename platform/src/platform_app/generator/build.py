"""Construye `runs/<escenario>/` a partir de un escenario: plan, verdad, eventos y etiquetas.

Los eventos son los del simulador incremental (`simulator.py`) ejecutado hasta el final sin
intervenciones: el reproductor en directo produce exactamente los mismos.
"""

from dataclasses import dataclass
from pathlib import Path

from poc_contracts.enums import Cause, FaultMode, LabelType, Rule
from poc_contracts.envelope import EventDraft
from poc_contracts.run_files import Label, LabelsFile, PlanFile, PlanSample, TruthFile
from poc_contracts.scenario import ScenarioConfig

from ..paths import RUNS_DIR
from .controller import STEP_S
from .simulator import Flight, Simulator, fly, plan_etas

EVAL_MARGIN_S = 60.0  # la ventana de evaluación acaba 60 s después de la anomalía


@dataclass(frozen=True)
class Run:
    """Todo lo que escribe el generador para un escenario."""

    name: str
    plan: PlanFile
    truth: TruthFile
    events: list[EventDraft]
    labels: LabelsFile


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
            also_accepted_causes=[],
            eval_window=(a, b + EVAL_MARGIN_S),
        )
        for i, (a, b, lt, rules, cause) in enumerate(sorted(anomalies, key=lambda x: x[0]), 1)
    ]
    for i, f in enumerate(sorted(config.faults, key=lambda f: f.start_s), 1):
        if f.start_s >= end_s:
            continue
        end = min(f.end_s, end_s)
        if f.mode == FaultMode.LOSS:
            # al recuperarse, el GPS salta a la verdad (puede saltar ROUTE_DEVIATION)
            label_type = LabelType.GPS_LOSS
            rules = [Rule.GPS_DEGRADED, Rule.SOURCE_DISCREPANCY, Rule.ROUTE_DEVIATION]
            cause, also = Cause.GPS_JAMMING, [Cause.SENSOR_FAULT]
        else:
            label_type, rules = LabelType.SOURCE_SILENT, [Rule.SOURCE_SILENT]
            cause, also = Cause.SENSOR_FAULT, []
        labels.append(
            Label(
                id=f"F{i}",
                type=label_type,
                source=f.source,
                start_s=f.start_s,
                end_s=end,
                expected_rules=rules,
                expected_cause=cause,
                also_accepted_causes=also,
                eval_window=(f.start_s, end + EVAL_MARGIN_S),
            )
        )
    return LabelsFile(labels=labels)


def _plan_file(config: ScenarioConfig, plan: Flight, etas: list[float]) -> PlanFile:
    per_second = round(1 / STEP_S)
    chosen = [s for s in plan.samples if s.n % per_second == 0]
    if chosen[-1].n != plan.samples[-1].n:
        chosen.append(plan.samples[-1])
    return PlanFile(
        mission_id=config.mission.id,
        cruise_speed_mps=config.drone.cruise_speed_mps,
        altitude_m=config.drone.altitude_m,
        acceptance_radius_m=config.drone.acceptance_radius_m,
        duration_s=plan.samples[-1].t,
        waypoints=[
            {"id": wid, "x": round(x, 1), "y": round(y, 1), "eta_s": eta}
            for wid, (x, y), eta in zip(plan.route_ids, plan.route, etas, strict=True)
        ],
        trajectory=[
            PlanSample(
                t=s.t,
                x=round(s.x, 2),
                y=round(s.y, 2),
                speed_mps=round(s.speed_mps, 2),
                heading_deg=round(s.heading_deg, 2),
            )
            for s in chosen
        ],
    )


def plan_for(config: ScenarioConfig) -> tuple[PlanFile, list[float]]:
    """`plan.json` del escenario (vuelo sin perturbaciones) y los `eta_s` de la ruta."""
    plan = fly(config, perturbed=False)
    if not plan.completed:
        raise ValueError("el plan no se completa dentro de max_duration_s")
    etas = plan_etas(plan)
    return _plan_file(config, plan, etas), etas


def generate(config: ScenarioConfig) -> Run:
    """Ejecuta el escenario completo sin intervenciones (determinista con `config.seed`)."""
    plan, etas = plan_for(config)
    sim = Simulator(config, etas=etas)
    events = sim.start()
    while not sim.finished:
        events += sim.step()
    return Run(config.name, plan, sim.truth(), events, _labels(config, sim.samples[-1].t))


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
