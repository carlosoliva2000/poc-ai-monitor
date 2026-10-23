"""Pruebas unitarias del detector con eventos sintéticos."""

import pytest
from synthetic import Maker, steady

from ai_module.detector import Detector, SilentConfig, load_config
from poc_contracts.enums import EventType, Rule, SensorSource, Severity
from poc_contracts.envelope import EventDraft
from poc_contracts.payloads import DetectionCleared, DetectionRaised

RAISED = EventType.DETECTION_RAISED
UPDATED = EventType.DETECTION_UPDATED
CLEARED = EventType.DETECTION_CLEARED


def quiet() -> Detector:
    """Detector sin `SOURCE_SILENT` (umbrales enormes): para probar las demás reglas con
    eventos de una sola fuente."""
    config = load_config()
    config.source_silent = SilentConfig(gps=1e9, radar=1e9, link=1e9, meteo=1e9, battery=1e9)
    return Detector(config)


def feed_all(detector: Detector, events: list[EventDraft]) -> list[EventDraft]:
    out: list[EventDraft] = []
    for event in events:
        out += detector.feed(event)
    return out


def kinds(detections: list[EventDraft], rule: Rule | None = None) -> list[tuple[float, EventType]]:
    """(sim_time, tipo) de las detecciones, opcionalmente de una sola regla."""
    return [
        (d.sim_time, d.type) for d in detections if rule is None or d.payload["rule"] == rule.value
    ]


def gps_run(maker: Maker, ys: dict[int, float], start: int, end: int) -> list[EventDraft]:
    """GPS cada segundo sobre el eje x con la desviación `ys[t]` (0 si no está)."""
    return [maker.gps(float(t), float(t), ys.get(t, 0.0)) for t in range(start, end)]


# --- ROUTE_DEVIATION -------------------------------------------------------------------------


def test_config_loads_documented_thresholds() -> None:
    config = load_config()
    assert config.route_deviation.open_m == 30.0
    assert config.route_deviation.close_hold_s == 5.0
    assert config.source_discrepancy.close_m == 12.0
    assert config.source_silent.radar == 6.0
    assert config.gps_degraded.max_hdop == 3.0


def test_route_deviation_opens_once_and_closes_only_after_hold() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    # Se aleja a 35 m en t=10 y se queda ahí hasta t=20; 20 m (entre umbrales) hasta t=25;
    # después, a 5 m: cierra 5 s más tarde (t=35).
    ys = dict.fromkeys(range(10, 20), 35.0) | dict.fromkeys(range(20, 25), 20.0)
    ys |= dict.fromkeys(range(25, 40), 5.0)
    out = feed_all(det, gps_run(maker, ys, 0, 40))
    assert kinds(out) == [(10.0, RAISED), (30.0, CLEARED)]
    raised = DetectionRaised.model_validate(out[0].payload)
    assert (raised.rule, raised.severity, raised.source) == (Rule.ROUTE_DEVIATION, "medium", None)
    assert raised.window.since == 10.0 and raised.threshold == 30.0 and raised.unit == "m"
    assert raised.trigger_event_ids == ["gps-000010", "gps-000011"]
    cleared = DetectionCleared.model_validate(out[1].payload)
    assert cleared.detection_id == raised.detection_id
    assert cleared.max_value == 35.0 and cleared.duration_s == 20.0


def test_route_deviation_hold_restarts_when_it_rises_again() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    # 4 s por debajo de 15 m, una lectura de 20 m y otra vez por debajo: no cierra hasta 5 s
    # seguidos.
    ys = dict.fromkeys(range(5, 10), 40.0) | {13: 20.0}
    out = feed_all(det, gps_run(maker, ys, 0, 30))
    assert kinds(out) == [(5.0, RAISED), (19.0, CLEARED)]


def test_route_deviation_updated_only_once_when_worse() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    ys = dict.fromkeys(range(5, 10), 40.0) | dict.fromkeys(range(10, 20), 90.0)
    ys |= dict.fromkeys(range(20, 25), 85.0)
    out = feed_all(det, gps_run(maker, ys, 0, 40))
    assert kinds(out) == [(5.0, RAISED), (10.0, UPDATED), (30.0, CLEARED)]
    updated = DetectionRaised.model_validate(out[1].payload)
    assert updated.severity == Severity.HIGH and updated.threshold == 80.0
    assert updated.detection_id == out[0].payload["detection_id"]
    assert DetectionCleared.model_validate(out[2].payload).max_value == 90.0


def test_route_deviation_opens_as_high_if_first_value_is_beyond_worsen_threshold() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    out = feed_all(det, gps_run(maker, {5: 120.0, 6: 130.0}, 0, 8))
    assert kinds(out) == [(5.0, RAISED)]
    assert out[0].payload["severity"] == "high"


def test_route_deviation_needs_the_plan() -> None:
    maker, det = Maker(), quiet()
    assert feed_all(det, gps_run(maker, dict.fromkeys(range(10), 100.0), 0, 10)) == []


def test_route_deviation_with_plan_from_tool_result() -> None:
    """El plan del bootstrap llega como el resultado de `get_mission_plan`."""
    maker, det = Maker(), quiet()
    plan = maker.plan().payload | {"next_waypoint": "P1"}
    det.set_plan(plan)
    out = feed_all(det, gps_run(maker, {5: 50.0}, 0, 8))
    assert kinds(out) == [(5.0, RAISED)]


def test_route_deviation_gap_in_gps_restarts_the_closing_timer() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    events = gps_run(maker, dict.fromkeys(range(3), 40.0), 0, 3)
    # Por debajo de 15 m desde t=3, un hueco de 4 s (t=5 a t=9) y sigue.
    events += gps_run(maker, {}, 3, 5) + gps_run(maker, {}, 9, 16)
    out = feed_all(det, events)
    # Sin el hueco habría cerrado en t=8; con él, el tiempo se cuenta desde t=9.
    assert kinds(out) == [(0.0, RAISED), (14.0, CLEARED)]


# --- SOURCE_DISCREPANCY ----------------------------------------------------------------------


def discrepancy_run(
    maker: Maker, t_from: int, t_to: int, offset: float, with_gps: bool = True
) -> list[EventDraft]:
    events: list[EventDraft] = []
    for t in range(t_from, t_to):
        if with_gps:
            events.append(maker.gps(float(t), float(t), 0.0))
        if t % 2 == 0:
            events.append(maker.radar(float(t), float(t), offset))
    return events


def test_source_discrepancy_hysteresis() -> None:
    maker, det = Maker(), quiet()
    events = discrepancy_run(maker, 0, 10, 2.0)
    events += discrepancy_run(maker, 10, 30, 40.0)  # abre (media de 3 > 25)
    events += discrepancy_run(maker, 30, 36, 18.0)  # entre umbrales: sigue abierta
    events += discrepancy_run(maker, 36, 60, 3.0)  # cierra tras 6 s por debajo de 12 m
    out = feed_all(det, events)
    kind = kinds(out)
    assert [k for _, k in kind] == [RAISED, CLEARED]
    # Con la ventana de 3 medidas: abre cuando la media pasa de 25 m (2.ª muestra de 40).
    assert 10.0 <= kind[0][0] <= 14.0
    assert kind[1][0] > 42.0
    raised = DetectionRaised.model_validate(out[0].payload)
    assert raised.rule == Rule.SOURCE_DISCREPANCY and raised.source is None
    assert raised.unit == "m" and raised.threshold == 25.0
    assert len(raised.trigger_event_ids) == 2


def test_source_discrepancy_updated_once() -> None:
    maker, det = Maker(), quiet()
    events = discrepancy_run(maker, 0, 20, 40.0) + discrepancy_run(maker, 20, 40, 100.0)
    out = feed_all(det, events)
    assert [k for _, k in kinds(out)] == [RAISED, UPDATED]


def test_source_discrepancy_not_evaluated_without_recent_radar() -> None:
    maker, det = Maker(), quiet()
    # Solo GPS: no hay radar, no hay comparación.
    events = [maker.gps(float(t), float(t), 0.0) for t in range(30)]
    assert feed_all(det, events) == []


def test_source_discrepancy_drops_stale_radar_samples() -> None:
    maker, det = Maker(), quiet()
    events = discrepancy_run(maker, 0, 10, 2.0)
    # Una sola medida de radar mala tras un silencio de radar de más de 6 s: una muestra sola no
    # basta (mínimo 2), así que no se evalúa con datos viejos.
    events += [maker.gps(float(t), float(t), 0.0) for t in range(10, 20)]
    events += [maker.radar(20.0, 20.0, 60.0), maker.gps(20.0, 20.0, 0.0)][::-1]
    out = feed_all(det, events)
    assert [d for d in out if d.payload["rule"] == "SOURCE_DISCREPANCY"] == []


def test_source_discrepancy_not_evaluated_across_a_gps_gap() -> None:
    maker, det = Maker(), quiet()
    # GPS en t=0..9 y de nuevo en t=14..; el radar de t=10 y t=12 cae en un hueco de 5 s.
    events = [maker.gps(float(t), float(t), 0.0) for t in range(10)]
    events += [maker.radar(10.0, 10.0, 80.0), maker.radar(12.0, 12.0, 80.0)]
    events += [maker.gps(float(t), float(t), 0.0) for t in range(14, 20)]
    assert feed_all(det, events) == []


def test_source_discrepancy_interpolates_gps_to_radar_instant() -> None:
    maker, det = Maker(), quiet()
    # GPS cada 2 s (x = t); radar en t impar: coincide con la interpolación, sin discrepancia.
    events: list[EventDraft] = []
    for t in range(0, 40):
        if t % 2 == 0:
            events.append(maker.gps(float(t), float(t), 0.0))
        else:
            events.append(maker.radar(float(t), float(t), 0.0))
    assert feed_all(det, events) == []


# --- SOURCE_SILENT ---------------------------------------------------------------------------


SILENT_CASES = [
    ("gps", "PositionUpdated", 3.0),
    ("radar", "TrackUpdated", 6.0),
    ("link", "LinkStatus", 15.0),
    ("meteo", "WindReported", 30.0),
    ("battery", "BatteryStatus", 30.0),
]


@pytest.mark.parametrize(("source", "type_name", "threshold"), SILENT_CASES)
def test_source_silent_opens_and_closes_per_source(
    source: str, type_name: str, threshold: float
) -> None:
    maker, det = Maker(), Detector()
    det.feed(maker.started())
    det.feed(maker.plan())
    out: list[EventDraft] = []
    for t in range(0, 100):
        # La fuente calla entre t=20 y t=79; el resto sigue con sus periodos.
        skip = (type_name,) if 20 <= t < 80 else ()
        out += feed_all(det, steady(maker, t, skip=skip))
    silent = [d for d in out if d.payload["rule"] == "SOURCE_SILENT"]
    assert [d.type for d in silent] == [RAISED, CLEARED]
    raised = DetectionRaised.model_validate(silent[0].payload)
    assert raised.source == SensorSource(source)
    assert raised.unit == "s" and raised.threshold == threshold
    assert raised.value > threshold
    # Abre con el primer evento que deja pasar el umbral; cierra con el siguiente de la fuente.
    assert silent[0].sim_time < 20 + threshold + 3
    assert silent[1].sim_time >= 80
    assert DetectionCleared.model_validate(silent[1].payload).detection_id == raised.detection_id
    # Solo esa fuente: ninguna otra regla ni otra fuente.
    assert [d for d in out if d.type == RAISED] == [silent[0]]


@pytest.mark.parametrize(
    ("source", "severity"),
    [("gps", "medium"), ("radar", "medium"), ("link", "low"), ("meteo", "low"), ("battery", "low")],
)
def test_source_silent_severity(source: str, severity: str) -> None:
    maker, det = Maker(), Detector()
    type_name = {s: t for s, t, _ in SILENT_CASES}[source]
    out: list[EventDraft] = []
    for t in range(0, 100):
        out += feed_all(det, steady(maker, t, skip=(type_name,) if t >= 10 else ()))
    raised = [d for d in out if d.type == RAISED]
    assert raised[0].payload["severity"] == severity


def test_source_silent_clock_is_the_sim_time_of_any_event() -> None:
    maker, det = Maker(), Detector()
    det.feed(maker.started())
    for t in range(0, 5):
        feed_all(det, steady(maker, t))
    # Un evento del dominio `sim` (el detector ignora el contenido) hace avanzar el reloj.
    out = det.feed(maker.fault(11.0, source="battery"))
    sources = {d.payload["source"] for d in out}
    assert sources == {"gps", "radar"}  # 7 s sin GPS y sin radar; el resto aún no
    assert all(d.type == RAISED for d in out)


def test_source_silent_stops_after_mission_completed_and_simulation_finished() -> None:
    maker, det = Maker(), Detector()
    for t in range(0, 10):
        feed_all(det, steady(maker, t))
    det.feed(maker.completed(10.0))
    assert det.feed(maker.finished(200.0)) == []
    assert det.feed(maker.fault(300.0)) == []

    maker, det = Maker(), Detector()
    for t in range(0, 10):
        feed_all(det, steady(maker, t))
    assert det.feed(maker.finished(10.5)) == []
    assert det.feed(maker.fault(300.0)) == []


def test_source_silent_initial_last_seen_is_the_first_event() -> None:
    """Un módulo que arranca tarde no ve silencio desde el instante 0."""
    maker, det = Maker(), Detector()
    out = feed_all(det, steady(maker, 500))
    assert out == []


# --- GPS_DEGRADED ----------------------------------------------------------------------------


def degraded_run(maker: Maker, bad: dict[str, object], bad_range: range) -> list[EventDraft]:
    events = []
    for t in range(0, 40):
        kwargs = bad if t in bad_range else {}
        events.append(maker.gps(float(t), float(t), 0.0, **kwargs))  # type: ignore[arg-type]
    return events


@pytest.mark.parametrize(
    ("bad", "severity", "expected_value", "word"),
    [
        ({"fix": "2d"}, "medium", 0.8, "fix 2d"),
        ({"sats": 4}, "medium", 0.8, "4 satellites (minimum 6)"),
        ({"hdop": 3.5}, "medium", 3.5, "hdop 3.5"),
        ({"fix": "none", "sats": 0, "hdop": 99.9}, "high", 99.9, "lost the fix"),
    ],
)
def test_gps_degraded_by_fix_sats_or_hdop(
    bad: dict[str, object], severity: str, expected_value: float, word: str
) -> None:
    maker, det = Maker(), quiet()
    out = feed_all(det, degraded_run(maker, bad, range(10, 20)))
    assert kinds(out) == [(10.0, RAISED), (25.0, CLEARED)]  # 5 s buenos desde t=20
    raised = DetectionRaised.model_validate(out[0].payload)
    assert raised.rule == Rule.GPS_DEGRADED and raised.source == SensorSource.GPS
    assert raised.severity == severity and raised.value == expected_value
    assert raised.threshold == 3.0 and raised.unit == "hdop"
    assert word in raised.message
    assert raised.trigger_event_ids == ["gps-000011"]


def test_gps_degraded_boundary_values_are_normal() -> None:
    maker, det = Maker(), quiet()
    events = [maker.gps(float(t), float(t), 0.0, sats=6, hdop=3.0) for t in range(10)]
    assert feed_all(det, events) == []


def test_gps_degraded_once_per_episode_and_hold_restarts() -> None:
    maker, det = Maker(), quiet()
    events = []
    for t in range(40):
        bad = t in range(10, 15) or t == 18
        events.append(maker.gps(float(t), float(t), 0.0, sats=3 if bad else 14))
    out = feed_all(det, events)
    # La lectura mala de t=18 reinicia los 5 s: cierra en t=24.
    assert kinds(out) == [(10.0, RAISED), (24.0, CLEARED)]


def test_gps_degraded_updated_when_fix_is_lost_after_a_milder_start() -> None:
    maker, det = Maker(), quiet()
    events = [maker.gps(float(t), float(t), 0.0, fix="2d" if t < 15 else "none") for t in range(10)]
    events += [maker.gps(float(t), float(t), 0.0, fix="2d") for t in range(10, 15)]
    events += [maker.gps(float(t), float(t), 0.0, fix="none") for t in range(15, 20)]
    out = feed_all(det, events)
    assert [k for _, k in kinds(out)] == [RAISED, UPDATED]
    assert out[1].payload["severity"] == "high"


# --- Reinicio, ignorar sim/ai y salida --------------------------------------------------------


def test_simulation_started_resets_everything() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    first = feed_all(det, gps_run(maker, dict.fromkeys(range(5, 10), 50.0), 0, 12))
    assert first[0].event_id == "det-0001" and det.open_detections() == ["det-0001"]
    det.feed(maker.started())
    assert det.open_detections() == [] and det.clock == 0.0
    # Sin plan no hay ROUTE_DEVIATION hasta el nuevo MissionPlanned; los ids vuelven a det-0001.
    assert feed_all(det, gps_run(maker, {5: 50.0}, 0, 8)) == []
    det.feed(maker.plan())
    again = feed_all(det, gps_run(maker, {5: 50.0}, 0, 8))
    assert again[0].event_id == "det-0001"


def test_simulation_reset_also_resets() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    feed_all(det, gps_run(maker, {5: 50.0}, 0, 8))
    det.feed(maker.reset())
    assert det.open_detections() == []


def test_sim_and_ai_events_only_move_the_clock() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    det.feed(maker.gps(0.0, 0.0, 0.0))
    # Un FaultInjected sobre el GPS no cambia nada por sí mismo (solo el reloj avanza).
    assert det.feed(maker.fault(1.0, source="gps", mode="loss")) == []
    assert det.clock == 1.0
    # Los eventos propios (ai) que vuelven por el bus tampoco se interpretan.
    own = feed_all(det, gps_run(maker, {5: 50.0}, 1, 8))
    assert det.feed(own[0]) == []


def test_detection_events_are_valid_and_coherent() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.plan())
    out = feed_all(det, gps_run(maker, dict.fromkeys(range(5, 9), 50.0), 0, 20))
    assert out
    for detection in out:
        assert detection.source == "ai-detector" and detection.asset == "d1"
        assert detection.topic.startswith("citadel.pub.evt.ai.d1.Detection")
        assert detection.topic.endswith(f"{detection.type.value}.v1")
        assert detection.event_id.startswith("det-")
        detection.typed_payload()
    assert len({d.event_id for d in out}) == len(out)
    assert out[0].event_time == "2026-10-20T10:00:05Z"


def test_every_event_updates_the_clock_monotonically() -> None:
    maker, det = Maker(), quiet()
    det.feed(maker.gps(10.0, 0.0, 0.0))
    det.feed(maker.gps(5.0, 0.0, 0.0))
    assert det.clock == 10.0


def test_operator_messages_do_not_move_the_clock_or_trigger_events() -> None:
    """Lo que escribe el operador (dominio `ops`) no cuenta ni como reloj ni como evidencia."""
    maker, det = Maker(), quiet()
    feed_all(det, [maker.gps(float(t), float(t), 0.0) for t in range(5)])
    message = EventDraft(
        event_id="ops-0001",
        topic="citadel.pub.evt.ops.monitor.OperatorMessage.v1",
        type=EventType.OPERATOR_MESSAGE,
        source="web-operator",
        asset=None,
        sim_time=9999.0,
        event_time="2026-10-20T10:00:04Z",
        payload={"conversation_id": "monitor", "text": "hola"},
    )
    assert det.feed(message) == []  # con el reloj adelantado habría saltado SOURCE_SILENT
    assert feed_all(det, [maker.gps(5.0, 5.0, 0.0)]) == []


def test_gps_degraded_message_names_the_failing_values() -> None:
    maker, det = Maker(), quiet()
    out = feed_all(det, degraded_run(maker, {"sats": 4, "hdop": 4.2}, range(10, 12)))
    message = DetectionRaised.model_validate(out[0].payload).message
    assert "4 satellites (minimum 6)" in message and "hdop 4.2 (maximum 3" in message
    assert "fix" not in message  # el fix es bueno
