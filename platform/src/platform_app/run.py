"""Ejecuta escenarios de principio a fin y muestra los incidentes del monitor de situación.

Levanta la plataforma y el monitor de situación (`ai_module.situation`) como procesos aparte (o usa
una plataforma ya en marcha con `--platform`), se conecta por el WebSocket como cliente `web`,
carga el escenario, pone la velocidad y da al play. Imprime cada revisión de incidente
(`IncidentUpdated`), los textos del asistente (`IncidentEnriched`), las respuestas del chat y el
informe, hasta `SimulationFinished` (y `ReportGenerated`, si el asistente lo publica).

    uv run --project platform python -m platform_app.run --scenario demo --speed 16
    uv run --project platform python -m platform_app.run --scenario demo --tables handwritten
    uv run --project platform python -m platform_app.run --scenario nominal --interactive \\
        --fault radar:mute:150:200 --fault gps:loss:240:285
    uv run --project platform python -m platform_app.run --scenario demo --speed 16 \\
        --ask monitor:398:"Why do you think the drone is being hijacked?"

`--tables learned|handwritten` elige las tablas de las facetas (por defecto, las aprendidas
congeladas). Con el monitor arranca también el asistente LLM (textos, chats, informe y, para el
instructor, órdenes y debriefing) contra el vLLM local (`--vllm-url`); `--no-llm` lo deja fuera.
Si vLLM no responde lo dice y sigue solo con el monitor (arráncalo con `tools/vllm/serve.sh start`).
`--ask CONVERSACIÓN:CUÁNDO:TEXTO` manda una pregunta al chat (`monitor` o `report`) cuando el
`sim_time` llega a CUÁNDO (segundos) o, con `end`, cuando se ha publicado el informe; imprime la
respuesta según llega.
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

from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from poc_contracts.enums import ConversationId, EventType
from poc_contracts.topics import source_for, topic_for

from .generator.scenario_io import list_scenarios
from .paths import REPO_ROOT
from .viewer_state import clock

log = logging.getLogger("run")

DEFAULT_PORT = 8100
AI_READY_MARKER = "connected"  # línea de log del monitor cuando ya está suscrito
AI_READY_TIMEOUT_S = 20.0
PLATFORM_READY_TIMEOUT_S = 30.0
RECV_TIMEOUT_S = 0.5
REPORT_TIMEOUT_S = 90.0  # el asistente espera unos 3 s tras el final y escribe el informe
DEFAULT_VLLM_URL = "http://127.0.0.1:8000/v1"
SETTLE_S = 2.0  # tras el informe, para que lleguen los últimos eventos al timeline


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
    command = [sys.executable, "-m", "platform_app.app", "--port", str(port)]
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


def start_assistant(platform_url: str) -> subprocess.Popen:
    """Arranca el asistente LLM del alumno (proceso aparte) y espera a que esté conectado."""
    command = ["uv", "run", "--project", str(REPO_ROOT / "ai-module-py"), "python", "-m",
               "ai_module.assistant", "--platform", platform_url,
               "--runs-dir", str(REPO_ROOT / "runs")]  # fmt: skip
    return _start(command, "the assistant")


def start_instructor_assistant(platform_url: str) -> subprocess.Popen:
    """Arranca el asistente del instructor (traductor y chat con la verdad), proceso aparte."""
    command = ["uv", "run", "--project", str(REPO_ROOT / "ai-module-py"), "python", "-m",
               "ai_module.instructor", "--platform", platform_url,
               "--runs-dir", str(REPO_ROOT / "runs")]  # fmt: skip
    return _start(command, "the instructor assistant")


def start_ai_module(platform_url: str, *, tables: str) -> subprocess.Popen:
    """Arranca el monitor de situación (proceso aparte) y espera a que esté conectado."""
    command = ["uv", "run", "--project", str(REPO_ROOT / "ai-module-py"), "python", "-m",
               "ai_module.situation", "--platform", platform_url, "--tables", tables]  # fmt: skip
    return _start(command, "the situation monitor")


def _start(command: list[str], name: str) -> subprocess.Popen:
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
        if proc.poll() is not None:  # p. ej. las tablas congeladas han cambiado
            time.sleep(0.3)  # deja que el hilo recoja las últimas líneas
            raise SystemExit(f"{name} stopped at startup:\n" + "\n".join(tail))
        if time.monotonic() > deadline:
            log.warning("%s did not report being connected in %.0f s", name, AI_READY_TIMEOUT_S)
            break
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
    incidents: list[dict]
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
        "source": source_for(EventType.OPERATOR_MESSAGE, conversation),
        "asset": None,
        "sim_time": sim_time,
        "event_time": event_time,
        "causation_id": None,
        "ephemeral": False,
        "payload": {"conversation_id": conversation.value, "text": ask.text},
    }


def _incident_line(event: dict) -> str:
    p = event["payload"]
    subject = f" ({p['subject']})" if p.get("subject") else ""
    return (
        f"{clock(p['as_of_sim_time'])}  {p['change']:<8} {p['incident_id']} "
        f"{p['name']}{subject} · {p['state']} · {p['severity']} · {p['confidence']}"
    )


def _enriched_line(event: dict) -> str:
    p = event["payload"]
    return f"{clock(event['sim_time'])}  TEXTO    {p['incident_id']} r{p['revision']}: {p['text']}"


def run_scenario(
    ws: ClientConnection,
    name: str,
    speed: float,
    interactive: bool,
    faults: list[ManualFault],
    timeout_s: float,
    *,
    reports: bool = False,
    asks: list[Ask] | None = None,
    quiet: bool = False,
) -> RunResult:
    """Carga `name`, lo ejecuta hasta `SimulationFinished` (y, con asistente, hasta el informe) y
    devuelve sus incidentes."""
    asks = [Ask(a.conversation, a.when, a.text) for a in (asks or [])]
    send(ws, "load", name)
    if not _wait_for(ws, lambda m: m.get("op") == "state" and m["scenario"] == name, 60):
        raise SystemExit(f"la plataforma no ha cargado {name}")
    send(ws, "speed", speed)
    send(ws, "interactive", interactive)
    send(ws, "play")

    result = RunResult([])
    incidents = result.incidents
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
        done = finished and (not reports or reported) and now >= settle_until
        if done and all(a.sent for a in asks) and not streaming and not awaiting:
            break
        if finished and reports and now > report_deadline:
            break  # el asistente no publica informe de este escenario
        if now > deadline:
            raise SystemExit(f"{name}: la simulación no ha terminado en el tiempo previsto")
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
        if kind == "IncidentUpdated":
            incidents.append(event)
            if not quiet:
                print(_incident_line(event), flush=True)
        elif kind == "IncidentEnriched":
            result.responses.append(event)
            if not quiet:
                print(_enriched_line(event), flush=True)
        elif kind == "AgentReplyChunk":
            if not streaming:
                print(f"🤖 {event['payload']['conversation_id']}: ", end="", flush=True)
            streaming = True
            print(event["payload"]["delta"], end="", flush=True)
        elif kind == "AgentReply":
            tools = ", ".join(event["payload"]["tool_calls"]) or "sin tools"
            if event["payload"].get("proposal"):
                tools += f"; propuesta: {event['payload']['proposal']}"
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
            settle_until = time.monotonic()
            if not reports:
                ask_due(event["sim_time"], True)
        elif kind == "ReportGenerated":
            reported = True
            settle_until = time.monotonic() + SETTLE_S
            if not quiet:
                report = event["payload"]
                print(
                    f"{clock(event['sim_time'])}  INFORME  {len(report['markdown'])} caracteres, "
                    f"{report['alerts_count']} incidentes",
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
    parser.add_argument(
        "--ask", action="append", type=Ask.parse, default=[],
        metavar="CONVERSACIÓN:CUÁNDO:TEXTO", help="pregunta al chat (monitor|report|instructor)",
    )  # fmt: skip
    parser.add_argument(
        "--tables", choices=["learned", "handwritten"], default="learned",
        help="tablas de las facetas: aprendidas congeladas (por defecto) o las del vídeo",
    )  # fmt: skip
    parser.add_argument(
        "--no-llm", action="store_true",
        help="no arrancar el asistente LLM (sin textos, chats, informe ni debriefing)",
    )  # fmt: skip
    parser.add_argument("--vllm-url", default=DEFAULT_VLLM_URL, help="el vLLM local")
    parser.add_argument(
        "--platform", help="URL de una plataforma ya en marcha (si no, arranca una)"
    )
    parser.add_argument("--no-ai", action="store_true", help="no arrancar el monitor")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--timeout", type=float, default=900.0, help="segundos de reloj por escenario"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    names = list_scenarios() if args.all else args.scenario
    if not names:
        parser.error("indica --scenario NOMBRE (repetible) o --all")
    monitor = not args.no_ai
    llm = monitor and not args.no_llm
    if llm and http_get(f"{args.vllm_url.rstrip('/')}/models") is None:
        print(
            f"AVISO: vLLM no responde en {args.vllm_url}. Sigo solo con el monitor: sin textos, "
            "chats, informe ni debriefing. Arráncalo con `tools/vllm/serve.sh start` y repite, "
            "o usa --no-llm para no ver este aviso.",
            file=sys.stderr, flush=True,
        )  # fmt: skip
        llm = False

    platform_proc = ai_proc = assistant_proc = instructor_proc = None
    url = args.platform or f"http://127.0.0.1:{args.port}"
    try:
        if args.platform is None:
            platform_proc = start_platform(args.port)
        if monitor:
            ai_proc = start_ai_module(url, tables=args.tables)
        if llm:
            # si un proceso del asistente no arranca (p. ej. vLLM sirve otro modelo), se dice y el
            # monitor sigue: el asistente nunca tumba al monitor
            try:
                assistant_proc = start_assistant(url)
                instructor_proc = start_instructor_assistant(url)
            except SystemExit as exc:
                print(f"AVISO: el asistente no ha arrancado y sigo sin él:\n{exc}", file=sys.stderr)
                llm = False
                stop(instructor_proc)
                stop(assistant_proc)
                instructor_proc = assistant_proc = None
        ws_url = url.replace("http", "ws", 1).rstrip("/") + "/ws"
        with connect(ws_url, open_timeout=5) as ws:
            ws.send(json.dumps({"op": "hello", "client": "web"}))
            ws.send(json.dumps({"op": "subscribe", "patterns": ["citadel.pub.evt.>"]}))
            for name in names:
                print(f"\n== {name} (a {args.speed:g}×) ==", flush=True)
                result = run_scenario(
                    ws, name, args.speed, args.interactive or bool(args.fault), args.fault,
                    args.timeout, reports=llm, asks=args.ask,
                )  # fmt: skip
                opened = sum(e["payload"]["change"] == "opened" for e in result.incidents)
                print(f"-- {name}: {opened} incidentes abiertos ({result.wall_s:.0f} s de reloj)")
    except (OSError, WebSocketException) as exc:
        print(f"error de conexión: {exc}", file=sys.stderr)
        return 2
    finally:
        stop(instructor_proc)
        stop(assistant_proc)
        stop(ai_proc)
        stop(platform_proc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
