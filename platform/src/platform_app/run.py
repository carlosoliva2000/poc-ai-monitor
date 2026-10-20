"""Ejecuta escenarios de principio a fin, sin LLM, y muestra lo que detecta el módulo de IA.

Levanta la plataforma y el módulo de IA como procesos aparte (o usa una plataforma ya en marcha
con `--platform`), se conecta por el WebSocket como cliente `web`, carga el escenario, pone la
velocidad y da al play. Imprime las detecciones (`DetectionRaised/Updated/Cleared`) con su
`sim_time` hasta `SimulationFinished`. No activa «esperar al agente» (no hay monitor en esta
fase: con él activado el reproductor espera 90 s de reloj por cada detección).

    uv run --project platform python -m platform_app.run --scenario demo --speed 16
    uv run --project platform python -m platform_app.run --all --check
    uv run --project platform python -m platform_app.run --scenario nominal --interactive \\
        --fault radar:mute:150:200 --fault gps:loss:240:285

`--check` compara las detecciones con las etiquetas de `runs/<escenario>/labels.json` (solo para
evaluar: lo lee este comando, nunca el módulo de IA).
"""

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from .generator.scenario_io import list_scenarios
from .paths import REPO_ROOT, RUNS_DIR
from .viewer_state import clock

log = logging.getLogger("run")

DEFAULT_PORT = 8100
DETECTION_TYPES = ("DetectionRaised", "DetectionUpdated", "DetectionCleared")
AI_READY_MARKER = "connected"  # línea de log del módulo de IA cuando ya está suscrito
AI_READY_TIMEOUT_S = 20.0
PLATFORM_READY_TIMEOUT_S = 30.0
RECV_TIMEOUT_S = 0.5


@dataclass(frozen=True)
class Detection:
    """Una línea de detección tal y como llegó por el bus."""

    kind: str  # Raised | Updated | Cleared
    t: float
    detection_id: str
    rule: str
    source: str | None
    severity: str | None
    value: float | None
    threshold: float | None
    unit: str | None
    message: str | None

    def line(self) -> str:
        src = self.source or "-"
        if self.kind == "Cleared":
            return (
                f"{clock(self.t)}  {self.kind.upper():8} {self.rule:19} {src:8} {self.detection_id}"
            )
        what = f"{self.value:g}/{self.threshold:g} {self.unit}"
        return (
            f"{clock(self.t)}  {self.kind.upper():8} {self.rule:19} {src:8} {what:14} "
            f"[{self.severity}] {self.message}"
        )


@dataclass(frozen=True)
class ManualFault:
    """`--fault fuente:modo:inicio:fin`: se activa y se termina con el reloj de la simulación."""

    source: str
    mode: str
    start_s: float
    end_s: float

    @classmethod
    def parse(cls, text: str) -> "ManualFault":
        try:
            source, mode, start, end = text.split(":")
            return cls(source, mode, float(start), float(end))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{text!r}: se esperaba fuente:modo:inicio:fin (p. ej. radar:mute:150:200)"
            ) from exc


def parse_detection(event: dict) -> Detection:
    p = event["payload"]
    kind = event["type"].removeprefix("Detection")
    if kind == "Cleared":
        return Detection(kind, event["sim_time"], p["detection_id"], p["rule"], None, None,
                         p["max_value"], None, None, None)  # fmt: skip
    return Detection(
        kind, event["sim_time"], p["detection_id"], p["rule"], p["source"], p["severity"],
        p["value"], p["threshold"], p["unit"], p["message"],
    )  # fmt: skip


# --- procesos -----------------------------------------------------------------------------------


def http_get(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def start_platform(port: int) -> subprocess.Popen:
    if http_get(f"http://127.0.0.1:{port}/api/state") is not None:
        raise SystemExit(
            f"el puerto {port} ya está en uso (¿hay una plataforma en marcha? usa --platform)"
        )
    proc = subprocess.Popen(
        [sys.executable, "-m", "platform_app.app", "--port", str(port)],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    deadline = time.monotonic() + PLATFORM_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit("la plataforma ha terminado al arrancar")
        if http_get(f"http://127.0.0.1:{port}/api/state") is not None:
            return proc
        time.sleep(0.2)
    proc.terminate()
    raise SystemExit("la plataforma no responde")


def start_ai_module(platform_url: str) -> subprocess.Popen:
    """Arranca el módulo de IA (proceso aparte) y espera a que esté conectado y suscrito."""
    proc = subprocess.Popen(
        ["uv", "run", "--project", str(REPO_ROOT / "ai-module-py"), "python", "-m", "ai_module",
         "--platform", platform_url, "--detector-only"],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )  # fmt: skip
    ready = threading.Event()

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:  # sigue leyendo para que el proceso no se bloquee
            if AI_READY_MARKER in line.lower():
                ready.set()
            log.debug("ai-module: %s", line.rstrip())

    threading.Thread(target=pump, daemon=True).start()
    if not ready.wait(AI_READY_TIMEOUT_S):
        log.warning("the AI module did not report being connected in %.0f s", AI_READY_TIMEOUT_S)
    return proc


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


# --- ejecución de un escenario ------------------------------------------------------------------


def send(ws: ClientConnection, action: str, value: object = None) -> None:
    ws.send(json.dumps({"op": "control", "action": action, "value": value}))


def run_scenario(
    ws: ClientConnection,
    name: str,
    speed: float,
    interactive: bool,
    faults: list[ManualFault],
    timeout_s: float,
    quiet: bool = False,
) -> list[Detection]:
    """Carga `name`, lo ejecuta hasta `SimulationFinished` y devuelve sus detecciones."""
    send(ws, "load", name)
    if not _wait_for(ws, lambda m: m.get("op") == "state" and m["scenario"] == name, 60):
        raise SystemExit(f"la plataforma no ha cargado {name}")
    send(ws, "speed", speed)
    send(ws, "interactive", interactive)
    send(ws, "play")

    detections: list[Detection] = []
    pending = sorted(
        [(f.start_s, f, True) for f in faults] + [(f.end_s, f, False) for f in faults],
        key=lambda x: x[0],
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            msg = json.loads(ws.recv(timeout=RECV_TIMEOUT_S))
        except TimeoutError:
            continue
        if msg.get("op") == "error":
            log.error("platform error: %s", msg["message"])
            continue
        if msg.get("op") != "event":
            continue
        event = msg["event"]
        while pending and event["sim_time"] >= pending[0][0]:
            _, fault, active = pending.pop(0)
            send(ws, "fault", {"source": fault.source, "mode": fault.mode, "active": active})
        if event["type"] in DETECTION_TYPES:
            detections.append(parse_detection(event))
            if not quiet:
                print(detections[-1].line(), flush=True)
        elif event["type"] == "SimulationFinished":
            return detections
    raise SystemExit(f"{name}: no ha terminado en {timeout_s:.0f} s")


def _wait_for(ws: ClientConnection, predicate, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            msg = json.loads(ws.recv(timeout=RECV_TIMEOUT_S))
        except TimeoutError:
            continue
        if predicate(msg):
            return True
    return False


# --- comprobación contra las etiquetas ------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    ok: bool
    what: str


def check_detections(labels: list[dict], detections: list[Detection]) -> list[Check]:
    """Comprueba las detecciones de un escenario contra sus etiquetas (solo para evaluar)."""
    raised = [d for d in detections if d.kind == "Raised"]
    out: list[Check] = []
    if not labels:
        out.append(Check(not detections, f"sin anomalías ni fallos: {len(detections)} detecciones"))
    inside: set[str] = set()
    for lb in labels:
        a, b = lb["eval_window"]
        window = [d for d in raised if a <= d.t <= b]
        inside |= {d.detection_id for d in window}
        for rule in lb["expected_rules"]:
            hits = [d for d in window if d.rule == rule and d.source in (None, lb["source"])]
            optional = rule == "ROUTE_DEVIATION" and lb["type"] in ("gps_spoofing", "gps_loss")
            if hits:
                out.append(
                    Check(
                        len(hits) == 1,
                        f"{lb['id']} {rule}: {len(hits)} vez/veces ({clock(hits[0].t)})",
                    )
                )
            elif not optional:
                out.append(Check(False, f"{lb['id']} {rule}: no ha saltado"))
        if lb["type"] == "gps_loss":
            first = next((d for d in window if d.rule == "GPS_DEGRADED"), None)
            ok = first is not None and first.t - lb["start_s"] <= 1.0
            out.append(Check(ok, f"{lb['id']} GPS_DEGRADED en el primer segundo"))
            disc = next((d for d in window if d.rule == "SOURCE_DISCREPANCY"), None)
            out.append(Check(bool(first and disc and disc.t > first.t),
                             f"{lb['id']} SOURCE_DISCREPANCY después de GPS_DEGRADED"))  # fmt: skip
        if lb["type"] == "source_silent":
            others = [d for d in window if d.rule == "SOURCE_SILENT" and d.source != lb["source"]
                      and lb["start_s"] <= d.t <= lb["end_s"] + 6]  # fmt: skip
            out.append(Check(not others, f"{lb['id']} solo salta SOURCE_SILENT de {lb['source']}"))
    stray = [d for d in raised if d.detection_id not in inside]
    if labels:
        out.append(
            Check(not stray, f"detecciones fuera de las ventanas de evaluación: {len(stray)}")
        )
    return out


def load_labels(name: str) -> list[dict]:
    path = RUNS_DIR / name / "labels.json"
    return json.loads(path.read_text(encoding="utf-8"))["labels"]


# --- programa -------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--scenario", action="append", default=[], help="escenario (repetible)")
    parser.add_argument("--all", action="store_true", help="los de scenarios/")
    parser.add_argument("--speed", type=float, default=16.0)
    parser.add_argument("--interactive", action="store_true", help="encender el modo interactivo")
    parser.add_argument(
        "--fault", action="append", type=ManualFault.parse, default=[],
        metavar="FUENTE:MODO:INICIO:FIN", help="fallo manual (activa --interactive)",
    )  # fmt: skip
    parser.add_argument("--check", action="store_true", help="comparar con labels.json")
    parser.add_argument(
        "--platform", help="URL de una plataforma ya en marcha (si no, arranca una)"
    )
    parser.add_argument("--no-ai", action="store_true", help="no arrancar el módulo de IA")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--timeout", type=float, default=300.0, help="segundos de reloj por escenario"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    names = list_scenarios() if args.all else args.scenario
    if not names:
        parser.error("indica --scenario NOMBRE (repetible) o --all")

    platform_proc = ai_proc = None
    url = args.platform or f"http://127.0.0.1:{args.port}"
    failed = False
    try:
        if args.platform is None:
            platform_proc = start_platform(args.port)
        if not args.no_ai:
            ai_proc = start_ai_module(url)
        ws_url = url.replace("http", "ws", 1).rstrip("/") + "/ws"
        with connect(ws_url, open_timeout=5) as ws:
            ws.send(json.dumps({"op": "hello", "client": "web"}))
            ws.send(json.dumps({"op": "subscribe", "patterns": ["citadel.pub.evt.>"]}))
            for name in names:
                print(f"\n== {name} (a {args.speed:g}×) ==", flush=True)
                found = run_scenario(ws, name, args.speed, args.interactive or bool(args.fault),
                                     args.fault, args.timeout)  # fmt: skip
                print(f"-- {name}: {sum(d.kind == 'Raised' for d in found)} detecciones abiertas")
                if args.check:
                    for c in check_detections(load_labels(name), found):
                        print(f"   {'✅' if c.ok else '❌'} {c.what}")
                        failed |= not c.ok
    except (OSError, WebSocketException) as exc:
        print(f"error de conexión: {exc}", file=sys.stderr)
        return 2
    finally:
        stop(ai_proc)
        stop(platform_proc)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
