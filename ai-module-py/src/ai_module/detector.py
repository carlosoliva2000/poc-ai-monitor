"""Detector de reglas determinista (sin LLM y sin E/S).

Recibe los eventos de uno en uno con `Detector.feed` y devuelve los eventos de detección que
hay que publicar (`DetectionRaised`, `DetectionUpdated` y `DetectionCleared`). Su reloj es el
`sim_time` de los eventos que llegan, no el reloj de pared: funciona igual a cualquier velocidad
y con un fichero de eventos.

Reglas (umbrales en `config/detector.yaml`), todas con histéresis y un solo aviso por episodio:

- `ROUTE_DEVIATION`: distancia del GPS a la polilínea de la ruta planificada.
- `SOURCE_DISCREPANCY`: distancia GPS-radar (GPS interpolado al instante del radar).
- `SOURCE_SILENT`: tiempo sin eventos de una fuente (una detección por fuente).
- `GPS_DEGRADED`: mala calidad del GPS (`fix`, satélites o `hdop`).

Severidades: `ROUTE_DEVIATION` y `SOURCE_DISCREPANCY` abren en `medium` y pasan a `high` al
empeorar (o abren ya en `high` si el primer valor supera el umbral de empeora); `SOURCE_SILENT`
es `medium` para gps y radar y `low` para el resto; `GPS_DEGRADED` es `high` con `fix: none` y
`medium` en los demás casos (si abre en `medium` y después pierde el fix, pasa a `high`).

Ids: todos los eventos del detector comparten el contador `det-0001`, `det-0002`… El id de un
`DetectionRaised` es también el `detection_id` del episodio; los `DetectionUpdated` y
`DetectionCleared` de ese episodio llevan el mismo `detection_id` y un id de evento nuevo.

Al terminar la misión (`MissionCompleted`) o la simulación (`SimulationFinished`) se dejan de
comprobar los silencios (las fuentes dejan de emitir) y los episodios que sigan abiertos se
**dejan abiertos**: el detector no afirma que el problema haya desaparecido. Se pueden consultar
con `open_detections()`. `SimulationStarted` y `SimulationReset` reinician el detector por completo.
"""

import importlib.resources
import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from poc_contracts.enums import EventType, GpsFix, Rule, SensorSource, Severity
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import (
    DetectionCleared,
    DetectionRaised,
    DetectionUpdated,
    DetectionWindow,
    MissionPlanned,
    Payload,
    PositionUpdated,
    TrackUpdated,
)
from poc_contracts.tools import MissionPlanResult
from poc_contracts.topics import EVENT_SPECS, asset_for, routing_for, source_for, topic_for

from .geometry import Point, distance, distance_to_route, interpolate

log = logging.getLogger(__name__)

# Tipo de evento de cada fuente que vigila `SOURCE_SILENT`.
_SOURCE_OF_TYPE: dict[EventType, SensorSource] = {
    EventType.POSITION_UPDATED: SensorSource.GPS,
    EventType.TRACK_UPDATED: SensorSource.RADAR,
    EventType.WIND_REPORTED: SensorSource.METEO,
    EventType.LINK_STATUS: SensorSource.LINK,
    EventType.BATTERY_STATUS: SensorSource.BATTERY,
}

# Cómo se nombra cada fuente en los mensajes.
_SOURCE_NAMES: dict[SensorSource, str] = {
    SensorSource.GPS: "El GPS",
    SensorSource.RADAR: "El radar",
    SensorSource.METEO: "La estación meteo",
    SensorSource.LINK: "El enlace de mando",
    SensorSource.BATTERY: "La batería",
}

_SILENT_SEVERITY: dict[SensorSource, Severity] = {
    SensorSource.GPS: Severity.MEDIUM,
    SensorSource.RADAR: Severity.MEDIUM,
    SensorSource.METEO: Severity.LOW,
    SensorSource.LINK: Severity.LOW,
    SensorSource.BATTERY: Severity.LOW,
}

# Dominios cuyo contenido el detector no mira (solo usa su `sim_time` como reloj). Del dominio
# `sim` solo usa el ciclo de vida de la ejecución: `SimulationStarted`/`SimulationReset` lo
# reinician y `SimulationFinished` deja de comprobar silencios.
_IGNORED_DOMAINS = ("sim", "ai", "ops")
_EPS = 1e-6


# --- Configuración ---------------------------------------------------------------------------


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThresholdConfig(_Config):
    """Umbrales de una regla con histéresis sobre un valor en metros."""

    open_m: float
    close_m: float
    close_hold_s: float
    worsen_m: float
    max_gps_gap_s: float


class DiscrepancyConfig(ThresholdConfig):
    window_samples: int
    min_samples: int
    max_radar_age_s: float


class SilentConfig(_Config):
    """Segundos sin eventos que abren `SOURCE_SILENT`, por fuente."""

    gps: float
    radar: float
    link: float
    meteo: float
    battery: float

    def threshold(self, source: SensorSource) -> float:
        return float(getattr(self, source.value))


class GpsDegradedConfig(_Config):
    min_sats: int
    max_hdop: float
    clear_hold_s: float


class DetectorConfig(_Config):
    route_deviation: ThresholdConfig
    source_discrepancy: DiscrepancyConfig
    source_silent: SilentConfig
    gps_degraded: GpsDegradedConfig


def load_config(text: str | None = None) -> DetectorConfig:
    """Carga la configuración: del texto YAML dado o de `config/detector.yaml` del paquete."""
    if text is None:
        text = (
            importlib.resources.files("ai_module")
            .joinpath("config/detector.yaml")
            .read_text(encoding="utf-8")
        )
    return DetectorConfig.model_validate(yaml.safe_load(text))


# --- Estado ----------------------------------------------------------------------------------


@dataclass
class _Episode:
    """Un episodio abierto de una regla."""

    detection_id: str
    rule: Rule
    source: SensorSource | None
    since: float
    severity: Severity
    max_value: float
    worsened: bool = False
    calm_since: float | None = None  # desde cuándo el valor está por debajo del umbral de cierre


@dataclass
class _Gps:
    t: float
    point: Point
    event_id: str


@dataclass
class _Sample:
    t: float
    distance_m: float


def _fmt(value: float, decimals: int = 1) -> str:
    """Número con coma decimal, como en los textos para personas."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _event_time(t0: datetime, sim_time: float) -> str:
    """`t0 + sim_time` en ISO 8601 UTC; con milisegundos solo si hacen falta."""
    moment = t0 + timedelta(seconds=sim_time)
    if moment.microsecond == 0:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


class Detector:
    """Detector de reglas. Un `feed` por evento; devuelve las detecciones a publicar."""

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or load_config()
        self._reset(clock=0.0)

    # --- Estado público -----------------------------------------------------------------

    @property
    def clock(self) -> float:
        """Último `sim_time` visto."""
        return self._clock

    def open_detections(self) -> list[str]:
        """Ids de las detecciones que siguen abiertas."""
        return [ep.detection_id for ep in self._episodes.values()]

    def set_plan(self, plan: MissionPlanned | dict[str, Any]) -> None:
        """Fija la ruta planificada (con la vuelta a la base) desde un `MissionPlanned`.

        También acepta el resultado de la tool `get_mission_plan` (el payload de `MissionPlanned`
        más `next_waypoint`), que es lo que se usa si el módulo arranca con la simulación en marcha.
        """
        if isinstance(plan, dict):
            plan = MissionPlanResult.model_validate(plan)
        self._route = [(w.x, w.y) for w in plan.waypoints]
        log.info("plan set: %s with %d points", plan.mission_id, len(self._route))

    # --- Entrada ------------------------------------------------------------------------

    def feed(self, event: EventDraft) -> list[EventDraft]:
        """Procesa un evento (`Envelope` o `EventDraft`) y devuelve las detecciones resultantes."""
        if event.type in (EventType.SIMULATION_STARTED, EventType.SIMULATION_RESET):
            self._reset(clock=event.sim_time)
            self._t0 = self._t0_of(event)
            if event.type == EventType.SIMULATION_STARTED:
                self._init_sources()
            return []

        self._clock = max(self._clock, event.sim_time)
        self._t0 = self._t0_of(event)
        self._init_sources()

        # El contenido de los eventos del simulador y de la IA se ignora: solo cuenta el reloj.
        if event.topic.split(".")[3] in _IGNORED_DOMAINS:
            if event.type == EventType.SIMULATION_FINISHED:
                self._silence_enabled = False
            return self._check_silences(event)

        out: list[EventDraft] = []
        source = _SOURCE_OF_TYPE.get(event.type)
        if event.type == EventType.MISSION_PLANNED:
            self.set_plan(MissionPlanned.model_validate(event.payload))
        elif event.type == EventType.MISSION_COMPLETED:
            self._silence_enabled = False
        out += self._check_silences(event)
        if source is not None:
            out += self._on_source_event(source, event)
        if event.type == EventType.POSITION_UPDATED:
            out += self._on_position(event)
        elif event.type == EventType.TRACK_UPDATED:
            out += self._on_track(event)
        return out

    # --- Reinicio y reloj ---------------------------------------------------------------

    def _reset(self, clock: float) -> None:
        self._clock = clock
        self._t0 = datetime(1970, 1, 1, tzinfo=UTC)
        self._route: list[Point] = []
        self._counter = 0
        self._episodes: dict[tuple[Rule, SensorSource | None], _Episode] = {}
        self._gps: deque[_Gps] = deque(maxlen=8)
        self._radar: deque[_Sample] = deque(maxlen=8)
        self._last_discrepancy_t: float | None = None
        self._last_seen: dict[SensorSource, float] = {}
        self._last_seen_id: dict[SensorSource, str] = {}
        self._silence_enabled = True
        self._last_gps_t: float | None = None

    def _init_sources(self) -> None:
        """Inicializa `last_seen` de las fuentes al primer instante visto."""
        for source in SensorSource:
            self._last_seen.setdefault(source, self._clock)

    @staticmethod
    def _t0_of(event: EventDraft) -> datetime:
        moment = datetime.fromisoformat(event.event_time.replace("Z", "+00:00"))
        return moment - timedelta(seconds=event.sim_time)

    # --- SOURCE_SILENT ------------------------------------------------------------------

    def _check_silences(self, event: EventDraft) -> list[EventDraft]:
        if not self._silence_enabled:
            return []
        out: list[EventDraft] = []
        for source in SensorSource:
            elapsed = self._clock - self._last_seen[source]
            threshold = self.config.source_silent.threshold(source)
            key = (Rule.SOURCE_SILENT, source)
            if key in self._episodes or elapsed <= threshold:
                continue
            trigger = [self._last_seen_id[source]] if source in self._last_seen_id else []
            if event.topic.split(".")[3] not in _IGNORED_DOMAINS:
                trigger.append(event.event_id)
            name = _SOURCE_NAMES[source]
            out.append(
                self._raise(
                    Rule.SOURCE_SILENT,
                    source,
                    _SILENT_SEVERITY[source],
                    value=elapsed,
                    threshold=threshold,
                    unit="s",
                    since=self._last_seen[source],
                    trigger=trigger,
                    message=(
                        f"{name} lleva {_fmt(elapsed)} s sin enviar eventos "
                        f"(umbral {_fmt(threshold)} s)"
                    ),
                )
            )
        return out

    def _on_source_event(self, source: SensorSource, event: EventDraft) -> list[EventDraft]:
        """Llega un evento de `source`: si estaba en silencio, se cierra el episodio."""
        out: list[EventDraft] = []
        episode = self._episodes.get((Rule.SOURCE_SILENT, source))
        if episode is not None:
            episode.max_value = max(episode.max_value, self._clock - episode.since)
            out.append(self._clear(episode))
        self._last_seen[source] = self._clock
        self._last_seen_id[source] = event.event_id
        return out

    # --- Reglas con umbrales: ROUTE_DEVIATION y SOURCE_DISCREPANCY -------------------------

    def _threshold_step(
        self,
        rule: Rule,
        cfg: ThresholdConfig,
        value: float,
        trigger: list[str],
        message: str,
    ) -> list[EventDraft]:
        """Un paso de la histéresis de una regla de distancia."""
        episode = self._episodes.get((rule, None))
        if episode is None:
            if value <= cfg.open_m:
                return []
            severity = Severity.HIGH if value > cfg.worsen_m else Severity.MEDIUM
            threshold = cfg.worsen_m if severity == Severity.HIGH else cfg.open_m
            raised = self._raise(
                rule,
                None,
                severity,
                value=value,
                threshold=threshold,
                unit="m",
                since=self._clock,
                trigger=trigger,
                message=message,
            )
            self._episodes[(rule, None)].worsened = severity == Severity.HIGH
            return [raised]

        out: list[EventDraft] = []
        episode.max_value = max(episode.max_value, value)
        if value > cfg.worsen_m and not episode.worsened:
            episode.worsened = True
            episode.severity = Severity.HIGH
            out.append(self._update(episode, value, cfg.worsen_m, "m", trigger, message))
        if value < cfg.close_m:
            if episode.calm_since is None:
                episode.calm_since = self._clock
            if self._clock - episode.calm_since >= cfg.close_hold_s - _EPS:
                out.append(self._clear(episode))
        else:
            episode.calm_since = None
        return out

    def _on_position(self, event: EventDraft) -> list[EventDraft]:
        pos = PositionUpdated.model_validate(event.payload)
        point = (pos.x, pos.y)
        cfg = self.config.route_deviation
        # Un hueco de GPS mayor que el permitido interrumpe el tiempo de cierre en curso.
        if self._last_gps_t is not None and self._clock - self._last_gps_t > cfg.max_gps_gap_s:
            for episode in self._episodes.values():
                if episode.rule == Rule.ROUTE_DEVIATION:
                    episode.calm_since = None
        self._last_gps_t = self._clock
        self._gps.append(_Gps(self._clock, point, event.event_id))

        out: list[EventDraft] = []
        if self._route:
            dev = distance_to_route(point, self._route)
            previous = [g.event_id for g in list(self._gps)[-2:]]
            out += self._threshold_step(
                Rule.ROUTE_DEVIATION,
                cfg,
                dev,
                previous,
                f"La posición del GPS se aleja {_fmt(dev)} m de la ruta planificada",
            )
        out += self._gps_quality(pos, event)
        return out

    def _on_track(self, event: EventDraft) -> list[EventDraft]:
        cfg = self.config.source_discrepancy
        track = TrackUpdated.model_validate(event.payload)
        t = self._clock
        # Muestras de radar demasiado viejas fuera; si la ventana queda vacía, el cierre en curso
        # se interrumpe (no se compara con datos viejos).
        while self._radar and t - self._radar[0].t > cfg.max_radar_age_s:
            self._radar.popleft()
        if not self._radar:
            for episode in self._episodes.values():
                if episode.rule == Rule.SOURCE_DISCREPANCY:
                    episode.calm_since = None

        bracket = self._gps_at(t, cfg.max_gps_gap_s)
        if bracket is None:
            return []
        gps_point, gps_id = bracket
        self._radar.append(_Sample(t, distance(gps_point, (track.x, track.y))))
        samples = list(self._radar)[-cfg.window_samples :]
        if len(samples) < cfg.min_samples:
            return []
        mean = sum(s.distance_m for s in samples) / len(samples)
        return self._threshold_step(
            Rule.SOURCE_DISCREPANCY,
            cfg,
            mean,
            [gps_id, event.event_id],
            f"El GPS y el radar difieren {_fmt(mean)} m (media de las últimas "
            f"{len(samples)} medidas)",
        )

    def _gps_at(self, t: float, max_gap_s: float) -> tuple[Point, str] | None:
        """Posición del GPS en `t` (interpolada) y el id del evento posterior que la fija.

        Devuelve `None` si no hay GPS a ambos lados de `t` o si el hueco entre ambos es mayor
        que `max_gap_s`.
        """
        samples = list(self._gps)
        for i, after in enumerate(samples):
            if abs(after.t - t) <= _EPS:
                return after.point, after.event_id
            if after.t > t and i > 0:
                before = samples[i - 1]
                if after.t - before.t > max_gap_s:
                    return None
                fraction = (t - before.t) / (after.t - before.t)
                return interpolate(before.point, after.point, fraction), after.event_id
        return None

    # --- GPS_DEGRADED -------------------------------------------------------------------

    def _gps_quality(self, pos: PositionUpdated, event: EventDraft) -> list[EventDraft]:
        cfg = self.config.gps_degraded
        bad = pos.fix != GpsFix.FIX_3D or pos.sats < cfg.min_sats or pos.hdop > cfg.max_hdop
        key = (Rule.GPS_DEGRADED, SensorSource.GPS)
        episode = self._episodes.get(key)
        severity = Severity.HIGH if pos.fix == GpsFix.NONE else Severity.MEDIUM
        if pos.fix == GpsFix.NONE:
            message = (
                f"El GPS ha perdido el fix (fix none, {pos.sats} satélites, hdop {_fmt(pos.hdop)})"
            )
        else:
            reasons = []
            if pos.fix != GpsFix.FIX_3D:
                reasons.append(f"fix {pos.fix.value}")
            if pos.sats < cfg.min_sats:
                reasons.append(f"{pos.sats} satélites (mínimo {cfg.min_sats})")
            if pos.hdop > cfg.max_hdop:
                reasons.append(f"hdop {_fmt(pos.hdop)} (máximo {_fmt(cfg.max_hdop)})")
            message = "La calidad del GPS se ha degradado: " + ", ".join(reasons)

        if episode is None:
            if not bad:
                return []
            raised = self._raise(
                Rule.GPS_DEGRADED,
                SensorSource.GPS,
                severity,
                value=pos.hdop,
                threshold=cfg.max_hdop,
                unit="hdop",
                since=self._clock,
                trigger=[event.event_id],
                message=message,
            )
            self._episodes[key].worsened = severity == Severity.HIGH
            return [raised]

        out: list[EventDraft] = []
        if bad:
            episode.calm_since = None
            episode.max_value = max(episode.max_value, pos.hdop)
            if severity == Severity.HIGH and not episode.worsened:
                episode.worsened = True
                episode.severity = Severity.HIGH
                out.append(
                    self._update(episode, pos.hdop, cfg.max_hdop, "hdop", [event.event_id], message)
                )
        else:
            if episode.calm_since is None:
                episode.calm_since = self._clock
            if self._clock - episode.calm_since >= cfg.clear_hold_s - _EPS:
                out.append(self._clear(episode))
        return out

    # --- Construcción de eventos ----------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"det-{self._counter:04d}"

    def _draft(self, event_type: EventType, event_id: str, payload: Payload) -> EventDraft:
        spec = EVENT_SPECS[event_type]
        return EventDraft(
            event_id=event_id,
            topic=topic_for(event_type),
            type=event_type,
            source=source_for(event_type),
            asset=asset_for(spec.domain, routing_for(event_type)),
            sim_time=self._clock,
            event_time=_event_time(self._t0, self._clock),
            payload=payload.model_dump(mode="json"),
        )

    def _raise(
        self,
        rule: Rule,
        source: SensorSource | None,
        severity: Severity,
        *,
        value: float,
        threshold: float,
        unit: str,
        since: float,
        trigger: list[str],
        message: str,
    ) -> EventDraft:
        detection_id = self._next_id()
        self._episodes[(rule, source)] = _Episode(
            detection_id=detection_id,
            rule=rule,
            source=source,
            since=since,
            severity=severity,
            max_value=value,
        )
        payload = DetectionRaised(
            detection_id=detection_id,
            rule=rule,
            severity=severity,
            value=round(value, 1),
            threshold=round(threshold, 1),
            unit=unit,
            source=source,
            window=DetectionWindow(since=since, until=self._clock),
            trigger_event_ids=trigger,
            message=message,
        )
        log.info("raised %s %s (%s)", detection_id, rule.value, message)
        return self._draft(EventType.DETECTION_RAISED, detection_id, payload)

    def _update(
        self,
        episode: _Episode,
        value: float,
        threshold: float,
        unit: str,
        trigger: list[str],
        message: str,
    ) -> EventDraft:
        payload = DetectionUpdated(
            detection_id=episode.detection_id,
            rule=episode.rule,
            severity=episode.severity,
            value=round(value, 1),
            threshold=round(threshold, 1),
            unit=unit,
            source=episode.source,
            window=DetectionWindow(since=episode.since, until=self._clock),
            trigger_event_ids=trigger,
            message=message,
        )
        log.info("updated %s %s (%s)", episode.detection_id, episode.rule.value, message)
        return self._draft(EventType.DETECTION_UPDATED, self._next_id(), payload)

    def _clear(self, episode: _Episode) -> EventDraft:
        del self._episodes[(episode.rule, episode.source)]
        payload = DetectionCleared(
            detection_id=episode.detection_id,
            rule=episode.rule,
            duration_s=round(self._clock - episode.since, 1),
            max_value=round(episode.max_value, 1),
        )
        log.info("cleared %s %s", episode.detection_id, episode.rule.value)
        return self._draft(EventType.DETECTION_CLEARED, self._next_id(), payload)
