"""Cómo se publica la respuesta de un chat: actividad, trozos rápidos, respuesta y fin.

El texto ya está comprobado: los trozos son el mismo texto escrito de golpe a la web (no hay
streaming real, que dejaría ver un texto que luego se rechazaría).
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from poc_contracts.enums import ActivityState, AgentName, ConversationId, EventType

Send = Callable[..., Awaitable[None]]
CHUNK_WORDS = 4
CHUNK_INTERVAL_S = 0.03


def chunks(text: str, words: int = CHUNK_WORDS) -> list[str]:
    """El texto en trozos de unas palabras, conservando espacios y saltos de línea."""
    pieces = re.split(r"(?<=\s)", text)
    return ["".join(pieces[i : i + words]) for i in range(0, len(pieces), words)]


async def activity(
    send: Send, agent: AgentName, invocation: str, reply_to: str, state: ActivityState
) -> None:
    payload = {"agent": agent.value, "invocation_id": invocation, "causation_id": reply_to,
               "state": state.value}  # fmt: skip
    await send(EventType.AGENT_ACTIVITY, payload, causation_id=reply_to)


async def publish_reply(
    send: Send,
    conversation: ConversationId,
    reply_to: str,
    text: str,
    *,
    tool_calls: list[str] | None = None,
    proposal: dict[str, Any] | None = None,
) -> None:
    """Los trozos y la respuesta final (con la propuesta, solo en el chat del instructor)."""
    for piece in chunks(text):
        await send(
            EventType.AGENT_REPLY_CHUNK,
            {"conversation_id": conversation.value, "reply_to": reply_to, "delta": piece},
            causation_id=reply_to, conversation=conversation,
        )  # fmt: skip
        await asyncio.sleep(CHUNK_INTERVAL_S)
    payload: dict[str, Any] = {"conversation_id": conversation.value, "reply_to": reply_to,
                               "text": text, "tool_calls": tool_calls or []}  # fmt: skip
    if conversation == ConversationId.INSTRUCTOR:
        payload["proposal"] = proposal
    await send(EventType.AGENT_REPLY, payload, causation_id=reply_to, conversation=conversation)
