"""Módulo de IA: `uv run --project ai-module-py python -m ai_module --platform http://127.0.0.1:8100`.

Por defecto ejecuta el detector de reglas y los agentes (monitor, informe y chats) contra el LLM
local; con `--detector-only` solo el detector. Imprime las detecciones con el mismo formato que
`detect_file`.
"""

import argparse
import asyncio
import contextlib
import logging
from pathlib import Path

from .agent.assets import DEFAULT_ASSETS, Assets
from .agent.llm import OpenAiLlm
from .bus_client import DEFAULT_PLATFORM, BusClient, fetch_mission_plan
from .detector import Detector
from .module import AiModule
from .runtime import Runtime

log = logging.getLogger("ai_module")

DEFAULT_RUNS = Path("runs")


async def run(
    platform_url: str,
    *,
    detector_only: bool = False,
    assets_dir: Path = DEFAULT_ASSETS,
    runs_dir: Path = DEFAULT_RUNS,
    llm_url: str | None = None,
) -> None:
    assets = Assets(assets_dir)
    llm = OpenAiLlm(llm_url or assets.llm.base_url, assets.llm.api_key, assets.llm.model)
    detector = Detector()

    async def bootstrap_plan() -> None:
        """Si la simulación ya está en marcha, no llegará `MissionPlanned`: se pide el plan."""
        plan = await fetch_mission_plan(platform_url)
        if plan is not None:
            detector.set_plan(plan)

    async with BusClient(platform_url, on_connected=bootstrap_plan) as bus:
        rt = Runtime(assets, llm, platform_url, bus.publish, runs_dir)
        module = AiModule(
            rt,
            detector,
            with_agents=not detector_only,
            on_detection=lambda line: print(line, flush=True),
        )
        module.start()
        try:
            async for message in bus.messages():
                await module.handle(message)
        finally:
            await module.stop()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI module of poc-ai-monitor")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="platform URL")
    parser.add_argument(
        "--detector-only", action="store_true", help="rule-based detector only, no agents"
    )
    parser.add_argument("--llm-url", help="LLM server URL (default: the one in agents.yaml)")
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="carpeta agent-assets/")
    parser.add_argument(
        "--runs", type=Path, default=DEFAULT_RUNS, help="runs/ folder where traces are saved"
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(
            run(
                args.platform,
                detector_only=args.detector_only,
                assets_dir=args.assets,
                runs_dir=args.runs,
                llm_url=args.llm_url,
            )
        )
    log.info("stopped")


if __name__ == "__main__":
    main()
