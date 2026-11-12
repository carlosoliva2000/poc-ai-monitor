"""Equivalencia de dos ejecuciones del monitor (Fase 15.1): mismas decisiones con y sin «esperar al
agente».

    uv run --project ai-module-py python tools/experiments/equivalence.py <ejec_A> <ejec_B>

Cada argumento es una carpeta de ejecución (`timeline.jsonl` y `llm_trace.jsonl`). Compara, para
cada respuesta del monitor y en orden, **qué decidió** (alerta con causa, severidad, fase,
`supersedes` y fallback; cierre; reconocimiento) y a qué instante de partida (`as_of_sim_time`), no
los textos, que pueden variar. Cuenta también los eventos de tools de datos posteriores al `as_of`
de cada invocación (`events_after_as_of`, debe ser 0). Sale con 0 si las decisiones coinciden.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

Decision = tuple[Any, ...]


def read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def decisions(timeline: list[dict[str, Any]]) -> list[Decision]:
    """Lo que decidió el monitor, en orden, sin textos ni ids: `(tipo, as_of, …)`."""
    out: list[Decision] = []
    alerts = {e["event_id"]: e["payload"] for e in timeline if e["type"] == "AnomalyDetected"}
    for e in timeline:
        p = e["payload"]
        if e["type"] == "AnomalyDetected":
            out.append(
                (
                    "alert",
                    round(p["as_of_sim_time"], 1),
                    p["cause"],
                    p["severity"],
                    p["phase"],
                    p["supersedes"] is not None,
                    bool(p["fallback"]),
                )  # fmt: skip
            )
        elif e["type"] == "AlertClosed":
            out.append(("closed", round(p["as_of_sim_time"], 1)))
        elif e["type"] == "DetectionAcknowledged":
            target = alerts.get(p["alert_id"], {}).get("cause") if p.get("alert_id") else None
            out.append(("ack", round(p["as_of_sim_time"], 1), target, bool(p["fallback"])))
    return out


def late_events(trace: list[dict[str, Any]]) -> int:
    return sum(r.get("events_after_as_of", 0) for r in trace)


def compare(a: Path, b: Path) -> tuple[list[str], list[str]]:
    """`(líneas del informe, diferencias)`."""
    da, db = decisions(read(a / "timeline.jsonl")), decisions(read(b / "timeline.jsonl"))
    lines = [
        f"A: {a} · {len(da)} decisiones · eventos posteriores al as_of: "
        f"{late_events(read(a / 'llm_trace.jsonl'))}",
        f"B: {b} · {len(db)} decisiones · eventos posteriores al as_of: "
        f"{late_events(read(b / 'llm_trace.jsonl'))}",
    ]
    diffs = []
    for i in range(max(len(da), len(db))):
        left = da[i] if i < len(da) else None
        right = db[i] if i < len(db) else None
        mark = "=" if left == right else "≠"
        lines.append(f"{i + 1:>3} {mark} A {left}  |  B {right}")
        if left != right:
            diffs.append(f"decisión {i + 1}: A {left} · B {right}")
    return lines, diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args(argv)
    lines, diffs = compare(args.a, args.b)
    print("\n".join(lines))
    print(f"\n{'IGUALES' if not diffs else f'{len(diffs)} DIFERENCIAS'}")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
