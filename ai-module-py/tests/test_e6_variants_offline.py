"""E6, paso 2b: las variantes de escenarios (`tools/experiments/variants.py`) y el arnés fuera de
línea con la tabla de decisión (`tools/experiments/e6_offline.py`)."""

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import yaml

from poc_contracts.scenario import ScenarioConfig

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools" / "experiments"
GRID = REPO / "experiments" / "e6-variantes" / "grid.yaml"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mini_grid(tmp_path: Path) -> Path:
    grid = {
        "base": "nominal",
        "families": {
            "degradation": {
                "window": {"start_s": 150.0, "end_s": 210.0},
                "ramp_s": [0.0],
                "gps": {"strong": {"sats": 4, "hdop": 9.0}},
                "link": {},
                "unlabeled": {
                    "link-noticeable": {
                        "source": "link",
                        "latency_ms": 100.0,
                        "rssi_dbm": -70.0,
                        "ramp_s": 15.0,
                    }
                },
            },  # fmt: skip
            "clean": {"seeds": [101]},
        },
    }
    path = tmp_path / "grid.yaml"
    path.write_text(yaml.safe_dump(grid, sort_keys=False), encoding="utf-8")
    return path


def test_the_grid_gives_unique_valid_variants() -> None:
    variants = _load("variants")
    grid = yaml.safe_load(GRID.read_text(encoding="utf-8"))
    built = variants.build_variants(grid)
    names = [v[0] for v in built]
    assert len(names) == len(set(names)) == 90
    families = {f: sum(1 for v in built if v[1] == f) for f in {v[1] for v in built}}
    assert families == {"wind": 32, "spoofing": 18, "hijack": 6, "faults": 7, "degradation": 8,
                        "unlabeled": 4, "clean": 10, "combination": 5}  # fmt: skip
    for name, _, _, raw in built:
        config = ScenarioConfig.model_validate(raw)
        assert config.name == name and config.mission.id == "MSN-NOMINAL"  # misma ruta
    raw = {v[0]: v[3] for v in built}
    assert raw["wind-from045-s14-L4"]["wind"]["episodes"][0]["from_deg"] == 45.0
    assert raw["spoofing-d135-r03-t250"]["spoofing"]["end_s"] == 400.0
    assert raw["deg-unlabeled-gps-mild"]["sensors"]["gps"]["episodes"][0]["labeled"] is False
    assert raw["clean-seed107"]["seed"] == 107


def test_variants_are_written_outside_runs_and_are_deterministic(tmp_path: Path) -> None:
    variants = _load("variants")
    grid = _mini_grid(tmp_path)
    for out in ("a", "b"):
        assert variants.main(["--grid", str(grid), "--out", str(tmp_path / out)]) == 0
    index = json.loads((tmp_path / "a" / "variants.json").read_text())
    assert [v["name"] for v in index] == [
        "deg-gps-strong-ramp00",
        "deg-unlabeled-link-noticeable",
        "clean-seed101",
    ]
    assert index[0]["labels"][0]["type"] == "gps_degraded" and index[1]["unlabeled"]
    for name in ("deg-gps-strong-ramp00", "deg-unlabeled-link-noticeable"):
        for f in ("events.jsonl", "labels.json", "truth.json"):
            a = tmp_path / "a" / "runs" / name / f
            assert a.read_bytes() == (tmp_path / "b" / "runs" / name / f).read_bytes()
    assert (
        tmp_path / "a" / "runs" / "deg-unlabeled-link-noticeable" / "unlabeled_episodes.json"
    ).exists()


def test_the_offline_run_answers_like_the_table_engine(tmp_path: Path) -> None:
    offline = _load("e6_offline")
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    shutil.copy(REPO / "scenarios" / "wind.yaml", scenarios / "wind.yaml")
    out = tmp_path / "resumen.md"
    assert offline.main(["--scenarios", str(scenarios), "--runs", str(tmp_path / "runs"),
                         "--out", str(out)]) == 0  # fmt: skip
    [result] = json.loads(out.with_suffix(".json").read_text())
    assert [(lb["id"], lb["verdict"]) for lb in result["labels"]] == [("A1", "✅")]
    assert result["rows"][0] == "C17" and result["false_alarms"] == 0
    assert result["forced_resumes"] == 0 and result["events_after_as_of"] == 0
    assert result["rejections"] == 0 and result["fallbacks"] == 0
    folder = tmp_path / "runs" / "wind" / "offline"
    for f in ("timeline.jsonl", "llm_trace.jsonl", "run_meta.json", "profile.json", "eval.md"):
        assert (folder / f).exists(), f
    alerts = [json.loads(x) for x in (folder / "timeline.jsonl").read_text().splitlines()]
    [alert] = [e for e in alerts if e["type"] == "AnomalyDetected"]
    assert alert["payload"]["decided_by"] == "table" and alert["payload"]["rule_id"] == "C17"


def test_an_unlabeled_episode_that_fires_is_not_a_false_alarm(tmp_path: Path) -> None:
    variants, offline = _load("variants"), _load("e6_offline")
    variants.main(["--grid", str(_mini_grid(tmp_path)), "--out", str(tmp_path)])
    out = tmp_path / "resumen.md"
    offline.main(["--scenarios", str(tmp_path / "scenarios"), "--runs", str(tmp_path / "runs"),
                  "--only", "deg-unlabeled-link-noticeable", "--out", str(out)])  # fmt: skip
    [result] = json.loads(out.with_suffix(".json").read_text())
    assert result["labels"] == [] and result["false_alarms"] == 0
    assert result["unlabeled"] == [
        {"id": "U1", "detections": 1, "alerts": ["SENSOR_FAULT"], "false": 0}
    ]


def test_running_twice_does_not_pile_up_the_trace(tmp_path: Path) -> None:
    offline = _load("e6_offline")
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    shutil.copy(REPO / "scenarios" / "wind.yaml", scenarios / "wind.yaml")
    args = ["--scenarios", str(scenarios), "--runs", str(tmp_path / "runs")]
    for _ in range(2):
        offline.main([*args, "--out", str(tmp_path / "r.md")])
    [result] = json.loads((tmp_path / "r.json").read_text())
    assert result["rows"].count("C17") == 1
