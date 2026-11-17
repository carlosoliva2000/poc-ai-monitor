"""E6: lo que se informa aparte en el conjunto reservado.

- **Avisos dudosos tras un secuestro:** un `ROUTE_DEVIATION` entre el fin de la ventana de
  evaluación del secuestro y la vuelta real a la ruta (`truth.json`) no es falsa alarma.
- **«`UNKNOWN` honesto»** (con el interruptor): `UNKNOWN` sobre una etiqueta cuya causa necesita una
  fuente callada por un fallo programado no cuenta ni como acierto ni como fallo.
"""

import json
from pathlib import Path

from test_evaluate import Builder

from ai_module.evaluate import (
    HONEST_ONLY,
    evaluate,
    main,
    render_markdown,
    summary_line,
    to_json,
)

HIJACK = {"id": "A1", "type": "hijack", "source": None, "start_s": 100.0, "end_s": 160.0,
          "expected_rules": ["LINK_ANOMALY", "ROUTE_DEVIATION"], "expected_cause": "HIJACK",
          "also_accepted_causes": [], "eval_window": [100.0, 220.0]}  # fmt: skip
SPOOF = {"id": "A1", "type": "gps_spoofing", "source": None, "start_s": 100.0, "end_s": 160.0,
         "expected_rules": ["ROUTE_DEVIATION", "SOURCE_DISCREPANCY"],
         "expected_cause": "GPS_SPOOFING", "also_accepted_causes": [],
         "eval_window": [100.0, 220.0]}  # fmt: skip


def builder(tmp_path: Path, labels: list[dict], back_s: float | None = None) -> Builder:
    """Ruta recta por el eje x; el dron se aparta 200 m y vuelve a 0 m en `back_s`."""
    b = Builder(tmp_path, "nominal")
    (b.root / "labels.json").write_text(json.dumps({"labels": labels}), encoding="utf-8")
    plan = {"waypoints": [{"id": "BASE", "x": 0.0, "y": 0.0}, {"id": "WP1", "x": 5000.0, "y": 0.0}]}
    (b.root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    if back_s is not None:
        trajectory = [
            {"t": float(t), "x": 10.0 * t, "y": 200.0 if 100 <= t < back_s else 0.0}
            for t in range(0, 400)
        ]
        (b.root / "truth.json").write_text(json.dumps({"trajectory": trajectory}), "utf-8")
    return b


def fault(b: Builder, kind: str, t: float, source: str, n: int) -> None:
    payload = {"source": source, "mode": "mute", "origin": "scenario"}
    b.ev(kind, t, payload, "platform-player", id=f"sim-{n:04d}")


def test_a_deviation_before_the_return_to_the_route_is_doubtful(tmp_path: Path) -> None:
    b = builder(tmp_path, [HIJACK], back_s=225.0)
    d = b.raised("det-0001", 102.0, "LINK_ANOMALY", "link")
    b.alert("ai-0002", 103.0, "HIJACK", d, ["det-0001"])
    late = b.raised("det-0003", 222.0, "ROUTE_DEVIATION")
    b.alert("ai-0004", 223.0, "UNKNOWN", late, ["det-0003"])
    ev = evaluate(b.write())
    assert not ev.stray_detections and not ev.stray_alerts
    [w] = ev.doubtful
    assert (w.start_s, w.end_s) == (220.0, 225.0)
    assert [i.detection_id for i in w.detections] == ["det-0003"]
    assert [a["payload"]["alert_id"] for a in w.alerts] == ["ai-0004"]
    assert "0 falsas alarmas" in summary_line(ev) and "2 avisos dudosos" in summary_line(ev)
    assert "## Avisos dudosos tras un secuestro" in render_markdown(ev)
    assert to_json(ev)["doubtful"][0]["detections"] == ["det-0003"]


def test_after_the_return_to_the_route_it_is_a_false_alarm(tmp_path: Path) -> None:
    b = builder(tmp_path, [HIJACK], back_s=225.0)
    b.raised("det-0001", 230.0, "ROUTE_DEVIATION")
    ev = evaluate(b.write())
    assert [i.detection_id for i in ev.stray_detections] == ["det-0001"]
    assert ev.doubtful == [] and "doubtful" not in to_json(ev)


def test_without_truth_nothing_changes(tmp_path: Path) -> None:
    b = builder(tmp_path, [HIJACK])
    b.raised("det-0001", 222.0, "ROUTE_DEVIATION")
    ev = evaluate(b.write())
    assert [i.detection_id for i in ev.stray_detections] == ["det-0001"] and ev.doubtful == []


def honest_run(tmp_path: Path) -> Path:
    b = builder(tmp_path, [SPOOF])
    fault(b, "FaultInjected", 90.0, "radar", 1)
    d = b.raised("det-0001", 105.0, "ROUTE_DEVIATION")
    b.alert("ai-0002", 106.0, "UNKNOWN", d, ["det-0001"])
    fault(b, "FaultCleared", 150.0, "radar", 2)
    return b.write()


def test_honest_unknown_is_apart_only_with_the_switch(tmp_path: Path) -> None:
    folder = honest_run(tmp_path)
    assert [r.verdict for r in evaluate(folder).results] == ["❌"]  # sin el interruptor, igual
    ev = evaluate(folder, honest_unknown=True)
    [r] = ev.results
    assert r.verdict == HONEST_ONLY and r.wrong == [] and ev.overall == "✅"
    assert [(lb.id, i.detection_id) for lb, i in ev.honest] == [("A1", "det-0001")]
    assert "1 UNKNOWN honestos (aparte)" in summary_line(ev)
    assert "con `radar` callada" in render_markdown(ev)
    assert to_json(ev)["honest_unknown"][0]["label"] == "A1"
    assert main([str(folder), "--honest-unknown"]) == 0
    assert json.loads((folder / "eval.json").read_text())["labels"][0]["verdict"] == HONEST_ONLY


def test_unknown_with_the_source_back_is_a_miss(tmp_path: Path) -> None:
    b = builder(tmp_path, [SPOOF])
    fault(b, "FaultInjected", 90.0, "radar", 1)
    fault(b, "FaultCleared", 100.0, "radar", 2)
    d = b.raised("det-0001", 105.0, "ROUTE_DEVIATION")
    b.alert("ai-0002", 106.0, "UNKNOWN", d, ["det-0001"])
    ev = evaluate(b.write(), honest_unknown=True)
    assert [r.verdict for r in ev.results] == ["❌"] and ev.honest == []
