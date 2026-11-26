# ruff: noqa: E501
"""Medida APROXIMADA de la hipótesis del asistente (fuera de línea).

Hay muy pocos «sin determinar» reales. Aquí se toman desviaciones de causa conocida (viento,
engaño, secuestro, estima) de variantes de la E7b, se quita de la entrada todo lo que nombra la
causa (el tipo del incidente, las facetas de causa y de modo, sus evidencias y su contexto) y se
pide la hipótesis con el mismo prompt. Se mide si la primera causa acierta y si los `checks`
incluyen la fuente que distingue la causa verdadera. **No es la entrada de un «sin determinar» de
verdad** (ahí las tablas dudaban entre causas): es una aproximación y va aparte.

    uv run --project ai-module-py python tools/assistant/hypothesis_approx.py <id> <dataset> <split> <por_causa>
"""

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "situation"))
sys.path.insert(0, str(REPO / "tools" / "assistant"))

from lib import variant_monitor  # noqa: E402
from texts import OUT, percentile, read_states, target_store  # noqa: E402

from ai_module.assistant.config import load_config  # noqa: E402
from ai_module.assistant.interpret import Interpreter  # noqa: E402
from ai_module.assistant.llm import VllmClient  # noqa: E402
from ai_module.outbox import format_t  # noqa: E402
from ai_module.situation.policy import load_policy  # noqa: E402
from ai_module.situation.replay import is_world, read_events  # noqa: E402
from poc_contracts.enums import IncidentKind  # noqa: E402

DATA = REPO / "experiments" / "e7b"
# Causa verdadera (drone.cause de la verdad) -> tipo de incidente que la nombra
CAUSE_KIND = {"wind": "WIND", "spoofed_position": "GPS_SPOOFING", "foreign_control": "HIJACK",
              "dead_reckoning": "DEAD_RECKONING"}  # fmt: skip
# La fuente que distingue cada causa de las demás (lo que un buen «qué comprobar» incluye)
DISCRIMINATOR = {
    "WIND": {"meteo", "autopilot"},
    "GPS_SPOOFING": {"radar", "receiver"},
    "HIJACK": {"link", "radar"},
    "DEAD_RECKONING": {"gps", "autopilot"},
}
CAUSE_FACETS = {"drone.cause", "drone.mode", "gps.integrity", "link.availability",
                "environment.wind", "gps.availability"}  # fmt: skip


def blind(update: dict) -> dict:
    """La misma revisión sin nada que nombre la causa, como un «sin determinar»."""
    policy = load_policy()
    return {
        **update, "incident_id": "inc-approx", "revision": 1, "kind": "UNDETERMINED",
        "name": "Undetermined deviation", "state": "open", "change": "opened",
        "severity": "medium", "confidence": "possible",
        "evidence": [e for e in update["evidence"] if e["facet"] not in CAUSE_FACETS],
        "context": [c for c in update["context"] if c["feature"] == "deviation_source"],
        "checks": policy.kinds[IncidentKind.UNDETERMINED].checks,
    }  # fmt: skip


async def main() -> None:
    run_id, dataset, split, per_cause = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    index = json.loads((DATA / dataset / "index.json").read_text())
    names = [v["name"] for v in index if v["split"] == split]
    config = load_config()
    client = VllmClient(config.llm)
    await client.check_model()
    interpreter = Interpreter(config, client)
    taken: dict[str, int] = defaultdict(int)
    records: list[dict] = []
    for name in names:
        if all(taken[k] >= per_cause for k in DISCRIMINATOR):
            break
        folder = DATA / dataset / "variants" / name
        states = read_states(folder / "states.jsonl.gz")
        monitor, store, done = variant_monitor(folder), target_store(f"{dataset}/{name}"), set()
        for raw in read_events(folder / "events.jsonl.gz"):
            if not is_world(raw):
                continue
            store.observe(raw)
            for _, upd in monitor.push(raw):
                facets = states.get(int(upd["as_of_sim_time"]), {})
                truth = CAUSE_KIND.get(facets.get("drone.cause", ""))
                key = (name, upd["incident_id"])
                if (
                    key in done or upd["kind"] != truth or taken[truth] >= per_cause
                    or facets.get("drone.situation") != "deviated"
                ):  # fmt: skip
                    continue
                done.add(key)
                taken[truth] += 1
                out = await interpreter.interpret(blind(upd), store)
                if out is None:
                    continue
                ranked = [c["kind"] for c in (out.hypothesis or {}).get("ranked", [])]
                targets = {c["target"] for c in (out.hypothesis or {}).get("checks", [])}
                records.append(
                    {
                        "variant": name,
                        "t": upd["as_of_sim_time"],
                        "truth": truth,
                        "published": out.text is not None,
                        "ranked": ranked,
                        "targets": sorted(targets),
                        "text": out.text,
                        "reasons": out.reasons,
                        "latency_s": round(out.latency_s, 2),
                        "input": out.input_text,
                    }  # fmt: skip
                )
                print(
                    name,
                    format_t(upd["as_of_sim_time"]),
                    truth,
                    ranked[:3],
                    sorted(targets),
                    flush=True,
                )
    (OUT / f"{run_id}.json").write_text(json.dumps(records, indent=1))
    (OUT / f"{run_id}.md").write_text(report(records, interpreter), encoding="utf-8")


def report(records: list[dict], interpreter: Interpreter) -> str:
    lines = ["# Hipótesis: medida aproximada (causa quitada de la entrada)", "",
             "**Es una aproximación, no la medida de la E8**: la entrada es la de una desviación de "
             "causa conocida con todo lo que nombra la causa quitado, no la de un «sin determinar» "
             "de verdad (ahí las tablas dudaban). Va separada de los casos reales.", "",
             f"Modelo: {interpreter.config.llm.model}. Casos: {len(records)}.", "",
             "| Causa verdadera | casos | con hipótesis publicada | primera acierta | está entre las tres | checks con la fuente que distingue |",
             "|---|---|---|---|---|---|"]  # fmt: skip
    for cause in DISCRIMINATOR:
        rows = [r for r in records if r["truth"] == cause]
        if not rows:
            continue
        pub = [r for r in rows if r["published"] and r["ranked"]]
        first = sum(r["ranked"][0] == cause for r in pub)
        top3 = sum(cause in r["ranked"] for r in pub)
        check = sum(bool(set(r["targets"]) & DISCRIMINATOR[cause]) for r in pub)
        lines.append(f"| {cause} | {len(rows)} | {len(pub)} | {first} | {top3} | {check} |")
    pub_all = [r for r in records if r["published"] and r["ranked"]]
    if pub_all:
        first_all = sum(r["ranked"][0] == r["truth"] for r in pub_all)
        lines += ["", f"Total con hipótesis publicada: {len(pub_all)} de {len(records)}; la primera acierta "
                  f"{first_all} ({100 * first_all / len(pub_all):.0f} %). Línea base: elegir siempre la "
                  "causa más frecuente de la muestra."]  # fmt: skip
        counts = Counter(r["truth"] for r in records)
        lines.append(f"Reparto de causas: {dict(counts)}.")
        lat = [r["latency_s"] for r in records]
        lines.append(
            f"Latencia: mediana {sorted(lat)[len(lat) // 2]:.1f} s, p90 {percentile(lat, 0.9):.1f} s."
        )
        confusion: Counter[tuple[str, str]] = Counter((r["truth"], r["ranked"][0]) for r in pub_all)
        lines += [
            "",
            "## Matriz (verdad → primera causa)",
            "",
            "| verdad | primera | veces |",
            "|---|---|---|",
        ]
        lines += [f"| {t} | {p} | {n} |" for (t, p), n in sorted(confusion.items())]
    lines += ["", "## Rechazos", ""]
    reasons = Counter(x.split(":")[0] for r in records for x in r["reasons"])
    lines += [f"- {k}: {v}" for k, v in reasons.most_common()] or ["- ninguno"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main())
