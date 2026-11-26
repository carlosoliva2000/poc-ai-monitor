"""Órdenes de control del reproductor: las comparten el WebSocket (`control`) y la API REST.

Un solo sitio para despacharlas garantiza que las dos caras validan y se comportan igual.
"""

import json
from pathlib import Path
from typing import Any

from poc_contracts.ws import (
    ControlFault,
    ControlInstructor,
    ControlInteractive,
    ControlLoad,
    ControlPause,
    ControlPlay,
    ControlReset,
    ControlSpeed,
    ControlStep,
)

from .player import Player, PlayerError

NO_SCENARIO = "no scenario is loaded"
# Todas las órdenes salvo cargar un escenario y encender el modo interactivo (que cada carga apaga)
NEEDS_SCENARIO = (
    ControlPlay,
    ControlPause,
    ControlStep,
    ControlReset,
    ControlSpeed,
    ControlFault,
    ControlInstructor,
)


def apply_control(player: Player, message: Any) -> None:
    """Ejecuta un mensaje `control` ya validado. Lanza `PlayerError` si la orden no procede.

    Sin escenario cargado, las órdenes que lo necesitan dan siempre «no scenario is loaded» (antes
    que cualquier otro motivo, como el modo interactivo apagado).
    """
    if isinstance(message, NEEDS_SCENARIO) and player.sim is None:
        raise PlayerError(NO_SCENARIO)
    match message:
        case ControlLoad():
            player.load(message.value)
        case ControlPlay():
            player.play()
        case ControlPause():
            player.pause()
        case ControlStep():
            player.step()
        case ControlReset():
            player.reset()
        case ControlSpeed():
            player.set_speed(message.value)
        case ControlInteractive():
            player.set_interactive(message.value)
        case ControlFault():
            f = message.value
            player.fault(f.source, f.mode, f.active)
        case ControlInstructor():
            player.instructor(message.value)


def generated_duration(runs_dir: Path, name: str) -> float | None:
    """Duración del escenario generado (`sim_time` del último evento), o `None` si no existe."""
    path = runs_dir / name / "events.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return float(json.loads(lines[-1])["sim_time"]) if lines else None
