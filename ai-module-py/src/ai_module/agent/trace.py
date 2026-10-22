"""Trazas: `runs/<escenario>/<run_id>/llm_trace.jsonl`, una línea por invocación de un agente.

Cada línea lleva los parámetros enviados, las tools ofrecidas, los `messages` completos (una sola
vez), lo que pasó en cada llamada al LLM y lo que publicó la invocación. Es lo que lee la
evaluación y lo que enseñará la consola de la web.
"""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CallTrace:
    """Una llamada al LLM dentro de una invocación."""

    index: int
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str | None
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    restricted_tools: list[str] | None = None
    """Tools ofrecidas en esta llamada si se redujeron (última iteración), si no `None`."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "latency_s": round(self.latency_s, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "finish_reason": self.finish_reason,  # solo como anotación
            "content": self.content,
            "tool_calls": self.tool_calls,
            "restricted_tools": self.restricted_tools,
        }


@dataclass
class InvocationTrace:
    invocation_id: str
    agent: str
    causation_ids: list[str] = field(default_factory=list)
    as_of: float = 0.0
    sim_time_end: float = 0.0
    queue_at_start: int = 0
    wall_start: str = ""
    wall_end: str = ""
    duration_s: float = 0.0
    model: str = ""
    sampling: dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    guided_mode: bool = False
    aids: dict[str, Any] = field(default_factory=dict)
    """Ayudas al modelo activas en esta invocación (interruptores del monitor)."""
    tools_offered: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    calls: list[CallTrace] = field(default_factory=list)
    skills_loaded: list[dict[str, str]] = field(default_factory=list)
    guardrail_rejections: list[dict[str, Any]] = field(default_factory=list)
    invalid_json: int = 0
    reminders: int = 0
    unseen_evidence: int = 0
    end_reason: str = ""
    deterministic: bool = False
    fallback: bool = False
    fallback_close: bool = False
    published: list[dict[str, str]] = field(default_factory=list)
    """Eventos publicados: `{"event_id", "type", "causation_id"}`."""
    conversation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {k: v for k, v in self.__dict__.items() if k != "calls"}
        data["iterations"] = len(self.calls)
        data["calls"] = [c.to_dict() for c in self.calls]
        return data


class TraceWriter:
    """Añade una línea JSON por invocación. Sin ruta (`None`) no escribe nada."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.records: list[dict[str, Any]] = []

    def write(self, trace: InvocationTrace) -> None:
        record = trace.to_dict()
        self.records.append(record)
        if self.path is None:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
