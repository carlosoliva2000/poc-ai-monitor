"""Los modelos de argumentos coinciden con los esquemas que ve el modelo (`tools.json`)."""

import json
from pathlib import Path
from typing import Any

import pytest

from poc_contracts.tools import TOOL_MODELS

TOOLS_JSON = Path(__file__).resolve().parents[3] / "agent-assets" / "tools.json"
TOOLS: dict[str, dict[str, Any]] = {
    t["function"]["name"]: t["function"]["parameters"]
    for t in json.loads(TOOLS_JSON.read_text(encoding="utf-8"))
}


def test_same_tool_names() -> None:
    assert set(TOOLS) == set(TOOL_MODELS)


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_args_match_tools_json(name: str) -> None:
    model_schema = TOOL_MODELS[name][0].model_json_schema()
    json_props = TOOLS[name]["properties"]
    assert set(model_schema.get("properties", {})) == set(json_props)
    # `checks` es obligatorio en `tools.json` y opcional en el modelo (`require_checks`)
    optional_in_model = {"checks"} if name == "publish_alert" else set()
    assert set(model_schema.get("required", [])) | optional_in_model == set(TOOLS[name]["required"])
    defs = model_schema.get("$defs", {})
    for prop, spec in json_props.items():
        if "enum" in spec:
            schema = model_schema["properties"][prop]
            ref = schema.get("$ref") or next(
                (a["$ref"] for a in schema.get("anyOf", []) if "$ref" in a), None
            )
            assert ref is not None, f"{name}.{prop}: el modelo no usa un enumerado"
            assert set(defs[ref.split("/")[-1]]["enum"]) == set(spec["enum"])
