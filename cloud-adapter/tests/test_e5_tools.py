"""Pruebas de las herramientas de E5 (`e5_tables.py`, `e5_style.py`) con datos sintéticos."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools" / "experiments"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"t_{name}", TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"t_{name}"] = module
    spec.loader.exec_module(module)
    return module


tables = load("e5_tables")
style = load("e5_style")


def text(kind, body, ref="ai-0001", scenario="demo", figures=0, ids=0, times=0, findings=None):
    return SimpleNamespace(
        kind=kind, text=body, ref=ref, scenario=scenario, chars=len(body),
        figures=figures, ids=ids, times=times, findings=findings or {},
    )  # fmt: skip


# --- tablas ----------------------------------------------------------------------------------


def test_cell_shows_mean_and_range_only_when_they_differ():
    assert tables.cell([1.0, 1.0, 1.0], 1) == "1.0"
    assert tables.cell([1.0, 2.0, 3.0], 1) == "2.0 (1.0–3.0)"
    assert tables.cell([2.0], 1) == "2.0"
    assert tables.cell([], 1) == "–"


def test_count_accepts_numbers_and_lists():
    assert tables.count(3) == 3
    assert tables.count(["a", "b"]) == 2
    assert tables.count([]) == 0


def test_percentile_of_a_short_list():
    assert tables.pct([], 0.5) == 0.0
    assert tables.pct([1, 2, 3, 4], 0.95) == 4


def test_render_has_one_column_per_series_and_the_series_costs():
    values = {key: 1.0 for key, _, _ in tables.METRICS}
    runs = {
        "A": [tables.RunMetrics("demo", 1, {**values, "cost_usd": 0.5})],
        "B": [tables.RunMetrics("demo", 1, {**values, "cost_usd": 0.25})],
    }
    out = tables.render(runs)
    assert "| | A | B |" in out
    assert "| A | 1 | 0.5000 |" in out and "| B | 1 | 0.2500 |" in out


# --- estilo ----------------------------------------------------------------------------------


def test_summary_limit_and_lengths():
    items = [
        text("alert.summary", "x" * 170),
        text("alert.summary", "short one.", ref="ai-0002"),
        text("alert.explanation", "One. Two. Three."),
    ]
    m = style.metrics_of(items)
    assert m["summary_over_limit"] == 1 and m["summary_max_chars"] == 170
    assert m["alert_explanation_sentences"] == 3


def test_recommendation_points_with_action_and_reason():
    rec = (
        "1. Switch to the radar because the GPS jumped 70 m.\n"
        "2. Keep calm.\n"
        "3. Check the link to rule out a takeover."
    )
    m = style.metrics_of([text("alert.recommendation", rec)])
    assert m["rec_points"] == 3
    assert m["rec_with_action"] == pytest.approx(2 / 3)
    assert m["rec_with_why"] == pytest.approx(2 / 3)
    assert m["rec_with_action_and_why"] == pytest.approx(2 / 3)


def test_hedges_and_unsupported_figures_and_leaks():
    items = [
        text(
            "alert.explanation",
            "The wind may explain it. The drone is 30 m off route.",
            figures=1,
            findings={"unsupported_figures": ["30 m"], "enum_names": ["WIND"]},
        )
    ]
    m = style.metrics_of(items)
    assert m["hedged_share"] == 0.5 and m["hedged_without_data_share"] == 0.5
    assert m["unsupported_figures"] == 1 and m["unsupported_share"] == 1
    assert m["opaque_sentences_share"] == 0.5


def test_summary_repeated_in_the_explanation():
    summary = text("alert.summary", "Drone drifted south because of strong northerly wind.")
    same = text("alert.explanation", "Drone drifted south because of strong northerly wind today.")
    other = text("alert.explanation", "GPS and radar agree about the position.")
    assert style.metrics_of([summary, same])["summary_repeated_in_explanation"] == 1.0
    assert style.metrics_of([summary, other])["summary_repeated_in_explanation"] == 0.0


def test_empty_input_gives_no_value_not_a_crash():
    m = style.metrics_of([])
    assert m["texts"] == 0 and m["alert_summary_chars"] is None
    assert m["rec_with_action"] is None
