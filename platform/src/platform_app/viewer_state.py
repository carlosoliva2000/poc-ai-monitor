"""Estado del visor en directo: qué pintar a partir de los eventos y qué hace cada tecla.

Sin ventana ni red: recibe los mensajes del WebSocket de la plataforma ya como diccionarios
(`event`, `state`, `error`) y la ruta o la verdad que sirve la API HTTP, y guarda lo necesario
para pintar. Así se prueba sin GUI. El visor solo publica `control` (nunca eventos de otros
dominios), igual que la web.
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field

from .geometry import Point

SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
FAULT_SOURCES = {"1": "gps", "2": "radar", "3": "meteo", "4": "link", "5": "battery"}
TRAIL_S = 180.0  # estela del GPS que se conserva (s de simulación)
RADAR_POINTS = 45  # últimos puntos de radar
NOTICE_S = 6.0  # segundos que se ve un aviso (de pared)

# Teclas que algunos backends nombran distinto
_SPACE = {" ", "space"}
_PLUS = {"+", "plus", "add", "="}
_MINUS = {"-", "minus", "subtract", "_"}


@dataclass(frozen=True)
class GpsPoint:
    t: float
    x: float
    y: float
    fix: str


@dataclass(frozen=True)
class RadarPoint:
    t: float
    x: float
    y: float


@dataclass(frozen=True)
class WindInfo:
    t: float
    speed_mps: float
    from_deg: float


@dataclass(frozen=True)
class Detection:
    detection_id: str
    rule: str
    severity: str
    source: str | None
    since: float


@dataclass(frozen=True)
class Action:
    """Lo que provoca una tecla: un mensaje `control`, o un cambio local del visor."""

    message: dict | None = None
    toggle_truth: bool = False
    ask_scenario: bool = False
    notice: str | None = None


def clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"T+{s // 60:02d}:{s % 60:02d}"


def control(action: str, value: object = None) -> dict:
    return {"op": "control", "action": action, "value": value}


@dataclass
class ViewerState:
    """Todo lo que el visor necesita para pintar un fotograma."""

    status: str = "idle"
    scenario: str | None = None
    run_id: str | None = None
    sim_time: float = 0.0
    speed: float = 1.0
    wait_agent: bool = False
    interactive: bool = False
    active_faults: list[dict] = field(default_factory=list)

    route: list[Point] = field(default_factory=list)
    waypoints: list[tuple[str, float, float]] = field(default_factory=list)
    gps: deque[GpsPoint] = field(default_factory=deque)
    radar: deque[RadarPoint] = field(default_factory=lambda: deque(maxlen=RADAR_POINTS))
    heading_deg: float | None = None
    wind: WindInfo | None = None
    detections: dict[str, Detection] = field(default_factory=dict)
    truth: list[Point] = field(default_factory=list)
    show_truth: bool = False
    needs_plan: bool = True
    connected: bool = False
    notice: str | None = None
    notice_until: float = 0.0

    # --- entrada ----------------------------------------------------------------------------

    def apply_message(self, msg: dict, now: float | None = None) -> None:
        """Procesa un mensaje del WebSocket (`event`, `state` o `error`)."""
        op = msg.get("op")
        if op == "event":
            self.apply_event(msg["event"])
        elif op == "state":
            self.apply_state(msg)
        elif op == "error":
            self.set_notice(f"error: {msg.get('message', '')}", now)

    def apply_state(self, msg: dict) -> None:
        scenario_changed = msg.get("run_id") != self.run_id
        self.status = msg["status"]
        self.scenario = msg["scenario"]
        self.sim_time = msg["sim_time"]
        self.speed = msg["speed"]
        self.wait_agent = msg["wait_agent"]
        self.interactive = msg["interactive"]
        self.active_faults = list(msg["active_faults"])
        if scenario_changed:
            self.run_id = msg["run_id"]
            self.reset_run()

    def reset_run(self) -> None:
        """Nueva ejecución: se borra lo pintado y hay que pedir de nuevo la ruta."""
        self.gps.clear()
        self.radar.clear()
        self.heading_deg = None
        self.wind = None
        self.detections.clear()
        self.truth = []
        self.route, self.waypoints = [], []
        self.needs_plan = self.run_id is not None

    def apply_event(self, ev: dict) -> None:
        kind, p, t = ev["type"], ev["payload"], ev["sim_time"]
        if kind == "PositionUpdated":
            self.gps.append(GpsPoint(t, p["x"], p["y"], p["fix"]))
            self.heading_deg = p["heading_deg"]
            while self.gps and self.gps[0].t < t - TRAIL_S:
                self.gps.popleft()
        elif kind == "TrackUpdated":
            self.radar.append(RadarPoint(t, p["x"], p["y"]))
        elif kind == "WindReported":
            self.wind = WindInfo(t, p["speed_mps"], p["from_deg"])
        elif kind in ("DetectionRaised", "DetectionUpdated"):
            self.detections[p["detection_id"]] = Detection(
                p["detection_id"], p["rule"], p["severity"], p["source"], p["window"]["since"]
            )
        elif kind == "DetectionCleared":
            self.detections.pop(p["detection_id"], None)
        elif kind == "SimulationStarted":
            self.run_id, self.scenario = p["run_id"], p["scenario"]
            self.reset_run()
        elif kind == "SimulationReset":
            self.reset_run()
        self.sim_time = max(self.sim_time, t) if kind != "SimulationStarted" else t

    def set_plan(self, plan: dict) -> None:
        """`GET /api/plan`: la polilínea planificada y los waypoints."""
        self.waypoints = [(w["id"], w["x"], w["y"]) for w in plan["waypoints"]]
        self.route = [(x, y) for _, x, y in self.waypoints]
        self.needs_plan = False

    def set_truth(self, truth: dict) -> None:
        """`GET /api/truth`: la verdad hasta el instante actual (solo para pintarla)."""
        self.truth = [(s["x"], s["y"]) for s in truth["trajectory"]]

    def set_notice(self, text: str, now: float | None = None) -> None:
        self.notice = text
        self.notice_until = (time.monotonic() if now is None else now) + NOTICE_S

    # --- salida (qué pintar) ------------------------------------------------------------------

    @property
    def drone(self) -> tuple[float, float, float] | None:
        """(x, y, rumbo) del dron según su GPS; `None` si aún no hay posición."""
        if not self.gps or self.heading_deg is None:
            return None
        last = self.gps[-1]
        return last.x, last.y, self.heading_deg

    @property
    def without_fix(self) -> bool:
        """`True` si la última posición del GPS no tiene fix (pérdida: es una estima)."""
        return bool(self.gps) and self.gps[-1].fix == "none"

    def highlight_since(self) -> float | None:
        """Inicio del episodio abierto más antiguo: desde ahí se resalta la estela."""
        return min((d.since for d in self.detections.values()), default=None)

    def silenced_sources(self) -> list[str]:
        return [f["source"] for f in self.active_faults if f["mode"] == "mute"]

    def bounds(self, margin_m: float = 150.0) -> tuple[float, float, float, float] | None:
        """(x_min, x_max, y_min, y_max) de todo lo que se pinta, con margen."""
        pts: list[Point] = list(self.route) + list(self.truth)
        pts += [(p.x, p.y) for p in self.gps] + [(p.x, p.y) for p in self.radar]
        if not pts:
            return None
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs) - margin_m, max(xs) + margin_m, min(ys) - margin_m, max(ys) + margin_m

    def wind_text(self) -> str:
        if self.wind is None:
            return "viento: sin datos"
        w = self.wind
        return f"viento {w.speed_mps:.1f} m/s del {w.from_deg:.0f}° ({clock(w.t)})"

    def wind_vector(self) -> tuple[float, float] | None:
        """Hacia dónde sopla (este, norte), de módulo 1; `None` sin datos."""
        if self.wind is None or self.wind.speed_mps <= 0:
            return None
        to = math.radians(self.wind.from_deg + 180.0)
        return math.sin(to), math.cos(to)

    def faults_text(self) -> str:
        if not self.active_faults:
            return "ninguno"
        return ", ".join(f"{f['source']}({f['mode']})" for f in self.active_faults)

    def status_line(self, now: float | None = None) -> str:
        """Línea de estado: tiempo, velocidad, estado, esperar al agente, interactivo y fallos."""
        if not self.connected:
            return "sin conexión con la plataforma"
        yes = {True: "sí", False: "no"}
        parts = [
            f"{self.scenario or '—'}",
            clock(self.sim_time),
            f"{self.speed:g}×",
            self.status,
            f"esperar al agente: {yes[self.wait_agent]}",
            f"interactivo: {'SÍ' if self.interactive else 'no'}",
            f"fallos: {self.faults_text()}",
        ]
        line = " · ".join(parts)
        if self.notice and (time.monotonic() if now is None else now) < self.notice_until:
            line += f"   ⚠ {self.notice}"
        return line

    def detections_lines(self) -> list[str]:
        lines = []
        for d in sorted(self.detections.values(), key=lambda d: d.since):
            what = f"{d.rule} ({d.source})" if d.source else d.rule
            lines.append(f"{what} · {d.severity} · desde {clock(d.since)}")
        return lines

    # --- teclado ------------------------------------------------------------------------------

    def key_action(self, key: str) -> Action | None:
        """Qué hace una tecla (o `None` si no hace nada). Los fallos exigen el modo interactivo."""
        if key in _SPACE:
            return Action(control("pause" if self.status == "running" else "play"))
        if key == "n":
            return Action(control("step"))
        if key in _PLUS or key in _MINUS:
            i = min(range(len(SPEEDS)), key=lambda k: abs(SPEEDS[k] - self.speed))
            j = min(len(SPEEDS) - 1, i + 1) if key in _PLUS else max(0, i - 1)
            self.speed = SPEEDS[j]  # optimista: pulsaciones seguidas suman; el `state` lo confirma
            return Action(control("speed", SPEEDS[j]))
        if key == "0":
            return Action(control("reset"))
        if key == "w":
            return Action(control("wait_agent", not self.wait_agent))
        if key == "t":
            return Action(toggle_truth=True)
        if key == "i":
            return Action(control("interactive", not self.interactive))
        if key == "l":
            return Action(ask_scenario=True)
        if key in FAULT_SOURCES or key == "g":
            if not self.interactive:
                return Action(notice="enciende el modo interactivo (tecla i) para inyectar fallos")
            if key == "g":
                return Action(control("fault", self._fault("gps", "loss")))
            return Action(control("fault", self._fault(FAULT_SOURCES[key], "mute")))
        return None

    def _fault(self, source: str, mode: str) -> dict:
        """Activa el fallo si la fuente no lo tiene; si lo tiene del mismo tipo, lo termina."""
        active = any(f["source"] == source and f["mode"] == mode for f in self.active_faults)
        return {"source": source, "mode": mode, "active": not active}
