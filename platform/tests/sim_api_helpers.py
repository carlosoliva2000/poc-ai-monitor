"""Apoyo de las pruebas de la API `/api/v1`: un servidor real en un hilo y un lector de SSE."""

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI

from platform_app.app import create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    """La plataforma en un hilo (uvicorn real) para probar el flujo SSE; sin reloj de pared: el
    reproductor avanza desde la prueba (`server.player.advance(...)`)."""

    def __init__(self, runs_dir: Path) -> None:
        self.app: FastAPI = create_app(runs_dir=runs_dir, run_clock=False)
        self.port = free_port()
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            timeout_graceful_shutdown=1,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def player(self):  # noqa: ANN201
        return self.app.state.player

    def __enter__(self) -> "LiveServer":
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("the server did not start")
            time.sleep(0.02)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def get(self, path: str) -> Any:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", path)
        body = conn.getresponse().read()
        conn.close()
        return json.loads(body)


@dataclass
class SseEvent:
    event: str
    id: int | None
    data: dict[str, Any]


class SseStream:
    """Cliente mínimo de `text/event-stream`: itera los eventos hasta que se cierra."""

    def __init__(self, port: int, path: str, headers: dict[str, str] | None = None) -> None:
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        self.conn.request("GET", path, headers=headers or {})
        self.response = self.conn.getresponse()
        self.status = self.response.status
        self.content_type = self.response.getheader("Content-Type")

    def __iter__(self) -> Iterator[SseEvent]:
        event, event_id, data = "message", None, ""
        while True:
            line = self.response.readline().decode().rstrip("\n")
            if not line:
                if data:
                    yield SseEvent(event, event_id, json.loads(data))
                event, event_id, data = "message", None, ""
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(": ")
            if field == "event":
                event = value
            elif field == "id":
                event_id = int(value)
            elif field == "data":
                data += value

    def messages(self, count: int) -> list[SseEvent]:
        """Los `count` primeros eventos `message` (ignora heartbeats)."""
        out: list[SseEvent] = []
        deadline = time.monotonic() + 8.0  # los heartbeats impiden que salte el timeout del socket
        for item in self:
            if item.event == "message":
                out.append(item)
                if len(out) == count:
                    return out
            if time.monotonic() > deadline:
                break
        return out

    def close(self) -> None:
        self.conn.close()
