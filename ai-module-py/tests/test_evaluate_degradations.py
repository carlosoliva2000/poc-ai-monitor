"""E6: evaluación de los episodios de degradación del GPS y del enlace.

Los etiquetados (`gps_degraded`, `link_degraded`) se evalúan como cualquier etiqueta; los de
`labeled: false` van en `unlabeled_episodes.json` y se cuentan aparte: sus avisos son informativos
y solo una alerta de ataque o de viento es una falsa alarma.
"""

import json
from pathlib import Path

from test_evaluate import Builder

from ai_module.evaluate import evaluate, render_markdown, summary_line, to_json

LABELS = [
    {"id": "F1", "type": "gps_degraded", "source": "gps", "start_s": 150.0, "end_s": 210.0,
     "expected_rules": ["GPS_DEGRADED"], "expected_cause": "SENSOR_FAULT",
     "also_accepted_causes": ["GPS_JAMMING"], "eval_window": [150.0, 270.0]},
    {"id": "F2", "type": "link_degraded", "source": "link", "start_s": 330.0, "end_s": 390.0,
     "expected_rules": ["LINK_ANOMALY"], "expected_cause": "SENSOR_FAULT",
     "also_accepted_causes": ["UNKNOWN"], "eval_window": [330.0, 450.0]},
]  # fmt: skip
UNLABELED = {"episodes": [
    {"id": "U1", "source": "gps", "start_s": 280.0, "end_s": 300.0, "rules": ["GPS_DEGRADED"],
     "eval_window": [280.0, 360.0]},
]}  # fmt: skip


def builder(tmp_path: Path, unlabeled: bool = True) -> Builder:
    b = Builder(tmp_path, "nominal")
    (b.root / "labels.json").write_text(json.dumps({"labels": LABELS}), encoding="utf-8")
    if unlabeled:
        (b.root / "unlabeled_episodes.json").write_text(json.dumps(UNLABELED), encoding="utf-8")
    return b


def verdicts(ev) -> dict[str, str]:  # noqa: ANN001
    return {r.label.id: r.verdict for r in ev.results}


def test_degradation_labels_accept_their_causes(tmp_path: Path) -> None:
    b = builder(tmp_path, unlabeled=False)
    gps = b.raised("det-0001", 152.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0002", 153.0, "GPS_JAMMING", gps, ["det-0001"], phase="active")
    link = b.raised("det-0003", 332.0, "LINK_ANOMALY", "link")
    b.alert("ai-0004", 333.0, "UNKNOWN", link, ["det-0003"], phase="active")
    ev = evaluate(b.write())
    assert verdicts(ev) == {"F1": "✅", "F2": "✅"}
    assert ev.recovery_misses == []  # la lógica de recuperación no se aplica a las degradaciones
    assert not ev.stray_detections and not ev.stray_alerts


def test_a_link_degradation_diagnosed_as_hijack_fails(tmp_path: Path) -> None:
    b = builder(tmp_path, unlabeled=False)
    link = b.raised("det-0001", 332.0, "LINK_ANOMALY", "link")
    b.alert("ai-0002", 333.0, "HIJACK", link, ["det-0001"])
    gps = b.raised("det-0003", 152.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0004", 153.0, "GPS_SPOOFING", gps, ["det-0003"])
    assert verdicts(evaluate(b.write())) == {"F1": "❌", "F2": "❌"}


def test_detections_in_an_unlabeled_episode_are_informative(tmp_path: Path) -> None:
    b = builder(tmp_path)
    d = b.raised("det-0001", 282.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0002", 283.0, "SENSOR_FAULT", d, ["det-0001"])
    d2 = b.raised("det-0003", 290.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0004", 291.0, "UNKNOWN", d2, ["det-0003"])
    ev = evaluate(b.write())
    assert not ev.stray_detections and not ev.stray_alerts and ev.unlabeled_false == 0
    [u] = ev.unlabeled
    assert [i.detection_id for i in u.detections] == ["det-0001", "det-0003"]
    assert [a["payload"]["alert_id"] for a in u.alerts] == ["ai-0002", "ai-0004"]
    assert "0 falsas alarmas" in summary_line(ev)
    md = render_markdown(ev)
    assert "## Episodios sin etiqueta" in md and "| U1 | gps |" in md
    assert to_json(ev)["unlabeled_episodes"][0]["false_alarms"] == []


def test_an_attack_or_wind_alert_in_an_unlabeled_episode_is_a_false_alarm(tmp_path: Path) -> None:
    b = builder(tmp_path)
    d = b.raised("det-0001", 282.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0002", 283.0, "GPS_JAMMING", d, ["det-0001"])
    b.alert("ai-0003", 290.0, "WIND", d, ["det-0001"], supersedes="ai-0002")
    other = b.raised("det-0004", 295.0, "ROUTE_DEVIATION")  # otra regla: falsa alarma de siempre
    b.alert("ai-0005", 296.0, "UNKNOWN", other, ["det-0004"])
    ev = evaluate(b.write())
    assert ev.unlabeled_false == 2
    assert [i.detection_id for i in ev.stray_detections] == ["det-0004"]
    assert [a["payload"]["alert_id"] for a in ev.stray_alerts] == ["ai-0005"]
    assert "4 falsas alarmas" in summary_line(ev)
    data = to_json(ev)
    assert data["false_alarms"] == 4
    assert data["unlabeled_episodes"][0]["false_alarms"] == ["ai-0002", "ai-0003"]


def test_a_detection_of_another_source_is_not_the_episode(tmp_path: Path) -> None:
    b = builder(tmp_path)
    b.raised("det-0001", 285.0, "LINK_ANOMALY", "link")
    ev = evaluate(b.write())
    assert [i.detection_id for i in ev.stray_detections] == ["det-0001"]
    assert ev.unlabeled[0].detections == []


def test_without_the_file_nothing_changes(tmp_path: Path) -> None:
    b = builder(tmp_path, unlabeled=False)
    d = b.raised("det-0001", 282.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0002", 283.0, "SENSOR_FAULT", d, ["det-0001"])
    ev = evaluate(b.write())
    assert ev.unlabeled == [] and len(ev.stray_detections) == 1 and len(ev.stray_alerts) == 1
    assert "unlabeled_episodes" not in to_json(ev)
    assert "Episodios sin etiqueta" not in render_markdown(ev)
