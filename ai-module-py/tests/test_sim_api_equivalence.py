"""Equivalencia de la API del simulador con el bus (≈ 60 s, plataforma real).

Un adaptador que solo lee la API REST/SSE de los assets (lo que hará el mediador) reconstruye los
eventos del mundo y alimenta un monitor de situación; el monitor real conectado al `/ws` hace lo
mismo con el bus. Tienen que dar los mismos eventos y los mismos incidentes en `demo`.
"""

import asyncio
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from ai_module.ids import IdAllocator
from ai_module.situation.__main__ import SituationProcess
from ai_module.situation.facets import LEARNED
from ai_module.situation.monitor import SituationMonitor
from ai_module.situation.replay import is_world

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "sim_api"))
import consume  # noqa: E402
from adapter import ASSETS, Lifecycle, Merger  # noqa: E402

pytestmark = pytest.mark.e2e


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(url: str, path: str, method: str = "GET", body: Any = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


class Adapter(threading.Thread):
    """Lee los cuatro flujos de la API, los mezcla y alimenta un monitor aparte del bus."""

    def __init__(self, url: str) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.stop = threading.Event()
        self.done = threading.Event()
        self.merger = Merger(ASSETS)
        self.monitor = SituationMonitor(IdAllocator("m"), LEARNED)
        self.events: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.inbox: queue.Queue = queue.Queue()
        for asset in ASSETS:
            threading.Thread(target=self._pump, args=(asset,), daemon=True).start()

    def _pump(self, asset: str) -> None:
        for event, _id, data in consume.stream_asset(self.url, asset, stop=self.stop):
            self.inbox.put((asset, event, data))

    def _handle(self, items: list[Any]) -> None:
        for item in items:
            if isinstance(item, Lifecycle):
                if item.kind in ("RunStarted", "RunReset"):
                    self.monitor.reset()
                else:
                    self.updates += [u for _, u in self.monitor.flush()]
                    self.done.set()
                continue
            raw = item.model_dump(mode="json")
            self.events.append(raw)
            if is_world(raw):
                self.updates += [u for _, u in self.monitor.push(raw)]

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                asset, event, data = self.inbox.get(timeout=0.2)
            except queue.Empty:
                continue
            self._handle(self.merger.feed(asset, event, data))


def test_the_api_gives_the_same_events_and_incidents_as_the_bus(tmp_path: Path) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "POC_RUNS_DIR": str(tmp_path)}
    platform = subprocess.Popen(
        ["uv", "run", "--project", str(REPO / "platform"), "python", "-m", "platform_app.app",
         "--port", str(port)],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    adapter: Adapter | None = None
    try:
        for _ in range(100):
            try:
                call(url, "/api/state")
                break
            except OSError:
                time.sleep(0.3)
        else:
            pytest.fail("the platform did not start")

        async def main() -> None:
            nonlocal adapter
            real = asyncio.create_task(SituationProcess(url).run())  # el monitor real, por `/ws`
            adapter = Adapter(url)  # el monitor alimentado solo con la API
            adapter.start()
            await asyncio.sleep(1.5)
            for path, method, body in (
                ("/api/v1/exercise/load", "POST", {"scenario": "demo"}),
                ("/api/v1/exercise/speed", "PUT", {"value": 16}),
                ("/api/v1/exercise/play", "POST", None),
            ):
                await asyncio.to_thread(call, url, path, method, body)
            deadline = time.monotonic() + 120
            while not adapter.done.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
            await asyncio.sleep(3.0)  # el monitor real publica su último cierre
            real.cancel()

        asyncio.run(main())
        assert adapter is not None and adapter.done.is_set(), "the run did not finish"
        timeline = call(url, "/api/timeline")["events"]
        bus_world = [
            {k: v for k, v in e.items() if k not in ("seq", "ingestion_time")}
            for e in timeline
            if e["topic"].split(".")[3] in ("air", "env")
        ]
        bus_incidents = [e["payload"] for e in timeline if e["type"] == "IncidentUpdated"]
        assert adapter.events == bus_world  # los mismos eventos del mundo, en el mismo orden
        assert bus_incidents, "the monitor opened no incident in demo"
        assert adapter.updates == bus_incidents  # y los mismos incidentes
    finally:
        if adapter is not None:
            adapter.stop.set()
        platform.terminate()
        platform.wait(timeout=10)
