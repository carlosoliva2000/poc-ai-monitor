# ruff: noqa: E501
"""Textos del asistente fuera de línea, con la verdad del escenario al lado (para revisarlos).

Reproduce cada objetivo (un escenario de `runs/` o una variante de la E7b) con el monitor de
situación, pasa cada revisión interpretable al asistente (el mismo núcleo que usa el proceso en
directo, con el vLLM local, de una en una: sin cola) y escribe:
- `experiments/e7d/<id>-textos.md`: texto, hipótesis y verdad de cada revisión;
- `experiments/e7d/<id>.json`: todos los registros (para las medidas);
- `experiments/e7d/<id>-medidas.md`: latencia por papel, rechazos por motivo y cuántos vienen de
  la regla «ahora frente a la apertura».

    uv run --project ai-module-py python tools/assistant/texts.py <id> demo nominal e7b-v3/v0002 ...
"""

import asyncio
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "situation"))
sys.path.insert(0, str(REPO / "tools" / "training"))

from features import variant_assets  # noqa: E402
from lib import variant_monitor  # noqa: E402

from ai_module.assistant.config import load_config  # noqa: E402
from ai_module.assistant.interpret import Interpreter, Outcome, is_interpreted  # noqa: E402
from ai_module.assistant.llm import VllmClient  # noqa: E402
from ai_module.assistant.store import Store  # noqa: E402
from ai_module.ids import IdAllocator  # noqa: E402
from ai_module.outbox import format_t  # noqa: E402
from ai_module.situation.features import load_assets  # noqa: E402
from ai_module.situation.monitor import SituationMonitor  # noqa: E402
from ai_module.situation.replay import is_world, read_events  # noqa: E402

OUT = REPO / "experiments" / "e7d"
DATA = REPO / "experiments" / "e7b"


def read_states(path: Path) -> dict[int, dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return {int(r["t"]): r["facets"] for r in (json.loads(x) for x in handle if x.strip())}


def target_store(target: str) -> Store:
    """El almacén con el receptor nominal de los activos del objetivo (los de su variante)."""
    folder = (
        DATA / target.split("/")[0] / "variants" / target.split("/")[1] if "/" in target else None
    )
    assets = variant_assets(folder) if folder else load_assets()
    return Store(assets.cn0_nominal_dbhz, assets.agc_nominal_db)


def load_target(target: str) -> tuple[SituationMonitor, list[dict], dict, list[dict]]:
    """Monitor, eventos, estados por segundo y anomalías programadas (la verdad)."""
    if "/" in target:
        dataset, name = target.split("/")
        folder = DATA / dataset / "variants" / name
        meta = json.loads((folder / "meta.json").read_text())
        end_of_flight = meta.get("duration_s", 0.0)

        def window(a: dict) -> tuple[float, float]:
            w = a.get("window") or [0.0, end_of_flight]
            return (w[0] if w[0] is not None else 0.0, w[1] if w[1] is not None else end_of_flight)

        truth = [
            {"type": a["family"], "start": window(a)[0], "end": window(a)[1], "params": a["params"]}
            for a in meta["anomalies"]
        ]
        return (variant_monitor(folder), read_events(folder / "events.jsonl.gz"),
                read_states(folder / "states.jsonl.gz"), truth)  # fmt: skip
    folder = REPO / "runs" / target
    labels = json.loads((folder / "labels.json").read_text())["labels"]
    truth = [{"type": x["type"], "start": x["start_s"], "end": x["end_s"],
              "params": {"source": x["source"]}} for x in labels]  # fmt: skip
    return (SituationMonitor(tables="learned"), read_events(folder / "events.jsonl"),
            read_states(folder / "states.jsonl"), truth)  # fmt: skip


def truth_now(t: float, states: dict[int, dict[str, str]], truth: list[dict]) -> str:
    facets = states.get(int(t), {})
    active = [a["type"] for a in truth if a["start"] <= t <= a["end"] + 60]
    return (
        f"cause={facets.get('drone.cause')}, situation={facets.get('drone.situation')}, "
        f"mode={facets.get('drone.mode')}; anomalies in window: {', '.join(active) or 'none'}"
    )


async def run_target(target: str, interpreter: Interpreter, records: list[dict]) -> None:
    monitor, events, states, truth = load_target(target)
    store = target_store(target)
    ids = IdAllocator()
    updates: list[dict[str, Any]] = []

    async def handle(payload: dict[str, Any]) -> None:
        event = {"type": "IncidentUpdated", "event_id": ids.next("ai"),
                 "sim_time": payload["as_of_sim_time"], "payload": payload}  # fmt: skip
        store.observe(event)
        updates.append(payload)
        if not is_interpreted(payload):
            return
        out: Outcome | None = await interpreter.interpret(payload, store)
        if out is None:
            return
        records.append(
            {
                "target": target, "update": payload, "role": out.role, "text": out.text,
                "hypothesis": out.hypothesis, "error": out.error, "reasons": out.reasons,
                "attempts": [a.__dict__ for a in out.attempts],
                "latency_s": round(out.latency_s, 2), "input": out.input_text,
                "truth_now": truth_now(payload["as_of_sim_time"], states, truth),
                "truth": truth,
            }
        )  # fmt: skip
        print(f"{target} {format_t(payload['as_of_sim_time'])} {payload['name']} "
              f"-> {out.role} {out.latency_s:.1f}s {'ok' if out.published else out.reasons}",
              flush=True)  # fmt: skip

    for raw in events:
        if not is_world(raw):
            continue
        store.observe(raw)
        for _, payload in monitor.push(raw):
            await handle(payload)
    for _, payload in monitor.flush():
        await handle(payload)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def measures(records: list[dict], interpreter: Interpreter) -> str:
    lines = ["# Medidas del asistente (fuera de línea, una llamada cada vez)", ""]
    lines.append(f"Modelo: {interpreter.config.llm.model}. Regla ahora/apertura: "
                 f"{interpreter.config.now_rule}. Interpretaciones: {len(records)}.\n")  # fmt: skip
    lines += ["| Papel | llamadas | publicadas | rechazadas | con reintento | latencia mediana (s) | p90 (s) | máx (s) |", "|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for role in ("explain", "hypothesis"):
        rows = [r for r in records if r["attempts"] and r["attempts"][0]]
        mine = [r for r in rows if (r["hypothesis"] is not None) == (role == "hypothesis")
                if r["role"] == role]  # fmt: skip
        if not mine:
            continue
        lat = [a["latency_s"] for r in mine for a in r["attempts"]]
        lines.append(
            f"| {role} | {len(mine)} | {sum(r['text'] is not None for r in mine)} | "
            f"{sum(r['text'] is None for r in mine)} | {sum(len(r['attempts']) > 1 for r in mine)} | "
            f"{statistics.median(lat):.1f} | {percentile(lat, 0.9):.1f} | {max(lat):.1f} |"
        )
    all_lat = [a["latency_s"] for r in records for a in r["attempts"]]
    if all_lat:
        lines.append(
            f"\nLatencia de cada llamada al LLM, todas: mediana {statistics.median(all_lat):.1f} s, "
            f"p90 {percentile(all_lat, 0.9):.1f} s, máx {max(all_lat):.1f} s "
            f"({len(all_lat)} llamadas)."
        )
    reasons = Counter(r.split(":")[0] if not r.startswith("now") else ":".join(r.split(":")[:2])
                      for rec in records for a in rec["attempts"] for r in a["reasons"])  # fmt: skip
    lines += [
        "",
        "## Rechazos por motivo (todos los intentos)",
        "",
        "| Motivo | veces |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in reasons.most_common()] or ["| (ninguno) | 0 |"]
    now_is = sum(1 for rec in records for a in rec["attempts"] for r in a["reasons"]
                 if r.startswith("now:is"))  # fmt: skip
    now_any = sum(1 for rec in records for a in rec["attempts"] for r in a["reasons"]
                  if r.startswith("now"))  # fmt: skip
    attempts = sum(len(r["attempts"]) for r in records)
    lines.append(
        f"\nRegla «ahora frente a la apertura»: {now_any} rechazos de {attempts} intentos "
        f"({now_is} solo por «is/are», {now_any - now_is} por «now/currently»)."
    )
    errors = [r for r in records if r["error"]]
    lines.append(f"Errores del LLM (tiempo o servidor): {len(errors)}.")
    return "\n".join(lines) + "\n"


def textos(records: list[dict]) -> str:
    out = ["# Textos del asistente con la verdad al lado", ""]
    current = None
    for rec in records:
        if rec["target"] != current:
            current = rec["target"]
            truth = (
                "; ".join(
                    f"{a['type']} {format_t(a['start'])}–{format_t(a['end'])} {a['params'] or ''}"
                    for a in rec["truth"]
                )
                or "nothing programmed"
            )
            out += [f"## {current}", "", f"**Programmed in the scenario:** {truth}", ""]
        u = rec["update"]
        out.append(
            f"### {format_t(u['as_of_sim_time'])} · {u['incident_id']} · {u['name']} · "
            f"{u['change']} / {u['state']} · {u['severity']} · {u['confidence']}"
        )
        out.append(f"- **Truth now:** {rec['truth_now']}")
        if rec["text"]:
            out.append(f"- **{rec['role'].capitalize()}** ({rec['latency_s']} s, "
                       f"{len(rec['attempts'])} attempt(s)): {rec['text']}")  # fmt: skip
        else:
            out.append(f"- **No text published** ({rec['error'] or 'rejected'}): "
                       f"{'; '.join(rec['reasons'])}")  # fmt: skip
        if rec["hypothesis"]:
            h = rec["hypothesis"]
            for i, c in enumerate(h["ranked"], 1):
                out.append(
                    f"  - {i}. {c['kind']} — supports: {c['supports']}; missing: {c['missing']}"
                )
            out.append(f"  - checks: {[(c['target'], c['text']) for c in h['checks']]}")
        elif (
            rec["attempts"]
            and rec["reasons"]
            and rec["text"] is None
            and rec["attempts"][-1]["raw"]
        ):
            out.append(f"  - last rejected output: {rec['attempts'][-1]['raw'][:300]}")
        out += [
            "",
            "<details><summary>input</summary>",
            "",
            "```",
            rec["input"],
            "```",
            "</details>",
            "",
        ]
    return "\n".join(out)


async def main() -> None:
    run_id, *targets = sys.argv[1:]
    config = load_config()
    client = VllmClient(config.llm)
    await client.check_model()
    interpreter = Interpreter(config, client)
    records: list[dict] = []
    OUT.mkdir(parents=True, exist_ok=True)
    for target in targets:
        await run_target(target, interpreter, records)
        (OUT / f"{run_id}.json").write_text(json.dumps(records, indent=1, ensure_ascii=False))
    (OUT / f"{run_id}-textos.md").write_text(textos(records), encoding="utf-8")
    (OUT / f"{run_id}-medidas.md").write_text(measures(records, interpreter), encoding="utf-8")
    print(f"written {OUT}/{run_id}-textos.md and -medidas.md")


if __name__ == "__main__":
    asyncio.run(main())
