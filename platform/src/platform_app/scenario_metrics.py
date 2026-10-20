"""Mide sobre `runs/<escenario>/` los criterios de aceptación de `scenarios/README.md`.

ATENCIÓN: este módulo lee `truth.json` y `labels.json` (la verdad del vuelo). Es solo para
las pruebas del generador y la evaluación; vive fuera de `tools/` y nada de lo que usan las
tools de datos lo importa (el agente nunca ve la verdad).

Uso: `uv run python -m platform_app.scenario_metrics [--all | nombre …]` imprime la tabla
Markdown «escenario → criterio → valor medido».
"""

import argparse
import json
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

from poc_contracts.enums import LabelType
from poc_contracts.run_files import Label, LabelsFile, PlanFile, TruthFile

from .geometry import Point, distance_to_route
from .paths import RUNS_DIR

Series = list[tuple[float, float]]

DEVIATION_LIMIT_M = 15.0  # desviación admitida en vuelo normal (esquinas incluidas)
DISCREPANCY_LIMIT_M = 20.0  # distancia GPS–radar (media móvil de 3) admitida sin anomalía
MEAN_MEMORY_S = 6.0  # la media móvil de 3 radares recuerda ~4 s: margen tras cada ventana
MAX_INTERP_GAP_S = 3.0  # no se interpola el GPS a través de un hueco mayor
NORMAL_LINK_ID = "GCS-1"
JUMP_MIN_M = 40.0  # salto mínimo del GPS cuando acaba el spoofing
HIJACK_MIN_M = 300.0  # «cientos de metros»


@dataclass(frozen=True)
class Check:
    scenario: str
    criterion: str
    value: str
    ok: bool


@dataclass(frozen=True)
class RunData:
    name: str
    plan: PlanFile
    truth: TruthFile
    labels: list[Label]
    events: list[dict]

    @property
    def route(self) -> list[Point]:
        return [(w.x, w.y) for w in self.plan.waypoints]

    def of_type(self, event_type: str) -> list[dict]:
        return [e for e in self.events if e["type"] == event_type]

    def positions(self, event_type: str) -> list[tuple[float, float, float]]:
        """(sim_time, x, y) de `PositionUpdated` (GPS) o `TrackUpdated` (radar)."""
        return [
            (e["sim_time"], e["payload"]["x"], e["payload"]["y"]) for e in self.of_type(event_type)
        ]


def load_run(name: str, runs_dir: Path = RUNS_DIR) -> RunData:
    d = runs_dir / name
    lines = (d / "events.jsonl").read_text("utf-8").splitlines()
    return RunData(
        name,
        PlanFile.model_validate_json((d / "plan.json").read_text("utf-8")),
        TruthFile.model_validate_json((d / "truth.json").read_text("utf-8")),
        LabelsFile.model_validate_json((d / "labels.json").read_text("utf-8")).labels,
        [json.loads(line) for line in lines],
    )


# --- series ---------------------------------------------------------------------------------


def truth_deviation(run: RunData) -> Series:
    """Distancia de la verdad a la ruta, cada segundo."""
    return [(s.t, distance_to_route((s.x, s.y), run.route)) for s in run.truth.trajectory]


def reported_deviation(run: RunData, event_type: str) -> Series:
    """Distancia a la ruta de lo que reporta el GPS (`PositionUpdated`) o el radar."""
    return [(t, distance_to_route((x, y), run.route)) for t, x, y in run.positions(event_type)]


def _gps_at(gps: list[tuple[float, float, float]], t: float) -> Point | None:
    """Posición del GPS en `t` por interpolación lineal; `None` si hay un hueco."""
    i = bisect_left([s[0] for s in gps], t)
    if i == 0 or i == len(gps):
        return None
    (t0, x0, y0), (t1, x1, y1) = gps[i - 1], gps[i]
    if t1 - t0 > MAX_INTERP_GAP_S:
        return None
    k = (t - t0) / (t1 - t0)
    return x0 + k * (x1 - x0), y0 + k * (y1 - y0)


def gps_radar_distance(run: RunData) -> Series:
    """Distancia GPS–radar con el GPS interpolado al instante del radar (media de las 3 últimas)."""
    gps = run.positions("PositionUpdated")
    raw: Series = []
    for t, rx, ry in run.positions("TrackUpdated"):
        g = _gps_at(gps, t)
        if g is not None:
            raw.append((t, ((g[0] - rx) ** 2 + (g[1] - ry) ** 2) ** 0.5))
    means: Series = []
    for i, (t, _) in enumerate(raw):
        last = [v for _, v in raw[max(0, i - 2) : i + 1]]
        means.append((t, sum(last) / len(last)))
    return means


def inside(series: Series, a: float, b: float) -> list[float]:
    """Valores con `a <= t < b`."""
    return [v for t, v in series if a <= t < b]


def outside(series: Series, windows: list[tuple[float, float]]) -> list[float]:
    return [v for t, v in series if not any(a <= t <= b for a, b in windows)]


def recovery_time(dev: Series, after_s: float, until_s: float | None = None) -> float | None:
    """Primer instante tras `after_s` desde el que la verdad queda a < 15 m hasta `until_s`.

    Sin `until_s`, hasta el final del vuelo. `None` si no llega a recuperar la ruta.
    """
    tail = [(t, v) for t, v in dev if t > after_s and (until_s is None or t <= until_s)]
    last_bad = max((t for t, v in tail if v >= DEVIATION_LIMIT_M), default=None)
    if last_bad is None:
        return tail[0][0] if tail else None
    return next((t for t, _ in tail if t > last_bad), None)


# --- criterios ------------------------------------------------------------------------------


class _Checks:
    """Acumula las comprobaciones de un escenario."""

    def __init__(self, run: RunData) -> None:
        self.run = run
        self.items: list[Check] = []

    def add(self, criterion: str, value: str, ok: bool) -> None:
        self.items.append(Check(self.run.name, criterion, value, ok))

    def recovery(self, label: Label, dev: Series, until_s: float | None) -> None:
        """La verdad vuelve a la ruta antes de la siguiente anomalía (o del fin del vuelo)."""
        t_r = recovery_time(dev, label.end_s, until_s)
        what = f"{label.id}: recupera la ruta (< {DEVIATION_LIMIT_M:.0f} m) antes de la siguiente"
        if t_r is None:
            self.add(what, "no la recupera", False)
        else:
            self.add(what, f"T+{t_r:.0f} s ({t_r - label.end_s:.0f} s tras el fin)", True)

    def completes(self) -> None:
        done = self.run.of_type("MissionCompleted")[-1]["payload"]
        ok = done["completed"] and done["reason"] == "returned_to_base"
        end = self.run.truth.duration_s
        self.add("la misión se completa", f"{done['reason']} a T+{end:.0f} s", ok)


def _nominal(c: _Checks, dev: Series) -> None:
    gps = reported_deviation(c.run, "PositionUpdated")
    truth_max, gps_max = max(v for _, v in dev), max(v for _, v in gps)
    limit = DEVIATION_LIMIT_M
    c.add(
        f"desviación de la verdad respecto al plan < {limit:.0f} m",
        f"{truth_max:.1f} m",
        truth_max < limit,
    )
    c.add(
        f"desviación del GPS respecto al plan < {limit:.0f} m", f"{gps_max:.1f} m", gps_max < limit
    )


def _wind(c: _Checks, label: Label, dev: Series, disc: Series, until_s: float | None) -> None:
    peak = max(inside(dev, label.start_s, label.end_s + 30))
    c.add(
        f"{label.id} viento: desviación máx. de la verdad (episodio + 30 s), 40–120 m",
        f"{peak:.1f} m",
        40 <= peak <= 120,
    )
    worst = max(inside(disc, label.start_s, label.end_s))
    c.add(
        f"{label.id} viento: GPS y radar coinciden en el episodio (< {DISCREPANCY_LIMIT_M:.0f} m)",
        f"{worst:.1f} m",
        worst < DISCREPANCY_LIMIT_M,
    )
    c.recovery(label, dev, until_s)


def _spoofing(c: _Checks, label: Label, dev: Series, until_s: float | None) -> None:
    a, b = label.start_s, label.end_s
    gps_max = max(inside(reported_deviation(c.run, "PositionUpdated"), a, b))
    c.add(
        f"{label.id} spoofing: GPS a < {DEVIATION_LIMIT_M:.0f} m del plan durante el engaño",
        f"{gps_max:.1f} m",
        gps_max < DEVIATION_LIMIT_M,
    )
    peak = max(inside(dev, a, b))
    c.add(
        f"{label.id} spoofing: la verdad se aleja 70–90 m al final del engaño",
        f"{peak:.1f} m",
        70 <= peak <= 90,
    )
    truth_end = inside(dev, b - 10, b)
    radar_end = inside(reported_deviation(c.run, "TrackUpdated"), b - 10, b)
    truth_mean, radar_mean = sum(truth_end) / len(truth_end), sum(radar_end) / len(radar_end)
    c.add(
        f"{label.id} spoofing: el radar ve lo mismo que la verdad (media 10 s, ±8 m)",
        f"radar {radar_mean:.1f} m, verdad {truth_mean:.1f} m",
        abs(radar_mean - truth_mean) < 8,
    )
    gps_pos = c.run.positions("PositionUpdated")
    before = [p for p in gps_pos if p[0] < b][-1]
    after = next(p for p in gps_pos if p[0] >= b)
    jump = ((after[1] - before[1]) ** 2 + (after[2] - before[2]) ** 2) ** 0.5
    c.add(
        f"{label.id} spoofing: el GPS salta al terminar el engaño (> {JUMP_MIN_M:.0f} m)",
        f"{jump:.1f} m",
        jump > JUMP_MIN_M,
    )
    c.recovery(label, dev, until_s)


def _hijack(c: _Checks, label: Label, dev: Series, until_s: float | None) -> None:
    a, b = label.start_s, label.end_s
    peak = max(inside(dev, a, b + 5))
    c.add(
        f"{label.id} secuestro: la verdad se aleja cientos de metros (> {HIJACK_MIN_M:.0f} m)",
        f"{peak:.1f} m",
        peak > HIJACK_MIN_M,
    )
    gps_max = max(inside(reported_deviation(c.run, "PositionUpdated"), a, b + 5))
    c.add(
        f"{label.id} secuestro: el GPS lo acompaña (> {HIJACK_MIN_M:.0f} m)",
        f"{gps_max:.1f} m",
        gps_max > HIJACK_MIN_M,
    )
    links = c.run.of_type("LinkStatus")
    changed = [e["sim_time"] for e in links if e["payload"]["controller_id"] != NORMAL_LINK_ID]
    expected = [e["sim_time"] for e in links if a <= e["sim_time"] < b]
    c.add(
        f"{label.id} secuestro: LinkStatus cambia de controlador solo durante el secuestro",
        f"{len(changed)} eventos, T+{min(changed):.0f}–{max(changed):.0f} s",
        changed == expected,
    )
    c.recovery(label, dev, until_s)


def _faults(c: _Checks, labels: list[Label]) -> None:
    run = c.run
    for f in labels:
        etype = {"gps": "PositionUpdated", "radar": "TrackUpdated"}[f.source.value]
        left = [e for e in run.of_type(etype) if f.start_s <= e["sim_time"] < f.end_s]
        marks = {
            e["type"]: e["sim_time"]
            for e in run.events
            if e["type"] in ("FaultInjected", "FaultCleared")
            and e["payload"] == {"source": f.source.value, "origin": "scenario"}
        }
        ok = not left and marks == {"FaultInjected": f.start_s, "FaultCleared": f.end_s}
        span = f"[{f.start_s:.0f}, {f.end_s:.0f})"
        what = f"{f.id} fallo: sin {etype} en {span} y con FaultInjected/Cleared"
        c.add(what, f"{len(left)} eventos dentro; marcas en {list(marks.values())}", ok)


def _same_as_nominal(c: _Checks, nominal: RunData) -> None:
    same_truth = c.run.truth == nominal.truth
    c.add(
        "trayectoria idéntica a nominal (truth.json)",
        "idéntica" if same_truth else "distinta",
        same_truth,
    )
    sensors = {"PositionUpdated", "TrackUpdated", "WindReported", "LinkStatus", "BatteryStatus"}
    mine = {e["event_id"]: e for e in c.run.events if e["type"] in sensors}
    theirs = {e["event_id"]: e for e in nominal.events if e["type"] in sensors}
    ok = set(mine) <= set(theirs) and all(mine[i] == theirs[i] for i in mine)
    c.add(
        "resto de eventos de fuentes idéntico a nominal (solo faltan los silenciados)",
        f"{len(set(theirs) - set(mine))} silenciados",
        ok,
    )


def _demo_order(c: _Checks, anomalies: list[Label]) -> None:
    kinds = [lb.type.value for lb in anomalies]
    gaps = [b.start_s - a.end_s for a, b in zip(anomalies, anomalies[1:], strict=False)]
    ok = kinds == ["wind", "gps_spoofing", "hijack"] and all(g > 0 for g in gaps)
    c.add(
        "anomalías en orden viento → spoofing → secuestro, sin solaparse",
        f"{' → '.join(kinds)}; huecos {', '.join(f'{g:.0f} s' for g in gaps)}",
        ok,
    )


def run_checks(name: str, runs_dir: Path = RUNS_DIR) -> list[Check]:
    """Todos los criterios aplicables al escenario `name` (según sus etiquetas)."""
    run = load_run(name, runs_dir)
    c = _Checks(run)
    dev, disc = truth_deviation(run), gps_radar_distance(run)
    anomalies = sorted(
        (lb for lb in run.labels if lb.type != LabelType.SOURCE_SILENT), key=lambda lb: lb.start_s
    )
    faults = [lb for lb in run.labels if lb.type == LabelType.SOURCE_SILENT]

    if not anomalies:
        _nominal(c, dev)
    for i, label in enumerate(anomalies):
        until_s = anomalies[i + 1].start_s if i + 1 < len(anomalies) else None
        if label.type == LabelType.WIND:
            _wind(c, label, dev, disc, until_s)
        elif label.type == LabelType.GPS_SPOOFING:
            _spoofing(c, label, dev, until_s)
        else:
            _hijack(c, label, dev, until_s)
    if len(anomalies) > 1:
        _demo_order(c, anomalies)
    if faults:
        _faults(c, faults)
        _same_as_nominal(c, load_run("nominal", runs_dir))

    windows = [(lb.start_s, lb.end_s + MEAN_MEMORY_S) for lb in run.labels]
    quiet = max(outside(disc, windows))
    c.add(
        f"GPS–radar (media móvil de 3) fuera de las ventanas < {DISCREPANCY_LIMIT_M:.0f} m",
        f"{quiet:.1f} m",
        quiet < DISCREPANCY_LIMIT_M,
    )
    c.completes()
    return c.items


def markdown_table(checks: list[Check]) -> str:
    rows = ["| Escenario | Criterio | Valor medido | OK |", "|---|---|---|---|"]
    rows += [
        f"| `{k.scenario}` | {k.criterion} | {k.value} | {'✅' if k.ok else '❌'} |" for k in checks
    ]
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--all", action="store_true", help="todos los de runs/ (por defecto)")
    args = parser.parse_args()
    names = args.names or sorted(
        p.name for p in RUNS_DIR.iterdir() if (p / "events.jsonl").exists()
    )
    print(markdown_table([k for name in names for k in run_checks(name)]))


if __name__ == "__main__":
    main()
