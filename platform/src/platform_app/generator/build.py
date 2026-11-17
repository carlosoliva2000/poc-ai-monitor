"""Construye `runs/<escenario>/` a partir de un escenario: plan, verdad, eventos y etiquetas.

Los eventos son los del simulador incremental (`simulator.py`) ejecutado hasta el final sin
intervenciones: el reproductor en directo produce exactamente los mismos.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from poc_contracts.enums import (
    Cause,
    FaultMode,
    InstructorCommandName,
    LabelType,
    Rule,
    SensorSource,
)
from poc_contracts.envelope import EventDraft
from poc_contracts.run_files import (
    Label,
    LabelsFile,
    PlanFile,
    PlanSample,
    TruthFile,
    UnlabeledEpisode,
    UnlabeledEpisodesFile,
)
from poc_contracts.scenario import FaultConfig, GpsEpisode, LinkEpisode, ScenarioConfig

from ..paths import RUNS_DIR
from .controller import STEP_S
from .simulator import Flight, Simulator, fly, plan_etas

EVAL_MARGIN_S = 60.0  # la ventana de evaluación acaba 60 s después de la anomalía
UNLABELED_FILE = "unlabeled_episodes.json"


@dataclass(frozen=True)
class Run:
    """Todo lo que escribe el generador para un escenario."""

    name: str
    plan: PlanFile
    truth: TruthFile
    events: list[EventDraft]
    labels: LabelsFile
    unlabeled: UnlabeledEpisodesFile | None = None
    """Episodios de degradación con `labeled: false` (`None` si no hay ninguno)."""


def _wind_command_windows(config: ScenarioConfig, end_s: float) -> list[tuple[float, float]]:
    """Ventana de cada viento puesto por un comando programado: del `set_wind` a su fin por
    duración, por el siguiente comando (otro `set_wind` o un `cancel_wind`) o por el fin del
    vuelo."""
    windows: list[list[float]] = []
    current: list[float] | None = None
    for c in sorted(config.commands, key=lambda c: c.at_s):
        if current is not None:
            current[1] = min(current[1], c.at_s)
        if c.command == InstructorCommandName.SET_WIND:
            assert c.params is not None
            d = c.params.duration_s
            current = [c.at_s, c.at_s + d if d is not None else math.inf]
            windows.append(current)
        else:
            current = None
    return [(a, min(b, end_s)) for a, b in windows if a < end_s]


def _labels(config: ScenarioConfig, end_s: float) -> LabelsFile:
    """Una etiqueta por anomalía (`A1…`, por inicio) y por fallo programado (`F1…`)."""
    anomalies: list[tuple[float, float, LabelType, list[Rule], Cause]] = [
        (e.start_s, min(e.end_s, end_s), LabelType.WIND, [Rule.ROUTE_DEVIATION], Cause.WIND)
        for e in config.wind.episodes
    ]
    anomalies += [
        (a, b, LabelType.WIND, [Rule.ROUTE_DEVIATION], Cause.WIND)
        for a, b in _wind_command_windows(config, end_s)
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
        # el cambio de controlador del enlace salta antes que la desviación de la ruta
        rules = [Rule.LINK_ANOMALY, Rule.ROUTE_DEVIATION]
        anomalies.append((h.start_s, end, LabelType.HIJACK, rules, Cause.HIJACK))
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
    for i, f in enumerate(_source_events(config), 1):
        if f.start_s >= end_s:
            continue
        end = min(f.end_s, end_s)
        if isinstance(f, (GpsEpisode, LinkEpisode)):
            # degradación con fix y con el mismo controlador: fallo del sensor o del enlace, o, en
            # el GPS, interferencia; no es un ataque ni viento (sin frontera por magnitud)
            window = episode_window(config, f, end_s)
            if window is None:
                continue  # lo que la anula la cubre entera: no se ve
            a, b = window
            label_type, source, rules, cause, also = _DEGRADED[type(f)]
            labels.append(
                Label(
                    id=f"F{i}",
                    type=label_type,
                    source=source,
                    start_s=a,
                    end_s=b,
                    expected_rules=rules,
                    expected_cause=cause,
                    also_accepted_causes=also,
                    eval_window=(a, b + EVAL_MARGIN_S),
                )
            )
            continue
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


_DEGRADED: dict[type, tuple[LabelType, SensorSource, list[Rule], Cause, list[Cause]]] = {
    GpsEpisode: (
        LabelType.GPS_DEGRADED,
        SensorSource.GPS,
        [Rule.GPS_DEGRADED],
        Cause.SENSOR_FAULT,
        [Cause.GPS_JAMMING],
    ),
    LinkEpisode: (
        LabelType.LINK_DEGRADED,
        SensorSource.LINK,
        [Rule.LINK_ANOMALY],
        Cause.SENSOR_FAULT,
        [Cause.UNKNOWN],
    ),
}


def _blockers(
    config: ScenarioConfig, episode: GpsEpisode | LinkEpisode
) -> list[tuple[float, float]]:
    """Ventanas en que el generador anula un episodio: la pérdida del GPS (sin fix) para uno del
    GPS y el secuestro (manda su `link_hint`) para uno del enlace."""
    if isinstance(episode, GpsEpisode):
        return [(f.start_s, f.end_s) for f in config.faults if f.mode == FaultMode.LOSS]
    h = config.hijack
    if h is None:
        return []
    return [(h.start_s, math.inf if h.end_s is None else h.end_s)]


def episode_window(
    config: ScenarioConfig, episode: GpsEpisode | LinkEpisode, end_s: float
) -> tuple[float, float] | None:
    """Tramo del episodio que se ve de verdad (convención de la E6): termina donde empieza lo que
    lo anula; si eso ya está activo al empezar, empieza cuando termina; `None` si lo cubre entero
    o si empieza después del fin del vuelo."""
    blockers = sorted(_blockers(config, episode))
    end = min(episode.end_s, end_s)
    a = episode.start_s
    moved = True
    while moved:
        moved = False
        for bs, be in blockers:
            if bs <= a < be:
                a, moved = be, True
    if a >= end:
        return None
    b = min((bs for bs, _ in blockers if a < bs < end), default=end)
    return a, b


def _source_events(config: ScenarioConfig) -> list[FaultConfig | GpsEpisode | LinkEpisode]:
    """Fallos programados y episodios de degradación etiquetados, por inicio (`F1…`): con un
    escenario sin episodios, la numeración de los fallos es la de siempre."""
    s = config.sensors
    episodes = [e for e in (*s.gps.episodes, *s.link.episodes) if e.labeled]
    return sorted([*config.faults, *episodes], key=lambda f: f.start_s)


def _unlabeled(config: ScenarioConfig, end_s: float) -> UnlabeledEpisodesFile | None:
    """Episodios `labeled: false` (`U1…`, por inicio), con la ventana de una etiqueta."""
    s = config.sensors
    episodes = sorted(
        (e for e in (*s.gps.episodes, *s.link.episodes) if not e.labeled and e.start_s < end_s),
        key=lambda e: e.start_s,
    )
    if not episodes:
        return None
    out: list[UnlabeledEpisode] = []
    for e in episodes:
        window = episode_window(config, e, end_s)
        if window is None:
            continue
        a, b = window
        _, source, rules, _, _ = _DEGRADED[type(e)]
        out.append(
            UnlabeledEpisode(
                id=f"U{len(out) + 1}",
                source=source,
                start_s=a,
                end_s=b,
                rules=rules,
                eval_window=(a, b + EVAL_MARGIN_S),
            )
        )
    return UnlabeledEpisodesFile(episodes=out) if out else None


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
        raise ValueError("the plan is not completed within max_duration_s")
    etas = plan_etas(plan)
    return _plan_file(config, plan, etas), etas


def generate(config: ScenarioConfig) -> Run:
    """Ejecuta el escenario completo sin intervenciones (determinista con `config.seed`)."""
    plan, etas = plan_for(config)
    sim = Simulator(config, etas=etas)
    events = sim.start()
    while not sim.finished:
        events += sim.step()
    end_s = sim.samples[-1].t
    return Run(
        config.name, plan, sim.truth(), events, _labels(config, end_s), _unlabeled(config, end_s)
    )


def write_run(run: Run, out_dir: Path | None = None) -> Path:
    """Escribe `plan.json`, `truth.json`, `events.jsonl`, `labels.json` y, si hay episodios sin
    etiqueta, `unlabeled_episodes.json` (si no los hay, no queda ninguno de antes)."""
    out = out_dir if out_dir is not None else RUNS_DIR / run.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(run.plan.model_dump_json() + "\n", encoding="utf-8")
    (out / "truth.json").write_text(run.truth.model_dump_json() + "\n", encoding="utf-8")
    (out / "labels.json").write_text(run.labels.model_dump_json(indent=2) + "\n", encoding="utf-8")
    lines = "".join(e.model_dump_json() + "\n" for e in run.events)
    (out / "events.jsonl").write_text(lines, encoding="utf-8")
    unlabeled = out / UNLABELED_FILE
    if run.unlabeled is not None:
        unlabeled.write_text(run.unlabeled.model_dump_json(indent=2) + "\n", encoding="utf-8")
    else:
        unlabeled.unlink(missing_ok=True)
    return out
