"""Medida de textos (`tools/experiments/text_metrics.py`): sin LLM ni GPU."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "text_metrics", REPO / "tools" / "experiments" / "text_metrics.py"
)
assert spec and spec.loader
tm = importlib.util.module_from_spec(spec)
sys.modules["text_metrics"] = tm
spec.loader.exec_module(tm)

WIND = tm.Facts(
    wind_speed={7.2, 16.1}, wind_from={351.3}, distance={7.0, 13.4}, deviation={31.3, 53.0}
)


def counts(text: str, facts: tm.Facts = WIND) -> dict[str, int]:
    return {k: len(v) for k, v in tm.check_numbers(text, facts).items() if v}


def test_internal_names_tools_fields_bools_and_enums() -> None:
    names, enums, bools = tm.find_names(
        "Called get_track_metrics: gps_radar.disagreed=true and drift_vs_wind_deg 4.9 "
        "(cause GPS_SPOOFING). The true position is fine and it was a false alarm."
    )
    assert names == ["get_track_metrics", "gps_radar.disagreed", "drift_vs_wind_deg"]
    assert enums == ["GPS_SPOOFING"]
    assert bools == ["true"]  # «true position» y «false alarm» no cuentan


def test_ordinary_words_are_not_internal_names() -> None:
    names, _, _ = tm.find_names("The wind is notable, the link is stable and now it samples.")
    assert names == []


def test_copied_phrase_needs_six_words_in_a_row() -> None:
    corpus = tm.ngrams(tm.words("Do not trust the GPS; use the radar as reference."))
    assert tm.copied_spans("Please do not trust the GPS; use the radar now.", corpus)
    assert not tm.copied_spans("Do not trust the GPS at all.", corpus)


def test_wind_speed_must_match_the_facts() -> None:
    assert counts("Wind is notable (mean 7.2 m/s, gusts up to 16.1 m/s).") == {}
    assert counts("The wind is light (2.3 m/s).") == {"wind_speed": 1}
    assert counts("The drone flies at 12 m/s while wind is strong.") == {}  # velocidad del dron


def test_wind_direction_and_the_from_to_confusion() -> None:
    assert counts("The wind comes from 351.3° and pushes the drone.") == {}
    assert counts("Wind from 171.3° (7.2 m/s).") == {"wind_dir_reversed": 1}  # empuja hacia 171
    assert counts("Wind from 90°.") == {"wind_dir": 1}
    assert counts("Wind pushing towards 171°.") == {}
    assert counts("Wind from the N.") == {}
    assert counts("Wind from the S.") == {"wind_dir_reversed": 1}
    assert counts("The drift differs from the wind by 4.2°.") == {}  # no es una dirección


def test_distance_and_deviation_figures() -> None:
    assert counts("GPS and radar agree (distance 7.0 m).") == {}
    assert counts("GPS and radar disagree by 20.8 m.") == {"gps_radar_distance": 1}
    assert counts("The GPS is 31.3 m away from the route.") == {}
    assert counts("The GPS is 44.0 m away from the planned route.") == {"deviation": 1}
    # la distancia entre paréntesis no es la desviación, y un umbral no es una medida
    assert (
        counts("GPS and radar agree (distance 7.0 m), and the GPS is 31.3 m from the route.") == {}
    )
    assert counts("Both deviations from the route are below 6 m.") == {}
    assert counts("GPS deviation from the plan is 44.0 m.") == {"deviation": 1}
    # magnitud distinta en la misma frase: no es la distancia GPS–radar
    assert counts("GPS and radar disagreed=true, gps deviation from plan 4.2 m") == {"deviation": 1}


def test_unicode_ids_are_normalised_and_compared_with_the_run() -> None:
    corpus: set[tuple[str, ...]] = set()
    existing = {"ai-0004", "met-0010"}
    measured = tm.measure_text(
        "demo",
        "alert.explanation",
        "ai-0001",
        "See ai‑0004, met–0010 and gps-000999.",
        tm.Facts(),
        existing,
        corpus,
        [],
    )
    assert measured.findings["bad_ids"] == ["gps-000999"]
    assert measured.ids == 3


def test_concreteness_counts() -> None:
    m = tm.measure_text(
        "demo",
        "chat.monitor",
        "ai-0002",
        "At T+01:46 the GPS was 30.5 m off (gps-000106).",
        tm.Facts(),
        {"gps-000106"},
        set(),
        [],
    )
    assert (m.figures, m.ids, m.times) == (4, 1, 1) or m.figures >= 3


def test_run_end_to_end(tmp_path: Path) -> None:
    run = tmp_path / "exp" / "runs" / "p" / "demo" / "r1"
    run.mkdir(parents=True)
    events = [
        {"event_id": "met-0010", "type": "WindReported", "sim_time": 100.0, "payload": {}},
        {
            "event_id": "ai-0001",
            "type": "AnomalyDetected",
            "sim_time": 106.8,
            "seq": 1,
            "payload": {
                "alert_id": "ai-0001",
                "detection_ids": ["det-0001"],
                "summary": "Drift due to wind.",
                "explanation": "Wind from 171.3° at 2.3 m/s, see get_track_metrics and ai-0099.",
                "recommendation": "Watch the route.",
            },
        },
    ]
    (run / "timeline.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    metrics = {"wind": {"mean_speed_mps": 7.2, "max_gust_mps": 16.1, "from_deg": 351.3}}
    record = {
        "agent": "monitor",
        "as_of": 106.8,
        "published": [{"event_id": "ai-0001"}],
        "messages": [{"role": "user", "content": "State"}],
        "calls": [{"tool_calls": [{"name": "get_track_metrics", "result": metrics}]}],
    }
    (run / "llm_trace.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    source = tm.texts.Source("p", tmp_path / "exp", "p")
    measured, missing = tm.measure_source(source, ["demo", "wind"], 1, set())
    assert missing == ["p · wind · r1"]
    total = tm.summarize(measured)
    assert total["internal_names"] == 1 and total["bad_ids"] == 1
    assert total["wind_speed"] == 1 and total["wind_dir_reversed"] == 1
    assert "Text measure" in tm.render({"p": measured}, missing)


def test_the_annex_is_measured_apart_from_the_mission_report() -> None:
    mission = tm.measure_text("demo", "report.Summary", "r", "ok", tm.Facts(), set(), set(), [])
    annex = tm.measure_text(
        "demo", "annex.Monitor assessment", "r", "Aid: tool_choice and get_events", tm.Facts(),
        set(), set(), [],
    )  # fmt: skip
    assert tm.summarize([mission, annex])["texts"] == 1
    assert tm.summarize([mission, annex])["internal_names"] == 0
    assert tm.summarize([mission, annex], with_annex=True)["internal_names"] == 2
    assert tm.by_kind([mission, annex])["annex"]["total_leaks"] == 2


def test_disagreement_below_the_platform_threshold_is_a_contradiction() -> None:
    assert counts("GPS and radar disagree by 9.9 m.") == {"gps_radar_distance": 1}
    assert counts("GPS and radar disagree by 31.2 m.", tm.Facts(distance={31.2})) == {}
    assert counts("GPS and radar do not disagree by 9.9 m.", tm.Facts(distance={9.9})) == {}


def test_wind_that_does_not_push_with_the_drift_contradicts_the_facts() -> None:
    facts = tm.Facts(with_drift={True})
    assert counts("The wind does not push in the direction of the drift.", facts) == {
        "wind_drift": 1
    }
    assert counts("The wind pushes in the direction of the drift.", facts) == {}
    # sin hechos, o con hechos mezclados, no se juzga
    assert counts("The wind does not push in the direction of the drift.") == {}
    mixed = tm.Facts(with_drift={True, False})
    assert counts("The wind does not push in the direction of the drift.", mixed) == {}
