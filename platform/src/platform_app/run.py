"""Ejecuta escenarios de principio a fin y muestra lo que detecta y responde el módulo de IA.

Levanta la plataforma y el módulo de IA como procesos aparte (o usa una plataforma ya en marcha
con `--platform`), se conecta por el WebSocket como cliente `web`, carga el escenario, pone la
velocidad y da al play. Imprime las detecciones (`DetectionRaised/Updated/Cleared`), las
respuestas del monitor y el informe, hasta `SimulationFinished` (y `ReportGenerated`).

    uv run --project platform python -m platform_app.run --scenario demo --speed 16 --detector-only
    uv run --project platform python -m platform_app.run --scenario demo --speed 16 \\
        --wait-agent --evaluate
    uv run --project platform python -m platform_app.run --all --check --detector-only
    uv run --project platform python -m platform_app.run --scenario nominal --interactive \\
        --fault radar:mute:150:200 --fault gps:loss:240:285
    uv run --project platform python -m platform_app.run --scenario wind --speed 16 \\
        --wait-agent --ask monitor:120:"¿Por qué crees que es viento?" --ask report:end:"¿Qué pasó?"

`--wait-agent` activa «esperar al agente» (el reproductor se pausa en cada detección hasta que
el monitor responde). `--detector-only` arranca el módulo de IA solo con el detector (sin LLM).
`--ask CONVERSACIÓN:CUÁNDO:TEXTO` manda una pregunta al chat (`monitor` o `report`) cuando el
`sim_time` llega a CUÁNDO (segundos) o, con `end`, cuando se ha publicado el informe; imprime la
respuesta según llega. `--evaluate` ejecuta la evaluación de la ejecución (`eval.md`).

`--check` compara las detecciones con las etiquetas de `runs/<escenario>/labels.json` (solo para
evaluar: lo lee este comando, nunca el módulo de IA).
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import yaml
from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from poc_contracts.enums import ConversationId, EventType
from poc_contracts.topics import topic_for

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
REPORT_TIMEOUT_S = 600.0
SETTLE_S = 2.0  # tras el informe, para que lleguen los últimos eventos al timeline
RESPONSE_TYPES = ("AnomalyDetected", "AlertClosed", "DetectionAcknowledged")


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


def start_platform(port: int, wait_timeout_s: float | None = None) -> subprocess.Popen:
    if http_get(f"http://127.0.0.1:{port}/api/state") is not None:
        raise SystemExit(
            f"el puerto {port} ya está en uso (¿hay una plataforma en marcha? usa --platform)"
        )
    command = [sys.executable, "-m", "platform_app.app", "--port", str(port)]
    if wait_timeout_s is not None:
        command += ["--wait-timeout", str(wait_timeout_s)]
    proc = subprocess.Popen(
        command, cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    deadline = time.monotonic() + PLATFORM_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit("la plataforma ha terminado al arrancar")
        if http_get(f"http://127.0.0.1:{port}/api/state") is not None:
            return proc
        time.sleep(0.2)
    proc.terminate()
    raise SystemExit("la plataforma no responde")


def start_ai_module(
    platform_url: str,
    *,
    detector_only: bool = False,
    llm_url: str | None = None,
    profile: str | None = None,
    tool_call_events: bool = True,
) -> subprocess.Popen:
    """Arranca el módulo de IA (proceso aparte) y espera a que esté conectado y suscrito."""
    command = ["uv", "run", "--project", str(REPO_ROOT / "ai-module-py"), "python", "-m",
               "ai_module", "--platform", platform_url, "--runs", str(RUNS_DIR)]  # fmt: skip
    if detector_only:
        command.append("--detector-only")
    if llm_url:
        command += ["--llm-url", llm_url]
    if profile:
        command += ["--profile", profile]
    if not tool_call_events:
        command.append("--no-tool-call-events")
    proc = subprocess.Popen(
        command, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        bufsize=1,
    )  # fmt: skip
    ready = threading.Event()
    tail: deque[str] = deque(maxlen=5)

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:  # sigue leyendo para que el proceso no se bloquee
            tail.append(line.rstrip())
            if AI_READY_MARKER in line.lower():
                ready.set()
            log.debug("ai-module: %s", line.rstrip())
            if os.environ.get("RUN_AI_LOG") and not line.startswith(("T+", "INFO")):
                print(f"   [módulo] {line.rstrip()}", flush=True)

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.monotonic() + AI_READY_TIMEOUT_S
    while not ready.wait(0.2):
        if proc.poll() is not None:  # p. ej. vLLM sirve otro modelo: el módulo para con un error
            time.sleep(0.3)  # deja que el hilo recoja las últimas líneas
            raise SystemExit("the AI module stopped at startup:\n" + "\n".join(tail))
        if time.monotonic() > deadline:
            log.warning(
                "the AI module did not report being connected in %.0f s", AI_READY_TIMEOUT_S
            )
            break
    return proc


def profile_wait_timeout(profile: str) -> float | None:
    """Espera de la plataforma que fija el perfil (`platform.wait_agent_timeout_s`), si la fija."""
    path = REPO_ROOT / "model-profiles" / f"{profile}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise SystemExit(f"cannot read profile {profile}: {exc}") from exc
    value = data.get("platform", {}).get("wait_agent_timeout_s")
    return None if value is None else float(value)


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


@dataclass
class Ask:
    """`--ask conversación:cuándo:texto`."""

    conversation: str
    when: float | None  # sim_time en segundos; `None` = tras el informe
    text: str
    sent: bool = False

    @classmethod
    def parse(cls, text: str) -> "Ask":
        try:
            conversation, when, question = text.split(":", 2)
            ConversationId(conversation)
            return cls(conversation, None if when == "end" else float(when), question)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f'{text!r}: se esperaba conversación:cuándo:texto (p. ej. monitor:200:"¿Por qué?")'
            ) from exc


@dataclass
class RunResult:
    detections: list[Detection]
    run_id: str | None = None
    wall_s: float = 0.0
    responses: list[dict] = field(default_factory=list)


def _operator_message(ask: Ask, number: int, sim_time: float, t0: datetime) -> dict:
    conversation = ConversationId(ask.conversation)
    event_time = (t0 + timedelta(seconds=sim_time)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "event_id": f"ops-{number:04d}",
        "topic": topic_for(EventType.OPERATOR_MESSAGE, conversation),
        "type": EventType.OPERATOR_MESSAGE.value,
        "source": "web-operator",
        "asset": None,
        "sim_time": sim_time,
        "event_time": event_time,
        "causation_id": None,
        "ephemeral": False,
        "payload": {"conversation_id": conversation.value, "text": ask.text},
    }


def _response_line(event: dict) -> str:
    p = event["payload"]
    at = clock(event["sim_time"])
    cause = event.get("causation_id")
    if event["type"] == "AnomalyDetected":
        fb = " [fallback]" if p["fallback"] else ""
        sup = f" (sustituye a {p['supersedes']})" if p["supersedes"] else ""
        return (
            f"{at}  ALERTA   {p['alert_id']} {p['cause']} {p['severity']} conf {p['confidence']:g}"
            f"{sup}{fb} ← {cause}: {p['summary']}"
        )
    if event["type"] == "AlertClosed":
        return f"{at}  CIERRE   {p['alert_id']} ← {cause}: {p['reason']}"
    fb = " [fallback]" if p["fallback"] else ""
    return (
        f"{at}  ACK      {p['detection_id']} → {p['alert_id'] or 'sin alerta'}{fb} ← {cause}: "
        f"{p['reason']}"
    )


def run_scenario(
    ws: ClientConnection,
    name: str,
    speed: float,
    interactive: bool,
    faults: list[ManualFault],
    timeout_s: float,
    *,
    wait_agent: bool = False,
    agents: bool = False,
    asks: list[Ask] | None = None,
    quiet: bool = False,
) -> RunResult:
    """Carga `name`, lo ejecuta hasta `SimulationFinished` (y, con agentes, hasta el informe) y
    devuelve sus detecciones."""
    asks = [Ask(a.conversation, a.when, a.text) for a in (asks or [])]
    send(ws, "load", name)
    if not _wait_for(ws, lambda m: m.get("op") == "state" and m["scenario"] == name, 60):
        raise SystemExit(f"la plataforma no ha cargado {name}")
    send(ws, "speed", speed)
    send(ws, "interactive", interactive)
    send(ws, "wait_agent", wait_agent)
    send(ws, "play")

    result = RunResult([])
    detections = result.detections
    pending = sorted(
        [(f.start_s, f, True) for f in faults] + [(f.end_s, f, False) for f in faults],
        key=lambda x: x[0],
    )
    started = time.monotonic()
    deadline = started + timeout_s
    finished = reported = False
    report_deadline = 0.0
    settle_until = 0.0
    t0 = datetime(1970, 1, 1, tzinfo=UTC)
    ops_number = 0
    streaming = False
    awaiting: set[str] = set()  # preguntas enviadas que aún no tienen `AgentReply`

    def ask_due(sim_time: float, after_report: bool) -> None:
        nonlocal ops_number
        for ask in asks:
            due = after_report if ask.when is None else sim_time >= ask.when
            if ask.sent or not due or (ask.when is None and not after_report):
                continue
            ask.sent = True
            ops_number += 1
            awaiting.add(f"ops-{ops_number:04d}")
            print(f"\n[{clock(sim_time)}] 👤 {ask.conversation}: {ask.text}", flush=True)
            ws.send(json.dumps({"op": "publish", "event": _operator_message(
                ask, ops_number, sim_time, t0)}))  # fmt: skip

    while True:
        now = time.monotonic()
        done = finished and (not agents or reported) and now >= settle_until
        if done and all(a.sent for a in asks) and not streaming and not awaiting:
            break
        if now > (report_deadline if finished and agents else deadline):
            where = "el informe" if finished else "la simulación"
            raise SystemExit(f"{name}: no ha terminado {where} en el tiempo previsto")
        try:
            msg = json.loads(ws.recv(timeout=RECV_TIMEOUT_S))
        except TimeoutError:
            continue
        if msg.get("op") == "error":
            log.error("platform error: %s", msg["message"])
            continue
        if msg.get("op") == "state":
            result.run_id = msg.get("run_id") or result.run_id
            continue
        if msg.get("op") != "event":
            continue
        event = msg["event"]
        moment = datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
        t0 = moment - timedelta(seconds=event["sim_time"])
        kind = event["type"]
        while pending and event["sim_time"] >= pending[0][0]:
            _, fault, active = pending.pop(0)
            send(ws, "fault", {"source": fault.source, "mode": fault.mode, "active": active})
        if kind in DETECTION_TYPES:
            detections.append(parse_detection(event))
            if not quiet:
                print(detections[-1].line(), flush=True)
        elif kind in RESPONSE_TYPES and event["source"] == "ai-monitor":
            result.responses.append(event)
            if not quiet:
                print(_response_line(event), flush=True)
        elif kind == "AgentReplyChunk":
            if not streaming:
                print(f"🤖 {event['payload']['conversation_id']}: ", end="", flush=True)
            streaming = True
            print(event["payload"]["delta"], end="", flush=True)
        elif kind == "AgentReply":
            tools = ", ".join(event["payload"]["tool_calls"]) or "sin tools"
            if not streaming:
                print(f"🤖 {event['payload']['conversation_id']}: {event['payload']['text']}",
                      end="")  # fmt: skip
            print(f"\n   ({tools})", flush=True)
            streaming = False
            awaiting.discard(event["payload"]["reply_to"])
        elif kind == "SimulationStarted":
            result.run_id = event["payload"]["run_id"]
        elif kind == "SimulationFinished":
            finished = True
            result.wall_s = time.monotonic() - started
            report_deadline = time.monotonic() + REPORT_TIMEOUT_S
            settle_until = time.monotonic() + (0.0 if agents else 0.0)
            if not agents:
                ask_due(event["sim_time"], True)
        elif kind == "ReportGenerated":
            reported = True
            settle_until = time.monotonic() + SETTLE_S
            if not quiet:
                report = event["payload"]
                print(
                    f"{clock(event['sim_time'])}  INFORME  {len(report['markdown'])} caracteres, "
                    f"{report['alerts_count']} alertas",
                    flush=True,
                )
            ask_due(event["sim_time"], True)
        if not finished:
            ask_due(event["sim_time"], False)
    return result


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


def evaluate(name: str, run_id: str) -> None:
    """Ejecuta la evaluación del módulo de IA sobre la carpeta de la ejecución."""
    folder = RUNS_DIR / name / run_id
    subprocess.run(
        ["uv", "run", "--project", str(REPO_ROOT / "ai-module-py"), "python", "-m",
         "ai_module.evaluate", str(folder)],
        cwd=REPO_ROOT, check=False,
    )  # fmt: skip


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
    parser.add_argument("--wait-agent", action="store_true", help="«esperar al agente»")
    parser.add_argument("--evaluate", action="store_true", help="generar eval.md de la ejecución")
    parser.add_argument(
        "--ask", action="append", type=Ask.parse, default=[],
        metavar="CONVERSACIÓN:CUÁNDO:TEXTO", help="pregunta al chat (monitor|report)",
    )  # fmt: skip
    parser.add_argument(
        "--detector-only", action="store_true", help="módulo de IA solo con el detector"
    )
    parser.add_argument("--llm-url", help="URL del servidor LLM (se pasa al módulo de IA)")
    parser.add_argument(
        "--profile", help="perfil de model-profiles/ (se pasa al módulo de IA y fija la espera)"
    )
    parser.add_argument(
        "--wait-timeout", type=float, help="espera al agente de la plataforma, en segundos"
    )
    parser.add_argument(
        "--platform", help="URL de una plataforma ya en marcha (si no, arranca una)"
    )
    parser.add_argument(
        "--no-tool-call-events",
        action="store_true",
        help="el módulo de IA no publica AgentToolCall (lo que la web muestra para depurar)",
    )
    parser.add_argument("--no-ai", action="store_true", help="no arrancar el módulo de IA")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--timeout", type=float, default=900.0, help="segundos de reloj por escenario"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    names = list_scenarios() if args.all else args.scenario
    if not names:
        parser.error("indica --scenario NOMBRE (repetible) o --all")
    agents = not (args.no_ai or args.detector_only)
    if args.wait_agent and args.no_ai:
        parser.error("--wait-agent necesita el módulo de IA")

    platform_proc = ai_proc = None
    url = args.platform or f"http://127.0.0.1:{args.port}"
    failed = False
    try:
        if args.platform is None:
            wait = args.wait_timeout
            if wait is None and args.profile:
                wait = profile_wait_timeout(args.profile)
            platform_proc = start_platform(args.port, wait)
        if not args.no_ai:
            ai_proc = start_ai_module(
                url,
                detector_only=args.detector_only,
                llm_url=args.llm_url,
                profile=args.profile,
                tool_call_events=not args.no_tool_call_events,
            )
        ws_url = url.replace("http", "ws", 1).rstrip("/") + "/ws"
        with connect(ws_url, open_timeout=5) as ws:
            ws.send(json.dumps({"op": "hello", "client": "web"}))
            ws.send(json.dumps({"op": "subscribe", "patterns": ["citadel.pub.evt.>"]}))
            for name in names:
                print(f"\n== {name} (a {args.speed:g}×) ==", flush=True)
                result = run_scenario(
                    ws, name, args.speed, args.interactive or bool(args.fault), args.fault,
                    args.timeout, wait_agent=args.wait_agent, agents=agents, asks=args.ask,
                )  # fmt: skip
                found = result.detections
                raised = sum(d.kind == "Raised" for d in found)
                print(f"-- {name}: {raised} detecciones abiertas ({result.wall_s:.0f} s de reloj)")
                if args.check:
                    for c in check_detections(load_labels(name), found):
                        print(f"   {'✅' if c.ok else '❌'} {c.what}")
                        failed |= not c.ok
                if args.evaluate and result.run_id:
                    evaluate(name, result.run_id)
    except (OSError, WebSocketException) as exc:
        print(f"error de conexión: {exc}", file=sys.stderr)
        return 2
    finally:
        stop(ai_proc)
        stop(platform_proc)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
