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


# --- Recomendaciones genéricas y sin acción (Fase 14.2) ----------------------------------------


def style(text: str) -> dict[str, int]:
    return {k: len(v) for k, v in tm.recommendation_style(text).items()}


def test_generic_formulas_from_the_review_are_counted() -> None:
    for text in (
        "Verify the authenticity of the GPS signals and ensure secure communication channels.",
        "Ensure no unauthorized access to the GPS system.",
        "Ensure no unauthorised access to the radar.",
        "Verify the integrity of the wind sensor.",
        "Verify the GPS signal integrity and the drone position.",
        "Verify if the signal is spoofed and take appropriate action if necessary.",
        "Follow standard security protocols.",
    ):
        assert style(text)["generic_recommendation"] == 1, text


def test_a_concrete_recommendation_is_neither_generic_nor_without_action() -> None:
    text = (
        "Use the radar as the position reference and tell the person in charge: the GPS is lying."
    )
    assert style(text) == {"generic_recommendation": 0, "no_action_recommendation": 0}
    for text in (
        "No intervention: keep watching that the deviation does not grow while the drone corrects.",
        "Check the command link and take back control of the drone if the controller changed.",
        "Return the drone to base on the radar position until the GPS is stable.",
    ):
        assert style(text) == {"generic_recommendation": 0, "no_action_recommendation": 0}, text


def test_a_recommendation_without_a_concrete_verb_and_object_has_no_action() -> None:
    assert style("Investigate GPS spoofing immediately.")["no_action_recommendation"] == 1
    assert style("Review the situation and consider the options.")["no_action_recommendation"] == 1
    # un verbo concreto sin objeto del dron, el radar, el enlace o la ruta
    assert style("Report it as soon as possible.")["no_action_recommendation"] == 1
    # una fórmula vacía suele ser también «sin acción»
    both = style("Ensure no unauthorized access to the GPS system.")
    assert both == {"generic_recommendation": 1, "no_action_recommendation": 1}


def test_each_numbered_point_of_the_report_is_judged_on_its_own() -> None:
    text = (
        "1. Switch to the radar as the position reference of the drone.\n"
        "2. Ensure secure communication channels.\n"
        "3. Check the link before the next flight."
    )
    assert tm.recommendation_points(text) == [
        "Switch to the radar as the position reference of the drone.",
        "Ensure secure communication channels.",
        "Check the link before the next flight.",
    ]
    assert style(text) == {"generic_recommendation": 1, "no_action_recommendation": 1}
    assert tm.recommendation_points("A single sentence.") == ["A single sentence."]


def test_style_counters_only_apply_to_recommendations_and_stay_out_of_leaks_and_errors() -> None:
    facts = tm.Facts()
    rec = tm.measure_text(
        "demo", "alert.recommendation", "ai-1", "Ensure secure communication channels.",
        facts, set(), set(), [],
    )  # fmt: skip
    other = tm.measure_text(
        "demo", "alert.summary", "ai-1", "Ensure secure communication channels.",
        facts, set(), set(), [],
    )  # fmt: skip
    assert rec.counts()["generic_recommendation"] == 1
    assert "generic_recommendation" not in other.counts()
    summary = tm.summarize([rec, other])
    assert summary["generic_recommendation"] == 1 and summary["no_action_recommendation"] == 1
    assert summary["total_leaks"] == 0 and summary["total_errors"] == 0
    report = tm.measure_text(
        "demo", "report.Recommendations", "report", "1. Use the radar as reference.\\n2. Ensure no "
        "unauthorized access to the GPS.", facts, set(), set(), [],
    )  # fmt: skip
    assert report.counts()["generic_recommendation"] == 1


# --- «Ahora» frente a la ventana y fuentes ajenas en el cierre (Fase 14.2) -----------------------

# ventana: GPS–radar mean 5,8 y max 12,4; viento medio 7,2 y racha 16,1. Ahora: 9,9 m y 2,3 m/s.
MIX = tm.Facts(
    window_distance={5.8, 12.4}, window_deviation={30.5, 53.0}, window_wind_speed={7.2, 16.1},
    now_distance={9.9}, now_deviation={4.1}, now_wind_speed={2.3},
)  # fmt: skip


def mix(text: str) -> int:
    return len(tm.now_window_mix(text, MIX))


def test_a_window_figure_presented_as_the_present_is_a_mix() -> None:
    assert mix("GPS and radar currently show a distance of 12.4 m.") == 1
    assert mix("The wind is now 7.2 m/s from the north.") == 1
    assert mix("The deviation is now 53.0 m from the route.") == 1


def test_a_now_figure_told_as_the_past_is_a_mix() -> None:
    assert mix("The distance between GPS and radar was 9.9 m during the episode.") == 1
    assert mix("The deviation from the route reached 4.1 m earlier.") == 1


def test_disagree_by_a_figure_that_only_exists_now_is_a_mix() -> None:
    assert mix("GPS and radar disagree by 9.9 m.") == 1  # el caso de la recuperación (Revisión §6)
    assert mix("GPS and radar disagree by 31.2 m.") == 0  # una cifra que no es de `now`
    assert mix("GPS and radar do not disagree by 9.9 m.") == 0  # negación


def test_the_unit_may_be_written_meters_or_metres() -> None:
    """El 32B escribe «9.9 meters»: con la unidad solo en «m» el contador no veía su frase (Fase
    14.3). La misma frase con «m» y con «meters» se cuenta igual, y «m/s» no es una longitud."""
    phrase = "GPS and radar disagree by 9.9 {u}, suggesting the GPS position is unreliable."
    for unit in ("m", "meters", "metres", "meter"):
        assert mix(phrase.format(u=unit)) == 1, unit
    assert mix("The deviation is now 53.0 meters from the route.") == 1
    assert mix("The GPS and radar now agree (distance 9.9 meters).") == 0
    assert mix("The wind is now 2.3 m/s, calm.") == 0


def test_disagree_followed_by_the_distance_in_brackets_is_also_a_mix() -> None:
    """«GPS and radar disagree (distance 5.1 m)» es el mismo error que «disagree by 5.1 m»."""
    both = tm.Facts(window_distance={60.0}, now_distance={5.1})
    text = "The GPS has jumped 90 m. GPS and radar disagree (distance 5.1 m)."
    assert len(tm.now_window_mix(text, both)) == 1
    assert tm.now_window_mix("GPS and radar agree (distance 5.1 m).", both) == []


def test_figures_written_in_meters_are_checked_like_those_in_m() -> None:
    """Las cifras en «meters» entran también en los errores de cifra, no solo en la mezcla."""
    facts = tm.Facts(distance={9.9}, deviation={73.9})
    wrong = tm.check_numbers(
        "GPS and radar distance of 31.0 meters; the drone is 12.0 meters off the planned route.",
        facts,
    )
    assert len(wrong["gps_radar_distance"]) == 1 and len(wrong["deviation"]) == 1
    right = tm.check_numbers(
        "GPS and radar distance of 9.9 meters; the drone is 73.9 meters off the planned route.",
        facts,
    )
    assert not right["gps_radar_distance"] and not right["deviation"]


def test_consistent_statements_are_not_a_mix() -> None:
    for text in (
        "The GPS and radar now agree (distance 9.9 m).",  # presente con la cifra de now
        # pasado con la ventana
        "The distance between GPS and radar was up to 12.4 m during the window.",
        "The wind averaged 7.2 m/s during the episode and is now 2.3 m/s.",
        "The drone is now 4.1 m from the route.",
        "No figures here, only now.",
    ):
        assert mix(text) == 0, text


def test_a_figure_in_both_now_and_window_is_not_ambiguous_enough_to_count() -> None:
    both = tm.Facts(window_distance={9.9}, now_distance={9.9})
    assert tm.now_window_mix("GPS and radar disagree by 9.9 m.", both) == []


WIND_CLOSE = "The wind is from NW (301°), pushing SE, but it is not notable or contributing."


def test_wind_in_the_close_of_a_hijack_a_spoofing_or_a_sensor_fault_is_foreign() -> None:
    for cause in ("HIJACK", "GPS_SPOOFING", "SENSOR_FAULT"):
        assert len(tm.foreign_source_in_close(WIND_CLOSE, cause, set())) == 1, cause
    # también para decir que no importa
    assert len(tm.foreign_source_in_close("There is no wind to speak of.", "HIJACK", set())) == 1


def test_wind_is_not_foreign_where_it_belongs_to_the_cause() -> None:
    assert tm.foreign_source_in_close(WIND_CLOSE, "WIND", set()) == []
    assert tm.foreign_source_in_close(WIND_CLOSE, "GPS_JAMMING", set()) == []  # deriva a estima
    # un fallo de la meteo sí tiene que ver con el viento
    assert tm.foreign_source_in_close(WIND_CLOSE, "SENSOR_FAULT", {"meteo"}) == []
    assert tm.foreign_source_in_close("GPS and radar agree.", "HIJACK", set()) == []
    assert tm.foreign_source_in_close(WIND_CLOSE, None, set()) == []


def test_the_new_counters_apply_to_alerts_and_closes_and_stay_out_of_leaks_and_errors() -> None:
    text = "GPS and radar disagree by 9.9 m."
    alert = tm.measure_text("demo", "alert.summary", "ai-1", text, MIX, set(), set(), [])
    close = tm.measure_text(
        "demo", "end.reason", "ai-1", WIND_CLOSE, MIX, set(), set(), [], "HIJACK", set()
    )
    chat = tm.measure_text("demo", "chat.monitor", "ai-2", text, MIX, set(), set(), [])
    assert alert.counts()["now_window_mix"] == 1 and "foreign_source_in_close" not in alert.counts()
    assert close.counts()["foreign_source_in_close"] == 1
    assert "now_window_mix" not in chat.counts()  # los chats no se miden con esta regla
    summary = tm.summarize([alert, close])
    assert summary["now_window_mix"] == 1 and summary["foreign_source_in_close"] == 1
    assert summary["total_leaks"] == 0


# --- Informe de misión: tipo de cada anomalía y jerga del monitor (Fase 14.2) ---------------------


def test_the_summary_must_name_the_type_of_every_anomaly() -> None:
    chains = [{"WIND"}, {"GPS_SPOOFING"}, {"HIJACK"}]
    named = "A wind drift, a GPS spoofing and a hijacking were detected; the hijacking was worst."
    assert tm.summary_missing_type(named, chains) == []
    # el texto de la Revisión §6: no nombra ningún tipo
    vague = "Three anomalies were encountered, the most severe being the potential event (A3)."
    assert tm.summary_missing_type(vague, chains) == ["WIND", "GPS_SPOOFING", "HIJACK"]
    partial = "A wind drift and a hijacking occurred."
    assert tm.summary_missing_type(partial, chains) == ["GPS_SPOOFING"]


def test_a_chain_is_named_by_any_of_its_causes() -> None:
    chains = [{"SENSOR_FAULT", "GPS_JAMMING"}]
    assert tm.summary_missing_type("The GPS was lost for 45 s.", chains) == []
    assert tm.summary_missing_type("The radar went silent for a minute.", chains) == []
    assert tm.summary_missing_type("Something happened.", chains) == ["GPS_JAMMING/SENSOR_FAULT"]
    assert tm.summary_missing_type("Whatever.", []) == []


def test_monitor_talk_is_counted_by_point_in_the_mission_recommendations() -> None:
    text = (
        "1. Use the radar as the reference of the drone until the GPS is stable.\n"
        "2. Reduce the wall-clock delay of the monitor and review the guardrail rejections.\n"
        "3. Check the link before the next flight."
    )
    found = tm.monitor_talk(text)
    assert len(found) == 1 and "wall-clock" in found[0]
    assert tm.monitor_talk("Switch to the radar and warn the operator.") == []
    # la latencia del enlace es del dron, no del sistema de monitorización
    assert tm.monitor_talk("Check the link: its latency and RSSI changed.") == []


def test_report_counters_apply_to_their_sections_only() -> None:
    facts = tm.Facts()
    chains = [{"WIND"}]
    summary = tm.measure_text(
        "demo", "report.Summary", "report", "Something happened.", facts, set(), set(), [],
        chains=chains,
    )  # fmt: skip
    rec = tm.measure_text(
        "demo", "report.Recommendations", "report", "1. Review the guardrail rejections.", facts,
        set(), set(), [],
    )  # fmt: skip
    other = tm.measure_text(
        "demo", "report.What was seen", "A1", "Something happened.", facts, set(), set(), [],
        chains=chains,
    )  # fmt: skip
    assert summary.counts()["summary_missing_type"] == 1
    assert rec.counts()["monitor_talk_in_recommendations"] == 1
    assert "summary_missing_type" not in other.counts()
    totals = tm.summarize([summary, rec])
    assert totals["summary_missing_type"] == 1 and totals["monitor_talk_in_recommendations"] == 1
    assert totals["total_leaks"] == 0 and totals["total_errors"] == 0


# --- GPS y radar «coinciden» sin fix (Fase 14.3) ---


def test_agreement_is_claimed_while_the_gps_has_no_fix() -> None:
    nofix = "The GPS and radar positions agree now, but the GPS is degraded."
    assert tm.agree_without_fix(nofix, True) == [nofix]
    assert tm.agree_without_fix("GPS and radar now agree (distance 9.9 m).", True) != []
    assert tm.agree_without_fix(nofix, False) == []  # con fix, es una comparación válida


def test_agreement_with_a_negation_or_in_the_past_is_not_claimed() -> None:
    for text in (
        "GPS and radar disagree by 26.2 m.",
        "GPS and radar do not agree.",
        "GPS and radar agreed before the loss.",
        "GPS and radar no longer agree.",
        "The GPS has no fix and its position is only an estimate.",
    ):
        assert tm.agree_without_fix(text, True) == [], text


def test_the_fix_is_read_from_the_last_gps_position_up_to_the_invocation() -> None:
    def gps(t: float, fix: str) -> dict:
        return {
            "type": "PositionUpdated",
            "source": "d1-gps",
            "sim_time": t,
            "payload": {"fix": fix},
        }

    events = [gps(244.0, "3d"), gps(245.0, "none"), gps(290.0, "3d")]
    assert tm.gps_without_fix_at(events, 245.8) is True
    assert tm.gps_without_fix_at(events, 244.5) is False
    assert tm.gps_without_fix_at(events, 290.4) is False
    assert tm.gps_without_fix_at([], 10.0) is False


# --- El cierre dice qué volvió a la normalidad de la causa (Fase 14.3) ---

GPS_ONLY_CLOSE = (
    "The deviation from the route has decreased to 3.1 m (GPS) and 4.7 m (radar), and GPS and "
    "radar now agree. The situation has returned to normal."
)


def test_a_hijack_closed_with_gps_and_radar_but_not_the_link_is_flagged() -> None:
    assert tm.close_without_cause_source(GPS_ONLY_CLOSE, "HIJACK") == [GPS_ONLY_CLOSE]
    link = "The command link is normal again: GCS-1 is in control (latency 52 ms, -64 dBm)."
    assert tm.close_without_cause_source(link, "HIJACK") == []
    controller = "The controller is the mission's again and the drone is back on the route."
    assert tm.close_without_cause_source(controller, "HIJACK") == []


def test_a_gps_cause_needs_gps_and_radar_in_the_close() -> None:
    for cause in ("GPS_SPOOFING", "GPS_JAMMING"):
        assert tm.close_without_cause_source(GPS_ONLY_CLOSE, cause) == []
        wind = "The wind is from NW (336°), pushing SE, at 2.3 m/s."
        assert tm.close_without_cause_source(wind, cause) == [wind]
        only_gps = "The GPS is back, 2.9 m from the route."
        assert tm.close_without_cause_source(only_gps, cause) == [only_gps]


def test_a_sensor_fault_needs_the_sensor_to_report_again() -> None:
    assert (
        tm.close_without_cause_source("The GPS reports again (gps-000300).", "SENSOR_FAULT") == []
    )
    assert tm.close_without_cause_source("The radar is available again.", "SENSOR_FAULT") == []
    wind = "The wind is from NW (298°), pushing SE."
    assert tm.close_without_cause_source(wind, "SENSOR_FAULT") == [wind]


def test_wind_and_unknown_closes_are_not_measured_and_only_closures_count() -> None:
    for cause in ("WIND", "UNKNOWN"):
        assert tm.close_without_cause_source("Back to normal.", cause) == []
    kwargs = {
        "scenario": "demo", "ref": "ai-0001", "facts": tm.Facts(), "existing_ids": set(),
        "corpus": set(), "prose": [], "cause": "HIJACK", "sources": set(),
    }  # fmt: skip
    closed = tm.measure_text(kind="end.reason", text=GPS_ONLY_CLOSE, is_close=True, **kwargs)
    ack = tm.measure_text(kind="end.reason", text=GPS_ONLY_CLOSE, is_close=False, **kwargs)
    assert closed.counts()["close_without_cause_source"] == 1
    assert "close_without_cause_source" not in ack.counts()  # un reconocimiento no es un cierre


# --- Cifras sin respaldo en las recomendaciones del informe (Fase 14.3) ---

KNOWN = tm.prompt_numbers(
    "Detector det-0010 ROUTE_DEVIATION at T+03:42 (value 73.9 m, threshold 30.0 m); GPS jump "
    "67.9 m; wind 2.3 m/s; GPS and radar distance 9.9 m; controller GCS-1, latency 51.8 ms."
)


def test_prompt_numbers_skip_ids_and_times() -> None:
    assert {73.9, 30.0, 67.9, 2.3, 9.9, 51.8} <= KNOWN
    assert 10.0 not in KNOWN and 3.0 not in KNOWN and 42.0 not in KNOWN  # det-0010 y T+03:42


def test_invented_thresholds_and_limits_are_unsupported_figures() -> None:
    for text in (
        "Review the wind data if wind exceeds 7 m/s.",
        "Check that GPS and radar converge within 10 m.",
        "Hold position for 30 s before resuming.",  # 30 s no es 30.0 m: otra unidad, pero 30.0 sí
        "Keep the link above 80%.",
    ):
        flagged = tm.unsupported_figures(text, KNOWN)
        # «30 s» coincide con el 30.0 de la cifra recibida: se cuenta por el valor, no por la unidad
        assert len(flagged) == (0 if "30 s" in text else 1), text


def test_figures_that_are_in_the_data_are_supported() -> None:
    for text in (
        "The GPS jumped 67.9 m: check the radar position, 73.9 m from the route.",
        "Verify the link, latency reached 51.8 ms and the wind was 2.3 m/s.",
        "The distance was about 10 m when it recovered.",  # redondea 9.9
        "At T+03:42 the drone was off route.",  # una hora no es una cifra con unidad
        "Verify the command link of ai-0010.",
    ):
        assert tm.unsupported_figures(text, KNOWN) == [], text
    assert tm.unsupported_figures("The distance was 10 m.", KNOWN) == ["10 m"]  # sin «about»


# --- La hora de la recuperación del informe no es la del cierre (Fase 14.3) ---

RECOVERIES = [(222.0, 234.0)]  # entró en recuperación a T+03:42 y se cerró a T+03:54


def test_the_closing_time_given_as_the_recovery_time_is_flagged() -> None:
    wrong = "GPS spoofing at T+03:12, which entered recovery by T+03:54."
    assert tm.recovery_time_mismatch(wrong, RECOVERIES) == ["recovery by T+03:54"]
    ending = "A GPS loss ending in recovery at T+03:54, resolved later."
    assert len(tm.recovery_time_mismatch(ending, RECOVERIES)) == 1


def test_the_right_times_are_not_flagged() -> None:
    for text in (
        "It entered recovery at T+03:42 and closed at T+03:54.",
        "GPS spoofing at T+03:12, which recovered at T+03:42; closed at T+03:54.",
        "No recovery to tell.",
        "It was closed at T+03:54.",  # sin la palabra recovery
    ):
        assert tm.recovery_time_mismatch(text, RECOVERIES) == [], text
    assert tm.recovery_time_mismatch("recovery at T+03:54", []) == []  # nada que contrastar
    # si entrada y cierre coinciden, no hay confusión posible
    assert tm.recovery_time_mismatch("recovery at T+03:54", [(234.0, 234.0)]) == []


def test_the_jump_the_module_computed_is_a_valid_figure() -> None:
    """Fase 14.4: el rechazo del guardrail le dice al modelo el salto que calculó el módulo, y
    escribirlo no es un error de cifra aunque la ventana del modelo no lo trajera."""
    record = {"calls": [], "messages": [], "recovery_jump": {"gps_max_step_m": 67.9, "jump": True}}
    assert 67.9 in tm.record_facts(record, with_prompts=False).deviation
    assert not tm.record_facts({"calls": [], "messages": []}, with_prompts=False).deviation


# --- «El radar no está» con el radar informando (Fase 14.4) ---


def test_a_text_that_says_the_radar_is_down_while_it_reports_is_flagged() -> None:
    for text in (
        "The radar is unavailable, so we cannot confirm the actual position of the drone.",
        "There is no radar data to confirm where the drone is.",
        "The radar is not reporting.",
        "Without radar confirmation the position cannot be checked.",
        "Radar data is missing for this window.",
    ):
        assert tm.false_radar_unavailable(text, True) == [text], text
        assert tm.false_radar_unavailable(text, False) == [], text  # radar callado de verdad


def test_radar_sentences_that_are_true_or_in_the_past_are_not_flagged() -> None:
    for text in (
        "The radar stopped reporting for 7 s.",
        "The radar was silent for 7 s and is reporting again.",
        "The radar is the reference for the real position of the drone.",
        "GPS and radar disagree by 26.2 m.",
        "The radar places the drone 8.4 m from the route.",
    ):
        assert tm.false_radar_unavailable(text, True) == [], text


def test_the_radar_reporting_is_read_from_the_last_track_up_to_the_invocation() -> None:
    def track(t: float) -> dict:
        return {"type": "TrackUpdated", "source": "radar-1", "sim_time": t, "payload": {}}

    events = [track(242.0), track(244.0), track(280.0)]
    assert tm.radar_reporting_at(events, 245.8) is True
    assert tm.radar_reporting_at(events, 250.0) is True  # 6 s: aún no es silencio
    assert tm.radar_reporting_at(events, 250.5) is False  # 6,5 s: ya es silencio
    assert tm.radar_reporting_at(events, 251.0) is False
    assert tm.radar_reporting_at(events, 241.0) is False  # aún no había pistas
    assert tm.radar_reporting_at([], 10.0) is False
