"""Visor en directo sin web: una ventana de matplotlib conectada al WebSocket de la plataforma.

Se conecta como cliente `web` (solo publica `control`, igual que la web), pinta lo que llega
(~10 fotogramas por segundo) y traduce las teclas en mensajes `control`:

    espacio  play/pausa      n  paso            +/-  velocidad       0  reinicio
    w  esperar al agente     t  verdad (GET /api/truth, apagada por defecto)
    i  modo interactivo      1-5  silenciar/reactivar gps, radar, meteo, enlace, batería
    g  pérdida de GPS        l  cargar otro escenario (pide el nombre por consola)

Los fallos (1-5 y g) solo se aceptan con el modo interactivo encendido. Si no hay forma de abrir
una ventana (sin pantalla o sin Tk), guarda un PNG que se refresca cada segundo (`--png`).

Uso: `uv run --project platform python -m platform_app.viewer [--platform http://127.0.0.1:8100]`.
La lógica de estado (qué pintar y qué hace cada tecla) está en `viewer_state.py`.
"""

import argparse
import json
import logging
import math
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib
from matplotlib.markers import MarkerStyle
from matplotlib.path import Path as MplPath
from matplotlib.transforms import Affine2D
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .viewer_state import Action, ViewerState

log = logging.getLogger("viewer")

DEFAULT_PLATFORM = "http://127.0.0.1:8100"
FRAME_MS = 100  # ~10 fotogramas por segundo
TRUTH_EVERY_FRAMES = 10  # la verdad se pide una vez por segundo mientras está activa
PNG_EVERY_S = 1.0
HTTP_TIMEOUT_S = 2.0

# Colores (los mismos que las gráficas de los escenarios)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3de"
PLAN = "#b9b8b2"
TRUTH = "#2a78d6"
GPS = "#eb6834"
RADAR = "#1baf7a"
ALERT = "#c0262d"

# Flecha del dron apuntando al norte; se gira con `Affine2D` (el marcador `(n, 0, ángulo)` de
# matplotlib no sirve para esto: con ángulos que no son múltiplos de 90° se ve mal)
DRONE_SHAPE = MplPath(
    [(0, 1), (-0.6, -0.8), (0, -0.4), (0.6, -0.8), (0, 1)],
    [MplPath.MOVETO, MplPath.LINETO, MplPath.LINETO, MplPath.LINETO, MplPath.CLOSEPOLY],
)


def drone_marker(heading_deg: float) -> MarkerStyle:
    """Marcador del dron con el morro hacia `heading_deg` (0 = norte, sentido horario)."""
    return MarkerStyle(DRONE_SHAPE, transform=Affine2D().rotate_deg(-heading_deg))


HELP = (
    "space play/pause · n step · +/- speed · 0 restart · w wait for the agent · "
    "t truth · i interactive · 1-5 mute gps/radar/meteo/link/battery · g GPS loss · "
    "l load scenario"
)


# --- enlace con la plataforma -----------------------------------------------------------------


def fetch_json(url: str) -> dict | None:
    """GET de una URL de la API que devuelve JSON; `None` si falla."""
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as response:  # noqa: S310
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None


class PlatformLink(threading.Thread):
    """Hilo que mantiene el WebSocket (reconecta solo) y vuelca los mensajes en `inbox`."""

    def __init__(self, platform_url: str, inbox: queue.Queue) -> None:
        super().__init__(daemon=True, name="platform-link")
        self.ws_url = platform_url.replace("http", "ws", 1).rstrip("/") + "/ws"
        self.inbox = inbox
        self._ws = None
        self._send_lock = threading.Lock()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with connect(self.ws_url, open_timeout=3) as ws:
                    self._ws = ws
                    ws.send(json.dumps({"op": "hello", "client": "web"}))
                    ws.send(json.dumps({"op": "subscribe", "patterns": ["citadel.pub.evt.>"]}))
                    self.inbox.put({"op": "_connected"})
                    while not self._stop_event.is_set():
                        try:
                            raw = ws.recv(timeout=0.5)
                        except TimeoutError:
                            continue
                        self.inbox.put(json.loads(raw))
            except (OSError, WebSocketException, ValueError) as exc:
                log.warning("websocket %s: %s", self.ws_url, exc)
            finally:
                self._ws = None
                self.inbox.put({"op": "_disconnected"})
            self._stop_event.wait(1.0)

    def send(self, message: dict) -> bool:
        """Envía un mensaje `control`; `False` si no hay conexión."""
        ws = self._ws
        if ws is None:
            return False
        try:
            with self._send_lock:
                ws.send(json.dumps(message))
        except (OSError, WebSocketException) as exc:
            log.warning("send failed: %s", exc)
            return False
        return True

    def close(self) -> None:
        self._stop_event.set()


# --- pintado ------------------------------------------------------------------------------------


class Renderer:
    """Crea los elementos de la figura una vez y en cada fotograma solo les cambia los datos."""

    def __init__(self, fig, ax) -> None:
        self.fig, self.ax = fig, ax
        self._limits: tuple[float, float, float, float] | None = None
        self._wp_artists: list = []
        self._wp_key: tuple = ()
        self._wind_arrow = None

        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel("x (m, east)")
        ax.set_ylabel("y (m, north)")
        ax.grid(True, color=GRID, lw=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        (self.route_line,) = ax.plot([], [], color=PLAN, lw=2.5, ls=(0, (6, 4)), zorder=1,
                                     label="planned route")  # fmt: skip
        (self.truth_line,) = ax.plot(
            [], [], color=TRUTH, lw=1.6, zorder=3, label="truth (simulator only)"
        )
        (self.truth_dot,) = ax.plot([], [], color=TRUTH, marker="o", ms=7, ls="", zorder=3)
        (self.trail,) = ax.plot([], [], color=GPS, lw=1.2, alpha=0.8, zorder=4, label="GPS (trail)")
        (self.trail_hot,) = ax.plot(
            [], [], color=ALERT, lw=2.4, zorder=5, label="with open detection"
        )
        (self.gps_dots,) = ax.plot(
            [], [], color=GPS, marker="o", ms=3.5, ls="", alpha=0.6, zorder=4
        )
        (self.gps_est,) = ax.plot([], [], color=GPS, marker="o", ms=5, ls="", mfc="none", zorder=4,
                                  label="GPS without fix (estimate)")  # fmt: skip
        (self.radar,) = ax.plot([], [], color=RADAR, marker="D", ms=5, ls="", alpha=0.7, zorder=4,
                                label="radar")  # fmt: skip
        (self.ring,) = ax.plot([], [], color=ALERT, marker="o", ms=24, ls="", mfc="none", mew=2,
                               zorder=6)  # fmt: skip
        (self.drone,) = ax.plot([], [], color=INK, marker=drone_marker(0), ms=20, ls="", zorder=7,
                                label="drone (heading)")  # fmt: skip
        ax.legend(loc="lower left", fontsize=8, frameon=False)

        self.det_text = ax.text(0.01, 0.99, "", transform=ax.transAxes, va="top", ha="left",
                                fontsize=9, color=ALERT, fontweight="bold")  # fmt: skip
        self.wind_text = ax.text(0.99, 0.99, "", transform=ax.transAxes, va="top", ha="right",
                                 fontsize=9, color=INK_SOFT)  # fmt: skip
        self.status_text = fig.text(0.01, 0.045, "", fontsize=10, color=INK, va="center")
        fig.text(0.01, 0.012, HELP, fontsize=7.5, color=INK_SOFT, va="center")

    def draw(self, state: ViewerState) -> None:
        r = list(zip(*state.route, strict=False))
        self.route_line.set_data(*(r or ([], [])))
        self._draw_waypoints(state)

        gps = list(state.gps)
        self.trail.set_data([p.x for p in gps], [p.y for p in gps])
        since = state.highlight_since()
        hot = [p for p in gps if since is not None and p.t >= since]
        self.trail_hot.set_data([p.x for p in hot], [p.y for p in hot])
        self.gps_dots.set_data(
            [p.x for p in gps if p.fix != "none"], [p.y for p in gps if p.fix != "none"]
        )
        self.gps_est.set_data(
            [p.x for p in gps if p.fix == "none"], [p.y for p in gps if p.fix == "none"]
        )
        radar = list(state.radar)
        self.radar.set_data([p.x for p in radar], [p.y for p in radar])

        pos = state.drone
        if pos is None:
            self.drone.set_data([], [])
            self.ring.set_data([], [])
        else:
            x, y, heading = pos
            self.drone.set_data([x], [y])
            self.drone.set_marker(drone_marker(heading))
            self.ring.set_data([x] if state.detections else [], [y] if state.detections else [])

        if state.show_truth and state.truth:
            self.truth_line.set_data(*zip(*state.truth, strict=True))
            self.truth_dot.set_data([state.truth[-1][0]], [state.truth[-1][1]])
        else:
            self.truth_line.set_data([], [])
            self.truth_dot.set_data([], [])

        self.det_text.set_text("\n".join(state.detections_lines()))
        self.wind_text.set_text(state.wind_text())
        self._draw_wind_arrow(state)
        self.status_text.set_text(state.status_line())
        self._fit(state)

    def _draw_waypoints(self, state: ViewerState) -> None:
        key = tuple(state.waypoints)
        if key == self._wp_key:
            return
        for artist in self._wp_artists:
            artist.remove()
        self._wp_artists = []
        self._wp_key = key
        for wid, x, y in state.waypoints:
            marker = "s" if wid == "BASE" else "o"
            (dot,) = self.ax.plot([x], [y], marker=marker, ms=9, mfc=SURFACE, mec=INK_SOFT, mew=1.5,
                                  ls="", zorder=2)  # fmt: skip
            label = self.ax.annotate(wid, (x, y), xytext=(8, 8), textcoords="offset points",
                                     fontsize=8, color=INK_SOFT)  # fmt: skip
            self._wp_artists += [dot, label]

    def _draw_wind_arrow(self, state: ViewerState) -> None:
        if self._wind_arrow is not None:
            self._wind_arrow.remove()
            self._wind_arrow = None
        vec = state.wind_vector()
        if vec is None:
            return
        cx, cy, k = 0.93, 0.89, 0.045
        self._wind_arrow = self.ax.annotate(
            "", xy=(cx + k * vec[0], cy + k * vec[1]), xytext=(cx - k * vec[0], cy - k * vec[1]),
            xycoords="axes fraction", textcoords="axes fraction",
            arrowprops={"arrowstyle": "-|>", "color": INK_SOFT, "lw": 2},
        )  # fmt: skip

    def _fit(self, state: ViewerState) -> None:
        """Ajusta los límites a lo pintado, en saltos de 100 m para que no tiemblen."""
        b = state.bounds()
        if b is None:
            return
        x0, x1, y0, y1 = (math.floor(b[0] / 100) * 100, math.ceil(b[1] / 100) * 100,
                          math.floor(b[2] / 100) * 100, math.ceil(b[3] / 100) * 100)  # fmt: skip
        if self._limits == (x0, x1, y0, y1):
            return
        self._limits = (x0, x1, y0, y1)
        self.ax.set_xlim(x0, x1)
        self.ax.set_ylim(y0, y1)


def make_figure():
    """Figura y ejes del visor (con el backend ya elegido)."""
    import matplotlib.pyplot as plt

    # g y l (fallo de GPS, cargar escenario) chocan con los atajos de matplotlib de la cuadrícula
    # y la escala logarítmica
    for key in ("keymap.grid", "keymap.grid_minor", "keymap.yscale", "keymap.xscale"):
        plt.rcParams[key] = []
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                         "savefig.facecolor": SURFACE})  # fmt: skip
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.subplots_adjust(top=0.96, left=0.07, right=0.98, bottom=0.12)
    return fig, Renderer(fig, ax)


# --- bucle principal ----------------------------------------------------------------------------


class Viewer:
    def __init__(self, platform_url: str) -> None:
        self.platform_url = platform_url.rstrip("/")
        self.state = ViewerState()
        self.inbox: queue.Queue = queue.Queue()
        self.link = PlatformLink(self.platform_url, self.inbox)
        self._frame = 0

    def start(self) -> None:
        self.link.start()

    def fetch(self, path: str, kind: str) -> None:
        """Pide `GET /api/<path>` en un hilo (para no bloquear la ventana) y lo deja en la cola."""

        def work() -> None:
            data = fetch_json(f"{self.platform_url}/api/{path}")
            if data is not None:
                self.inbox.put({"op": f"_{kind}", "data": data})

        threading.Thread(target=work, daemon=True).start()

    def update(self) -> None:
        """Procesa lo que ha llegado desde el último fotograma."""
        st = self.state
        while True:
            try:
                msg = self.inbox.get_nowait()
            except queue.Empty:
                break
            op = msg.get("op")
            if op == "_connected":
                st.connected = True
            elif op == "_disconnected":
                st.connected = False
            elif op == "_plan":
                st.set_plan(msg["data"])
            elif op == "_truth":
                st.set_truth(msg["data"])
            else:
                st.apply_message(msg)
        if st.connected and st.needs_plan and st.run_id is not None:
            st.needs_plan = False  # una petición; si falla, se vuelve a pedir al cambiar de run
            self.fetch("plan", "plan")
        self._frame += 1
        if st.show_truth and st.connected and self._frame % TRUTH_EVERY_FRAMES == 0:
            self.fetch("truth", "truth")

    def on_key(self, key: str) -> None:
        action = self.state.key_action(key)
        if action is not None:
            self.perform(action)

    def perform(self, action: Action) -> None:
        st = self.state
        if action.notice:
            st.set_notice(action.notice)
        if action.toggle_truth:
            st.show_truth = not st.show_truth
            st.truth = []
            if st.show_truth:
                self.fetch("truth", "truth")
        if action.ask_scenario:
            threading.Thread(target=self._ask_scenario, daemon=True).start()
        if action.message is not None and not self.link.send(action.message):
            st.set_notice("no connection to the platform")

    def _ask_scenario(self) -> None:
        try:
            name = input("Scenario to load (YAML name): ").strip()
        except EOFError:
            return
        if name and not self.link.send({"op": "control", "action": "load", "value": name}):
            self.state.set_notice("no connection to the platform")


def window_available() -> bool:
    """`True` si matplotlib puede abrir una ventana Tk (hay pantalla y `tkinter`)."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        import tkinter

        root = tkinter.Tk()
        root.destroy()
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de Tk significa «sin ventana»
        log.warning("Tk is not usable: %s", exc)
        return False
    return True


def run_window(viewer: Viewer) -> None:
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    fig, renderer = make_figure()
    fig.canvas.manager.set_window_title("poc-ai-monitor · live viewer")
    fig.canvas.mpl_connect("key_press_event", lambda e: viewer.on_key(e.key or ""))

    def tick() -> None:
        viewer.update()
        renderer.draw(viewer.state)
        fig.canvas.draw_idle()

    timer = fig.canvas.new_timer(interval=FRAME_MS)
    timer.add_callback(tick)
    timer.start()
    plt.show()


def run_png(viewer: Viewer, path: Path) -> None:
    """Sin ventana: pinta con Agg y guarda un PNG que se refresca cada segundo."""
    matplotlib.use("Agg")
    fig, renderer = make_figure()
    last_save = 0.0
    log.info("writing %s every %.0f s (Ctrl+C to stop); keys are not available in this mode",
             path, PNG_EVERY_S)  # fmt: skip
    while True:
        viewer.update()
        renderer.draw(viewer.state)
        if time.monotonic() - last_save >= PNG_EVERY_S:
            tmp = path.with_suffix(".tmp.png")
            fig.savefig(tmp, dpi=100)
            tmp.replace(path)
            last_save = time.monotonic()
        time.sleep(FRAME_MS / 1000)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="platform URL")
    parser.add_argument("--png", type=Path, help="no abrir ventana: guardar un PNG cada segundo")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    viewer = Viewer(args.platform)
    viewer.start()
    try:
        if args.png is None and window_available():
            run_window(viewer)
        else:
            if args.png is None:
                log.warning("no window available: falling back to viewer.png")
            run_png(viewer, args.png or Path("viewer.png"))
    except KeyboardInterrupt:
        pass
    finally:
        viewer.link.close()


if __name__ == "__main__":
    main()
