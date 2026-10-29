"""Simulador incremental del vuelo: estado + `step()` (paso de 0,1 s).

Es el único motor: lo usan el generador (para `runs/<escenario>/`) y el reproductor en directo.
Cada `step()` devuelve los eventos del instante actual y avanza la física al siguiente. Sin
intervenciones, el resultado es siempre el mismo (un único `random.Random(seed)` y el ruido de
cada fuente se saca siempre en el mismo orden, aunque esté silenciada o en pérdida).

Orden de los eventos de un instante: misión, fallos, GPS, radar, meteo, enlace, batería.

Fallos (`set_fault` y los programados del escenario):
- `mute`: la fuente deja de publicarse; el dron vuela igual.
- `loss` (solo GPS): el dron navega a estima. Integra su velocidad respecto al aire, sin conocer
  el viento, y el controlador sigue el plan con esa estimación (puede dar por alcanzado un
  waypoint que no ha alcanzado). Mientras dura, el GPS publica la posición estimada con
  `fix: none`, `sats: 0` y `hdop` alto; al recuperarse, la posición salta a la real.

Una fuente solo tiene un fallo a la vez, salvo el GPS, que puede tener `loss` y `mute` a la vez
(receptor muerto): navega a estima y no publica nada; al terminar uno sigue el otro.
"""

import math
import random
from dataclasses import dataclass

from poc_contracts.enums import EventType, FaultMode, FaultOrigin, SensorSource
from poc_contracts.envelope import EventDraft
from poc_contracts.run_files import TruthFile, TruthSample, TruthWind
from poc_contracts.scenario import ScenarioConfig

from ..geometry import Point, angle_diff_deg, bearing_deg
from . import sensors
from .controller import STEP_S, Sample, aim_point, build_route
from .disturbances import is_hijacked, spoof_offset, spoof_offset_rate, wind_at
from .events import make_event


@dataclass(frozen=True)
class Flight:
    samples: list[Sample]
    route_ids: list[str]  # BASE, WP1…, BASE: el índice es el de `WaypointReached`
    route: list[Point]
    reached: list[tuple[int, int]]  # (paso, índice en la ruta) de cada waypoint alcanzado
    completed: bool

    @property
    def end_n(self) -> int:
        return self.samples[-1].n


@dataclass(frozen=True)
class ActiveFault:
    mode: FaultMode
    origin: FaultOrigin


def plan_etas(plan: Flight) -> list[float]:
    """Instante previsto de llegada a cada punto de la ruta, en un vuelo sin perturbaciones."""
    etas = [0.0] * len(plan.route)
    for n, i in plan.reached:
        etas[i] = round(n * STEP_S, 6)
    return etas


class Simulator:
    """Vuelo en directo de la misión de un escenario.

    Con `perturbed=False` es el plan (sin viento, spoofing, secuestro ni fallos). Con
    `events=False` solo calcula la física (no saca ruido ni crea eventos).
    """

    def __init__(
        self,
        config: ScenarioConfig,
        *,
        perturbed: bool = True,
        events: bool = True,
        etas: list[float] | None = None,
    ) -> None:
        self.config = config
        self.perturbed = perturbed
        self._events = events
        self.route_ids, self.route = build_route(config)
        self._max_steps = round(config.max_duration_s / STEP_S)
        self._rng = random.Random(config.seed)
        self._spoofing = config.spoofing if perturbed else None
        self._hijack = config.hijack if perturbed else None
        self._target = (self._hijack.target.x, self._hijack.target.y) if self._hijack else None
        self._schedule = list(config.faults) if perturbed else []
        self._scheduled_state = ["pending"] * len(
            self._schedule
        )  # pending | active | skipped | done
        if events and etas is None:
            etas = plan_etas(Simulator(config, perturbed=False, events=False).run_physics())
        self._etas = etas
        self._periods = {
            "gps": sensors.period_steps(config.sensors.gps.period_s),
            "radar": sensors.period_steps(config.sensors.radar.period_s),
            "meteo": sensors.period_steps(config.sensors.meteo.period_s),
            "link": sensors.period_steps(config.sensors.link.period_s),
            "battery": sensors.period_steps(config.sensors.battery.period_s),
        }
        self._ids = {"mis": 0, "sim": 0}

        self.n = 0
        self._i = 1  # índice del waypoint pendiente en la ruta
        self._x = self._y = self._speed = 0.0
        self._heading = bearing_deg(self.route[1][0], self.route[1][1])
        self._est: Point | None = None  # estima del dron mientras no tiene GPS
        self.samples = [Sample(0, 0.0, 0.0, 0.0, 0.0, self._heading, (0.0, 0.0))]
        self.reached: list[tuple[int, int]] = []
        self.completed = False
        self.finished = False
        self._faults: dict[tuple[SensorSource, FaultMode], ActiveFault] = {}
        self._queued: list[tuple[SensorSource, ActiveFault, bool]] = []

    # --- Estado -------------------------------------------------------------------------------

    @property
    def t(self) -> float:
        """Instante simulado (s) del próximo `step()`."""
        return round(self.n * STEP_S, 6)

    @property
    def active_faults(self) -> list[tuple[SensorSource, ActiveFault]]:
        """Fallos en curso, por orden de activación (los aceptados por `set_fault` ya cuentan,
        aunque aún no se hayan publicado sus eventos)."""
        return [(source, fault) for (source, _), fault in self._faults.items()]

    def flight(self) -> Flight:
        return Flight(self.samples, self.route_ids, self.route, self.reached, self.completed)

    def run_physics(self) -> Flight:
        """Vuela hasta el final sin eventos y devuelve el vuelo."""
        while not self.finished:
            self.step()
        return self.flight()

    def _believed(self) -> Point:
        """Posición que cree tener el dron: la estima si no tiene GPS; si no, el GPS sin ruido."""
        return self._est if self._est is not None else self.samples[self.n].gps

    def _distance_to_waypoint(self) -> float:
        b, (gx, gy) = self.route[self._i], self._believed()
        return math.hypot(b[0] - gx, b[1] - gy)

    # --- Fallos -------------------------------------------------------------------------------

    def set_fault(
        self, source: SensorSource, mode: FaultMode, active: bool, origin: FaultOrigin
    ) -> None:
        """Activa o termina un fallo a partir del instante actual (el siguiente `step()`).

        Lanza `ValueError` si no es posible: `loss` fuera del GPS, fuente que ya tiene un fallo
        (el GPS admite uno de cada modo), fallo que no está activo o programado por el escenario
        (ese solo lo termina el escenario).
        """
        current = self._faults.get((source, mode))
        if active:
            if mode == FaultMode.LOSS and source != SensorSource.GPS:
                raise ValueError("`loss` only exists for the GPS")
            blocking = self._blocking(source, mode)
            if blocking is not None:
                raise ValueError(f"{source.value} already has an active fault ({blocking.value})")
            self._start_fault(source, ActiveFault(mode, origin))
            self._queued.append((source, ActiveFault(mode, origin), True))
            return
        if current is None:
            raise ValueError(f"{source.value} has no active {mode.value} fault")
        if current.origin != origin:
            raise ValueError(
                f"the {source.value} fault was scheduled by the scenario: it ends by itself"
            )
        self._end_fault(source, mode)
        self._queued.append((source, current, False))

    def _blocking(self, source: SensorSource, mode: FaultMode) -> FaultMode | None:
        """Modo del fallo en curso que impide activar `mode` en `source`, si lo hay: el mismo
        modo o, fuera del GPS, cualquiera."""
        for (src, active_mode), _ in self._faults.items():
            if src == source and (source != SensorSource.GPS or active_mode == mode):
                return active_mode
        return None

    def _start_fault(self, source: SensorSource, fault: ActiveFault) -> None:
        self._faults[(source, fault.mode)] = fault
        if fault.mode == FaultMode.LOSS:
            self._est = self.samples[self.n].gps  # arranca la estima donde cree estar

    def _end_fault(self, source: SensorSource, mode: FaultMode) -> None:
        fault = self._faults.pop((source, mode))
        if fault.mode == FaultMode.LOSS:
            self._est = None  # el GPS vuelve: la posición salta a la real

    def _fault_event(self, source: SensorSource, fault: ActiveFault, injected: bool) -> EventDraft:
        self._ids["sim"] += 1
        et = EventType.FAULT_INJECTED if injected else EventType.FAULT_CLEARED
        payload = {"source": source.value, "mode": fault.mode.value, "origin": fault.origin.value}
        return make_event(self.config, et, self.t, self._ids["sim"], payload)

    def _scheduled_transitions(self) -> list[EventDraft]:
        """Fallos del escenario que empiezan o terminan en este instante."""
        out: list[EventDraft] = []
        t = self.t
        for k, f in enumerate(self._schedule):
            state = self._scheduled_state[k]
            if state == "active" and t >= f.end_s:
                self._scheduled_state[k] = "done"
                out.append(self._fault_event(f.source, self._faults[(f.source, f.mode)], False))
                self._end_fault(f.source, f.mode)
            elif state == "pending" and f.start_s <= t < f.end_s:
                if self._blocking(f.source, f.mode) is not None:  # ya hay un fallo manual: se omite
                    self._scheduled_state[k] = "skipped"
                    continue
                self._scheduled_state[k] = "active"
                fault = ActiveFault(f.mode, FaultOrigin.SCENARIO)
                self._start_fault(f.source, fault)
                out.append(self._fault_event(f.source, fault, True))
        return out

    # --- Un paso ------------------------------------------------------------------------------

    def _mission_event(self, et: EventType, payload: dict) -> EventDraft:
        self._ids["mis"] += 1
        return make_event(self.config, et, self.t, self._ids["mis"], payload)

    def start(self) -> list[EventDraft]:
        """`MissionPlanned` y `MissionStarted` (t = 0)."""
        assert self._etas is not None, "start() necesita events=True"
        m, d = self.config.mission, self.config.drone
        waypoints = [
            {"id": wid, "x": round(x, 1), "y": round(y, 1), "eta_s": eta}
            for wid, (x, y), eta in zip(self.route_ids, self.route, self._etas, strict=True)
        ]
        planned = {
            "mission_id": m.id,
            "cruise_speed_mps": d.cruise_speed_mps,
            "altitude_m": d.altitude_m,
            "acceptance_radius_m": d.acceptance_radius_m,
            "waypoints": waypoints,
        }
        return [
            self._mission_event(EventType.MISSION_PLANNED, planned),
            self._mission_event(EventType.MISSION_STARTED, {"mission_id": m.id}),
        ]

    def step(self) -> list[EventDraft]:
        """Eventos del instante actual (en el orden del contrato) y avance de 0,1 s."""
        if self.finished:
            raise RuntimeError("the simulation has finished")
        d = self.config.drone
        t = self.t

        faults = [self._fault_event(s, f, inj) for s, f, inj in self._queued]
        self._queued.clear()
        if self.perturbed:
            faults += self._scheduled_transitions()

        mission: list[EventDraft] = []
        timeout = self.n >= self._max_steps
        if not timeout:
            while (
                self._i < len(self.route)
                and not is_hijacked(t, self._hijack)
                and self._distance_to_waypoint() < d.acceptance_radius_m
            ):
                self.reached.append((self.n, self._i))
                if self._events:
                    payload = {"waypoint_id": self.route_ids[self._i], "index": self._i}
                    mission.append(self._mission_event(EventType.WAYPOINT_REACHED, payload))
                self._i += 1
        if timeout or self._i >= len(self.route):
            self.finished = True
            self.completed = self._i >= len(self.route)
            if self._events:
                reason = "returned_to_base" if self.completed else "timeout"
                payload = {
                    "mission_id": self.config.mission.id,
                    "completed": self.completed,
                    "reason": reason,
                }
                mission.append(self._mission_event(EventType.MISSION_COMPLETED, payload))
            # un fallo que acabaría después del fin de la misión se recorta a ese instante
            for source, mode in list(self._faults):
                faults.append(self._fault_event(source, self._faults[(source, mode)], False))
                self._end_fault(source, mode)

        readings = self._readings() if self._events else []
        if not self.finished:
            self._advance()
        return [*mission, *faults, *readings]

    def _readings(self) -> list[EventDraft]:
        """Medidas de las fuentes cuyo periodo cae en este instante (con ruido siempre)."""
        n, t, cfg, rng = self.n, self.t, self.config, self._rng
        if n == 0:
            return []
        s = self.samples[n]
        out: list[EventDraft] = []

        def emit(name: str, et: EventType, source: SensorSource, payload: dict) -> None:
            if (source, FaultMode.MUTE) not in self._faults:
                out.append(make_event(cfg, et, t, n // self._periods[name], payload))

        if n % self._periods["gps"] == 0:
            if self._est is not None:
                rad = math.radians(s.heading_deg)
                vel = (self._speed * math.sin(rad), self._speed * math.cos(rad))
                payload = sensors.gps_payload(cfg, rng, self._est, vel, loss=True)
            else:
                dvx, dvy = spoof_offset_rate(t, self._spoofing)
                payload = sensors.gps_payload(cfg, rng, s.gps, (s.vx + dvx, s.vy + dvy), loss=False)
            emit("gps", EventType.POSITION_UPDATED, SensorSource.GPS, payload)
        if n % self._periods["radar"] == 0:
            emit(
                "radar",
                EventType.TRACK_UPDATED,
                SensorSource.RADAR,
                sensors.radar_payload(cfg, rng, s),
            )
        if n % self._periods["meteo"] == 0:
            emit(
                "meteo",
                EventType.WIND_REPORTED,
                SensorSource.METEO,
                sensors.meteo_payload(cfg, rng, t),
            )
        if n % self._periods["link"] == 0:
            emit(
                "link",
                EventType.LINK_STATUS,
                SensorSource.LINK,
                sensors.link_payload(cfg, rng, t),
            )
        if n % self._periods["battery"] == 0:
            emit(
                "battery",
                EventType.BATTERY_STATUS,
                SensorSource.BATTERY,
                sensors.battery_payload(cfg, rng, t),
            )
        return out

    def _advance(self) -> None:
        """Guiado, giro, aceleración, viento e integración: de `t` a `t + 0,1 s`."""
        d, t = self.config.drone, self.t
        believed = self._believed()
        if is_hijacked(t, self._hijack):
            assert self._target is not None
            aim = self._target
        else:
            aim = aim_point(self.route[self._i - 1], self.route[self._i], believed, d.lookahead_m)
        err = angle_diff_deg(bearing_deg(aim[0] - believed[0], aim[1] - believed[1]), self._heading)
        step = d.max_turn_rate_dps * STEP_S
        self._heading = (self._heading + max(-step, min(step, err))) % 360.0
        self._speed = min(d.cruise_speed_mps, self._speed + d.max_accel_mps2 * STEP_S)
        wx, wy = wind_at(t, self.config.wind).vector() if self.perturbed else (0.0, 0.0)
        ax = self._speed * math.sin(math.radians(self._heading))
        ay = self._speed * math.cos(math.radians(self._heading))
        vx, vy = ax + wx, ay + wy
        self._x += vx * STEP_S
        self._y += vy * STEP_S
        if self._est is not None:  # a estima: solo la velocidad respecto al aire
            self._est = (self._est[0] + ax * STEP_S, self._est[1] + ay * STEP_S)
        self.n += 1
        offset = spoof_offset(self.t, self._spoofing)
        self.samples.append(Sample(self.n, self._x, self._y, vx, vy, self._heading, offset))

    # --- Verdad -------------------------------------------------------------------------------

    def truth(self) -> TruthFile:
        """Trayectoria real y viento real hasta el instante actual (una muestra por segundo más
        la última). Solo para las gráficas, la evaluación y la web: el agente no lo ve."""
        per_second = round(1 / STEP_S)
        chosen = [s for s in self.samples if s.n % per_second == 0]
        if chosen[-1].n != self.samples[-1].n:
            chosen.append(self.samples[-1])
        return TruthFile(
            duration_s=self.samples[-1].t,
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
                    speed_mps=round((w := wind_at(s.t, self.config.wind)).speed_mps, 2),
                    gust_mps=round(w.gust_mps, 2),
                    from_deg=round(w.from_deg, 2),
                )
                for s in chosen
            ],
        )


def fly(config: ScenarioConfig, perturbed: bool) -> Flight:
    """Vuela la misión sin eventos; `perturbed=False` es el plan (sin perturbaciones)."""
    return Simulator(config, perturbed=perturbed, events=False).run_physics()
