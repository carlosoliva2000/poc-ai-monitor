"""Reproductor: reloj simulado que ejecuta el simulador en directo y publica sus eventos.

No lee `events.jsonl`: ejecuta `Simulator` paso a paso (0,1 s). Sin intervenciones y con el modo
interactivo apagado, lo que publica es idéntico a `runs/<escenario>/events.jsonl`.

Diseño:
- Toda la lógica es **síncrona y determinista**: `advance(sim_seconds)` hace avanzar la
  simulación esa cantidad de tiempo simulado y `run_to_end()` la ejecuta hasta el final. Las
  pruebas usan estos métodos y no necesitan tiempo real.
- El bucle de asyncio (`run_clock`) solo mide el reloj de pared y llama a `advance`.
- Los eventos que el simulador ya ha producido pero aún no se han publicado esperan en una cola
  (`_queue`). Así «paso» publica exactamente un evento y la pausa por «esperar al agente» puede
  cortar a mitad de un instante sin perder nada.
- `sim_time` (el instante actual para el estado y para el corte temporal de las tools) es el
  del evento más antiguo aún sin publicar o, si no hay ninguno, el del próximo paso del
  simulador; ningún evento publicado tiene un `sim_time` posterior.
- `cursor` cuenta los eventos publicados que produce el simulador (misión, fuentes y fallos);
  no cuenta los del reproductor (`plr-`). Al terminar sin intervenciones coincide con
  `total_events`.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from poc_contracts.enums import (
    EventType,
    FaultMode,
    FaultOrigin,
    PauseReason,
    PlayerStatus,
    SensorSource,
)
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.run_files import PlanFile, RunMeta, TruthFile
from poc_contracts.scenario import ScenarioConfig
from poc_contracts.ws import SPEEDS, ActiveFault, PlayerState

from .bus import Bus
from .generator.build import generate, write_run
from .generator.controller import STEP_S
from .generator.events import make_event
from .generator.scenario_io import list_scenarios, load_scenario
from .generator.simulator import Simulator
from .paths import RUNS_DIR, SCENARIOS_DIR

log = logging.getLogger(__name__)

TICK_S = 0.05  # periodo del bucle de reloj (reloj de pared)
MAX_TICK_S = 0.5  # tras un atasco no se recupera más de esto de golpe
WAIT_AGENT_TIMEOUT_S = 90.0  # reloj de pared
AI_PATTERN = "citadel.pub.evt.ai.>"
MONITOR_SOURCE = "ai-monitor"
INTERACTIVE_OFF_MESSAGE = "interactive mode is off: turn it on to inject faults"
META_KEYS = ("speed", "wait_agent", "interactive")


class PlayerError(Exception):
    """Error de una orden al reproductor; el mensaje (en español) llega al cliente."""


class Player:
    def __init__(
        self,
        bus: Bus,
        *,
        runs_dir: Path = RUNS_DIR,
        scenarios_dir: Path = SCENARIOS_DIR,
        wait_timeout_s: float = WAIT_AGENT_TIMEOUT_S,
        wall_clock: Callable[[], float] = time.monotonic,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.bus = bus
        self.runs_dir = runs_dir
        self.scenarios_dir = scenarios_dir
        self.wait_timeout_s = wait_timeout_s
        self._wall_clock = wall_clock
        self._run_id_factory = run_id_factory or _default_run_id
        self.speed = 1.0
        self.wait_agent = False
        self.interactive = False
        self.listeners: list[Callable[[], None]] = []

        self.config: ScenarioConfig | None = None
        self.sim: Simulator | None = None
        self.plan: PlanFile | None = None
        self.run_id: str | None = None
        self.total_events = 0
        self.duration_s = 0.0
        self._status = PlayerStatus.IDLE
        self._queue: deque[EventDraft] = deque()
        self._budget = 0.0
        self._plr_n = 0
        self._cursor = 0
        self._started = False
        self._dumped = False
        self._waiting_for: set[str] = set()
        self._wait_deadline = 0.0
        self._history: dict[str, list[dict]] = {key: [] for key in META_KEYS}
        bus.subscribe(AI_PATTERN, self._on_ai_event)

    # --- Estado -------------------------------------------------------------------------------

    @property
    def status(self) -> PlayerStatus:
        return self._status

    @property
    def scenario(self) -> str | None:
        return self.config.name if self.config else None

    @property
    def sim_time(self) -> float:
        """Instante actual de la simulación (ver el docstring del módulo)."""
        if self.sim is None:
            return 0.0
        return self._queue[0].sim_time if self._queue else self.sim.t

    def state(self) -> PlayerState:
        faults = self.sim.active_faults if self.sim else []
        return PlayerState(
            status=self._status,
            scenario=self.scenario,
            run_id=self.run_id,
            sim_time=self.sim_time,
            speed=self.speed,
            wait_agent=self.wait_agent,
            interactive=self.interactive,
            active_faults=[ActiveFault(source=s, mode=f.mode, origin=f.origin) for s, f in faults],
            cursor=self._cursor,
            total_events=self.total_events,
        )

    def truth(self) -> TruthFile:
        """Verdad de la simulación en curso, sin pasar del instante actual. Solo para la web,
        el visor y la evaluación: ninguna tool la usa."""
        sim = self._require_sim()
        full = sim.truth()
        limit = self.sim_time + 1e-9
        return TruthFile(
            duration_s=min(full.duration_s, self.sim_time),
            trajectory=[s for s in full.trajectory if s.t <= limit],
            wind=[w for w in full.wind if w.t <= limit],
        )

    def _notify(self) -> None:
        for listener in self.listeners:
            try:
                listener()
            except Exception:
                log.exception("state listener failed")

    def _require_sim(self) -> Simulator:
        if self.sim is None:
            raise PlayerError("no scenario is loaded")
        return self.sim

    # --- Carga y reinicio ---------------------------------------------------------------------

    def load(self, name: str) -> None:
        """Carga un escenario (lo genera en `runs/<nombre>/` si no existe) con un `run_id` nuevo."""
        if name not in list_scenarios(self.scenarios_dir):
            raise PlayerError(f"unknown scenario: {name!r}")
        config = load_scenario(name, self.scenarios_dir)
        run = generate(config)  # resultado esperado sin intervenciones
        if not (self.runs_dir / name / "events.jsonl").exists():
            write_run(run, self.runs_dir / name)

        if self.config is not None:
            self._plr(EventType.SIMULATION_RESET, {})
            self._dump_timeline()
        was_interactive = self.interactive
        self.interactive = False  # cada carga empieza con el modo interactivo apagado
        self.bus.reset()
        self.config = config
        self.plan = run.plan
        self.total_events = len(run.events)
        self.duration_s = run.truth.duration_s
        self.run_id = self._new_run_id()
        etas = [w.eta_s for w in run.plan.waypoints]
        self.sim = Simulator(config, etas=etas)
        self._queue = deque(self.sim.start())  # t = 0: se publican al primer play o paso
        self._budget = 0.0
        self._plr_n = 0
        self._cursor = 0
        self._started = False
        self._dumped = False
        self._waiting_for.clear()
        self._history = {key: [] for key in META_KEYS}
        self._status = PlayerStatus.IDLE
        self._plr(
            EventType.SIMULATION_STARTED,
            {
                "scenario": name,
                "run_id": self.run_id,
                "duration_s": self.duration_s,
                "total_events": self.total_events,
            },
        )
        if was_interactive:  # queda registrado en el timeline nuevo que se ha apagado
            self._plr(EventType.INTERACTIVE_MODE_CHANGED, {"interactive": False})
        self._notify()

    def reset(self) -> None:
        """Recarga el mismo escenario: `run_id` nuevo, bus y timeline limpios, `seq` desde 1."""
        if self.config is None:
            raise PlayerError("no scenario is loaded")
        self.load(self.config.name)

    def _new_run_id(self) -> str:
        run_id = self._run_id_factory()
        while run_id == self.run_id:  # dos cargas en el mismo segundo
            stamp = datetime.strptime(run_id, "%Y%m%d-%H%M%S") + timedelta(seconds=1)
            run_id = stamp.strftime("%Y%m%d-%H%M%S")
        return run_id

    def _dump_timeline(self) -> None:
        """Vuelca el timeline de la ejecución si empezó y aún no se ha volcado."""
        if self.config is None or not self._started or self._dumped:
            return
        path = self.runs_dir / self.config.name / str(self.run_id) / "timeline.jsonl"
        self.bus.timeline.dump(path)
        self._dumped = True
        self._write_meta()
        log.info("timeline written to %s", path)

    # --- Datos de la ejecución (`run_meta.json`) ------------------------------------------------

    def _mark_started(self) -> None:
        """La ejecución arranca (primer play o paso): se guardan los valores iniciales."""
        if self._started:
            return
        self._started = True
        values = {
            "speed": self.speed,
            "wait_agent": self.wait_agent,
            "interactive": self.interactive,
        }
        for key in META_KEYS:
            self._history[key] = [{"sim_time": 0.0, "value": values[key]}]
        self._write_meta()

    def _record(self, key: str, value: float | bool) -> None:
        """Anota un cambio de velocidad, de «esperar al agente» o del modo interactivo durante la
        ejecución (los anteriores al primer play no cuentan: son el valor inicial)."""
        if not self._started or self.config is None:
            return
        history = self._history[key]
        if history and history[-1]["value"] == value:
            return
        history.append({"sim_time": round(self.sim_time, 1), "value": value})
        self._write_meta()

    def _write_meta(self) -> None:
        """`runs/<escenario>/<run_id>/run_meta.json`: lo que no está en el timeline y la evaluación
        pone en la cabecera de `eval.md` (valores iniciales y sus cambios con el instante)."""
        if self.config is None or not self._started:
            return
        fields: dict = {"scenario": self.config.name, "run_id": self.run_id}
        for key in META_KEYS:
            history = self._history[key]
            fields[key] = history[0]["value"]
            fields[f"{key}_changes"] = history[1:]
        meta = RunMeta.model_validate(fields)
        folder = self.runs_dir / self.config.name / str(self.run_id)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "run_meta.json").write_text(
                meta.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            log.exception("could not write run_meta.json")

    def shutdown(self) -> None:
        """Al parar el servidor: no se pierde el timeline de una ejecución a medias."""
        self._dump_timeline()

    # --- Órdenes ------------------------------------------------------------------------------

    def play(self) -> None:
        self._require_sim()
        if self._status == PlayerStatus.FINISHED:
            raise PlayerError("the simulation has finished: restart it to watch it again")
        if self._status == PlayerStatus.RUNNING:
            return
        was_paused = self._status == PlayerStatus.PAUSED
        self._waiting_for.clear()
        self._mark_started()
        self._status = PlayerStatus.RUNNING
        if was_paused:
            self._plr(EventType.SIMULATION_RESUMED, {})
        self._notify()

    def pause(self) -> None:
        self._require_sim()
        if self._status == PlayerStatus.RUNNING:
            self._pause(PauseReason.USER)
        elif self._status == PlayerStatus.PAUSED:
            self._waiting_for.clear()  # una pausa del usuario no se levanta sola
            self._notify()

    def step(self) -> None:
        """Publica el siguiente evento y se queda en pausa."""
        sim = self._require_sim()
        if self._status == PlayerStatus.FINISHED:
            raise PlayerError("the simulation has finished: restart it to watch it again")
        if self._status == PlayerStatus.RUNNING:
            self._pause(PauseReason.USER)
        self._waiting_for.clear()
        self._mark_started()
        while not self._queue and not sim.finished:
            self._queue.extend(sim.step())
        if self._queue:
            self._publish_sim_event(self._queue.popleft())
        if self._status == PlayerStatus.IDLE:
            self._pause(PauseReason.USER)  # así el play siguiente publica un Resumed coherente
        if not self._queue and sim.finished:
            self._finish()
        self._notify()

    def set_speed(self, speed: float) -> None:
        if speed not in SPEEDS:
            raise PlayerError(f"invalid speed: {speed} (values: {SPEEDS})")
        self.speed = speed
        self._record("speed", speed)
        self._notify()

    def set_wait_agent(self, value: bool) -> None:
        self.wait_agent = value
        self._record("wait_agent", value)
        if not value and self._waiting_for:
            self._stop_waiting()
        self._notify()

    def set_interactive(self, value: bool) -> None:
        if value == self.interactive:
            return
        self.interactive = value
        self._record("interactive", value)
        if self.config is not None:
            self._plr(EventType.INTERACTIVE_MODE_CHANGED, {"interactive": value})
        self._notify()

    def fault(self, source: SensorSource, mode: FaultMode, active: bool) -> None:
        """Activa o termina un fallo manual desde el instante actual (solo en modo interactivo)."""
        if not self.interactive:
            raise PlayerError(INTERACTIVE_OFF_MESSAGE)
        sim = self._require_sim()
        if sim.finished and not self._queue:
            raise PlayerError("the simulation has finished: faults cannot be injected")
        try:
            sim.set_fault(source, mode, active, FaultOrigin.MANUAL)
        except ValueError as exc:
            raise PlayerError(str(exc)) from exc
        self._notify()

    # --- Avance -------------------------------------------------------------------------------

    def advance(self, sim_seconds: float) -> None:
        """Hace avanzar la simulación `sim_seconds` de tiempo simulado si está en marcha."""
        if self._status != PlayerStatus.RUNNING:
            return
        sim = self._require_sim()
        self._budget += sim_seconds
        while True:
            self._drain_queue()
            if self._status != PlayerStatus.RUNNING:
                self._budget = 0.0
                return
            if sim.finished:
                self._budget = 0.0
                self._finish()
                return
            if self._budget < STEP_S - 1e-9:
                return
            self._budget -= STEP_S
            self._queue.extend(sim.step())

    def run_to_end(self) -> None:
        """Pone en marcha (si hace falta) y ejecuta hasta el final, sin tiempo real. Se detiene
        antes si el reproductor se pausa (p. ej. esperando al agente)."""
        if self._status != PlayerStatus.RUNNING:
            self.play()
        self.advance(float("inf"))

    def _drain_queue(self) -> None:
        while self._queue and self._status == PlayerStatus.RUNNING:
            self._publish_sim_event(self._queue.popleft())

    def _publish_sim_event(self, event: EventDraft) -> Envelope:
        self._cursor += 1
        return self.bus.publish(event)

    def _finish(self) -> None:
        self._status = PlayerStatus.FINISHED
        assert self.config is not None
        self._plr(
            EventType.SIMULATION_FINISHED, {"scenario": self.config.name, "run_id": self.run_id}
        )
        self._dump_timeline()
        self._notify()

    def _pause(self, reason: PauseReason) -> None:
        self._status = PlayerStatus.PAUSED
        self._plr(EventType.SIMULATION_PAUSED, {"reason": reason.value})
        self._notify()

    def _plr(self, event_type: EventType, payload: dict) -> Envelope:
        """Evento propio del reproductor (`plr-`), con el instante actual de la simulación."""
        assert self.config is not None
        self._plr_n += 1
        event = make_event(self.config, event_type, self.sim_time, self._plr_n, payload)
        return self.bus.publish(event)

    # --- Esperar al agente --------------------------------------------------------------------

    def _on_ai_event(self, event: Envelope) -> None:
        """Pausa ante un evento de detección (nueva, actualizada o cerrada) y reanuda cuando el
        monitor responde a todos con un evento que lleve su `event_id` como `causation_id`."""
        if event.type in (
            EventType.DETECTION_RAISED,
            EventType.DETECTION_UPDATED,
            EventType.DETECTION_CLEARED,
        ):
            if not self.wait_agent:
                return
            if self._status == PlayerStatus.RUNNING:
                self._pause(PauseReason.WAITING_AGENT)
            elif not self._waiting_for:
                return  # pausa del usuario o fin de simulación: no se espera a nadie
            self._waiting_for.add(event.event_id)
            self._wait_deadline = self._wall_clock() + self.wait_timeout_s
        elif (
            self._waiting_for
            and event.source == MONITOR_SOURCE
            and event.causation_id in self._waiting_for
        ):
            self._waiting_for.discard(event.causation_id)  # type: ignore[arg-type]
            if not self._waiting_for:
                self._stop_waiting()

    def _stop_waiting(self) -> None:
        self._waiting_for.clear()
        if self._status == PlayerStatus.PAUSED:
            self._status = PlayerStatus.RUNNING
            self._plr(EventType.SIMULATION_RESUMED, {})
        self._notify()

    def check_wait_timeout(self) -> None:
        """Reanuda si se ha agotado la espera al agente (reloj de pared)."""
        if self._waiting_for and self._wall_clock() >= self._wait_deadline:
            log.warning("agent did not answer in %.0f s: resuming", self.wait_timeout_s)
            self._stop_waiting()

    # --- Reloj de pared -----------------------------------------------------------------------

    async def run_clock(self) -> None:
        """Bucle de asyncio: convierte el reloj de pared en tiempo simulado según la velocidad."""
        last = time.monotonic()
        while True:
            await asyncio.sleep(TICK_S)
            now = time.monotonic()
            elapsed, last = min(now - last, MAX_TICK_S), now
            try:
                self.advance(elapsed * self.speed)
                self.check_wait_timeout()
            except Exception:
                log.exception("player tick failed")


def _default_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
