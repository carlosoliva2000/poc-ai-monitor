"""El módulo completo (`run`) contra un bus falso que reproduce un `events.jsonl`."""

import asyncio
import json
from pathlib import Path

from synthetic import envelope
from websockets.asyncio.server import ServerConnection, serve

from ai_module.__main__ import run
from ai_module.detect_file import detect, read_events

SPOOFING = Path(__file__).resolve().parents[2] / "runs" / "spoofing" / "events.jsonl"


def test_run_publishes_the_same_detections_as_the_file(capsys) -> None:
    expected = detect(SPOOFING)
    published: list[dict] = []
    done = asyncio.Event()

    async def handler(ws: ServerConnection) -> None:
        await ws.recv()  # hello
        await ws.recv()  # subscribe
        for seq, event in enumerate(read_events(SPOOFING), start=1):
            await ws.send(json.dumps({"op": "event", "event": envelope(event, seq).model_dump()}))
        async for raw in ws:
            published.append(json.loads(raw))
            if len(published) == len(expected):
                done.set()

    async def scenario() -> None:
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            task = asyncio.create_task(run(f"http://127.0.0.1:{port}"))
            try:
                await asyncio.wait_for(done.wait(), 10)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert [m["op"] for m in published] == ["publish"] * len(expected)
    assert [m["event"]["event_id"] for m in published] == [d.event_id for d in expected]
    assert [m["event"]["type"] for m in published] == [d.type.value for d in expected]
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == len(expected) and "SOURCE_DISCREPANCY" in lines[0]
