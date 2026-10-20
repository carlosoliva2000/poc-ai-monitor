"""El detector sobre los `runs/<escenario>/events.jsonl` de los seis escenarios."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ai_module.detect_file import detect
from ai_module.detection_format import DetectionFormatter
from poc_contracts.enums import EventType, Rule
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import DetectionCleared, DetectionRaised

RUNS = Path(__file__).resolve().parents[2] / "runs"
SCENARIOS = ["nominal", "viento", "spoofing", "secuestro", "fallos", "demo"]


@dataclass
class Episode:
    detection_id: str
    rule: str
    source: str | None
    raised: float
    updated: list[float] = field(default_factory=list)
    cleared: float | None = None


def episodes_of(detections: list[EventDraft]) -> list[Episode]:
    episodes: dict[str, Episode] = {}
    for d in detections:
        if d.type == EventType.DETECTION_RAISED:
            raised = DetectionRaised.model_validate(d.payload)
            source = raised.source.value if raised.source else None
            episodes[raised.detection_id] = Episode(
                raised.detection_id, raised.rule.value, source, d.sim_time
            )
        elif d.type == EventType.DETECTION_UPDATED:
            episodes[d.payload["detection_id"]].updated.append(d.sim_time)
        else:
            cleared = DetectionCleared.model_validate(d.payload)
            episodes[cleared.detection_id].cleared = d.sim_time
    return list(episodes.values())


def table(detections: list[EventDraft]) -> str:
    formatter = DetectionFormatter()
    return "\n".join(formatter.format(d) for d in detections) or "(sin detecciones)"


def labels_of(scenario: str) -> list[dict]:
    return json.loads((RUNS / scenario / "labels.json").read_text())["labels"]


@pytest.fixture(scope="module")
def results() -> dict[str, list[EventDraft]]:
    return {name: detect(RUNS / name / "events.jsonl") for name in SCENARIOS}


def find(episodes: list[Episode], rule: str, source: str | None = None) -> list[Episode]:
    return [e for e in episodes if e.rule == rule and (source is None or e.source == source)]


def in_window(episode: Episode, window: list[float]) -> bool:
    return window[0] <= episode.raised <= window[1]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_raised_is_cleared_and_payloads_validate(
    scenario: str, results: dict[str, list[EventDraft]]
) -> None:
    detections = results[scenario]
    episodes = episodes_of(detections)
    for d in detections:
        d.typed_payload()
    ids = [d.event_id for d in detections]
    assert len(ids) == len(set(ids)), table(detections)
    for episode in episodes:
        assert episode.cleared is not None, f"{episode} sigue abierta\n{table(detections)}"
        assert len(episode.updated) <= 1, table(detections)


def test_nominal_has_no_detections(results: dict[str, list[EventDraft]]) -> None:
    assert results["nominal"] == [], table(results["nominal"])


@pytest.mark.parametrize("scenario", ["viento", "spoofing", "secuestro", "demo"])
def test_each_label_fires_its_expected_rules_once(
    scenario: str, results: dict[str, list[EventDraft]]
) -> None:
    detections = results[scenario]
    episodes = episodes_of(detections)
    expected_total = 0
    for label in labels_of(scenario):
        for rule in label["expected_rules"]:
            found = [e for e in find(episodes, rule) if in_window(e, label["eval_window"])]
            assert len(found) == 1, f"{label['id']} {rule}: {len(found)} episodios\n" + table(
                detections
            )
            expected_total += 1
    # Ninguna detección fuera de las ventanas de evaluación: todo es esperado.
    assert len(episodes) == expected_total, table(detections)


def test_wind_is_a_single_route_deviation(results: dict[str, list[EventDraft]]) -> None:
    episodes = episodes_of(results["viento"])
    assert [(e.rule, e.source) for e in episodes] == [("ROUTE_DEVIATION", None)]
    assert 95.0 <= episodes[0].raised <= 150.0


def test_spoofing_discrepancy_then_recovery_deviation(
    results: dict[str, list[EventDraft]],
) -> None:
    episodes = episodes_of(results["spoofing"])
    (discrepancy,) = find(episodes, "SOURCE_DISCREPANCY")
    (recovery,) = find(episodes, "ROUTE_DEVIATION")
    # La discrepancia salta durante el engaño; la desviación de ruta, al volver el GPS a la verdad.
    assert 168.0 <= discrepancy.raised <= 222.0, table(results["spoofing"])
    assert recovery.raised >= 222.0 and recovery.raised > discrepancy.raised
    assert len(episodes) == 2


def test_hijack_is_a_route_deviation_that_gets_worse(
    results: dict[str, list[EventDraft]],
) -> None:
    episodes = episodes_of(results["secuestro"])
    assert [(e.rule, e.source) for e in episodes] == [("ROUTE_DEVIATION", None)]
    assert 335.0 <= episodes[0].raised <= 380.0
    assert len(episodes[0].updated) == 1


def test_faults_each_muted_source_fires_its_own_silent_detection(
    results: dict[str, list[EventDraft]],
) -> None:
    detections = results["fallos"]
    episodes = episodes_of(detections)
    silent = find(episodes, "SOURCE_SILENT")
    assert sorted(e.source or "" for e in silent) == ["gps", "radar"], table(detections)
    by_source = {e.source: e for e in silent}
    radar, gps = by_source["radar"], by_source["gps"]
    assert 120.0 <= radar.raised <= 180.0 and radar.cleared == 180.0, table(detections)
    assert 300.0 <= gps.raised <= 312.0 and gps.cleared == 312.0, table(detections)


def test_faults_gps_loss_is_degraded_at_once_and_discrepancy_after(
    results: dict[str, list[EventDraft]],
) -> None:
    detections = results["fallos"]
    episodes = episodes_of(detections)
    (degraded,) = find(episodes, "GPS_DEGRADED")
    assert degraded.source == "gps" and degraded.raised == 245.0, table(detections)
    # El GPS recupera el fix en t=290 y el detector lo da por normal 5 s después.
    assert degraded.cleared == 295.0
    (discrepancy,) = find(episodes, "SOURCE_DISCREPANCY")
    assert 245.0 < discrepancy.raised <= 290.0, table(detections)
    # Al recuperarse, el GPS salta a la posición real: desviación de ruta de recuperación.
    (recovery,) = find(episodes, "ROUTE_DEVIATION")
    assert 290.0 <= recovery.raised <= 350.0, table(detections)
    assert {e.rule for e in episodes} == {
        "SOURCE_SILENT",
        "GPS_DEGRADED",
        "SOURCE_DISCREPANCY",
        "ROUTE_DEVIATION",
    }
    assert len(episodes) == 5


def test_faults_labels_match_the_expected_rules(results: dict[str, list[EventDraft]]) -> None:
    detections = results["fallos"]
    episodes = episodes_of(detections)
    for label in labels_of("fallos"):
        for rule in label["expected_rules"]:
            found = [e for e in find(episodes, rule) if in_window(e, label["eval_window"])]
            if rule in (Rule.SOURCE_SILENT, Rule.GPS_DEGRADED):
                found = [e for e in found if e.source == label["source"]]
            assert len(found) == 1, f"{label['id']} {rule}\n{table(detections)}"


def test_demo_has_exactly_the_three_anomalies(results: dict[str, list[EventDraft]]) -> None:
    episodes = episodes_of(results["demo"])
    summary = [(e.rule, e.source) for e in episodes]
    assert summary == [
        ("ROUTE_DEVIATION", None),  # viento
        ("SOURCE_DISCREPANCY", None),  # spoofing
        ("ROUTE_DEVIATION", None),  # recuperación tras el spoofing
        ("ROUTE_DEVIATION", None),  # secuestro
    ], table(results["demo"])
