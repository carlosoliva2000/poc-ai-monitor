"""Utilidades de las pruebas de la plataforma."""

from pathlib import Path
from typing import Any

import yaml

from platform_app.bus import Bus
from platform_app.paths import SCENARIOS_DIR
from platform_app.player import Player
from platform_app.timeline import Timeline
from poc_contracts.scenario import ScenarioConfig


def scenario_config(name: str = "nominal", **overrides: object) -> ScenarioConfig:
    """Escenario de `scenarios/` con campos de primer nivel sustituidos (diccionarios ya listos)."""
    raw = yaml.safe_load((SCENARIOS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    raw.update(overrides)
    return ScenarioConfig.model_validate(raw)


def make_player(runs_dir: Path, **options: Any) -> Player:
    """Reproductor con un bus nuevo que escribe en `runs_dir` (sin reloj de pared)."""
    return Player(Bus(Timeline()), runs_dir=runs_dir, **options)


def published_drafts(player: Player) -> list[dict]:
    """Eventos de la simulación publicados (sin `plr-`, `seq` ni `ingestion_time`)."""
    return [
        e.model_dump(mode="json", exclude={"seq", "ingestion_time"})
        for e in player.bus.timeline.all()
        if not e.event_id.startswith("plr-")
    ]
