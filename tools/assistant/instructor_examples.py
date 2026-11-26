# ruff: noqa: E501
"""Ejemplos del chat del instructor y de órdenes con el LLM real (para la revisión del paso 4).

Reproduce `demo` por el proceso del instructor (el mismo código que en directo) y hace las
preguntas en los instantes dados; si la propuesta se «confirma», se emite el `InstructorCommand`
que mandaría la plataforma, para que «quitar el viento» tenga un viento que quitar.

    uv run --project ai-module-py python tools/assistant/instructor_examples.py experiments/e7d/paso4-ejemplos.md
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ai_module.assistant.config import load_config
from ai_module.assistant.llm import VllmClient
from ai_module.ids import IdAllocator
from ai_module.instructor.__main__ import InstructorProcess
from ai_module.outbox import EventFactory, format_t
from ai_module.situation.monitor import SituationMonitor
from ai_module.situation.replay import is_world, read_events
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope

REPO = Path(__file__).resolve().parents[2]
BASE = {"asset": None, "event_time": "2026-10-20T10:00:00Z", "causation_id": None,
        "ephemeral": False}  # fmt: skip

# (instante, frase, confirmar la propuesta)
SCRIPT: list[tuple[float, str, bool]] = [
    (30, "Put a strong wind from the north, 19 m/s, until I cancel it", True),
    (35, "Remove the wind", True),
    (36, "Remove the wind", False),
    (40, "wind from the north-east at 8 m/s for two minutes with a 20 second ramp", False),
    (45, "Make it windy", False),
    (46, "Stronger", False),
    (47, "wind from the south", False),
    (48, "20 knots from the west", False),
    (49, "Spoof the GPS now", False),
    (50, "Cut the battery of the drone", False),
    (51, "wind at 60 m/s from the east", False),
    (53, "wind from the west at 20 knots", False),
    (54, "wind from the north at 50 km/h for one minute", False),
    (55, "wind at 100 knots from the east", False),
    (56, "wind force 6 from the south", False),
    (52, "Gentle breeze from 225 degrees, 3 m/s, ramp 5 seconds, 30 seconds long", False),
    (300, "What did I program for this exercise?", False),
    (300, "Did the system see the spoofing? How fast?", False),
    (480, "Did the system detect everything that was injected?", False),
    (480, "Which of the three events was detected latest?", False),
    (480, "Was the hijack caused by the wind?", False),
]  # fmt: skip


def envelope(n: int, event: dict[str, Any]) -> Envelope:
    return Envelope.model_validate({**event, "seq": n, "ingestion_time": "2026-10-20T10:00:00Z"})


class Capture:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish(self, draft: Any) -> None:
        self.events.append(draft)


async def main(out_path: Path) -> None:
    config = load_config()
    client = VllmClient(config.llm)
    await client.check_model()
    process = InstructorProcess("http://127.0.0.1:1", config, client)
    bus = Capture()
    process.bus = bus  # type: ignore[assignment]
    folder = REPO / "runs" / "demo"
    labels = json.loads((folder / "labels.json").read_text())["labels"]
    monitor, factory, n = SituationMonitor(tables="learned"), EventFactory(IdAllocator()), 0
    pending = sorted(SCRIPT, key=lambda x: x[0])
    rows: list[str] = [
        "# Chat del instructor y órdenes (demo; la verdad: viento T+02:05–02:40, engaño "
        "T+03:18–04:12, secuestro T+06:08–06:53)", ""
    ]  # fmt: skip

    async def feed(raw: dict[str, Any]) -> None:
        nonlocal n
        n += 1
        await process.handle(envelope(n, raw))

    async def ask(t: float, text: str, confirm: bool) -> None:
        nonlocal n
        bus.events.clear()
        n += 1
        await process.handle(
            envelope(
                n,
                {
                    **BASE,
                    "event_id": f"ops-{n:04d}",
                    "type": "OperatorMessage",
                    "source": "web-instructor",
                    "sim_time": t,
                    "topic": "citadel.pub.evt.ops.instructor.OperatorMessage.v1",
                    "payload": {"conversation_id": "instructor", "text": text, "context": None},
                },
            )  # fmt: skip
        )
        await process.queue.idle()
        reply = next(e for e in bus.events if e.type == EventType.AGENT_REPLY)
        proposal = reply.payload.get("proposal")
        rows.append(f"**{format_t(t)} — Instructor:** {text}\n")
        rows.append(f"> **Assistant:** {reply.payload['text']}")
        rows.append(f"> tool: `{', '.join(reply.payload['tool_calls']) or '—'}` · proposal: "
                    f"`{json.dumps(proposal) if proposal else 'none'}`\n")  # fmt: skip
        if proposal and confirm:  # lo que haría la web al pulsar Confirm y la plataforma al aplicar
            command = {**BASE, "event_id": f"cmd-{n:04d}", "type": "InstructorCommand",
                       "source": "platform-player", "sim_time": t,
                       "topic": "citadel.pub.evt.sim.instructor.InstructorCommand.v1",
                       "payload": {"command": proposal["command"], "params": proposal["params"],
                                   "issued_by": "llm", "text": text}}  # fmt: skip
            await feed(command)
            rows.append("_(the instructor confirms: the platform applies the command)_\n")

    await feed({**BASE, "event_id": "plr-0001", "type": "SimulationStarted",
                "source": "platform-player", "sim_time": 0.0,
                "topic": "citadel.pub.evt.sim.player.SimulationStarted.v1",
                "payload": {"scenario": "demo", "run_id": "examples", "duration_s": 572.0,
                            "total_events": 1}})  # fmt: skip
    await feed({**BASE, "event_id": "inj-0001", "type": "ExerciseInjects",
                "source": "platform-player", "sim_time": 0.0,
                "topic": "citadel.pub.evt.sim.instructor.ExerciseInjects.v1",
                "payload": {"injects": [{"id": x["id"], "type": x["type"], "source": x["source"],
                                         "start_s": x["start_s"], "end_s": x["end_s"]}
                                        for x in labels]}})  # fmt: skip
    for raw in read_events(folder / "events.jsonl"):
        if not is_world(raw):
            continue
        while pending and pending[0][0] <= raw["sim_time"]:
            await ask(*pending.pop(0))
        await feed(raw)
        for _, payload in monitor.push(raw):
            draft = factory.make(EventType.INCIDENT_UPDATED, payload,
                                 sim_time=payload["as_of_sim_time"])  # fmt: skip
            await feed(draft.model_dump(mode="json"))
    while pending:
        await ask(*pending.pop(0))
    out_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"written {out_path}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
