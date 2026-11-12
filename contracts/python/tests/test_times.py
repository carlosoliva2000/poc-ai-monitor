"""Tiempos de las tools (v0.17): segundos o `T+mm:ss`; `last_s`; el código convierte y valida."""

import pytest
from pydantic import ValidationError

from poc_contracts.times import parse_duration, parse_sim_time
from poc_contracts.tools import GetEventsArgs, GetTrackMetricsArgs


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        (222, 222.0),
        (222.5, 222.5),
        ("222", 222.0),
        ("222s", 222.0),
        ("T+03:42", 222.0),
        ("t+03:42", 222.0),
        ("03:42", 222.0),
        ("3:42", 222.0),
        ("T+01:30", 90.0),
        ("T+09:16", 556.0),
        ("T+75:00", 4500.0),
        ("T+1:02:03", 3723.0),
        ("1:02:03", 3723.0),
        (" T+00:00 ", 0.0),
    ],
)
def test_good_times(value, seconds) -> None:
    assert parse_sim_time(value) == seconds


@pytest.mark.parametrize(
    "value",
    ["", "T+", "T+03:4", "T+03:60", "T+1:75:00", "yesterday", "03:42:", "-5", -5, True, [1]],
)
def test_bad_times_say_the_valid_formats(value) -> None:
    with pytest.raises(ValueError, match=r"T\+mm:ss"):
        parse_sim_time(value)


@pytest.mark.parametrize(
    ("value", "seconds"),
    [(60, 60.0), ("60", 60.0), ("90s", 90.0), ("1:30", 90.0), ("1m30s", 90.0), ("2m", 120.0),
     ("1 m 30 s", 90.0), ("1.5s", 1.5)],
)  # fmt: skip
def test_good_durations(value, seconds) -> None:
    assert parse_duration(value) == seconds


@pytest.mark.parametrize("value", ["", "soon", "T+01:30", "0", 0, -3, "1h", True])
def test_bad_durations_say_the_valid_formats(value) -> None:
    with pytest.raises(ValueError, match="1m30s"):
        parse_duration(value)


def test_the_arguments_of_the_tools_convert_the_times() -> None:
    args = GetEventsArgs.model_validate({"source": "gps", "since": "T+01:30", "until": "T+01:50"})
    assert (args.since, args.until) == (90.0, 110.0)
    metrics = GetTrackMetricsArgs.model_validate({"since": "03:42", "until": 240})
    assert (metrics.since, metrics.until) == (222.0, 240.0)
    assert GetEventsArgs.model_validate({"last_s": "1m30s"}).last_s == 90.0


def test_a_bad_time_is_an_error_with_the_formats() -> None:
    with pytest.raises(ValidationError, match=r"(?s)since.*T\+mm:ss"):
        GetEventsArgs.model_validate({"source": "gps", "since": "tomorrow"})


def test_events_without_source_or_all_are_the_same_request() -> None:
    assert GetEventsArgs.model_validate({}).source is None
    assert GetEventsArgs.model_validate({"source": "all"}).source == "all"
    assert "last_n" not in GetEventsArgs.model_validate({"source": "all"}).model_fields_set


def test_last_s_cannot_be_combined_with_since_and_metrics_need_a_window() -> None:
    with pytest.raises(ValidationError, match="last_s or since"):
        GetEventsArgs.model_validate({"source": "gps", "last_s": 60, "since": 10})
    with pytest.raises(ValidationError, match="last_s or since"):
        GetTrackMetricsArgs.model_validate({"last_s": 60, "since": 10, "until": 20})
    with pytest.raises(ValidationError, match="since and until, or last_s"):
        GetTrackMetricsArgs.model_validate({"since": 10})
    assert GetTrackMetricsArgs.model_validate({"last_s": 60}).until is None
