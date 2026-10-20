"""Rutas del repositorio (la plataforma se ejecuta desde un checkout, en modo editable)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_DIR = REPO_ROOT / "scenarios"
RUNS_DIR = REPO_ROOT / "runs"
