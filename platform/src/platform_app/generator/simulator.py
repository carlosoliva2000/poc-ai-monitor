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

Comandos del instructor (`apply_command` y los `commands` del escenario): `set_wind` y
`cancel_wind`. El viento del instructor es un episodio más (ver `disturbances.CommandWind`): lo
mide la estación y empuja al dron con la física de siempre; no gasta números aleatorios.

Una fuente solo tiene un fallo a la vez, salvo el GPS, que puede tener `loss` y `mute` a la vez
(receptor muerto): navega a estima y no publica nada; al terminar uno sigue el otro.
"""

import math
import random
from collections import deque
from dataclasses import dataclass

from poc_contracts.commands import CommandBody, ScheduledCommand
from poc_contracts.enums import (
    CommandIssuer,
    EventType,
    FaultMode,
    FaultOrigin,
    InstructorCommandName,
    SensorSource,
)
from poc_contracts.envelope import EventDraft
from poc_contracts.run_files import TruthFile, TruthSample, TruthWind
from poc_contracts.scenario import ScenarioConfig

from ..geometry import Point, angle_diff_deg, bearing_deg, project_on_segment
from . import radio, sensors
from .controller import (
    STEP_S,
    Sample,
    aim_point,
    build_route,
    corner_speed,
    limit_air_velocity,
    speed_profile,
    unit,
)
from .disturbances import CommandWind, Wind, is_hijacked, spoof_offset, spoof_offset_rate, wind_at
from .energy import Battery
from .events import make_event
from .receiver import Estimator, GnssEpoch, GnssModel, stable_rng

HOLD_MAX_SPEED_MPS = 3.0  # lazo P del punto de espera: tope de la velocidad sobre el suelo
LATERAL_INT_WINDOW_M = 15.0  # la integral solo acumula con un error lateral menor que esto
LATERAL_CORR_MAX_MPS = 3.0  # tope de la corrección integral (anti-windup)
LINK_LOSS_WINDOW_S = 10.0  # ventana con la que `LinkStatus` mide los paquetes perdidos
ENDURANCE_HOLD_S = 5.0  # segundos seguidos sin llegar a casa para que salte el failsafe ⚠️
ENDURANCE_WIND_MARGIN_MPS = 1.0  # margen sobre el viento al calcular la energía (el estimado a
# bordo y el real en la verdad: parte de la definición de «no llega») ⚠️


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
class Aux:
    """Verdad ampliada de un instante (cada segundo y el último): lo que no cabe en `Sample` y hace
    falta para `truth.json` y para las etiquetas por faceta (`states.py`)."""

    n: int
    leg_index: int  # índice del waypoint pendiente en la ruta
    ref_dist_m: float  # distancia real al tramo pendiente (la referencia del modo en misión)
    est: Point  # lo que cree el dron: su GPS sin ruido (o la estima, sin GPS)
    mode: str
    link_up: bool
    battery_soc: float
    gps_sigma_m: float
    cn0_dbhz: float
    emitters_active: tuple[str, ...]
    wind_speed_mps: float
    wind_from_deg: float
    gps_mute: bool
    gps_loss: bool
    radar_mute: bool
    meteo_mute: bool
    link_mute: bool
    battery_mute: bool
    spoofing: bool
    hijack: bool
    link_latency_ms: float
    link_loss_pct: float
    radar_in_range: bool
    can_reach_home: bool


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
        self._ids = {"mis": 0, "sim": 0, "cmd": 0}
        self._scheduled_cmds: list[ScheduledCommand] = (
            sorted(config.commands, key=lambda c: c.at_s) if perturbed else []
        )
        self._wind_cmds: list[CommandWind] = []  # viento del instructor, por orden de llegada
        self._cmd_queue: list[tuple[CommandBody, CommandIssuer, str | None]] = []

        self.n = 0
        self._i = 1  # índice del waypoint pendiente en la ruta
        self._x = self._y = self._speed = 0.0
        self._heading = bearing_deg(self.route[1][0], self.route[1][1])
        self._est: Point | None = None  # estima del dron mientras no tiene GPS
        # Guiado de multirrotor (`simulator.multirotor_guidance`): velocidad respecto al aire como
        # vector, integral del error lateral y modo del autopiloto.
        self._multirotor = config.simulator.multirotor_guidance
        self._va: Point = (0.0, 0.0)
        self._int = 0.0
        self._mode = "mission"  # `mission` | `failsafe_hold` | `failsafe_return`
        sim = config.simulator
        # Receptor GPS realista y estimador a bordo (pasos 3 y 4): el ruido sale de generadores
        # propios y se saca también en los vuelos sin eventos (la trayectoria depende de él).
        self._gnss = GnssModel(config) if sim.gps_receiver and perturbed else None
        self._gnss_last: GnssEpoch | None = None
        self._filter = (
            Estimator(
                (0.0, 0.0), config.drone.estimator_position_gain, config.drone.estimator_wind_gain
            )
            if sim.onboard_estimator
            else None
        )
        self._innovation: float | None = None
        # Enlace con física, batería con consumo y emisores (pasos 5 y 6).
        self._link_phys = sim.link_physics
        self._emitters_on = sim.emitters
        self._link_rng = stable_rng(config.seed, "link_loss")
        self._pkt_history: deque[tuple[float, bool]] = deque()  # (instante, perdido) por paquete
        self._link_down_s = 0.0  # segundos seguidos sin enlace con nuestra estación (en el dron)
        self._battery = Battery(config.sensors.battery) if sim.battery_model else None
        self._emitter_state: tuple[float, float, tuple[str, ...]] = (0.0, 0.0, ())
        self._land_end: float | None = None  # instante en que acaba el aterrizaje
        self._cannot_reach_s = 0.0  # segundos seguidos en que la estima dice que no llega a casa
        self._radar_geometry = sim.radar_geometry
        self._ground_station = sim.ground_station
        self._hold: Point | None = None  # punto de espera en `failsafe_hold`
        self._leg_start: Point | None = None  # origen del tramo a casa en `failsafe_return`
        self.samples = [Sample(0, 0.0, 0.0, 0.0, 0.0, self._heading, (0.0, 0.0))]
        self.reached: list[tuple[int, int]] = []
        self.completed = False
        self.finished = False
        self._faults: dict[tuple[SensorSource, FaultMode], ActiveFault] = {}
        self._queued: list[tuple[SensorSource, ActiveFault, bool]] = []
        self.aux: dict[int, Aux] = {}  # verdad ampliada por paso (cada segundo y el último)

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
        """Posición que cree tener el dron: la del estimador a bordo; si no, la estima sin GPS y, si
        no, el GPS sin ruido."""
        if self._filter is not None:
            return self._filter.p
        return self._est if self._est is not None else self.samples[self.n].gps

    def _distance_to_waypoint(self) -> float:
        b, (gx, gy) = self.route[self._i], self._believed()
        return math.hypot(b[0] - gx, b[1] - gy)

    def _leg(self) -> tuple[Point, Point]:
        """Tramo de referencia: el pendiente de la ruta o, al volver por failsafe, el que va del
        punto donde se activó a casa."""
        last = len(self.route) - 1
        i = min(self._i, last)
        a = self._leg_start if self._leg_start is not None else self.route[max(i - 1, 0)]
        return a, self.route[i]

    def _waypoint_reached(self) -> bool:
        """Punto pendiente alcanzado. Multirrotor: entra en el radio de aceptación o cruza la
        perpendicular del final del tramo (regla de PX4 y ArduPilot para no volver atrás)."""
        if self._distance_to_waypoint() < self.config.drone.acceptance_radius_m:
            return True
        if not self._multirotor:
            return False
        a, b = self._leg()
        u = unit(b[0] - a[0], b[1] - a[1])
        p = self._believed()
        return (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1] >= math.hypot(b[0] - a[0], b[1] - a[1])

    def set_mode(self, mode: str) -> None:
        """Cambia el modo del autopiloto (`mission`, `failsafe_hold`, `failsafe_return`,
        `failsafe_land`); solo con el guiado de multirrotor. `failsafe_hold` mantiene la posición
        donde cree estar; `failsafe_return` va en línea recta a casa desde ahí y `failsafe_land` se
        mantiene y aterriza (`drone.land_duration_s`: termina el vuelo con `reason: landed`)."""
        if not self._multirotor:
            raise ValueError("the autopilot modes need simulator.multirotor_guidance")
        p = self._believed()
        self._hold = p if mode in ("failsafe_hold", "failsafe_land") else None
        if mode == "failsafe_land":
            self._land_end = self.t + self.config.drone.land_duration_s
        self._leg_start = p if mode == "failsafe_return" else None
        if mode == "failsafe_return":
            self._i = len(self.route) - 1
        self._mode, self._int = mode, 0.0

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

    # --- Comandos del instructor ----------------------------------------------------------------

    def apply_command(
        self,
        body: CommandBody,
        issued_by: CommandIssuer,
        text: str | None = None,
        at_s: float | None = None,
    ) -> None:
        """Aplica un comando del instructor desde `at_s` (por defecto, el instante actual).

        `set_wind` sustituye al viento del instructor que hubiera (el nuevo sube con su rampa y el
        anterior se mantiene hasta entonces); `cancel_wind` baja el que haya con su rampa hasta el
        viento del escenario. Lanza `ValueError` si no hay viento del instructor que cancelar.
        """
        t = self.t if at_s is None else at_s
        active = next((c for c in reversed(self._wind_cmds) if self._is_active(c, t)), None)
        if body.command == InstructorCommandName.SET_WIND:
            assert body.params is not None
            new = CommandWind(t, body.params)
            if active is not None:
                active.cut_at = t
                active.release_after = min(
                    body.params.ramp_s, (body.params.duration_s or float("inf")) / 2
                )
            self._wind_cmds.append(new)
        else:
            if active is None:
                raise ValueError("there is no instructor wind to cancel")
            active.cut_at, active.release_after = t, 0.0
        self._cmd_queue.append((body, issued_by, text))

    @staticmethod
    def _is_active(command: CommandWind, t: float) -> bool:
        """En curso y sin orden de terminar."""
        return command.cut_at is None and command.level(t) is not None

    def instructor_wind_active(self) -> bool:
        return any(self._is_active(c, self.t) for c in self._wind_cmds)

    def _apply_scheduled_commands(self) -> None:
        while self._scheduled_cmds and self._scheduled_cmds[0].at_s <= self.t:
            c = self._scheduled_cmds.pop(0)
            self.apply_command(c, CommandIssuer.SCENARIO, None, at_s=c.at_s)

    def _command_events(self) -> list[EventDraft]:
        out: list[EventDraft] = []
        for body, issued_by, text in self._cmd_queue:
            self._ids["cmd"] += 1
            payload = {
                "command": body.command.value,
                "params": body.params.model_dump() if body.params else None,
                "issued_by": issued_by.value,
                "text": text,
            }
            out.append(
                make_event(
                    self.config, EventType.INSTRUCTOR_COMMAND, self.t, self._ids["cmd"], payload
                )
            )
        self._cmd_queue.clear()
        return out

    def _wind(self, t: float) -> Wind:
        return wind_at(t, self.config.wind, self._wind_cmds)

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
            "mission_controller_id": self.config.sensors.link.controller_id,
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
        t = self.t

        faults = [self._fault_event(s, f, inj) for s, f, inj in self._queued]
        self._queued.clear()
        if self.perturbed:
            faults += self._scheduled_transitions()
            self._apply_scheduled_commands()
        commands = self._command_events()
        self._gnss_epoch()
        self._check_failsafes()

        mission: list[EventDraft] = []
        timeout = self.n >= self._max_steps
        if not timeout:
            while (
                self._i < len(self.route)
                and not is_hijacked(t, self._hijack)
                and self._waypoint_reached()
            ):
                self.reached.append((self.n, self._i))
                if self._events and self._delivered():  # el aviso viaja por el enlace
                    payload = {"waypoint_id": self.route_ids[self._i], "index": self._i}
                    mission.append(self._mission_event(EventType.WAYPOINT_REACHED, payload))
                self._i += 1
        landed = self._land_end is not None and t >= self._land_end
        if timeout or landed or self._i >= len(self.route):
            self.finished = True
            self.completed = self._i >= len(self.route) and not landed
            self._record_aux()
            if self._events:
                reason = "landed" if landed else "returned_to_base" if self.completed else "timeout"
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

        if not self.finished and self.n % round(1 / STEP_S) == 0:
            self._record_aux()
        readings = self._readings() if self._events else []
        if not self.finished:
            self._advance()
        return [*mission, *faults, *commands, *readings]

    def _gnss_epoch(self) -> None:
        """Medida del receptor (cada periodo del GPS): saca su ruido, esté silenciado o no, y con el
        estimador a bordo corrige con ella (sin GPS solo predice)."""
        if self._gnss is None or self.n == 0 or self.n % self._periods["gps"] != 0:
            return
        s = self.samples[self.n]
        if self._emitters_on:
            self._emitter_state = radio.emitter_effects(self.config, self.t, s.x, s.y)
        ep = self._gnss.epoch(self.config, self.t, self._emitter_state[0], self._emitter_state[1])
        self._gnss_last = ep
        if self._filter is None:
            return
        if self._est is not None:  # sin GPS: no hay medida que corrija
            self._innovation = None
            return
        gx, gy = self.samples[self.n].gps
        self._innovation = self._filter.correct(
            (round(gx + ep.noise[0], 1), round(gy + ep.noise[1], 1))
        )

    def _delivered(self) -> bool:
        """Llega el paquete de telemetría (la del dron: GPS, receptor, autopiloto, batería y
        puntos de paso). Siempre saca su número aleatorio, esté el enlace como esté, para que el
        resto no cambie. Sin `link_physics` todo llega. Cuenta los perdidos para `LinkStatus`."""
        if not self._link_phys:
            return True
        u = self._link_rng.random()
        s = self.samples[self.n]
        up = self._ours_link_up(s.x, s.y)
        lost = (not up) or u < radio.loss_probability(
            self.config, radio.rssi_dbm(self.config, s.x, s.y, self.t)
        )
        self._pkt_history.append((self.t, lost))
        return not lost

    def _link_down_physical(self, x: float, y: float) -> bool:
        """Lo que nota el dron: no le llega nada de nuestra estación (enlace silenciado o señal
        por debajo del mínimo). Un secuestro no cuenta: el dron sí tiene enlace, con el otro."""
        if (SensorSource.LINK, FaultMode.MUTE) in self._faults:
            return True
        return radio.rssi_dbm(self.config, x, y, self.t) < self.config.sensors.link.rssi_floor_dbm

    def _ours_link_up(self, x: float, y: float) -> bool:
        """Nuestra estación recibe al dron: ni secuestro ni enlace caído."""
        return not is_hijacked(self.t, self._hijack) and not self._link_down_physical(x, y)

    def _check_failsafes(self) -> None:
        """Failsafe del enlace (tras `link_loss_timeout_s` sin enlace) y de la batería (niveles de
        PX4 o «no llega a casa»). Con el dron secuestrado no obedece: manda el otro."""
        if not self._multirotor or not self.perturbed:
            return
        if is_hijacked(self.t, self._hijack):
            self._link_down_s = 0.0
            return
        d, s = self.config.drone, self.samples[self.n]
        if self._link_phys:
            down = self._link_down_physical(s.x, s.y)
            self._link_down_s = self._link_down_s + STEP_S if down else 0.0
            action = {"hold": "failsafe_hold", "return": "failsafe_return", "land": "failsafe_land"}
            if (
                self._link_down_s >= d.link_loss_timeout_s
                and self._mode == "mission"
                and d.link_loss_action in action
            ):
                self.set_mode(action[d.link_loss_action])
        b = self._battery
        if b is None or self._mode == "failsafe_land":
            return
        cfg = self.config.sensors.battery
        if b.soc_pct < cfg.failsafe_land_pct:
            self.set_mode("failsafe_land")
        elif b.soc_pct < cfg.failsafe_return_pct and self._mode != "failsafe_return":
            self.set_mode("failsafe_return")
        elif cfg.endurance_action == "return" and self._mode == "mission":
            # «No llega a casa»: la estimación depende mucho del viento estimado (al acercarse a la
            # velocidad máxima respecto al aire), así que tiene que mantenerse unos segundos.
            wind = self._filter.wind if self._filter else None
            if self._filter is not None:  # lo que cree: su velocidad estimada y un margen de viento
                velocity = (self._va[0] + wind[0], self._va[1] + wind[1])
            else:
                velocity = (s.vx, s.vy)
            if self._can_reach_home(self._believed(), wind, velocity, ENDURANCE_WIND_MARGIN_MPS):
                self._cannot_reach_s = 0.0
            else:
                self._cannot_reach_s += STEP_S
                if self._cannot_reach_s >= ENDURANCE_HOLD_S:
                    self.set_mode("failsafe_return")

    def _can_reach_home(
        self, pos: Point, wind: Point | None, velocity: Point, margin_mps: float = 0.0
    ) -> bool:
        """Con la energía que queda, ¿llega a casa con ese viento (el estimado a bordo o, sin
        estimador, el real) y con la reserva?"""
        assert self._battery is not None
        d = self.config.drone
        w = wind if wind is not None else self._wind(self.t).vector()
        return self._battery.can_reach_home(
            pos, w, d.cruise_speed_mps, d.max_airspeed_mps, velocity, d.max_accel_mps2, margin_mps
        )

    def _loss_pct(self, x: float, y: float) -> float:
        """Paquetes que se pierden de verdad (modelo, sin azar); 100 con el enlace caído."""
        if not self._link_phys:
            return 0.0
        if not self._ours_link_up(x, y):
            return 100.0
        return 100.0 * radio.loss_probability(
            self.config, radio.rssi_dbm(self.config, x, y, self.t)
        )

    def _truth_can_reach_home(self, s: Sample) -> bool:
        """Verdad: con la energía que queda, la posición real y el viento real, ¿llega a casa?"""
        if self._battery is None:
            return True
        return self._can_reach_home((s.x, s.y), None, (s.vx, s.vy), ENDURANCE_WIND_MARGIN_MPS)

    def _station_wind(self, t: float) -> Wind:
        """Lo que mide la estación en tierra: el viento del dron por un factor, con retraso (media
        móvil de los últimos `lag_s` segundos)."""
        m = self.config.sensors.meteo
        vecs = [self._wind(t - k).vector() for k in range(int(min(m.lag_s, t)) + 1)]
        mx, my = sum(v[0] for v in vecs) / len(vecs), sum(v[1] for v in vecs) / len(vecs)
        speed = math.hypot(mx, my)
        from_deg = (bearing_deg(mx, my) + 180.0) % 360.0 if speed > 1e-9 else self._wind(t).from_deg
        return Wind(m.factor * speed, from_deg)

    def _radar_in_range(self, x: float, y: float) -> bool:
        if not self._radar_geometry:
            return True
        return sensors.radar_range_m(self.config, x, y) <= self.config.sensors.radar.max_range_m

    def _link_payload(self, rng: random.Random) -> dict:
        """`LinkStatus` que mide nuestra estación (nunca se silencia: el enlace caído se ve como
        100 % de paquetes perdidos). Los paquetes perdidos se miden en los últimos 10 s."""
        s = self.samples[self.n]
        up = self._ours_link_up(s.x, s.y)
        while self._pkt_history and self._pkt_history[0][0] < self.t - LINK_LOSS_WINDOW_S:
            self._pkt_history.popleft()
        total = len(self._pkt_history)
        lost = (
            100.0 * sum(1 for _, was_lost in self._pkt_history if was_lost) / total
            if total
            else 0.0
        )
        rssi = radio.rssi_dbm(self.config, s.x, s.y, self.t)
        latency = sensors.link_quality(self.config, self.t)[1]
        return sensors.link_payload_physics(self.config, rng, rssi, latency, up, lost)

    def _gnss_payload(self, loss: bool) -> dict:
        ep = self._gnss_last
        assert ep is not None
        return {
            "h_acc_m": 99.9 if loss else round(ep.h_acc_m, 2),
            "cn0_dbhz": round(ep.cn0_dbhz, 1),
            "agc_db": round(ep.agc_db, 2),
        }

    def _autopilot_payload(self) -> dict:
        f = self._filter
        assert f is not None
        gx, gy = (
            self._va[0] + f.wind[0],
            self._va[1] + f.wind[1],
        )  # velocidad sobre el suelo estimada
        return {
            "mode": self._mode,
            "heading_deg": round(self._heading, 1),
            "airspeed_mps": round(math.hypot(*self._va), 1),
            "wind_est_speed_mps": round(math.hypot(*f.wind), 1),
            "wind_est_from_deg": round(f.wind_from_deg(), 1),
            "innovation_m": None if self._innovation is None else round(self._innovation, 1),
            "est_x": round(f.p[0], 1),
            "est_y": round(f.p[1], 1),
            "ground_speed_mps": round(math.hypot(gx, gy), 1),
            "course_deg": round(
                bearing_deg(gx, gy) if math.hypot(gx, gy) > 0.1 else self._heading, 1
            ),
        }

    def _readings(self) -> list[EventDraft]:
        """Medidas de las fuentes cuyo periodo cae en este instante (con ruido siempre)."""
        n, t, cfg, rng = self.n, self.t, self.config, self._rng
        if n == 0:
            return []
        s = self.samples[n]
        out: list[EventDraft] = []

        def emit(
            name: str,
            et: EventType,
            source: SensorSource | None,
            payload: dict,
            telemetry: bool = False,
        ) -> None:
            delivered = self._delivered() if telemetry else True  # saca su número aunque calle
            if delivered and (source is None or (source, FaultMode.MUTE) not in self._faults):
                out.append(make_event(cfg, et, t, n // self._periods[name], payload))

        if n % self._periods["gps"] == 0:
            loss = self._est is not None
            if loss:
                rad = math.radians(s.heading_deg)
                vel = (self._speed * math.sin(rad), self._speed * math.cos(rad))
                pos = self._est
                if self._multirotor:
                    vel = self._va  # a estima solo conoce su velocidad respecto al aire
                if self._filter is not None:  # y, con el estimador, su viento estimado
                    pos = self._filter.p
                    vel = (self._va[0] + self._filter.wind[0], self._va[1] + self._filter.wind[1])
            else:
                dvx, dvy = spoof_offset_rate(t, self._spoofing)
                pos, vel = s.gps, (s.vx + dvx, s.vy + dvy)
            payload = sensors.gps_payload(cfg, rng, pos, vel, loss, t, self._gnss_last)
            emit("gps", EventType.POSITION_UPDATED, SensorSource.GPS, payload, telemetry=True)
            if self._gnss_last is not None:
                payload = self._gnss_payload(loss)
                emit("gps", EventType.GNSS_STATUS, SensorSource.GPS, payload, telemetry=True)
            if self._filter is not None:
                payload = self._autopilot_payload()
                emit("gps", EventType.AUTOPILOT_STATUS, None, payload, telemetry=True)
        if n % self._periods["radar"] == 0:
            payload = sensors.radar_payload(cfg, rng, s, self._radar_geometry)
            if self._radar_in_range(s.x, s.y):  # fuera de alcance no hay traza (el ruido se gasta)
                emit("radar", EventType.TRACK_UPDATED, SensorSource.RADAR, payload)
        if n % self._periods["meteo"] == 0:
            emit(
                "meteo",
                EventType.WIND_REPORTED,
                SensorSource.METEO,
                sensors.meteo_payload(
                    cfg, rng, self._station_wind(t) if self._ground_station else self._wind(t)
                ),
            )
        if n % self._periods["link"] == 0:
            if self._link_phys:
                emit("link", EventType.LINK_STATUS, None, self._link_payload(rng))
            else:
                payload = sensors.link_payload(cfg, rng, t)
                emit("link", EventType.LINK_STATUS, SensorSource.LINK, payload)
        if n % self._periods["battery"] == 0:
            model = None
            if self._battery is not None:
                b = self._battery
                model = (b.soc_pct, b.power_w, b.time_remaining_s())
            payload = sensors.battery_payload(cfg, rng, t, model)
            emit("battery", EventType.BATTERY_STATUS, SensorSource.BATTERY, payload, telemetry=True)
        return out

    def _ground_command(self, p: Point, hijacked: bool) -> Point:
        """Velocidad sobre el suelo que pide el guiado de multirrotor: hacia el punto de mira, con
        el perfil de velocidad (frena antes del punto según el giro y se puede parar) y la
        corrección integral del error lateral. En espera, un lazo P hacia el punto de espera."""
        d = self.config.drone
        if hijacked:  # lleva el dron al punto del secuestrador y se queda allí
            self._int = 0.0
            aim = end = self._target
            assert aim is not None
            v_pass, corr = 0.0, (0.0, 0.0)
        elif self._mode in ("failsafe_hold", "failsafe_land"):
            assert self._hold is not None
            gx, gy = 0.5 * (self._hold[0] - p[0]), 0.5 * (self._hold[1] - p[1])
            m = math.hypot(gx, gy)
            return (
                (gx, gy)
                if m <= HOLD_MAX_SPEED_MPS
                else (gx * HOLD_MAX_SPEED_MPS / m, gy * HOLD_MAX_SPEED_MPS / m)
            )
        else:
            a, b = self._leg()
            aim, end = aim_point(a, b, p, d.lookahead_m), b
            v_pass = (
                0.0
                if self._leg_start is not None
                else corner_speed(self.route, self._i, d.cruise_speed_mps, d.max_accel_mps2)
            )
            corr = self._lateral_correction(a, b, p)
        speed = speed_profile(
            math.hypot(end[0] - p[0], end[1] - p[1]),
            v_pass,
            d.cruise_speed_mps,
            d.max_accel_mps2,
            d.acceptance_radius_m,
        )
        ux, uy = unit(aim[0] - p[0], aim[1] - p[1])
        return speed * ux + corr[0], speed * uy + corr[1]

    def _lateral_correction(self, a: Point, b: Point, p: Point) -> Point:
        """Velocidad lateral que corrige el error acumulado respecto al tramo (integral)."""
        ki = self.config.drone.lateral_ki_per_s
        ux, uy = unit(b[0] - a[0], b[1] - a[1])
        nx, ny = -uy, ux  # normal a la izquierda
        err = (p[0] - a[0]) * nx + (p[1] - a[1]) * ny
        if ki == 0.0:
            return 0.0, 0.0
        if abs(err) < LATERAL_INT_WINDOW_M:
            cap = LATERAL_CORR_MAX_MPS / ki
            self._int = max(-cap, min(cap, self._int + err * STEP_S))
        return -ki * self._int * nx, -ki * self._int * ny

    def _advance_multirotor(self) -> None:
        """Lazo de velocidad de un multirrotor: de `t` a `t + 0,1 s`. La velocidad respecto al aire
        sigue a la que pide el guiado con la aceleración limitada; el viento se suma al suelo. Con
        la estima (sin GPS) no conoce el viento y deriva con él."""
        d, t = self.config.drone, self.t
        p = self._believed()
        hijacked = is_hijacked(t, self._hijack)
        wind = self._wind(t).vector() if self.perturbed else (0.0, 0.0)
        known = (0.0, 0.0) if self._est is not None else wind
        if self._filter is not None:  # el lazo de velocidad usa el viento que estima a bordo
            known = self._filter.wind
        cmd = limit_air_velocity(self._ground_command(p, hijacked), known, d.max_airspeed_mps)
        dvx, dvy = cmd[0] - self._va[0], cmd[1] - self._va[1]
        m, step_a = math.hypot(dvx, dvy), d.max_accel_mps2 * STEP_S
        if m > step_a:
            dvx, dvy = dvx * step_a / m, dvy * step_a / m
        self._va = (self._va[0] + dvx, self._va[1] + dvy)
        if self._filter is not None:
            self._filter.predict(self._va, STEP_S)
        vx, vy = self._va[0] + wind[0], self._va[1] + wind[1]
        # el morro mira al siguiente punto (en espera se queda como está)
        target = self._target if hijacked else self.route[min(self._i, len(self.route) - 1)]
        if target is not None and (
            hijacked or self._mode not in ("failsafe_hold", "failsafe_land")
        ):
            dx, dy = target[0] - p[0], target[1] - p[1]
            if math.hypot(dx, dy) > 1.0:
                err = angle_diff_deg(bearing_deg(dx, dy), self._heading)
                step = d.max_turn_rate_dps * STEP_S
                self._heading = (self._heading + max(-step, min(step, err))) % 360.0
        self._x += vx * STEP_S
        self._y += vy * STEP_S
        if self._est is not None:
            self._est = (self._est[0] + self._va[0] * STEP_S, self._est[1] + self._va[1] * STEP_S)
        self.n += 1
        offset = spoof_offset(self.t, self._spoofing)
        self.samples.append(Sample(self.n, self._x, self._y, vx, vy, self._heading, offset))

    def _advance(self) -> None:
        """Guiado, giro, aceleración, viento e integración: de `t` a `t + 0,1 s`."""
        if self._multirotor:
            self._advance_multirotor()
        else:
            self._advance_legacy()
        if self._battery is not None:
            air = math.hypot(*self._va) if self._multirotor else self._speed
            self._battery.step(air, STEP_S)

    def _advance_legacy(self) -> None:
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
        wx, wy = self._wind(t).vector() if self.perturbed else (0.0, 0.0)
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

    def _record_aux(self) -> None:
        """Anota la verdad ampliada del instante actual (tras aplicar fallos y comandos)."""
        n, t, cfg = self.n, self.t, self.config
        s = self.samples[n]
        leg = min(self._i, len(self.route) - 1)
        hijack = is_hijacked(t, self._hijack)
        a, b = (self._hold, self._hold) if self._hold and not hijack else self._leg()
        _, ref = project_on_segment((s.x, s.y), a, b)
        g, b = cfg.sensors.gps, cfg.sensors.battery
        _, hdop = sensors.gps_quality(cfg, t)
        sigma = g.sigma_m * hdop / g.hdop
        if self._gnss_last is not None:
            sigma = self._gnss_last.sigma_m
        w = self._wind(t)
        down = {src: (src, FaultMode.MUTE) in self._faults for src in SensorSource}
        self.aux[n] = Aux(
            n=n,
            leg_index=leg,
            ref_dist_m=ref,
            est=self._believed(),
            mode="foreign_control" if hijack else self._mode,
            link_up=self._ours_link_up(s.x, s.y)
            if self._link_phys
            else not (hijack or down[SensorSource.LINK]),
            battery_soc=self._battery.soc_pct
            if self._battery is not None
            else max(0.0, min(100.0, b.start_pct - b.drain_pct_per_min * t / 60)),
            gps_sigma_m=sigma,
            cn0_dbhz=sensors.GNSS_CN0_NOMINAL_DBHZ + self._emitter_state[0],
            emitters_active=self._emitter_state[2],
            wind_speed_mps=w.speed_mps,
            wind_from_deg=w.from_deg,
            gps_mute=down[SensorSource.GPS],
            gps_loss=(SensorSource.GPS, FaultMode.LOSS) in self._faults,
            radar_mute=down[SensorSource.RADAR],
            meteo_mute=down[SensorSource.METEO],
            link_mute=down[SensorSource.LINK],
            battery_mute=down[SensorSource.BATTERY],
            spoofing=self._spoofing is not None
            and self._spoofing.start_s <= t < self._spoofing.end_s,
            hijack=hijack,
            link_latency_ms=sensors.link_quality(cfg, t)[1],
            link_loss_pct=self._loss_pct(s.x, s.y),
            radar_in_range=self._radar_in_range(s.x, s.y),
            can_reach_home=self._truth_can_reach_home(s),
        )

    def truth(self) -> TruthFile:
        """Trayectoria real y viento real hasta el instante actual (una muestra por segundo más
        la última). Solo para las gráficas, la evaluación y la web: el agente no lo ve."""
        chosen = [s for s in self.samples if s.n in self.aux]  # cada segundo y el último
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
                    leg_index=(a := self.aux[s.n]).leg_index,
                    ref_dist_m=round(a.ref_dist_m, 2),
                    est_x=round(a.est[0], 2),
                    est_y=round(a.est[1], 2),
                    mode=a.mode,
                    link_up=a.link_up,
                    battery_soc=round(a.battery_soc, 2),
                    gps_sigma_m=round(a.gps_sigma_m, 2),
                    cn0_dbhz=round(a.cn0_dbhz, 1),
                    emitters_active=list(a.emitters_active),
                )
                for s in chosen
            ],
            wind=[
                TruthWind(
                    t=s.t,
                    speed_mps=round(self.aux[s.n].wind_speed_mps, 2),
                    from_deg=round(self.aux[s.n].wind_from_deg, 2),
                )
                for s in chosen
            ],
            emitters=radio.truth_emitters(self.config) if self._emitters_on else [],
        )


def fly(config: ScenarioConfig, perturbed: bool) -> Flight:
    """Vuela la misión sin eventos; `perturbed=False` es el plan (sin perturbaciones)."""
    return Simulator(config, perturbed=perturbed, events=False).run_physics()
