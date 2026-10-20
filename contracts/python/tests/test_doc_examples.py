"""Valida todos los ejemplos JSON de `contracts/eventos.md` (bloques y spans en línea) con los
modelos Pydantic. Si el documento cambia (un ejemplo nuevo o movido), la prueba falla hasta que
se actualice `EXPECTED`: así el documento y el código no se separan."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from poc_contracts.api import ScenarioInfo, ScenariosResponse, ToolError
from poc_contracts.enums import EventType
from poc_contracts.envelope import Envelope
from poc_contracts.payloads import PAYLOAD_MODELS
from poc_contracts.run_files import LabelsFile, PlanFile, TruthFile
from poc_contracts.scenario import ScenarioConfig
from poc_contracts.tools import (
    FlightSummary,
    GetEventsResult,
    MyAlertsResult,
    PublishAlertResult,
    TrackMetrics,
)
from poc_contracts.ws import FaultControl

DOC = Path(__file__).resolve().parents[2] / "eventos.md"
EXAMPLE_RE = re.compile(r"```json\n(.*?)```|`(\{[^`]*\})`", re.S)

Check = Callable[[Any], object]
SKIP = "SKIP"


def payload_of(event_type: EventType) -> Check:
    return PAYLOAD_MODELS[event_type].model_validate


def model(cls: Any) -> Check:
    return cls.model_validate


def extract_examples() -> list[str]:
    text = DOC.read_text(encoding="utf-8")
    return [m.group(1) or m.group(2) for m in EXAMPLE_RE.finditer(text)]


def _envelope_with_position_payload(example: Any) -> object:
    """El sobre de §2 lleva `"payload": { }`: se valida con el payload de §4 (`PositionUpdated`)."""
    assert example["payload"] == {}
    position = json.loads(extract_examples()[5])
    return Envelope.model_validate({**example, "payload": position})


T = EventType
# (principio del ejemplo con los espacios colapsados, cómo se valida) en el orden del documento.
EXPECTED: list[tuple[str, Check | str]] = [
    ('{ "event_id": "gps-000061"', _envelope_with_position_payload),
    ('{ "mission_id": "MSN-DEMO", "cruise_speed_mps"', payload_of(T.MISSION_PLANNED)),
    ('{ "mission_id": "MSN-DEMO" }', payload_of(T.MISSION_STARTED)),
    ('{ "waypoint_id": "WP2"', payload_of(T.WAYPOINT_REACHED)),
    ('{ "mission_id": "MSN-DEMO", "completed"', payload_of(T.MISSION_COMPLETED)),
    ('{ "x": 512.3', payload_of(T.POSITION_UPDATED)),
    ('{ "x": 498.7', payload_of(T.POSITION_UPDATED)),
    ('{ "radar_id"', payload_of(T.TRACK_UPDATED)),
    ('{ "station_id"', payload_of(T.WIND_REPORTED)),
    ('{ "controller_id"', payload_of(T.LINK_STATUS)),
    ('{ "battery_pct"', payload_of(T.BATTERY_STATUS)),
    ('{ "scenario": "demo", "run_id": "20261020', payload_of(T.SIMULATION_STARTED)),
    ('{ "reason": "user" }', payload_of(T.SIMULATION_PAUSED)),
    ("{}", payload_of(T.SIMULATION_RESUMED)),
    ('{ "scenario": "demo", "run_id": "…" }', payload_of(T.SIMULATION_FINISHED)),
    ("{}", payload_of(T.SIMULATION_RESET)),
    ('{ "interactive": true }', payload_of(T.INTERACTIVE_MODE_CHANGED)),
    ('{ "source": "radar", "mode": "mute", "origin"', payload_of(T.FAULT_INJECTED)),
    (
        '{ "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "severity"',
        payload_of(T.DETECTION_RAISED),
    ),
    ('{ "detection_id": "det-0004", "rule": "GPS_DEGRADED"', payload_of(T.DETECTION_RAISED)),
    (
        '{ "detection_id": "det-0002", "rule": "ROUTE_DEVIATION", "duration_s"',
        payload_of(T.DETECTION_CLEARED),
    ),
    ('{ "alert_id": "ai-0003", "detection_ids"', payload_of(T.ANOMALY_DETECTED)),
    ('{ "alert_id": "ai-0003", "reason"', payload_of(T.ALERT_CLOSED)),
    ('{ "run_id": "…", "markdown"', payload_of(T.REPORT_GENERATED)),
    ('{ "conversation_id": "monitor", "text"', payload_of(T.OPERATOR_MESSAGE)),
    (
        '{ "conversation_id": "monitor", "reply_to": "ops-0004", "delta"',
        payload_of(T.AGENT_REPLY_CHUNK),
    ),
    ('{ "conversation_id": "monitor", "reply_to": "ops-0004", "text"', payload_of(T.AGENT_REPLY)),
    ('{ "agent"', payload_of(T.AGENT_ACTIVITY)),
    ('{"source": "gps", "mode": "loss", "active"', model(FaultControl)),
    ('{"scenarios"', model(ScenariosResponse)),
    ('{"ok": true, "result"', SKIP),  # ilustrativo: `…` no es JSON; `result` depende de cada tool
    ('{"ok": false, "error"', model(ToolError)),
    ('{"events"', model(GetEventsResult)),
    ('{ "since": 60.0', model(TrackMetrics)),
    ('{"alerts"', model(MyAlertsResult)),
    ('{ "mission_id": "MSN-DEMO", "duration_s"', model(FlightSummary)),
    ('{"ok": true, "alert_id"', TypeAdapter(PublishAlertResult).validate_python),
    ('{"ok": false, "errors"', TypeAdapter(PublishAlertResult).validate_python),
    (
        '{ "mission_id": "MSN-DEMO", "cruise_speed_mps": 15.0, "altitude_m": 60.0, '
        '"acceptance_radius_m": 25.0, "duration_s"',
        model(PlanFile),
    ),
    ('{ "duration_s": 556.3, "trajectory"', model(TruthFile)),
    ('{ "labels"', model(LabelsFile)),
]


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_example_count_matches() -> None:
    examples = extract_examples()
    assert len(examples) == len(EXPECTED), (
        f"el documento tiene {len(examples)} ejemplos JSON y EXPECTED {len(EXPECTED)}: "
        "actualiza EXPECTED en el mismo orden"
    )


@pytest.mark.parametrize("index", range(len(EXPECTED)))
def test_example_validates(index: int) -> None:
    start, check = EXPECTED[index]
    source = _collapse(extract_examples()[index])
    assert source.startswith(start), (
        f"el ejemplo {index} ya no empieza por {start!r}: {source[:80]!r}"
    )
    if check == SKIP:
        pytest.skip("ejemplo ilustrativo, no es JSON válido")
    assert callable(check)
    check(json.loads(source))


YAML_RE = re.compile(r"```yaml\n(.*?)```", re.S)


def test_yaml_example_of_the_scenario_validates() -> None:
    """El ejemplo completo de §8.1 es un escenario válido."""
    import yaml

    blocks = YAML_RE.findall(DOC.read_text(encoding="utf-8"))
    assert len(blocks) == 1
    config = ScenarioConfig.model_validate(yaml.safe_load(blocks[0]))
    assert config.name == "demo"
    assert config.hijack is not None
    assert config.faults[0].source.value == "radar"


def test_scenario_info_null_duration() -> None:
    """`duration_s` es null si el escenario no está generado."""
    info = ScenarioInfo(name="demo", description="x", generated=False, duration_s=None)
    assert info.duration_s is None
