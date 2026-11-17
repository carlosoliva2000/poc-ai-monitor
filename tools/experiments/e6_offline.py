"""E6, paso 2b: el monitor con la tabla de decisión sobre escenarios generados, sin GPU ni red.

    uv run --project ai-module-py python tools/experiments/e6_offline.py \
        [--scenarios D] [--runs D] [--only NOMBRE ...] [--family F ...] [--out resumen.md]

Por defecto, sobre las variantes de `tools/experiments/variants.py` (`experiments/e6-variantes/`).
Monta en un solo proceso las piezas reales de una ejecución con «esperar al agente»: el
reproductor (`platform_app.player.Player`, paso a paso y sin reloj de pared), el bus y el timeline
de la plataforma, y el módulo de IA (`ai_module.module.AiModule`: detector, monitor con
`engine: table` del perfil `table`, guardrails y trazas). Las tools de datos son las de la
plataforma (`platform_app.tools.call_tool`, con el corte en el instante del reproductor), servidas
como las sirve la API (`ToolOk` en JSON; un fallo, `PlatformToolError`). Lo único que no es igual
que en directo es el transporte (en proceso, sin WebSocket) y el reloj: entre paso y paso se deja
que todo lo asíncrono termine, así que el monitor contesta siempre en el instante del aviso.

Cada ejecución queda en `<runs>/<escenario>/offline/` (`timeline.jsonl`, `llm_trace.jsonl`,
`run_meta.json`, `profile.json`, `eval.md` y `eval.json`) y el resumen, en `--out`.
"""

import argparse
import asyncio
import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform" / "src"))

from ai_module.agent.assets import Assets  # noqa: E402
from ai_module.agent.llm import OpenAiLlm  # noqa: E402
from ai_module.agent.profiles import load_profile  # noqa: E402
from ai_module.bus_client import DEFAULT_PATTERNS, PlatformToolError  # noqa: E402
from ai_module.detector import Detector, load_config  # noqa: E402
from ai_module.evaluate import write_evaluation  # noqa: E402
from ai_module.module import AiModule  # noqa: E402
from ai_module.runtime import Runtime  # noqa: E402
from platform_app.bus import Bus  # noqa: E402
from platform_app.generator.controller import STEP_S  # noqa: E402
from platform_app.generator.scenario_io import list_scenarios  # noqa: E402
from platform_app.player import Player, PlayerStatus  # noqa: E402
from platform_app.timeline import Timeline  # noqa: E402
from platform_app.tools import call_tool  # noqa: E402
from platform_app.tools.context import ToolContext, ToolFailure  # noqa: E402
from poc_contracts.api import ToolOk  # noqa: E402
from poc_contracts.envelope import Envelope  # noqa: E402
from poc_contracts.topics import topic_matches  # noqa: E402

VARIANTS = REPO / "experiments" / "e6-variantes"
RUN_ID = "offline"
PROFILE = "table"


class OfflineRun:
    """Una ejecución de un escenario con el reproductor y el módulo de IA en el mismo proceso."""

    def __init__(self, scenarios_dir: Path, runs_dir: Path) -> None:
        self.bus = Bus(Timeline())
        self.player = Player(
            self.bus,
            runs_dir=runs_dir,
            scenarios_dir=scenarios_dir,
            wall_clock=lambda: 0.0,
            run_id_factory=lambda: RUN_ID,
        )
        profile = load_profile(PROFILE)
        assets = Assets(profile.assets_dir, profile)
        if assets.agent("monitor").engine != "table":
            raise SystemExit(f"the profile {PROFILE} does not use the decision table")
        config = load_config()
        config.link_anomaly.enabled &= assets.agent("monitor").link_anomaly  # como `__main__`
        tools = ToolContext(self.bus.timeline, lambda: self.player.sim_time)

        async def platform_call(url: str, name: str, args: dict[str, Any], timeout_s: float = 10):
            if self.player.config is None:
                raise PlatformToolError("no scenario is loaded")
            try:
                result = call_tool(tools, name, args)
            except ToolFailure as exc:
                raise PlatformToolError(str(exc)) from exc
            return json.loads(ToolOk(result=result).model_dump_json())["result"]

        async def publish(event: Any) -> None:
            self.bus.publish(event)

        llm = OpenAiLlm("http://127.0.0.1:1/v1", "none", assets.llm.model)  # nunca se llama
        self.rt = Runtime(assets, llm, "offline", publish, runs_dir, platform_call=platform_call)
        self.module = AiModule(self.rt, Detector(config), with_llm_agents=False)
        self.bus.subscribe("citadel.>", self._to_module)  # una sola suscripción: mismo orden
        self.forced_resumes = 0

    async def _to_module(self, event: Envelope) -> None:
        if any(topic_matches(p, event.topic) for p in DEFAULT_PATTERNS):
            await self.module.handle_event(event)

    def _busy(self) -> bool:
        monitor = self.module.monitor
        subs_busy = any(s.pending or s.draining for s in self.bus._subs)
        return subs_busy or bool(monitor and (monitor.queue or monitor._busy))

    async def _settle(self) -> None:
        """Deja que el módulo procese todo lo publicado y que el monitor conteste."""
        quiet = 0
        while quiet < 3:
            await asyncio.sleep(0)
            quiet = 0 if self._busy() else quiet + 1

    async def run(self, name: str) -> Path:
        # la traza se añade al final del fichero: cada ejecución empieza con la carpeta vacía
        shutil.rmtree(self.player.runs_dir / name / RUN_ID, ignore_errors=True)
        self.module.start()
        try:
            p = self.player
            p.load(name)
            p.set_speed(16.0)
            p.set_wait_agent(True)
            p.play()
            await self._settle()
            while p.status != PlayerStatus.FINISHED:
                if p.status == PlayerStatus.RUNNING:
                    p.advance(STEP_S)
                await self._settle()
                if p.status == PlayerStatus.PAUSED and p._waiting_for:
                    self.forced_resumes += 1  # el monitor no contestó: como una espera agotada
                    p._stop_waiting()
            await self._settle()
        finally:
            await self.module.stop()
        folder = p.runs_dir / name / RUN_ID
        self.bus.timeline.dump(folder / "timeline.jsonl")  # con lo publicado tras el fin
        return folder


def table_rows(folder: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = folder / "llm_trace.jsonl"
    if not path.exists():  # sin detecciones, el monitor no escribe trazas
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for entry in record.get("table") or []:
            rows.append(entry)
    return rows


def summarize(name: str, family: str, folder: Path, ev: Any, wall_s: float, forced: int) -> dict:
    data = ev.data
    trace = data.trace
    labels = []
    for r in ev.results:
        lb = r.label
        first_det = r.first_detection.event["sim_time"] if r.first_detection else None
        first_alert = r.first_alert["sim_time"] if r.first_alert else None
        causes = sorted({i.cause() for i in r.raised})
        labels.append({
            "id": lb.id, "type": lb.type.value, "verdict": r.verdict,
            "detected": bool(r.raised), "causes": causes,
            "detection_delay_s": None if first_det is None else round(first_det - lb.start_s, 1),
            "diagnosis_delay_s": None if first_det is None or first_alert is None
            else round(first_alert - first_det, 1),
            "chains": r.chains,
        })  # fmt: skip
    rows = table_rows(folder)
    return {
        "name": name,
        "family": family,
        "labels": labels,
        "false_alarms": len(ev.stray_detections) + len(ev.stray_alerts) + ev.unlabeled_false,
        "stray": [f"{i.detection_id} {i.rule}" for i in ev.stray_detections]
        + [f"{a['payload']['alert_id']} {a['payload']['cause']}" for a in ev.stray_alerts],
        "unlabeled": [
            {
                "id": u.episode.id,
                "detections": len(u.detections),
                "alerts": [a["payload"]["cause"] for a in u.alerts],
                "false": len(u.false_alerts),
            }
            for u in ev.unlabeled
        ],  # fmt: skip
        "rejections": sum(len(t.get("guardrail_rejections") or []) for t in trace),
        "fallbacks": ev.fallbacks,
        "unanswered": len(ev.unanswered),
        "open_at_end": len(ev.open_alerts),
        "events_after_as_of": sum(t.get("events_after_as_of") or 0 for t in trace),
        "forced_resumes": forced,
        "recovery_misses": None if ev.recovery_misses is None else len(ev.recovery_misses),
        "rows": [r.get("rows", {}).get("cause") for r in rows],
        "ambiguous": [
            {
                "detection": f"{a.item.detection_id} {a.item.rule}",
                "cause": a.cause,
                "candidates": [lb.id for lb in a.item.candidates],
                "strict_label": a.strict_label.id,
                "strict_ok": a.strict_ok,
                "permissive_ok": a.permissive_ok,
            }
            for a in ev.ambiguous
        ],  # fmt: skip
        "wall_s": round(wall_s, 2),
    }


def _ambiguous_text(rs: list[dict[str, Any]]) -> str:
    amb = [a for r in rs for a in r["ambiguous"]]
    if not amb:
        return "0"
    strict = sum(a["strict_ok"] for a in amb)
    permissive = sum(a["permissive_ok"] for a in amb)
    return f"{len(amb)} ({strict} / {permissive})"


def render(results: list[dict[str, Any]], table_hash: str) -> str:
    out = ["# E6 · paso 2b · tabla de decisión fuera de línea sobre las variantes", ""]
    out.append(f"Tabla: `{table_hash[:16]}…` · {len(results)} ejecuciones · perfil `{PROFILE}`.")
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_family[r["family"]].append(r)
    out += ["", "## Por familia", "",
            "| Familia | Ejecuciones | Etiquetas ✅ | ⚠️ | ❌ | ❌ sin detección | 🔀 solo ambiguas "
            "| Avisos ambiguos (estricto ✅ / permisivo ✅) | Falsas alarmas "
            "| Rechazos | Fallbacks | Sin respuesta | Abiertas al final |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for family, rs in by_family.items():
        verdicts = Counter(lb["verdict"] for r in rs for lb in r["labels"])
        undetected = sum(
            1 for r in rs for lb in r["labels"] if lb["verdict"] == "❌" and not lb["detected"]
        )
        out.append(
            f"| {family} | {len(rs)} | {verdicts['✅']} | {verdicts['⚠️']} | {verdicts['❌']} | "
            f"{undetected} | {verdicts['🔀']} | {_ambiguous_text(rs)} | "
            f"{sum(r['false_alarms'] for r in rs)} | "
            f"{sum(r['rejections'] for r in rs)} | {sum(r['fallbacks'] for r in rs)} | "
            f"{sum(r['unanswered'] for r in rs)} | {sum(r['open_at_end'] for r in rs)} |"
        )
    rows = Counter(row for r in results for row in r["rows"])
    out += [
        "",
        "## Filas de causa que se disparan",
        "",
        " · ".join(f"{k}: {v}" for k, v in sorted(rows.items(), key=lambda x: str(x[0]))),
    ]
    out += ["", "## Por ejecución", "",
            "| Ejecución | Etiqueta | Veredicto | Causas | Retraso detección (s) "
            "| Retraso diagnóstico (s) | Cadenas | Falsas alarmas | Filas |",
            "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in results:
        rowtext = " ".join(str(x) for x in r["rows"])
        if not r["labels"]:
            extra = "; ".join(
                f"{u['id']}: {u['detections']} avisos, alertas {u['alerts'] or '—'}"
                for u in r["unlabeled"]
            )
            out.append(f"| {r['name']} | — {extra} | | | | | | {r['false_alarms']} | {rowtext} |")
        for i, lb in enumerate(r["labels"]):
            fa = r["false_alarms"] if i == 0 else ""
            out.append(
                f"| {r['name']} | {lb['id']} {lb['type']} | {lb['verdict']} | "
                f"{', '.join(lb['causes']) or '—'} | {lb['detection_delay_s']} | "
                f"{lb['diagnosis_delay_s']} | {lb['chains']} | {fa} | "
                f"{rowtext if i == 0 else ''} |"
            )
    amb = [(r["name"], a) for r in results for a in r["ambiguous"]]
    out += ["", "## Avisos ambiguos (aparte: no cuentan en los veredictos)", ""]
    out += [
        f"- {n}: {a['detection']} → {a['cause']} · candidatas {', '.join(a['candidates'])} · "
        f"estricto ({a['strict_label']}) {'✅' if a['strict_ok'] else '❌'} · "
        f"permisivo {'✅' if a['permissive_ok'] else '❌'}"
        for n, a in amb
    ] or ["Ninguno."]
    stray = [(r["name"], s) for r in results for s in r["stray"]]
    out += ["", "## Falsas alarmas", ""]
    out += [f"- {n}: {s}" for n, s in stray] or ["Ninguna."]
    keys = ("events_after_as_of", "forced_resumes", "rejections", "fallbacks")
    checks = {k: sum(r[k] for r in results) for k in keys}
    out += ["", "## Comprobaciones", ""] + [f"- `{k}`: {v}" for k, v in checks.items()]
    return "\n".join(out) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    index = {}
    index_path = args.scenarios.parent / "variants.json"
    if index_path.exists():
        index = {v["name"]: v["family"] for v in json.loads(index_path.read_text("utf-8"))}
    names = args.only or list_scenarios(args.scenarios)
    if args.family:
        names = [n for n in names if index.get(n) in args.family]
    results = []
    table_hash = ""
    for name in names:
        t0 = time.perf_counter()
        run = OfflineRun(args.scenarios, args.runs)
        folder = await run.run(name)
        ev = write_evaluation(folder)
        table_hash = run.module.monitor.tables.sha256 if run.module.monitor.tables else ""
        r = summarize(name, index.get(name, "base"), folder, ev,
                      time.perf_counter() - t0, run.forced_resumes)  # fmt: skip
        results.append(r)
        verdicts = " ".join(f"{lb['id']}{lb['verdict']}" for lb in r["labels"]) or "sin etiquetas"
        print(f"{name:34} {verdicts:24} falsas {r['false_alarms']} · {r['wall_s']:.1f} s",
              flush=True)  # fmt: skip
    if args.out:
        args.out.write_text(render(results, table_hash), encoding="utf-8")
        args.out.with_suffix(".json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"resumen en {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=VARIANTS / "scenarios")
    parser.add_argument("--runs", type=Path, default=VARIANTS / "runs")
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--family", nargs="*", default=None)
    parser.add_argument("--out", type=Path, default=None)
    return asyncio.run(main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
