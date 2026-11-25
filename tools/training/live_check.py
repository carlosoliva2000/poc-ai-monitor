"""E7b, paso 2: las características en directo son idénticas a las de `events.jsonl`.

    uv run --project ai-module-py python tools/training/live_check.py [--scenario demo]

Arranca la plataforma (puerto 8100, salida en una carpeta temporal), se conecta por el WebSocket
como la web, ejecuta el escenario a 16× y pasa **uno a uno** los eventos del mundo que llegan por
el bus por el `FeatureExtractor` del monitor. Al terminar compara sus filas, valor a valor, con
las que sale de `runs/<escenario>/events.jsonl` (lo que usa el entrenamiento). Sale con 1 si
difieren. La plataforma queda parada al terminar.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

from ai_module.situation.features import FeatureExtractor, FeatureRow
from ai_module.situation.replay import is_world, read_events

REPO = Path(__file__).resolve().parents[2]
PORT = 8100


def live_rows(scenario: str, speed: float) -> list[FeatureRow]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    scratch = tempfile.mkdtemp(prefix="e7b-live-")
    env["POC_RUNS_DIR"] = scratch
    cmd = ["uv", "run", "--project", "platform", "python", "-m", "platform_app.app"]
    server = subprocess.Popen(
        [*cmd, "--port", str(PORT)], cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/scenarios", timeout=1)
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("the platform did not start")
        fx = FeatureExtractor()
        rows: list[FeatureRow] = []
        with connect(f"ws://127.0.0.1:{PORT}/ws", open_timeout=5) as ws:
            ws.send(json.dumps({"op": "hello", "client": "web"}))
            ws.send(json.dumps({"op": "subscribe", "patterns": ["citadel.pub.evt.>"]}))
            for action, value in (("load", scenario), ("speed", speed), ("play", None)):
                ws.send(json.dumps({"op": "control", "action": action, "value": value}))
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                try:
                    msg = json.loads(ws.recv(timeout=1.0))
                except TimeoutError:
                    continue
                if msg.get("op") != "event":
                    continue
                event = msg["event"]
                if event["type"] == "SimulationFinished":
                    rows += fx.flush()
                    return rows
                if is_world(event):
                    rows += fx.push(event)
        raise RuntimeError("the simulation did not finish")
    finally:
        server.terminate()
        server.wait(timeout=20)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="demo")
    parser.add_argument("--speed", type=float, default=16.0)
    args = parser.parse_args()
    live = live_rows(args.scenario, args.speed)
    fx = FeatureExtractor()
    offline: list[FeatureRow] = []
    for event in read_events(REPO / "runs" / args.scenario / "events.jsonl"):
        if is_world(event):
            offline += fx.push(event)
    offline += fx.flush()
    same = [(r.t, r.values) for r in live] == [(r.t, r.values) for r in offline]
    print(f"{args.scenario}: {len(live)} filas en directo, {len(offline)} fuera de línea, "
          f"{'IDÉNTICAS' if same else 'DISTINTAS'}")  # fmt: skip
    if not same:
        for a, b in zip(live, offline, strict=False):
            if (a.t, a.values) != (b.t, b.values):
                diff = {
                    k: (a.values[k], b.values[k]) for k in a.values if a.values[k] != b.values[k]
                }
                print(f"primera diferencia en t={a.t}/{b.t}: {diff}")
                break
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
