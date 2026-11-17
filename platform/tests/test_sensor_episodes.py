"""E6: episodios de degradación del GPS y del enlace en el generador.

Un episodio solo cambia el valor nominal sobre el que se publica la medida (sin números aleatorios
nuevos): los escenarios sin episodios salen idénticos a los de `runs/`, byte a byte.
"""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from helpers import scenario_config
from platform_app.generator.build import UNLABELED_FILE, generate, write_run
from platform_app.paths import SCENARIOS_DIR
from poc_contracts.run_files import LabelsFile, UnlabeledEpisodesFile
from poc_contracts.scenario import ScenarioConfig

EXAMPLE = Path(__file__).parent / "data" / "degradations-example.yaml"
FILES = ["events.jsonl", "labels.json", "plan.json", "truth.json"]
SCENARIOS = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))


def example_raw() -> dict:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def example(**sensors: dict) -> ScenarioConfig:
    raw = example_raw()
    for name, value in sensors.items():
        raw["sensors"][name].update(value)
    return ScenarioConfig.model_validate(raw)


def readings(config: ScenarioConfig, event_type: str) -> dict[float, dict]:
    return {
        e.sim_time: e.payload.model_dump() if hasattr(e.payload, "model_dump") else e.payload
        for e in generate(config).events
        if e.type == event_type
    }


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenarios_without_episodes_are_byte_identical_to_runs(
    tmp_path: Path, runs_dir: Path, name: str
) -> None:
    out = write_run(generate(scenario_config(name)), tmp_path / name)
    for f in FILES:
        assert sha(out / f) == sha(runs_dir / name / f), f
    assert not (out / UNLABELED_FILE).exists()


def test_the_example_is_deterministic(tmp_path: Path) -> None:
    config = ScenarioConfig.model_validate(example_raw())
    for i in (1, 2):
        write_run(generate(config), tmp_path / str(i))
    for f in [*FILES, UNLABELED_FILE]:
        assert (tmp_path / "1" / f).read_bytes() == (tmp_path / "2" / f).read_bytes(), f


def test_gps_episode_follows_its_ramp_and_keeps_the_3d_fix() -> None:
    gps = readings(ScenarioConfig.model_validate(example_raw()), "PositionUpdated")
    assert (gps[149.0]["sats"], gps[149.0]["hdop"]) == (14, 0.8)  # antes: lo nominal
    assert (gps[150.0]["sats"], gps[150.0]["hdop"]) == (14, 0.8)  # al empezar, k = 0
    assert (gps[155.0]["sats"], gps[155.0]["hdop"]) == (9, 4.9)  # mitad de la rampa
    assert (gps[180.0]["sats"], gps[180.0]["hdop"]) == (4, 9.0)  # meseta
    assert (gps[205.0]["sats"], gps[205.0]["hdop"]) == (9, 4.9)  # bajada
    assert (gps[211.0]["sats"], gps[211.0]["hdop"]) == (14, 0.8)  # después
    assert {gps[t]["fix"] for t in gps} == {"3d"}
    assert isinstance(gps[155.0]["sats"], int)


def test_the_gps_loss_wins_over_an_episode() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "gps", "mode": "loss", "start_s": 170.0, "end_s": 190.0}]
    gps = readings(ScenarioConfig.model_validate(raw), "PositionUpdated")
    assert (gps[180.0]["fix"], gps[180.0]["sats"]) == ("none", 0)
    assert (gps[195.0]["fix"], gps[195.0]["sats"], gps[195.0]["hdop"]) == ("3d", 4, 9.0)


def test_link_episode_shifts_the_nominal_value_and_keeps_the_noise() -> None:
    base = readings(scenario_config("nominal"), "LinkStatus")
    link = readings(ScenarioConfig.model_validate(example_raw()), "LinkStatus")
    assert base.keys() == link.keys()
    for t in base:
        if not 330.0 <= t <= 390.0:
            assert link[t] == base[t], t  # fuera del episodio, idéntico a nominal
            continue
        # sin rampa: el mismo ruido sobre el valor objetivo (redondeo de 0,1)
        assert link[t]["controller_id"] == "GCS-1"
        assert link[t]["latency_ms"] == pytest.approx(base[t]["latency_ms"] + 205.0, abs=0.11)
        assert link[t]["rssi_dbm"] == pytest.approx(base[t]["rssi_dbm"] - 23.0, abs=0.11)


def test_the_hijack_link_wins_over_a_link_episode() -> None:
    hijack = scenario_config("hijack")
    raw = hijack.model_dump(mode="json")
    start = hijack.hijack.start_s
    raw["sensors"]["link"]["episodes"] = [
        {"start_s": start - 20, "end_s": start + 20, "latency_ms": 400.0}
    ]
    link = readings(ScenarioConfig.model_validate(raw), "LinkStatus")
    plain = readings(hijack, "LinkStatus")
    during = [t for t in link if start <= t <= start + 20]
    before = [t for t in link if start - 20 < t < start]
    assert during and before
    assert all(link[t] == plain[t] for t in during)  # manda el enlace del secuestro
    assert all(link[t]["latency_ms"] > plain[t]["latency_ms"] + 300 for t in before)


def test_labels_of_the_example(tmp_path: Path) -> None:
    run = generate(ScenarioConfig.model_validate(example_raw()))
    labels = {lb.id: lb for lb in run.labels.labels}
    assert set(labels) == {"F1", "F2"}  # el episodio `labeled: false` no tiene etiqueta
    gps, link = labels["F1"], labels["F2"]
    assert (gps.type, gps.source, gps.start_s, gps.end_s) == ("gps_degraded", "gps", 150.0, 210.0)
    assert gps.expected_rules == ["GPS_DEGRADED"] and gps.expected_cause == "SENSOR_FAULT"
    assert gps.also_accepted_causes == ["GPS_JAMMING"] and gps.eval_window == (150.0, 270.0)
    assert (link.type, link.source, link.expected_rules) == (
        "link_degraded",
        "link",
        ["LINK_ANOMALY"],
    )
    assert link.expected_cause == "SENSOR_FAULT" and link.also_accepted_causes == ["UNKNOWN"]
    out = write_run(run, tmp_path)
    LabelsFile.model_validate_json((out / "labels.json").read_text("utf-8"))
    unlabeled = UnlabeledEpisodesFile.model_validate_json((out / UNLABELED_FILE).read_text("utf-8"))
    [u] = unlabeled.episodes
    assert (u.id, u.source, u.start_s, u.end_s, u.rules) == (
        "U1",
        "gps",
        250.0,
        300.0,
        ["GPS_DEGRADED"],
    )
    assert u.eval_window == (250.0, 360.0)


def test_degradations_are_numbered_with_the_faults_by_start() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "radar", "mode": "mute", "start_s": 240.0, "end_s": 245.0}]
    labels = generate(ScenarioConfig.model_validate(raw)).labels.labels
    assert [(lb.id, lb.type) for lb in labels] == [
        ("F1", "gps_degraded"),
        ("F2", "source_silent"),
        ("F3", "link_degraded"),
    ]


def test_writing_a_run_without_unlabeled_episodes_removes_an_old_file(tmp_path: Path) -> None:
    write_run(generate(ScenarioConfig.model_validate(example_raw())), tmp_path)
    assert (tmp_path / UNLABELED_FILE).exists()
    write_run(generate(scenario_config("nominal")), tmp_path)
    assert not (tmp_path / UNLABELED_FILE).exists()
    assert json.loads((tmp_path / "labels.json").read_text())["labels"] == []


@pytest.mark.parametrize(
    ("sensor", "episode", "error"),
    [
        ("gps", {"start_s": 10.0, "end_s": 5.0, "hdop": 3.0}, "end_s must be greater"),
        ("gps", {"start_s": 10.0, "end_s": 20.0}, "needs sats, hdop or both"),
        ("gps", {"start_s": 10.0, "end_s": 20.0, "sats": 3}, "greater than or equal to 4"),
        ("gps", {"start_s": 10.0, "end_s": 20.0, "hdop": 2.0, "fix": "2d"}, "Extra inputs"),
        ("link", {"start_s": 10.0, "end_s": 20.0}, "needs latency_ms, rssi_dbm or both"),
        ("link", {"start_s": 1.0, "end_s": 2.0, "rssi_dbm": -80, "ramp_s": -1}, "greater than or"),
        ("link", {"start_s": 1.0, "end_s": 2.0, "controller_id": "X", "rssi_dbm": -80}, "Extra"),
    ],
)
def test_malformed_episodes_are_rejected(sensor: str, episode: dict, error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        example(**{sensor: {"episodes": [episode]}})


def test_overlapping_episodes_of_a_source_are_rejected() -> None:
    episodes = [
        {"start_s": 10.0, "end_s": 30.0, "hdop": 3.0},
        {"start_s": 25.0, "end_s": 40.0, "hdop": 5.0},
    ]
    with pytest.raises(ValidationError, match="must not overlap"):
        example(gps={"episodes": episodes})


def test_without_episodes_the_field_defaults_to_an_empty_list() -> None:
    config = scenario_config("nominal")
    assert config.sensors.gps.episodes == [] and config.sensors.link.episodes == []


# --- Convención de la E6: una degradación termina donde empieza lo que la anula ---------------


def _labels_of(raw: dict) -> list:
    return generate(ScenarioConfig.model_validate(raw)).labels.labels


def _only(raw: dict, label_type: str):
    [label] = [lb for lb in _labels_of(raw) if lb.type == label_type]
    return label


def test_a_link_degradation_ends_where_the_hijack_starts() -> None:
    raw = scenario_config("hijack").model_dump(mode="json")
    start = raw["hijack"]["start_s"]
    raw["sensors"]["link"]["episodes"] = [
        {"start_s": start - 15, "end_s": start + 20, "latency_ms": 250.0}
    ]
    label = _only(raw, "link_degraded")
    assert (label.start_s, label.end_s) == (start - 15, start)
    assert label.eval_window == (start - 15, start + 60)


def test_a_gps_degradation_ends_where_the_gps_loss_starts() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "gps", "mode": "loss", "start_s": 170.0, "end_s": 190.0}]
    label = _only(raw, "gps_degraded")
    assert (label.start_s, label.end_s) == (150.0, 170.0)


def test_a_degradation_already_cancelled_starts_when_that_ends() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "gps", "mode": "loss", "start_s": 140.0, "end_s": 160.0}]
    label = _only(raw, "gps_degraded")
    assert (label.start_s, label.end_s) == (160.0, 210.0)


def test_a_degradation_fully_cancelled_has_no_label_nor_unlabeled_window() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "gps", "mode": "loss", "start_s": 100.0, "end_s": 320.0}]
    run = generate(ScenarioConfig.model_validate(raw))
    assert [lb.type for lb in run.labels.labels] == ["gps_loss", "link_degraded"]
    assert run.unlabeled is None  # el episodio suave (250–300 s) también queda anulado


def test_an_unlabeled_episode_is_cut_like_a_label() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "gps", "mode": "loss", "start_s": 270.0, "end_s": 280.0}]
    run = generate(ScenarioConfig.model_validate(raw))
    [u] = run.unlabeled.episodes
    assert (u.start_s, u.end_s, u.eval_window) == (250.0, 270.0, (250.0, 330.0))


def test_other_faults_do_not_cut_a_degradation() -> None:
    raw = example_raw()
    raw["faults"] = [{"source": "gps", "mode": "mute", "start_s": 170.0, "end_s": 180.0}]
    label = _only(raw, "gps_degraded")
    assert (label.start_s, label.end_s) == (150.0, 210.0)
