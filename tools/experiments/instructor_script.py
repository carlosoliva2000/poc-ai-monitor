"""Guion del agente del instructor contra vLLM, sin plataforma ni web (Fase 16).

    uv run --project ai-module-py python tools/experiments/instructor_script.py [--out FICHERO.md]

Cada frase se pregunta al chat del instructor con el historial vacío (y, si el caso lo pide, con
un viento del instructor activo) y se imprime la propuesta validada, las llamadas a tools y la
latencia. Necesita vLLM en `127.0.0.1:8000/v1` con el modelo de `agents.yaml`.
"""

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_module.agent.assets import Assets
from ai_module.agent.llm import OpenAiLlm
from ai_module.instructor import InstructorChat
from ai_module.runtime import Runtime
from poc_contracts.enums import ConversationId, EventType
from poc_contracts.envelope import Envelope, EventDraft
from poc_contracts.topics import source_for, topic_for

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = {"from_deg": 0.0, "speed_mps": 12.0, "gust_mps": 16.0, "remaining_s": 41.0}
# (frase, viento activo, qué se espera)
CASES: list[tuple[str, dict[str, Any] | None, str]] = [
    ("Wind from the north-east at 8 m/s on the drone", None, "set_wind 45°, 8 m/s, defaults"),
    (
        "Put a 12 m/s wind from the north with gusts of 16 for one minute",
        None,
        "0°, 12, gust 16, 60 s",
    ),
    ("West wind, 10 m/s, for 2 minutes", None, "270°, 10, 120 s"),
    (
        "Wind from 225 degrees, 8 m/s, gusts 12, ramp up in 20 seconds",
        None,
        "225°, 8, gust 12, ramp 20",
    ),
    ("Remove the wind", ACTIVE, "cancel_wind (con viento activo)"),
    ("Stronger", None, "pregunta (sin viento activo)"),
    ("Stronger", ACTIVE, "pregunta la nueva velocidad en m/s"),
    ("Wind from the south", None, "pregunta la velocidad o la rellena y lo dice"),
    ("East wind at 100 m/s", None, "fuera de rango: lo dice y no propone"),
]


# Conversación seguida, sin reiniciar el historial (lo que hace el instructor en la web): el
# modelo llegó a imitar sus respuestas anteriores y a «proponer» sin llamar a la tool.
CONVERSATION = [
    "wind from the east at 15 m/s for 10 seconds",
    "put a very strong wind from the south-east now, for 60 seconds",
    "stronger",
    "wind from the south at 8 m/s",
    "put a very strong wind with 25 m/s from east, for 20 seconds",
    "put a very strong wind with 25 m/s from east, for 20 seconds",
    "put a very strong wind with 25 m/s from east, for 20 seconds",
    "west wind 10 m/s for 2 minutes",
    "remove the wind",
    "wind from 225 degrees, 8 m/s",
]


def operator_event(n: int, text: str, context: dict[str, Any] | None) -> Envelope:
    conv = ConversationId.INSTRUCTOR
    payload: dict[str, Any] = {"conversation_id": "instructor", "text": text}
    if context is not None:
        payload["context"] = {"active_wind": context}
    return Envelope(
        event_id=f"ops-{n:04d}",
        topic=topic_for(EventType.OPERATOR_MESSAGE, conv),
        type=EventType.OPERATOR_MESSAGE,
        source=source_for(EventType.OPERATOR_MESSAGE, conv),
        asset=None,
        seq=n,
        sim_time=0.0,
        event_time="2026-10-20T10:00:00Z",
        ingestion_time="2026-10-20T10:00:00.000Z",
        payload=payload,
    )


async def main(out: Path | None, repeat: int, keep_history: bool = False) -> None:
    assets = Assets(ROOT / "agent-assets", None)
    published: list[EventDraft] = []

    async def publish(event: EventDraft) -> None:
        published.append(event)

    rt = Runtime(assets, OpenAiLlm(assets.llm.base_url, assets.llm.api_key, assets.llm.model),
                 "http://127.0.0.1:8100", publish, Path(tempfile.mkdtemp()))  # fmt: skip
    chat = InstructorChat(rt)
    lines = [f"# Instructor script · model {assets.llm.model}\n"]
    n = 0
    cases = [(p, ACTIVE if "remove" in p else None, "propuesta con tool") for p in CONVERSATION]
    for phrase, active, expected in cases if keep_history else CASES:
        for _k in range(repeat):
            n += 1
            if not keep_history:
                chat.reset()
            published.clear()
            started = time.monotonic()
            await chat.answer(operator_event(n, phrase, active))
            latency = time.monotonic() - started
            reply = next(e for e in published if e.type == EventType.AGENT_REPLY)
            calls = [e.payload for e in published if e.type == EventType.AGENT_TOOL_CALL]
            proposal = reply.payload.get("proposal")
            lines += [
                f"## {n}. «{phrase}»" + (" (con viento activo)" if active else ""),
                f"- Esperado: {expected}",
                *(
                    f"- Llamada: `{c['tool']}({c['arguments']})` → {c['status']} {c['result']}"
                    for c in calls
                ),
                f"- Propuesta: `{json.dumps(proposal)}`" if proposal else "- Propuesta: ninguna",
                f"- Respuesta: {reply.payload['text']}",
                f"- Latencia: {latency:.1f} s\n",
            ]
            print("\n".join(lines[-(len(calls) + 5) :]), flush=True)
    if out:
        out.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--keep-history", action="store_true", help="una conversación seguida")
    args = parser.parse_args()
    asyncio.run(main(args.out, args.repeat, args.keep_history))
