"""Evaluación: atribución, recuperación, causas aceptadas, falsas alarmas, cadenas, alertas
abiertas al final y esperas. Sobre ejecuciones sintéticas con las etiquetas reales de `demo`."""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ai_module.evaluate import (
    RunData,
    contradicting_rules,
    evaluate,
    render_markdown,
    write_evaluation,
)

RUNS = Path(__file__).resolve().parents[2] / "runs"
BASE = datetime(2026, 10, 20, 10, 0, 0)


class Builder:
    """Escribe un `timeline.jsonl` mínimo y los demás ficheros de una ejecución."""

    def __init__(self, tmp_path: Path, scenario: str = "demo") -> None:
        self.root = tmp_path / scenario
        self.folder = self.root / "20261021-000000"
        self.folder.mkdir(parents=True)
        shutil.copy(RUNS / scenario / "labels.json", self.root / "labels.json")
        self.events: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self.n = 0

    def ev(
        self,
        event_type: str,
        t: float,
        payload: dict,
        source: str,
        *,
        id: str,
        causation: str | None = None,
        wall: float | None = None,
    ) -> dict:
        self.n += 1
        wall = t / 16 if wall is None else wall
        event = {
            "event_id": id,
            "topic": "x",
            "type": event_type,
            "source": source,
            "asset": None,
            "seq": self.n,
            "sim_time": t,
            "event_time": "2026-10-20T10:00:00Z",
            "ingestion_time": (BASE + timedelta(seconds=wall)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z",
            "causation_id": causation,
            "ephemeral": False,
            "payload": payload,
        }
        self.events.append(event)
        return event

    def raised(self, det: str, t: float, rule: str, source: str | None = None) -> dict:
        payload = {
            "detection_id": det,
            "rule": rule,
            "severity": "medium",
            "value": 1.0,
            "threshold": 1.0,
            "unit": "m",
            "source": source,
            "window": {"since": t, "until": t},
            "trigger_event_ids": [],
            "message": "m",
        }
        return self.ev("DetectionRaised", t, payload, "ai-detector", id=det)

    def cleared(self, det: str, t: float, rule: str) -> dict:
        payload = {"detection_id": det, "rule": rule, "duration_s": 1.0, "max_value": 1.0}
        return self.ev("DetectionCleared", t, payload, "ai-detector", id=f"{det}-c")

    def alert(
        self,
        alert_id: str,
        t: float,
        cause: str,
        causation: dict,
        dets: list[str],
        supersedes: str | None = None,
        fallback: bool = False,
        conf: float = 0.8,
        texts: dict[str, str] | None = None,
        checks: dict[str, Any] | None = None,
    ) -> dict:
        payload = {
            "alert_id": alert_id,
            "detection_ids": dets,
            "cause": cause,
            "severity": "high",
            "confidence": conf,
            "summary": "s",
            "explanation": "e",
            "recommendation": "r",
            "evidence_event_ids": [],
            "supersedes": supersedes,
            "as_of_sim_time": t,
            "fallback": fallback,
            "checks": checks,
            **(texts or {}),
        }
        return self.ev(
            "AnomalyDetected",
            t,
            payload,
            "ai-monitor",
            id=alert_id,
            causation=causation["event_id"],
            wall=causation_wall(causation) + 3,
        )

    def ack(
        self,
        ack_id: str,
        t: float,
        causation: dict,
        det: str,
        alert_id: str | None,
        fallback: bool = False,
    ) -> dict:
        payload = {
            "detection_id": det,
            "alert_id": alert_id,
            "reason": "r",
            "as_of_sim_time": t,
            "fallback": fallback,
        }
        return self.ev(
            "DetectionAcknowledged",
            t,
            payload,
            "ai-monitor",
            id=ack_id,
            causation=causation["event_id"],
            wall=causation_wall(causation) + 2,
        )

    def close(self, close_id: str, t: float, causation: dict, alert_id: str) -> dict:
        payload = {"alert_id": alert_id, "reason": "r", "as_of_sim_time": t}
        return self.ev(
            "AlertClosed",
            t,
            payload,
            "ai-monitor",
            id=close_id,
            causation=causation["event_id"],
            wall=causation_wall(causation) + 2,
        )

    def write(self, meta: dict | None = None) -> Path:
        (self.folder / "timeline.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in self.events), encoding="utf-8"
        )
        (self.folder / "llm_trace.jsonl").write_text(
            "".join(json.dumps(t) + "\n" for t in self.trace), encoding="utf-8"
        )
        if meta is not None:
            (self.folder / "run_meta.json").write_text(json.dumps(meta))
        return self.folder


def causation_wall(event: dict) -> float:
    start = datetime.fromisoformat(event["ingestion_time"].replace("Z", ""))
    return (start - BASE).total_seconds()


def trace_record(agent: str = "monitor", **overrides: Any) -> dict:
    record = {
        "invocation_id": "inv-1",
        "agent": agent,
        "causation_ids": ["det-1"],
        "as_of": 100.0,
        "sim_time_end": 101.0,
        "queue_at_start": 0,
        "wall_start": "2026-10-20T10:00:00.000Z",
        "wall_end": "2026-10-20T10:00:05.000Z",
        "duration_s": 5.0,
        "model": "m",
        "sampling": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 800,
            "extra_body": {"top_k": -1, "repetition_penalty": 1.0},
        },
        "stream": False,
        "guided_mode": False,
        "tools_offered": [],
        "messages": [],
        "calls": [
            {
                "index": 1,
                "latency_s": 2.0,
                "prompt_tokens": 4000,
                "completion_tokens": 50,
                "finish_reason": "stop",
                "content": "",
                "tool_calls": [{"name": "load_skill"}, {"name": "publish_alert"}],
            }
        ],
        "skills_loaded": [{"name": "route-deviation", "by": "model"}],
        "guardrail_rejections": [],
        "invalid_json": 0,
        "reminders": 0,
        "unseen_evidence": 0,
        "end_reason": "done",
        "deterministic": False,
        "fallback": False,
        "fallback_close": False,
        "published": [],
        "iterations": 1,
        "conversation_id": None,
    }
    record.update(overrides)
    return record


def demo_run(
    tmp_path: Path,
    *,
    wind: str = "WIND",
    spoof: str = "GPS_SPOOFING",
    recovery: str = "GPS_SPOOFING",
    hijack: str = "HIJACK",
) -> Builder:
    """`demo` con las cuatro detecciones de la tabla 4.4 y la causa que se indique en cada una."""
    b = Builder(tmp_path)
    r1 = b.raised("det-0001", 106.0, "ROUTE_DEVIATION")
    b.alert("ai-0002", 107.0, wind, r1, ["det-0001"])
    c1 = b.cleared("det-0001", 156.0, "ROUTE_DEVIATION")
    b.ack("ai-0003", 157.0, c1, "det-0001", None)
    r2 = b.raised("det-0010", 192.0, "SOURCE_DISCREPANCY")
    b.alert("ai-0011", 193.0, spoof, r2, ["det-0010"])
    r3 = b.raised("det-0020", 222.0, "ROUTE_DEVIATION")
    b.alert("ai-0021", 223.0, recovery, r3, ["det-0020"], supersedes="ai-0011")
    r4 = b.raised("det-0030", 338.0, "ROUTE_DEVIATION")
    b.alert("ai-0031", 339.0, hijack, r4, ["det-0030"])
    return b


def test_perfect_demo_is_all_green(tmp_path: Path) -> None:
    b = demo_run(tmp_path)
    ev = evaluate(b.write())
    assert [r.verdict for r in ev.results] == ["✅", "✅", "✅"]
    assert ev.overall == "✅" and not ev.stray_detections and not ev.stray_alerts
    assert not ev.unanswered
    spoof = next(r for r in ev.results if r.label.id == "A2")
    assert [i.detection_id for i in spoof.raised] == [
        "det-0010",
        "det-0020",
    ]  # el RD de recuperación
    assert spoof.chains == 1  # ai-0011 -> ai-0021: una sola cadena
    md = render_markdown(ev)
    assert "no tratado como recuperación ✅" in md  # el RD del secuestro
    assert "alerta ai-0021 (sustituye)" in md


def test_recovery_attributed_to_the_spoofing_counts_and_to_another_cause_does_not(
    tmp_path: Path,
) -> None:
    ev = evaluate(demo_run(tmp_path, recovery="HIJACK").write())
    spoof = next(r for r in ev.results if r.label.id == "A2")
    assert spoof.verdict == "⚠️"  # hay una alerta correcta, pero un aviso mal atribuido
    assert [i.detection_id for i in spoof.wrong] == ["det-0020"]
    assert ev.overall == "⚠️"


def test_hijack_deviation_treated_as_recovery_is_flagged(tmp_path: Path) -> None:
    ev = evaluate(demo_run(tmp_path, hijack="GPS_SPOOFING").write())
    hijack = next(r for r in ev.results if r.label.id == "A3")
    assert hijack.verdict == "❌"
    assert "tratado como recuperación ❌" in render_markdown(ev)


def test_wrong_cause_everywhere_is_red(tmp_path: Path) -> None:
    ev = evaluate(
        demo_run(tmp_path, wind="UNKNOWN", spoof="WIND", recovery="WIND", hijack="WIND").write()
    )
    assert [r.verdict for r in ev.results] == ["❌", "❌", "❌"]
    assert ev.overall == "❌"


def test_fallback_is_no_diagnosis(tmp_path: Path) -> None:
    b = Builder(tmp_path)
    r = b.raised("det-0001", 106.0, "ROUTE_DEVIATION")
    b.alert("ai-0002", 107.0, "UNKNOWN", r, ["det-0001"], fallback=True)
    ev = evaluate(b.write())
    wind = next(x for x in ev.results if x.label.id == "A1")
    assert wind.verdict == "❌" and wind.wrong[0].cause() == "sin diagnóstico"
    assert "sin diagnóstico" in render_markdown(ev)


def test_acknowledge_takes_the_cause_of_the_alert_it_links_to(tmp_path: Path) -> None:
    b = Builder(tmp_path)
    r1 = b.raised("det-0001", 192.0, "SOURCE_DISCREPANCY")
    b.alert("ai-0002", 193.0, "GPS_SPOOFING", r1, ["det-0001"])
    r2 = b.raised("det-0003", 222.0, "ROUTE_DEVIATION")
    b.ack("ai-0004", 223.0, r2, "det-0003", "ai-0002")
    c = b.cleared("det-0003", 241.0, "ROUTE_DEVIATION")
    b.ack("ai-0005", 242.0, c, "det-0003", "ai-0002")
    ev = evaluate(b.write())
    spoof = next(r for r in ev.results if r.label.id == "A2")
    assert spoof.verdict == "✅"
    assert all(i.cause() == "GPS_SPOOFING" for i in spoof.raised)


def test_false_alarms_and_unanswered_detections(tmp_path: Path) -> None:
    b = Builder(tmp_path)
    r = b.raised("det-0001", 20.0, "SOURCE_SILENT", "battery")  # fuera de toda ventana
    b.alert("ai-0002", 21.0, "SENSOR_FAULT", r, ["det-0001"])
    b.raised("det-0003", 30.0, "ROUTE_DEVIATION")  # sin respuesta
    ev = evaluate(b.write())
    assert len(ev.stray_detections) == 2 and len(ev.stray_alerts) == 1
    assert [i.detection_id for i in ev.unanswered] == ["det-0003"]
    assert "0 detecciones sin respuesta" not in render_markdown(ev)


def test_source_silent_is_attributed_by_source(tmp_path: Path) -> None:
    b = Builder(tmp_path, "fallos")
    r = b.raised("det-0001", 125.0, "SOURCE_SILENT", "radar")
    b.alert("ai-0002", 126.0, "SENSOR_FAULT", r, ["det-0001"])
    other = b.raised("det-0003", 130.0, "SOURCE_SILENT", "meteo")  # no es la fuente del fallo
    b.ack("ai-0004", 131.0, other, "det-0003", None)
    ev = evaluate(b.write())
    f1 = next(r for r in ev.results if r.label.id == "F1")
    assert [i.detection_id for i in f1.raised] == ["det-0001"]
    assert [i.detection_id for i in ev.stray_detections] == ["det-0003"]


def test_loss_accepts_sensor_fault_and_counts_one_chain(tmp_path: Path) -> None:
    b = Builder(tmp_path, "fallos")
    labels = json.loads((b.root / "labels.json").read_text())["labels"]
    loss = next(lb for lb in labels if lb["type"] == "gps_loss")
    t0 = loss["start_s"]
    gd = b.raised("det-0001", t0, "GPS_DEGRADED", "gps")
    b.alert("ai-A", t0 + 1, "SENSOR_FAULT", gd, ["det-0001"])
    sd = b.raised("det-0002", t0 + 13, "SOURCE_DISCREPANCY")
    b.alert("ai-B", t0 + 14, "GPS_JAMMING", sd, ["det-0002"], supersedes="ai-A")
    rd = b.raised("det-0003", t0 + 45, "ROUTE_DEVIATION")
    b.alert("ai-C", t0 + 46, "GPS_JAMMING", rd, ["det-0003"], supersedes="ai-B")
    ev = evaluate(b.write())
    f2 = next(r for r in ev.results if r.label.id == loss["id"])
    assert f2.verdict == "✅" and f2.chains == 1
    assert [e["payload"]["alert_id"] for e in ev.open_alerts] == ["ai-C"]
    assert "alertas abiertas al final" in summary(ev) and "1 alertas abiertas" in summary(ev)


def summary(ev: Any) -> str:
    return render_markdown(ev).splitlines()[2]


def test_manual_faults_generate_synthetic_labels(tmp_path: Path) -> None:
    b = Builder(tmp_path, "nominal")
    shutil.copy(RUNS / "demo" / "labels.json", b.root / "labels.json")
    (b.root / "labels.json").write_text('{"labels": []}')
    b.ev(
        "FaultInjected",
        150.0,
        {"source": "radar", "mode": "mute", "origin": "manual"},
        "platform-player",
        id="sim-0001",
    )
    b.ev(
        "FaultCleared",
        200.0,
        {"source": "radar", "mode": "mute", "origin": "manual"},
        "platform-player",
        id="sim-0002",
    )
    b.ev(
        "FaultInjected",
        240.0,
        {"source": "gps", "mode": "loss", "origin": "manual"},
        "platform-player",
        id="sim-0003",
    )
    r = b.raised("det-0001", 157.0, "SOURCE_SILENT", "radar")
    b.alert("ai-0002", 158.0, "SENSOR_FAULT", r, ["det-0001"])
    gd = b.raised("det-0003", 241.0, "GPS_DEGRADED", "gps")
    b.alert("ai-0004", 242.0, "GPS_JAMMING", gd, ["det-0003"])
    ev = evaluate(b.write())
    labels = {r.label.id: r for r in ev.results}
    assert set(labels) == {"F101", "F102"}  # el segundo, sin fin: dura hasta el final
    assert all(r.verdict == "✅" for r in ev.results)
    assert (
        labels["F101"].label.source.value == "radar"
        and labels["F102"].label.type.value == "gps_loss"
    )


def test_scenario_faults_do_not_duplicate_labels(tmp_path: Path) -> None:
    b = Builder(tmp_path, "fallos")
    b.ev(
        "FaultInjected",
        120.0,
        {"source": "radar", "mode": "mute", "origin": "scenario"},
        "platform-player",
        id="sim-0001",
    )
    assert len(RunData(b.write()).labels) == len(
        json.loads((b.root / "labels.json").read_text())["labels"]
    )


def test_nominal_without_detections_is_green(tmp_path: Path) -> None:
    b = Builder(tmp_path, "nominal")
    (b.root / "labels.json").write_text('{"labels": []}')
    b.ev("SimulationStarted", 0.0, {}, "platform-player", id="plr-0001")
    ev = evaluate(b.write())
    assert ev.overall == "✅" and not ev.results and not ev.open_alerts
    assert "0/0" in summary(ev)


def test_waits_timeouts_and_chat_overlap(tmp_path: Path) -> None:
    b = Builder(tmp_path)
    p1 = b.ev(
        "SimulationPaused",
        106.0,
        {"reason": "waiting_agent"},
        "platform-player",
        id="plr-1",
        wall=10,
    )
    b.ev("SimulationResumed", 106.0, {}, "platform-player", id="plr-2", wall=14)
    b.ev(
        "SimulationPaused",
        192.0,
        {"reason": "waiting_agent"},
        "platform-player",
        id="plr-3",
        wall=20,
    )
    b.ev("SimulationResumed", 192.0, {}, "platform-player", id="plr-4", wall=110)
    b.ev("SimulationPaused", 250.0, {"reason": "user"}, "platform-player", id="plr-5", wall=120)
    b.trace = [
        trace_record(
            "chat-monitor",
            wall_start="2026-10-20T10:00:12.000Z",
            wall_end="2026-10-20T10:00:13.000Z",
        )
    ]
    assert p1
    ev = evaluate(b.write({"wait_agent": True, "speed": 16, "wall_s": 120}))
    assert [round(w["wall_s"]) for w in ev.wait_list] == [4, 90]
    assert [w["chat"] for w in ev.wait_list] == [True, False]
    assert ev.timeouts == 1
    md = render_markdown(ev)
    assert "1 agotadas" in md and "## 6." not in md


def test_agent_section_and_no_wait_section(tmp_path: Path) -> None:
    b = demo_run(tmp_path)
    b.trace = [
        trace_record(),
        trace_record(
            "monitor",
            invocation_id="inv-2",
            skills_loaded=[{"name": "x", "by": "guided"}],
            reminders=1,
            fallback=True,
            fallback_close=True,
            invalid_json=2,
            guardrail_rejections=[{"tool": "publish_alert", "errors": ["e"]}],
            unseen_evidence=3,
            queue_at_start=2,
            causation_ids=["a", "b", "c"],
            published=[
                {"event_id": "ai-0002", "type": "AnomalyDetected", "causation_id": "det-0001"}
            ],
        ),
        trace_record(
            "monitor",
            invocation_id="inv-3",
            deterministic=True,
            iterations=0,
            calls=[],
            skills_loaded=[],
        ),
    ]
    ev = evaluate(b.write({"wait_agent": False, "speed": 1, "wall_s": 500}))
    s = ev.agents["monitor"]
    assert s["invocations"] == 3 and s["deterministic"] == 1 and s["llm_invocations"] == 2
    assert s["llm_calls"] == 2 and s["max_prompt_tokens"] == 4000 and s["prompt_tokens"] == 8000
    assert s["tools"] == {"load_skill": 2, "publish_alert": 2}
    assert (s["skills_by_model"], s["skills_guided"]) == (1, 1)
    assert (s["reminders"], s["fallbacks"], s["fallback_closes"], s["invalid_json"]) == (1, 1, 1, 2)
    assert s["rejections"] == 1 and s["unseen_evidence"] == 3
    md = render_markdown(ev)
    assert "## 6. Sin esperar al agente" in md and "lotes de más de una detección: 1" in md
    assert "máximo de prompt en una llamada: 4000" in md and "esperar al agente: no" in md


def test_write_evaluation_creates_both_files(tmp_path: Path) -> None:
    folder = demo_run(tmp_path).write()
    write_evaluation(folder)
    assert (folder / "eval.md").read_text().startswith("# Evaluación · demo")
    data = json.loads((folder / "eval.json").read_text())
    assert data["overall"] == "✅" and [lb["verdict"] for lb in data["labels"]] == ["✅"] * 3
    assert data["unanswered"] == [] and data["open_alerts"] == ["ai-0002", "ai-0021", "ai-0031"]


def test_agent_code_never_reads_labels_or_truth() -> None:
    """Aislamiento: solo `evaluate.py` conoce las etiquetas; nadie importa `evaluate`."""
    source = Path(__file__).resolve().parents[1] / "src" / "ai_module"
    for path in source.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "evaluate.py":
            continue
        assert "labels.json" not in text and "truth" not in text.lower().replace("truthy", ""), path
        assert "from .evaluate" not in text and "import evaluate" not in text, path
        assert "platform_app" not in text, path  # regla 3: nada de importar `platform/`


def test_header_lists_the_aids_that_were_on(tmp_path: Path) -> None:
    b = demo_run(tmp_path)
    aids = {
        "tool_choice": "required",
        "final_iteration_response_tools_only": True,
        "require_checks": True,
        "coherence_guardrail": False,
        "computed_facts": True,
    }
    b.trace = [trace_record(aids=aids)]
    md = render_markdown(evaluate(b.write()))
    assert "Ayudas al modelo: tool_choice = required" in md
    assert "guardrail de coherencia: no" in md and "hechos calculados: sí" in md
    b2 = demo_run(tmp_path / "otra")
    assert "Ayudas al modelo: n/d" in render_markdown(evaluate(b2.write()))


def test_header_shows_the_run_meta_written_by_the_platform_with_its_changes(
    tmp_path: Path,
) -> None:
    meta = {
        "wait_agent": True, "wait_agent_changes": [{"sim_time": 120.0, "value": False}],
        "speed": 4.0, "speed_changes": [{"sim_time": 60.0, "value": 8.0}],
        "interactive": False, "interactive_changes": [{"sim_time": 30.0, "value": True}],
    }  # fmt: skip
    a = demo_run(tmp_path / "a")
    a.trace = [trace_record()]
    md = render_markdown(evaluate(a.write(meta)))
    assert (
        "esperar al agente: sí → no (a T+02:00) · velocidad: 4× → 8× (a T+01:00) · "
        "modo interactivo: no → sí (a T+00:30)"
    ) in md
    assert "## 6. Sin esperar al agente" in md  # dejó de esperar: hay tramo sin espera
    b = demo_run(tmp_path / "b")
    b.trace = [trace_record()]
    always = render_markdown(evaluate(b.write({"wait_agent": True, "speed": 4.0})))
    assert "esperar al agente: sí · velocidad: 4×" in always
    assert "## 6. Sin esperar al agente" not in always
    nothing = render_markdown(evaluate(demo_run(tmp_path / "c").write()))
    assert "esperar al agente: n/d · velocidad: n/d · modo interactivo: n/d" in nothing


WIND_YES = {"wind_with_drift": True, "gps_radar_disagreed": False}


def test_phrases_against_the_drift_contradict_a_drift_in_favour() -> None:
    for sentence in (
        "El viento es notable (3,9 m/s) y empuja en dirección contraria a la deriva (4,9°).",
        "El viento sopla de 299° a 119° contra la deriva (36,4°).",
        "La deriva del dron va contra el viento.",
        "El viento empuja en sentido opuesto a la deriva.",
        "El viento es notable pero no es relevante, y empuja en dirección contraria a la deriva.",
    ):
        assert contradicting_rules(sentence, WIND_YES), sentence


def test_phrases_that_agree_with_the_checks_are_not_flagged() -> None:
    for sentence in (
        "El viento empuja en la dirección de la deriva (4,9°).",
        "El viento no empuja en dirección contraria a la deriva.",
        "El viento empuja el dron en dirección contraria a la ruta planificada.",
        "El dron corrige en sentido contrario al error de rumbo.",
        "El GPS y el radar discrepan poco (6,8 m).",
        "El GPS y el radar no discrepan, 6,8 m de distancia.",
        "El GPS y el radar discrepan ligeramente de la ruta planificada.",
    ):
        assert contradicting_rules(sentence, WIND_YES) == [], sentence


def test_gps_radar_disagreement_figure_contradicts_a_check_of_no_disagreement() -> None:
    assert contradicting_rules("El GPS y el radar discrepan 13,8 m.", WIND_YES)
    assert contradicting_rules("El GPS y el radar discrepan en 13,8 m.", WIND_YES)
    assert contradicting_rules("La discrepancia entre GPS y radar es de 12 m.", WIND_YES)


def test_rules_only_apply_when_the_check_says_so() -> None:
    drift_against = {"wind_with_drift": False, "gps_radar_disagreed": True}
    assert (
        contradicting_rules("El viento empuja en dirección contraria a la deriva.", drift_against)
        == []
    )
    assert contradicting_rules("El GPS y el radar discrepan 13,8 m.", drift_against) == []
    unknown = {"wind_with_drift": None, "gps_radar_disagreed": None}
    assert contradicting_rules("El GPS y el radar discrepan 13,8 m.", unknown) == []
    assert contradicting_rules("El GPS y el radar discrepan 13,8 m.", None) == []


def test_contradictions_are_listed_in_the_report_and_the_json(tmp_path: Path) -> None:
    b = demo_run(tmp_path)
    r = b.raised("det-0040", 400.0, "ROUTE_DEVIATION")
    b.alert(
        "ai-0041",
        401.0,
        "WIND",
        r,
        ["det-0040"],
        texts={
            "summary": "Viento contra la deriva",
            "explanation": "Todo bien. El GPS y el radar discrepan 13,8 m. Sigue.",
            "recommendation": "Vigilar.",
        },
        checks=WIND_YES,
    )
    ev = evaluate(b.write())
    assert [(c.alert_id, c.field) for c in ev.contradictions] == [
        ("ai-0041", "resumen"),
        ("ai-0041", "explicación"),
    ]
    md = render_markdown(ev)
    assert "2 frases que contradicen los checks" in summary(ev)
    assert "## Frases que contradicen los checks" in md
    assert "«El GPS y el radar discrepan 13,8 m.»" in md
    ev2 = write_evaluation(b.folder)
    data = json.loads((b.folder / "eval.json").read_text(encoding="utf-8"))
    assert len(data["contradictions"]) == 2 and ev2.contradictions


def test_a_run_without_contradictions_says_none(tmp_path: Path) -> None:
    ev = evaluate(demo_run(tmp_path).write())
    assert ev.contradictions == []
    assert "0 frases que contradicen los checks" in summary(ev)
    assert "## Frases que contradicen los checks\n\nNinguna." in render_markdown(ev)


def test_english_phrases_are_checked_with_the_same_rules() -> None:
    for sentence in (
        "The wind is notable (3.9 m/s) and pushes against the drift (4.9°).",
        "The wind pushes in the opposite direction to the drift.",
        "The drone drift is contrary to the wind.",
        "GPS and radar disagree by 13.8 m.",
        "The discrepancy between GPS and radar is 12 m.",
    ):
        assert contradicting_rules(sentence, WIND_YES), sentence
    for sentence in (
        "The wind pushes in the direction of the drift (4.9°).",
        "The wind does not push against the drift.",
        "The wind doesn't push in the opposite direction to the drift.",
        "The wind pushes the drone contrary to the planned route.",
        "GPS and radar disagree slightly (6.8 m).",
        "GPS and radar do not disagree, 6.8 m apart.",
    ):
        assert contradicting_rules(sentence, WIND_YES) == [], sentence
