"""Monitor de situación con las tablas aprendidas congeladas (E7b): lo congelado se ejecuta, el
catálogo de incidentes, el seguidor y la política de la causa dudosa."""

from pathlib import Path

import pytest

from ai_module.ids import IdAllocator
from ai_module.situation import freeze
from ai_module.situation.catalog import View, candidates
from ai_module.situation.engine import IncidentEngine
from ai_module.situation.export_tables import build_frozen
from ai_module.situation.facets import HANDWRITTEN, LEARNED, LearnedFacets
from ai_module.situation.monitor import SituationMonitor
from ai_module.situation.policy import load_policy
from ai_module.situation.replay import replay
from poc_contracts.enums import EventType, IncidentKind
from poc_contracts.payloads import PAYLOAD_MODELS

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
POLICY = load_policy()
K = POLICY.defaults.k_open
K_WIND = POLICY.k_open(IncidentKind.WIND)
K_LINK_Q = POLICY.k_open(IncidentKind.LINK_DEGRADED)
CALM = {
    "gps.availability": "normal", "gps.quality": "good", "gps.integrity": "reliable",
    "radar.availability": "normal", "meteo.availability": "normal",
    "battery.availability": "normal", "battery.level": "normal", "battery.endurance": "sufficient",
    "link.availability": "connected", "link.quality": "good", "environment.wind": "calm",
    "drone.mode": "mission", "drone.situation": "on_route", "drone.cause": "n/a",
}  # fmt: skip


def updates(scenario: str, tables: str = LEARNED) -> list[dict]:
    out = []
    for _, p in replay(RUNS / scenario / "events.jsonl", tables):
        PAYLOAD_MODELS[EventType.INCIDENT_UPDATED].model_validate(p)  # cumple el contrato
        out.append(p)
    return out


def lifecycle(scenario: str, tables: str = LEARNED) -> list[tuple[str, str, str]]:
    """`(incidente, cambio, tipo)` de las aperturas, cambios de nombre, recuperaciones y cierres."""
    keep = ("opened", "renamed", "closed")
    return [
        (p["incident_id"], p["change"], p["kind"])
        for p in updates(scenario, tables)
        if p["change"] in keep or (p["change"] == "state" and p["state"] == "recovering")
    ]


# --- lo congelado se ejecuta ---------------------------------------------------------------------


def test_the_monitor_checks_the_freeze_and_refuses_to_start_if_a_frozen_file_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert freeze.changed_files() == []
    LearnedFacets()  # arranca
    monkeypatch.setattr(freeze, "changed_files", lambda: ["ai-module-py/.../tables_learned.yaml"])
    with pytest.raises(freeze.FreezeError, match="tables_learned"):
        LearnedFacets()
    SituationMonitor(tables=HANDWRITTEN)  # la alternativa a mano no está congelada


def test_the_situation_rule_runs_with_the_margin_of_the_freeze_file() -> None:
    """El fichero congelado (`situation_rule.py`) dice 1,0 y la evaluación de la E7b usó 0,5."""
    assert LearnedFacets().margin_k == 0.5 == freeze.margin_k()


def test_the_evidence_of_a_learned_row_is_readable_and_every_row_is_in_the_web_rules() -> None:
    frozen = build_frozen()["facets"]
    for scenario in ("demo", "faults", "jamming", "endurance"):
        for update in updates(scenario):
            for item in update["evidence"]:
                assert item["rule_id"] in {r["id"] for r in frozen[item["facet"]]["rules"]}
                for c in item["conditions"]:
                    assert c["op"] in (">=", "<=", ">", "<", "==", "!=")


# --- el catálogo sobre los escenarios ------------------------------------------------------------


def test_demo_gives_the_three_incidents_each_with_one_recovery() -> None:
    assert lifecycle("demo") == [
        ("inc-0001", "opened", "WIND"), ("inc-0001", "state", "WIND"),
        ("inc-0001", "closed", "WIND"),
        ("inc-0002", "opened", "GPS_SPOOFING"), ("inc-0002", "state", "GPS_SPOOFING"),
        ("inc-0002", "closed", "GPS_SPOOFING"),
        ("inc-0003", "opened", "LINK_LOSS"), ("inc-0003", "renamed", "HIJACK"),
        ("inc-0003", "state", "HIJACK"), ("inc-0003", "closed", "HIJACK"),
    ]  # fmt: skip
    # sin el viento falso al acabar el engaño ni la batería «callada» al volver el enlace
    assert {p["kind"] for p in updates("demo")} == {"WIND", "GPS_SPOOFING", "LINK_LOSS", "HIJACK"}


def test_demo_opens_within_a_few_seconds_of_the_hand_tables() -> None:
    def opens(tables: str) -> dict[str, float]:
        out = {}
        for t, p in replay(RUNS / "demo" / "events.jsonl", tables):
            if p["change"] == "opened":
                out[p["kind"]] = t
        return out

    learned, hand = opens(LEARNED), opens(HANDWRITTEN)
    assert learned.keys() == hand.keys() == {"WIND", "GPS_SPOOFING", "LINK_LOSS"}
    assert all(abs(learned[k] - hand[k]) <= 6 for k in learned)


def test_the_hand_tables_cannot_see_a_hijack_without_the_cause_facets() -> None:
    kinds = {p["kind"] for p in updates("demo", HANDWRITTEN)}
    assert "HIJACK" not in kinds and "LINK_LOSS" in kinds


@pytest.mark.parametrize("scenario", ["nominal"])
def test_a_clean_flight_gives_no_incident(scenario: str) -> None:
    assert updates(scenario) == []


def test_each_scenario_gives_the_incident_that_it_injects() -> None:
    seen = {s: {p["kind"] for p in updates(s)} for s in ("wind", "spoofing", "hijack", "faults")}
    assert seen["wind"] == {"WIND"}
    assert seen["spoofing"] == {"GPS_SPOOFING"}
    assert seen["hijack"] == {"LINK_LOSS", "HIJACK"}
    assert {"SOURCE_SILENT", "GPS_NO_FIX", "DEAD_RECKONING"} <= seen["faults"]


def test_jamming_is_one_gps_incident_that_changes_its_name() -> None:
    gps = [p for p in updates("jamming") if p["kind"] in ("GPS_DEGRADED", "GPS_NO_FIX")]
    assert {p["incident_id"] for p in gps} == {"inc-0001"}
    assert [p["kind"] for p in gps if p["change"] in ("opened", "renamed")] == [
        "GPS_DEGRADED", "GPS_NO_FIX",
    ]  # fmt: skip


def test_a_failsafe_nothing_explains_is_its_own_incident_and_a_silent_source_has_its_subject() -> (
    None
):
    failsafe = next(p for p in updates("endurance") if p["kind"] == "FAILSAFE")
    assert failsafe["subject"] == "failsafe_return" and "returning home" in failsafe["name"]
    silent = next(p for p in updates("demo-meteo") if p["kind"] == "SOURCE_SILENT")
    assert (silent["subject"], silent["name"]) == ("meteo", "Weather station silent")
    assert silent["evidence"][0]["facet"] == "meteo.availability"


def test_a_silent_battery_is_not_closed_by_the_link_loss_that_hides_its_telemetry() -> None:
    battery = [p for p in updates("demo-battery") if p["incident_id"] == "inc-0001"]
    assert [p["change"] for p in battery] == ["opened"]  # abierto hasta el final, sin parpadeo


def test_the_hijack_card_follows_the_drone_while_it_flies_away() -> None:
    """La tarjeta enseña la distancia de ahora (una revisión cuando se duplica, no cada segundo)."""
    cards = [p for p in updates("demo") if p["kind"] == "HIJACK" and p["state"] == "open"]

    def distance(p: dict) -> float:
        situation = next(e for e in p["evidence"] if e["facet"] == "drone.situation")
        return next(c["value"] for c in situation["conditions"] if c["feature"] == "dev_lo_m")

    distances = [distance(p) for p in cards]
    assert distances[-1] > 250 and distances[-1] >= 2 * distances[0]  # 141 m → 298 m
    assert len(cards) <= 3


def test_spoofing_is_seen_before_the_drone_leaves_the_route() -> None:
    opened = next(p for p in updates("demo") if p["kind"] == "GPS_SPOOFING")
    situation = next(e for e in opened["evidence"] if e["facet"] == "drone.situation")
    assert situation["state"] == "on_route"
    integrity = next(e for e in opened["evidence"] if e["facet"] == "gps.integrity")
    assert (integrity["state"], integrity["rule_id"]) == ("spoofed", "GI-01")


# --- la política de la causa dudosa ------------------------------------------------------------


def view(
    conf: dict[str, str] | None = None, families: frozenset[str] = frozenset(), **states: str
) -> View:
    return View(
        {**CALM, **{k.replace("__", "."): v for k, v in states.items()}}, conf or {}, families
    )


def kinds(v: View) -> dict[str, str]:
    return {family: c.kind.value for family, c in candidates(v, POLICY).items()}


def test_a_possible_cause_is_undetermined_not_a_diagnosis() -> None:
    v = view({"drone.cause": "possible"}, drone__situation="deviated", drone__cause="wind")
    assert kinds(v) == {"undetermined": "UNDETERMINED"}


def test_a_probable_or_confirmed_cause_names_the_incident() -> None:
    v = view({"drone.cause": "probable"}, drone__situation="deviated", drone__cause="wind")
    assert kinds(v) == {"wind": "WIND"}


def test_a_hijack_needs_both_tables_confirmed_and_a_probable_one_stays_a_link_loss() -> None:
    lost = {
        "link__availability": "lost", "drone__situation": "deviated",
        "drone__cause": "foreign_control", "drone__mode": "foreign_control",
    }  # fmt: skip
    both = {"drone.cause": "confirmed", "drone.mode": "confirmed"}
    assert kinds(view(both, **lost)) == {"control": "HIJACK"}
    assert kinds(view({**both, "drone.mode": "probable"}, **lost)) == {"control": "LINK_LOSS"}
    assert kinds(view({**both, "drone.cause": "possible"}, **lost)) == {"control": "LINK_LOSS"}
    only_cause = {k: v for k, v in lost.items() if k != "drone__mode"}  # una sola tabla no basta
    assert kinds(view(both, **only_cause)) == {"control": "LINK_LOSS"}


def test_a_possible_row_opens_nothing_except_a_silent_source() -> None:
    conf = {"gps.integrity": "possible", "battery.availability": "possible"}
    v = view(conf, gps__integrity="spoofed", battery__availability="no_data")
    assert kinds(v) == {"source:battery": "SOURCE_SILENT"}


def test_a_deviation_that_an_open_incident_explains_is_not_undetermined() -> None:
    v = view({"drone.cause": "possible"}, frozenset({"control"}), drone__situation="deviated")
    assert kinds(v) == {}


def test_the_false_wind_after_a_spoofing_does_not_open_a_wind_incident() -> None:
    v = view(frozenset(), frozenset({"spoofing"}), environment__wind="beyond_limit")
    assert kinds(v) == {}


# --- el seguidor ---------------------------------------------------------------------------------


def run(
    steps: list[tuple[int, dict[str, str]]], conf: dict[str, str] | None = None
) -> list[tuple[int, str, str, str]]:
    """Alimenta el motor con `(segundos, estados)` y devuelve `(t, cambio, tipo, estado)`."""
    engine = IncidentEngine(IdAllocator(), POLICY)
    out, t = [], 0
    for seconds, states in steps:
        for _ in range(seconds):
            t += 1
            for inc in engine.step(float(t), {**CALM, **states}, conf):
                out.append((t, inc.change.value, inc.kind.value, inc.state.value))
    return out


LOST = {"link.availability": "lost"}
SPOOF = {"gps.integrity": "spoofed"}


def test_an_incident_opens_after_k_instants_and_closes_after_m() -> None:
    k, m = POLICY.defaults.k_open, POLICY.defaults.m_close
    result = run([(k - 1, SPOOF), (5, {}), (k, SPOOF), (m + 3, {})])
    assert [r for r in result if r[1] == "opened"] == [
        (k - 1 + 5 + k, "opened", "GPS_SPOOFING", "open")
    ]
    assert result[-1][1:] == ("closed", "GPS_SPOOFING", "closed")
    assert result[-1][0] - (k - 1 + 5 + k + 1) >= m - 1  # cierra tras m instantes normales


def test_several_incidents_can_be_open_at_once_one_per_family() -> None:
    result = run([(K + 2, SPOOF), (K_LINK_Q + 2, {**SPOOF, "link.quality": "degraded"}), (3, {})])
    assert {r[2] for r in result if r[1] == "opened"} == {"GPS_SPOOFING", "LINK_DEGRADED"}


def test_the_name_only_changes_towards_a_graver_type_of_its_family() -> None:
    result = run(
        [
            (K_LINK_Q + 1, {"link.quality": "degraded"}),
            (K + 2, LOST),
            (3, {"link.quality": "degraded"}),
        ]
    )
    renamed = [r[2] for r in result if r[1] == "renamed"]
    assert renamed == ["LINK_LOSS"]  # y no vuelve atrás a LINK_DEGRADED


def test_a_cause_that_comes_back_inside_the_bounce_window_does_not_reopen() -> None:
    # fin de la causa, vuelve a los 5 s: sigue en recuperación, sin las dos revisiones de más
    wind = {"environment.wind": "beyond_limit"}
    result = run([(K_WIND + 1, wind), (2, {}), (K_WIND + 1, wind), (3, {})])
    states = [r[3] for r in result if r[1] == "state"]
    assert states == ["recovering"]  # una vez, sin volver a `open`


def test_a_cause_that_comes_back_after_the_bounce_window_reopens() -> None:
    wind = {"environment.wind": "beyond_limit"}
    result = run([(K_WIND + 1, wind), (3, {"drone.situation": "deviated"}), (30, wind), (3, {})])
    assert [r[3] for r in result if r[1] == "state"][:2] == ["recovering", "open"]


def test_severity_goes_up_once_for_worsening_once_for_age_and_down_in_recovery() -> None:
    wind = {"environment.wind": "beyond_limit"}
    deviated = {**wind, "drone.situation": "deviated", "drone.cause": "wind"}
    steps = [
        (K_WIND + 1, wind),
        (5, deviated),
        (140, deviated),
        (3, {"drone.situation": "deviated"}),
    ]
    result = run(steps, {"drone.cause": "confirmed", "environment.wind": "confirmed"})
    severities = [(r[1], r[3]) for r in result]
    assert [c for c, _ in severities].count("severity") == 2  # al desviarse y por edad
    assert any(c == "state" for c, _ in severities)


def test_a_possible_confidence_never_raises_the_severity() -> None:
    result = run([(200, {"link.availability": "connected", "gps.availability": "no_data"})],
                 {"gps.availability": "possible"})  # fmt: skip
    assert [r for r in result if r[1] == "severity"] == []


def test_what_cannot_be_read_does_not_close_an_incident() -> None:
    silent = {"battery.availability": "no_data"}
    result = run([(5, silent), (30, {**LOST, "battery.availability": "no_data"})],
                 {"battery.availability": "confirmed"})  # fmt: skip
    assert [r[1:3] for r in result if r[2] == "SOURCE_SILENT"] == [("opened", "SOURCE_SILENT")]


def test_an_undetermined_deviation_becomes_the_cause_that_is_confirmed() -> None:
    dev = {**CALM, "drone.situation": "deviated", "drone.cause": "wind"}
    engine = IncidentEngine(IdAllocator(), POLICY)
    changes = []
    for conf in ("possible",) * (K + 2) + ("confirmed",) * (K_WIND + 2):
        changes += engine.step(float(len(changes)), dev, {"drone.cause": conf})
    assert [c.change.value for c in changes[:2]] == ["opened", "renamed"]
    assert [c.kind.value for c in changes[:2]] == ["UNDETERMINED", "WIND"]
    assert changes[0].incident_id == changes[1].incident_id  # el mismo incidente
