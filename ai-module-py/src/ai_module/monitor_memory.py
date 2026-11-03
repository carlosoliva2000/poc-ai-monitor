"""Memoria A del monitor (`monitor.memory: per_run`): una sola conversación durante la simulación.

Cada aviso nuevo se añade como mensaje de usuario con el estado de ese instante; las respuestas,
las tool calls y los resultados anteriores se quedan en el historial. Como `max_model_len` es
limitado, antes de cada turno el historial se **compacta por bloques** cuando su tamaño estimado
supera `budget` y se baja de una vez hasta `target` (así el prefijo queda estable hasta la
siguiente compactación y la caché de prefijos de vLLM se reutiliza):

- nivel A, de los turnos más antiguos a los más nuevos: el resultado de cada tool de datos se
  sustituye por una nota (se conserva el mensaje, para que cada `tool_call_id` siga emparejado),
  el objetivo antiguo se queda en una línea y se quitan los recordatorios; se conservan las
  llamadas, las decisiones y los rechazos;
- nivel B, si no basta: el turno entero pasa a una línea de un resumen común.

Nunca se toca el mensaje de sistema ni el turno en curso. Los mensajes antiguos no se modifican
en su sitio (se construyen otros nuevos), de modo que las copias que guardan las trazas no cambian.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .agent.assets import render, sections
from .agent.llm import Messages

DECISION_TOOLS = ("publish_alert", "acknowledge_detection", "close_alert")
ID_RE = re.compile(r"\b(?:gps|rad|met|lnk|bat|mis|det|ai|ops)-\d+\b")
DEFAULT_SLOPE = 1 / 2.7  # tokens por carácter
DEFAULT_OVERHEAD = 1000.0  # tokens fijos (las tools que se ofrecen)


def chars_of(messages: Messages) -> int:
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)


@dataclass
class Turn:
    """Los mensajes de una invocación del monitor, con lo necesario para compactarla."""

    t: str
    warnings: str
    messages: Messages
    outcome: str = ""
    level_a: bool = False


@dataclass
class TurnInfo:
    """Lo que `begin_turn` cuenta a la traza."""

    turn: int
    tokens_before: int
    tokens_after: int
    compacted_a: int = 0
    compacted_b: int = 0


@dataclass
class MonitorMemory:
    texts: str
    """Contenido de `monitor_memory.md`."""
    budget: int
    target: int
    turns: list[Turn] = field(default_factory=list)
    digest: list[str] = field(default_factory=list)
    slope: float = DEFAULT_SLOPE
    overhead: float = DEFAULT_OVERHEAD
    count: int = 0
    _prefix: int = 0
    _system: str = ""

    def __post_init__(self) -> None:
        _, self._secs = sections(self.texts)

    def reset(self) -> None:
        self.turns.clear()
        self.digest.clear()
        self.slope, self.overhead = DEFAULT_SLOPE, DEFAULT_OVERHEAD
        self.count = 0

    # --- Tamaño ---------------------------------------------------------------------------

    def estimate(self, messages: Messages) -> int:
        return round(self.overhead + self.slope * chars_of(messages))

    def observe(self, first: tuple[int, int], last: tuple[int, int]) -> None:
        """Ajusta la estimación con dos puntos (caracteres, tokens de prompt) de una invocación:
        su primera y su última llamada al LLM."""
        (c1, t1), (c2, t2) = first, last
        if c2 - c1 < 2000 or t2 <= t1:
            return
        slope = (t2 - t1) / (c2 - c1)
        overhead = t1 - slope * c1
        if 1 / 8 <= slope <= 1 / 1.2 and 0 <= overhead <= 6000:
            self.slope, self.overhead = slope, overhead

    # --- Turnos ---------------------------------------------------------------------------

    def _flat(self, system: str) -> Messages:
        out: Messages = [{"role": "system", "content": system}]
        if self.digest:
            lines = "\n".join(self.digest)
            out.append({"role": "user", "content": render(self._secs["digest"], lines=lines)})
        for turn in self.turns:
            out.extend(turn.messages)
        return out

    def begin_turn(
        self, system: str, objective: str, *, t: str, warnings: str
    ) -> tuple[Messages, TurnInfo]:
        """Compacta si hace falta y devuelve el historial más el mensaje de usuario del turno (la
        lista que ampliará el motor)."""
        content = objective
        if self.turns or self.digest:
            content = self._secs["next_turn"] + "\n\n" + objective
        user: dict[str, Any] = {"role": "user", "content": content}
        before = self.estimate([*self._flat(system), user])
        info = TurnInfo(self.count + 1, before, before)
        if before > self.budget:
            info.compacted_a, info.compacted_b = self._compact(system, user)
            info.tokens_after = self.estimate([*self._flat(system), user])
        flat = self._flat(system)
        self._prefix = len(flat)
        flat.append(user)
        self.turns.append(Turn(t, warnings, [user]))
        self.count += 1
        return flat, info

    def end_turn(self, messages: Messages, outcome: str) -> None:
        """Guarda lo que añadió el turno. Cierra las tool calls que se quedaron sin resultado (la
        invocación se cortó) para que el historial siga siendo una conversación válida."""
        turn = self.turns[-1]
        turn.messages = self._close_pending_calls(messages[self._prefix :])
        turn.outcome = outcome

    def _close_pending_calls(self, messages: Messages) -> Messages:
        answered = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
        out = list(messages)
        for message in messages:
            for call in message.get("tool_calls") or []:
                if call["id"] not in answered:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": self._secs["aborted_call"],
                        }
                    )
        return out

    # --- Compactación ---------------------------------------------------------------------

    def _compact(self, system: str, user: dict[str, Any]) -> tuple[int, int]:
        def size() -> int:
            return self.estimate([*self._flat(system), user])

        level_a = level_b = 0
        for turn in self.turns:
            if size() <= self.target:
                break
            if not turn.level_a:
                turn.messages = self._level_a(turn)
                turn.level_a = True
                level_a += 1
        while size() > self.target and self.turns[:-1]:
            oldest = self.turns.pop(0)
            line = render(
                self._secs["compacted_turn"],
                t=oldest.t,
                warnings=oldest.warnings,
                outcome=oldest.outcome or "no recorded outcome",
            )
            self.digest.append(line)
            level_b += 1
        return level_a, level_b

    def _level_a(self, turn: Turn) -> Messages:
        names = {
            call["id"]: call["function"]["name"]
            for m in turn.messages
            for call in (m.get("tool_calls") or [])
        }
        out: Messages = []
        for index, message in enumerate(turn.messages):
            role = message.get("role")
            if index == 0 and role == "user":
                content = render(
                    self._secs["compacted_objective"], t=turn.t, warnings=turn.warnings
                )
                out.append({"role": "user", "content": content})
            elif role == "user":
                continue  # un recordatorio
            elif role == "tool" and names.get(message["tool_call_id"]) not in DECISION_TOOLS:
                content = self._secs["compacted_result"]
                out.append({**message, "content": content})
            else:
                out.append(message)
        return out

    def history_ids(self) -> set[str]:
        """Los ids que aún se ven en el historial retenido (menos el turno en curso)."""
        text = json.dumps([m for t in self.turns[:-1] for m in t.messages], ensure_ascii=False)
        return set(ID_RE.findall(text))
