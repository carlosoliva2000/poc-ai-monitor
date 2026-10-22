"""Exporta los modelos a JSON Schema en `contracts/schemas/`.

Uso: `uv run --project contracts/python python -m poc_contracts.export_schemas [--out DIR]`.
La salida es determinista; una prueba comprueba que `contracts/schemas/` está al día.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from .api import ScenariosResponse, TimelineResponse, ToolError, ToolOk
from .envelope import Envelope, EventDraft
from .payloads import PAYLOAD_MODELS
from .run_files import LabelsFile, PlanFile, RunMeta, TruthFile
from .scenario import ScenarioConfig
from .tools import TOOL_MODELS, PublishAlertResult
from .ws import ClientMessage, ServerMessage, StateMessage

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "schemas"


def build_schemas() -> dict[str, dict[str, Any]]:
    """Ruta relativa (con `/`) -> esquema JSON de cada modelo del contrato."""
    schemas: dict[str, dict[str, Any]] = {
        "envelope.json": Envelope.model_json_schema(),
        "event_draft.json": EventDraft.model_json_schema(),
        "ws/client_message.json": TypeAdapter(ClientMessage).json_schema(),
        "ws/server_message.json": TypeAdapter(ServerMessage).json_schema(),
        "api/state.json": StateMessage.model_json_schema(),
        "api/scenarios_response.json": ScenariosResponse.model_json_schema(),
        "api/timeline_response.json": TimelineResponse.model_json_schema(),
        "api/tool_ok.json": ToolOk.model_json_schema(),
        "api/tool_error.json": ToolError.model_json_schema(),
        "tools/publish_alert.result.json": TypeAdapter(PublishAlertResult).json_schema(),
        "files/scenario.json": ScenarioConfig.model_json_schema(),
        "files/plan.json": PlanFile.model_json_schema(),
        "files/truth.json": TruthFile.model_json_schema(),
        "files/labels.json": LabelsFile.model_json_schema(),
        "files/run_meta.json": RunMeta.model_json_schema(),
    }
    for event_type, model in PAYLOAD_MODELS.items():
        schemas[f"payloads/{event_type.value}.json"] = model.model_json_schema()
    for name, (args, result) in TOOL_MODELS.items():
        schemas[f"tools/{name}.args.json"] = _schema(args)
        if result is not None:
            schemas[f"tools/{name}.result.json"] = _schema(result)
    return schemas


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()


def render(schema: dict[str, Any]) -> str:
    """Texto exacto que se escribe en el fichero."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def write_schemas(out: Path) -> list[Path]:
    """Escribe los esquemas y borra los `.json` de `out` que ya no se generan."""
    schemas = build_schemas()
    written: list[Path] = []
    for rel, schema in schemas.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(schema), encoding="utf-8")
        written.append(path)
    for stale in sorted(set(out.rglob("*.json")) - set(written)):
        stale.unlink()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="carpeta de salida")
    args = parser.parse_args()
    written = write_schemas(args.out)
    print(f"{len(written)} esquemas escritos en {args.out}")


if __name__ == "__main__":
    main()
