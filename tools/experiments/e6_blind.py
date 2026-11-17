"""Comparación a ciegas de la E6: alertas de L frente a las de H sobre los mismos avisos.

    uv run --project ai-module-py python tools/experiments/e6_blind.py \\
        --runs-root experiments/e6-reservado-generado --out experiments/e6-ciego \\
        L=experiments/e6-reservado-l:actual:1 H=experiments/e6-reservado-th:hybrid

Empareja, en cada escenario, la alerta (`AnomalyDetected`) con la que cada fuente respondió al
mismo aviso del detector (misma regla y mismo instante; el detector es determinista) y elige
`--n` parejas (20 por defecto) con una semilla fija, repartidas por escenario por turnos. Escribe:

- `pares.md`: cada pareja con sus dos alertas como «A» y «B», en orden barajado. Cada alerta
  muestra causa, severidad, confianza, resumen, explicación y recomendación; en H, la
  interpretación publicada (`AlertEnriched`) va al final de la explicación, para que el formato
  no delate de dónde viene. Sin ids de alerta, filas de la tabla ni `decided_by`.
- `clave.json`: qué fuente es «A» y cuál «B» en cada pareja (aparte: no abrir antes de puntuar).
"""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SEED = 6


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def runs_of(spec: str, runs_root: Path) -> tuple[str, dict[str, Path]]:
    name, _, rest = spec.partition("=")
    parts = rest.split(":")
    matrix, profile = REPO / parts[0], parts[1]
    rep = int(parts[2]) if len(parts) > 2 else 1
    manifest = json.loads((matrix / "manifest.json").read_text(encoding="utf-8"))
    return name, {
        r["scenario"]: runs_root / r["scenario"] / r["run_id"]
        for r in manifest["runs"]
        if r["profile"] == profile and r["rep"] == rep and r.get("status") == "ok"
    }


def alerts_by_warning(folder: Path) -> dict[tuple[str, float], dict[str, Any]]:
    """(regla, instante) del aviso → su primera alerta, con la interpretación si la hay."""
    events = read_jsonl(folder / "timeline.jsonl")
    warnings = {
        e["event_id"]: (e["payload"]["rule"], e["sim_time"])
        for e in events
        if e["type"] in ("DetectionRaised", "DetectionUpdated")
    }
    enriched = {
        e["payload"]["alert_id"]: e["payload"]["text"]
        for e in events
        if e["type"] == "AlertEnriched"
    }
    out: dict[tuple[str, float], dict[str, Any]] = {}
    for e in events:
        if e["type"] != "AnomalyDetected" or e["causation_id"] not in warnings:
            continue
        key = warnings[e["causation_id"]]
        if key not in out:
            out[key] = {**e["payload"], "interpretation": enriched.get(e["payload"]["alert_id"])}
    return out


def alert_text(alert: dict[str, Any]) -> list[str]:
    explanation = alert["explanation"]
    if alert.get("interpretation"):
        explanation = f"{explanation} {alert['interpretation']}"
    return [
        f"- **Cause:** {alert['cause']} · **severity:** {alert['severity']} · "
        f"**confidence:** {alert['confidence']:g}",
        f"- **Summary:** {alert['summary']}",
        f"- **Explanation:** {explanation}",
        f"- **Recommendation:** {alert['recommendation']}",
    ]


def pick(pairs: dict[str, list[tuple[str, float]]], n: int, rng: random.Random) -> list:
    """Hasta `n` parejas, por turnos entre escenarios (cada uno barajado con la semilla)."""
    queues = {s: rng.sample(keys, len(keys)) for s, keys in sorted(pairs.items()) if keys}
    chosen: list[tuple[str, tuple[str, float]]] = []
    while len(chosen) < n and any(queues.values()):
        for scenario, queue in queues.items():
            if queue and len(chosen) < n:
                chosen.append((scenario, queue.pop(0)))
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs=2, help="nombre=carpeta:perfil[:repetición] (dos)")
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args(argv)
    (name_a, runs_a), (name_b, runs_b) = (
        runs_of(s, args.runs_root.resolve()) for s in args.sources
    )
    alerts = {name_a: {}, name_b: {}}
    pairs: dict[str, list[tuple[str, float]]] = {}
    for scenario in sorted(set(runs_a) & set(runs_b)):
        a, b = alerts_by_warning(runs_a[scenario]), alerts_by_warning(runs_b[scenario])
        alerts[name_a][scenario], alerts[name_b][scenario] = a, b
        pairs[scenario] = sorted(set(a) & set(b), key=lambda k: (k[1], k[0]))
    rng = random.Random(SEED)
    chosen = pick(pairs, args.n, rng)
    rng.shuffle(chosen)
    lines = [
        "# E6 · Comparación a ciegas",
        "",
        "Cada pareja son dos alertas sobre el mismo aviso del detector, escritas por dos monitores "
        "distintos. Puntúa cada una (por ejemplo, de 1 a 5: correcta, clara y útil para quien "
        "vigila el dron) **antes** de abrir `clave.json`.",
    ]
    key: dict[str, dict[str, str]] = {}
    for number, (scenario, (rule, t)) in enumerate(chosen, 1):
        order = [name_a, name_b]
        rng.shuffle(order)
        key[f"P{number:02d}"] = {"A": order[0], "B": order[1], "scenario": scenario}
        lines += ["", f"## P{number:02d} · {rule} a T+{int(t) // 60:02d}:{int(t) % 60:02d}", ""]
        for letter, source in zip("AB", order, strict=True):
            lines += [f"**{letter}**", "", *alert_text(alerts[source][scenario][(rule, t)]), ""]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "pares.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out / "clave.json").write_text(
        json.dumps({"seed": SEED, "pairs": key}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{len(chosen)} parejas → {args.out / 'pares.md'} (clave: {args.out / 'clave.json'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
