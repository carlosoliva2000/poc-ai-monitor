"""Proceso del monitor de situación: se conecta a la plataforma y publica los incidentes.

    uv run --project ai-module-py python -m ai_module.situation --platform http://127.0.0.1:8100

La plataforma se arranca sin el módulo anterior (con `--no-ai`). Se reinicia con
`SimulationStarted` y `SimulationReset`; con `SimulationFinished` cierra el último segundo y, con
el asistente preparado, publica el informe del escenario si tiene uno.
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.ws import EventMessage, StateMessage

from ..bus_client import DEFAULT_PLATFORM, BusClient, fetch_mission_plan
from ..ids import IdAllocator
from ..outbox import EventFactory, format_t
from .monitor import SituationMonitor
from .policy import HERE
from .replay import is_world
from .scripted import ScriptedAssistant

log = logging.getLogger("ai_module.situation")
RESET_TYPES = {EventType.SIMULATION_STARTED, EventType.SIMULATION_RESET}


class SituationProcess:
    def __init__(self, platform_url: str, assistant: str) -> None:
        self.platform_url = platform_url
        self.ids = IdAllocator()
        self.factory = EventFactory(self.ids)
        self.monitor = SituationMonitor(self.ids)
        self.bus = BusClient(platform_url, on_connected=self._on_connected)
        self.now = 0.0
        self.scenario: str | None = None
        self.run_id = ""
        self.assistant = (
            ScriptedAssistant(self.factory, self.bus.publish, lambda: self.now)
            if assistant == "scripted"
            else None
        )

    async def _on_connected(self) -> None:
        """Si la simulación ya estaba en marcha, el plan se pide por HTTP."""
        plan = await fetch_mission_plan(self.platform_url)
        if plan and not self.monitor.features.waypoints:
            self.monitor.set_plan(plan["waypoints"])

    def _reset(self) -> None:
        self.ids.reset()
        self.monitor.reset()
        self.now = 0.0
        if self.assistant:
            self.assistant.reset()

    async def _publish_updates(self, updates: list[tuple[float, dict[str, Any]]]) -> None:
        for sim_time, payload in updates:
            draft = self.factory.make(EventType.INCIDENT_UPDATED, payload, sim_time=sim_time)
            await self.bus.publish(draft)
            log.info(
                "%s %s %s %s -> %s", format_t(sim_time), payload["incident_id"],
                payload["change"], payload["kind"], payload["state"],
            )  # fmt: skip
            if self.assistant:
                self.assistant.on_incident(draft)

    async def handle(self, event: Envelope) -> None:
        kind = event.type
        if kind in RESET_TYPES:
            self._reset()
            if kind == EventType.SIMULATION_STARTED:
                self.scenario = event.payload.get("scenario")
                self.run_id = str(event.payload.get("run_id", ""))
            return
        if kind == EventType.SIMULATION_FINISHED:
            await self._publish_updates(self.monitor.flush())
            if self.assistant:
                self.assistant.on_finished(self.scenario, self.run_id, self.monitor.tracker.count)
            return
        if kind == EventType.OPERATOR_MESSAGE:
            if self.assistant:
                self.assistant.on_operator_message(event.event_id, event.payload)
            return
        raw = event.model_dump(mode="json")
        if not is_world(raw):
            return  # lo que publica el propio módulo (dominio ai) no entra en el monitor
        self.factory.observe(event)
        self.now = max(self.now, event.sim_time)
        await self._publish_updates(self.monitor.push(raw))

    async def run(self) -> None:
        async with self.bus:
            async for message in self.bus.messages():
                if isinstance(message, StateMessage):
                    self.now = max(self.now, message.sim_time)
                    self.scenario = message.scenario or self.scenario
                    self.run_id = message.run_id or self.run_id
                elif isinstance(message, EventMessage):
                    await self.handle(message.event)


def main() -> None:
    parser = argparse.ArgumentParser(description="Situation monitor (incidents)")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM)
    parser.add_argument("--config", type=Path, default=HERE / "config.yaml")
    parser.add_argument("--assistant", choices=["scripted", "off"], default=None)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    assistant = args.assistant or str(config.get("assistant", "off"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info("situation monitor, assistant=%s, platform=%s", assistant, args.platform)
    asyncio.run(SituationProcess(args.platform, assistant).run())


if __name__ == "__main__":
    main()
