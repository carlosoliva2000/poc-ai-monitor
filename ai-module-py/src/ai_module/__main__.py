"""Módulo de IA: `uv run --project ai-module-py python -m ai_module --platform http://127.0.0.1:8100`.

En esta fase solo ejecuta el detector de reglas: lee los eventos del bus, publica las detecciones
y las imprime con el mismo formato que `detect_file`.
"""

import argparse
import asyncio
import contextlib
import logging

from .bus_client import DEFAULT_PLATFORM, BusClient, fetch_mission_plan
from .detection_format import DetectionFormatter
from .detector import Detector

log = logging.getLogger("ai_module")


async def run(platform_url: str) -> None:
    detector = Detector()
    formatter = DetectionFormatter()

    async def bootstrap_plan() -> None:
        """Si la simulación ya está en marcha, no llegará `MissionPlanned`: se pide el plan."""
        plan = await fetch_mission_plan(platform_url)
        if plan is not None:
            detector.set_plan(plan)

    async with BusClient(platform_url, on_connected=bootstrap_plan) as bus:
        async for event in bus.events():
            for detection in detector.feed(event):
                print(formatter.format(detection), flush=True)
                await bus.publish(detection)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Módulo de IA de poc-ai-monitor")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="URL de la plataforma")
    parser.add_argument(
        "--detector-only",
        action="store_true",
        help="solo el detector de reglas, sin agentes (único modo por ahora)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(args.platform))
    log.info("stopped")


if __name__ == "__main__":
    main()
