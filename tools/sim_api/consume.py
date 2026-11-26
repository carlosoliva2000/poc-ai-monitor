"""Consumidor de referencia de la API del simulador (línea de órdenes).

Se suscribe al flujo SSE de uno o varios assets y escribe JSON Lines por stdout:
`{"asset_id", "event", "id", "data"}`. Reconecta con `Last-Event-ID` y descarta lo ya visto. Con
`--as-bus` escribe en su lugar los eventos del bus ya reconstruidos y en orden (lo que hará el
mediador). Solo la biblioteca estándar (y `poc_contracts` con `--as-bus`).

    python tools/sim_api/consume.py --all
    python tools/sim_api/consume.py --assets d1,radar-1 --types PositionUpdated --since -1
    uv run --project contracts/python python tools/sim_api/consume.py --all --as-bus
"""

import argparse
import http.client
import json
import queue
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:8100"
MAX_BACKOFF_S = 5.0


class NotLoadedError(Exception):
    """404 «no scenario is loaded»: se arreglará solo cuando se cargue un ejercicio."""


def _get_json(url: str, path: str) -> Any:
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    if response.status == 404 and b"no scenario is loaded" in body:
        raise NotLoadedError(path)
    if response.status != 200:
        raise RuntimeError(f"{path}: HTTP {response.status} {body.decode()[:200]}")
    return json.loads(body)


def _backoff(attempt: int, base: float = 0.5) -> float:
    return min(base * 2 ** min(attempt, 4), MAX_BACKOFF_S)


def _wait(stop: threading.Event | None, seconds: float) -> None:
    (stop or threading.Event()).wait(seconds)


def fetch_asset(
    url: str, asset_id: str, *, stop: threading.Event | None = None, base: float = 0.5
) -> dict[str, Any]:
    """La ficha de un asset. Antes de que se cargue un ejercicio la API contesta 404 («no scenario
    is loaded»): se reintenta con espera creciente hasta que haya escenario. Un asset que no
    existe también es 404, pero ese no se reintenta."""
    attempt = 0
    while True:
        try:
            return _get_json(url, f"/api/v1/assets/{asset_id}")
        except NotLoadedError:
            reason = "no scenario is loaded"
        except (OSError, ValueError) as exc:  # plataforma aún no arrancada o conexión cortada
            reason = str(exc)
        print(f"{asset_id}: {reason}; retrying", file=sys.stderr)
        if stop is not None and stop.is_set():
            raise KeyboardInterrupt
        _wait(stop, _backoff(attempt, base))
        attempt += 1


def asset_ids(url: str, *, stop: threading.Event | None = None, base: float = 0.5) -> list[str]:
    """Los assets del inventario; espera a que haya un escenario cargado."""
    attempt = 0
    while True:
        try:
            assets = _get_json(url, "/api/v1/assets")["assets"]
            if assets:
                return [a["id"] for a in assets]
            reason = "no scenario is loaded"
        except (OSError, ValueError) as exc:
            reason = str(exc)
        print(f"inventory: {reason}; retrying", file=sys.stderr)
        _wait(stop, _backoff(attempt, base))
        attempt += 1


def _read_events(response: http.client.HTTPResponse) -> Iterator[tuple[str, int | None, Any]]:
    event, event_id, data = "message", None, ""
    while True:
        raw = response.readline()
        if not raw:
            return  # el servidor cerró la conexión
        line = raw.decode().rstrip("\n")
        if not line:
            if data:
                yield event, event_id, json.loads(data)
            event, event_id, data = "message", None, ""
        elif not line.startswith(":"):
            field, _, value = line.partition(": ")
            if field == "event":
                event = value
            elif field == "id":
                event_id = int(value)
            elif field == "data":
                data += value


def stream_asset(
    url: str,
    asset_id: str,
    *,
    types: str | None = None,
    since: int | None = None,
    stop: threading.Event | None = None,
) -> Iterator[tuple[str, int | None, Any]]:
    """Los eventos SSE de un asset, sin fin: si se corta, reconecta con `Last-Event-ID` y no repite
    ningún mensaje."""
    stop = stop or threading.Event()
    parts = urlsplit(url)
    last_id = since
    attempt = 0
    while not stop.is_set():
        path = f"/api/v1/assets/{asset_id}/stream" + (f"?types={types}" if types else "")
        headers = {} if last_id is None else {"Last-Event-ID": str(last_id)}
        try:
            conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            if response.status != 200:
                raise OSError(f"HTTP {response.status}")
            for event, event_id, data in _read_events(response):
                attempt = 0
                if event_id is not None:
                    if last_id is not None and event_id <= last_id:
                        continue
                    last_id = event_id
                yield event, event_id, data
                if stop.is_set():
                    break
        except (OSError, ValueError) as exc:
            print(f"{asset_id}: {exc}; reconnecting", file=sys.stderr)
        finally:
            conn.close()
        if stop.is_set():
            return
        attempt += 1
        stop.wait(min(0.5 * 2 ** min(attempt - 1, 4), MAX_BACKOFF_S))


def _pump(url: str, asset_id: str, out: queue.Queue, stop: threading.Event, **kw: Any) -> None:
    try:
        card = fetch_asset(url, asset_id, stop=stop)  # espera a que haya escenario
    except (KeyboardInterrupt, RuntimeError) as exc:
        print(f"{asset_id}: {exc}", file=sys.stderr)
        return
    out.put((asset_id, "asset", None, card))
    for event, event_id, data in stream_asset(url, asset_id, stop=stop, **kw):
        out.put((asset_id, event, event_id, data))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--assets", help="ids separados por comas")
    group.add_argument("--all", action="store_true", help="todos los del inventario")
    parser.add_argument("--types", help="tipos de mensaje separados por comas")
    parser.add_argument("--since", type=int, help="repetir desde el `seq` siguiente (-1: todo)")
    parser.add_argument("--heartbeats", action="store_true", help="escribir también los heartbeat")
    parser.add_argument("--as-bus", action="store_true", help="eventos del bus reconstruidos")
    parser.add_argument("--max-seconds", type=float, help="parar a los N segundos")
    args = parser.parse_args()
    assets = args.assets.split(",") if args.assets else asset_ids(args.url)

    merger = None
    if args.as_bus:
        from adapter import Merger  # noqa: PLC0415

        merger = Merger(tuple(assets))
    out: queue.Queue = queue.Queue()
    stop = threading.Event()
    for asset_id in assets:
        threading.Thread(
            target=_pump, args=(args.url, asset_id, out, stop),
            kwargs={"types": args.types, "since": args.since}, daemon=True,
        ).start()  # fmt: skip
    deadline = time.monotonic() + args.max_seconds if args.max_seconds else None
    try:
        while deadline is None or time.monotonic() < deadline:
            try:
                asset_id, event, event_id, data = out.get(timeout=0.5)
            except queue.Empty:
                continue
            if event == "asset":
                if merger is None:
                    print(
                        json.dumps({"asset_id": asset_id, "event": "asset", "data": data}),
                        flush=True,
                    )
            elif merger is not None:
                for item in merger.feed(asset_id, event, data):
                    payload = (
                        item.model_dump(mode="json") if hasattr(item, "model_dump") else vars(item)
                    )
                    print(json.dumps({"event": "bus", "data": payload}), flush=True)
            elif event != "heartbeat" or args.heartbeats:
                line = {"asset_id": asset_id, "event": event, "id": event_id, "data": data}
                print(json.dumps(line), flush=True)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
