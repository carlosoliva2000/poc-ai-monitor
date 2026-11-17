"""Rutas del repositorio (la plataforma se ejecuta desde un checkout, en modo editable).

`POC_SCENARIOS_DIR` y `POC_RUNS_DIR` (opcionales) cambian de dónde se leen los escenarios y dónde
van las salidas, para ejecutar un conjunto de escenarios que no está en `scenarios/` sin copiarlo
ni tocar `runs/`. Los heredan los procesos que lanza `run.py` (plataforma y módulo de IA).
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_DIR = Path(os.environ.get("POC_SCENARIOS_DIR") or REPO_ROOT / "scenarios").resolve()
RUNS_DIR = Path(os.environ.get("POC_RUNS_DIR") or REPO_ROOT / "runs").resolve()
