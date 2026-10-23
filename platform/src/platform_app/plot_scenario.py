"""Gráficas de un escenario generado (`runs/<escenario>/`), sin reproducir nada.

- `plan_xy.png`: solo lo planificado (waypoints y trayectoria con flechas por rumbo y velocidad).
- `scenario_xy.png`: lo planificado en tono claro, la trayectoria real, los puntos de GPS y de radar
  y las zonas de anomalía.
- `scenario_time.png`: en el tiempo, desviación respecto al plan, distancia GPS–radar y viento,
  con las ventanas de `labels.json` sombreadas.

Uso: `uv run python -m platform_app.plot_scenario [--all | nombre …] [--only plan|xy|time]`.
Lee `truth.json` y `labels.json` (es una herramienta de comprobación; el agente no la usa).
"""

import argparse
import math
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator

from poc_contracts.enums import LabelType
from poc_contracts.run_files import Label, PlanFile

from .generator.scenario_io import load_scenario
from .geometry import Point
from .paths import RUNS_DIR
from .scenario_metrics import (
    RunData,
    gps_radar_distance,
    load_run,
    reported_deviation,
    truth_deviation,
)

plt.switch_backend("Agg")

# Colores: paleta categórica validada (verdad / GPS / radar son los tres primeros huecos, que
# pasan la comprobación entre todos los pares) sobre el fondo claro de la figura.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3de"
PLAN_LIGHT = "#b9b8b2"
TRUTH = "#2a78d6"
GPS = "#eb6834"
RADAR = "#1baf7a"  # contraste < 3:1 sobre claro: va siempre con leyenda y marcador propio
DISCREPANCY = "#6250d6"
METEO = "#d55181"
BAND = INK_SOFT
SPEED_CMAP = LinearSegmentedColormap.from_list(
    "speed", ["#86b6ef", "#3987e5", "#256abf", "#1c5cab", "#0d366b"]
)

ARROW_EVERY_S = 8
ARROW_FIRST_S = 4  # una flecha en plena aceleración (≈ 8 m/s) para que se vea el color
ARROW_LENGTH_M = 100.0
MARGIN_M = 450.0
FIG_DPI = 150

LABEL_NAMES = {
    LabelType.WIND: "wind",
    LabelType.HIJACK: "hijacking",
    LabelType.GPS_SPOOFING: "GPS spoofing",
}

# Umbrales de las reglas del detector, para ver a qué altura caen las medidas
ROUTE_DEVIATION_OPEN_M, ROUTE_DEVIATION_CLOSE_M = 30.0, 15.0
DISCREPANCY_OPEN_M, DISCREPANCY_CLOSE_M = 25.0, 12.0

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_SOFT,
        "axes.titlecolor": INK,
        "text.color": INK,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "legend.frameon": False,
    }
)


# --- piezas comunes -------------------------------------------------------------------------


def _clock(seconds: float, prefix: str = "T+") -> str:
    s = int(round(seconds))
    return f"{prefix}{s // 60:02d}:{s % 60:02d}"


def _label_name(label: Label) -> str:
    if label.type == LabelType.SOURCE_SILENT:
        return f"{label.source.value if label.source else '?'} silent"
    if label.type == LabelType.GPS_LOSS:
        return "GPS loss"
    return LABEL_NAMES[label.type]


def _arrows(
    ax: Axes,
    xs: Sequence[float],
    ys: Sequence[float],
    headings_deg: Sequence[float],
    speeds: Sequence[float],
    norm: Normalize,
    zorder: int = 3,
):
    """Flechas de longitud fija orientadas por el rumbo (0 = norte) y coloreadas por velocidad."""
    u = [ARROW_LENGTH_M * math.sin(math.radians(h)) for h in headings_deg]
    v = [ARROW_LENGTH_M * math.cos(math.radians(h)) for h in headings_deg]
    return ax.quiver(
        xs,
        ys,
        u,
        v,
        speeds,
        angles="xy",
        scale_units="xy",
        scale=1,
        pivot="middle",
        cmap=SPEED_CMAP,
        norm=norm,
        width=0.003,
        headwidth=4.5,
        headlength=5.0,
        headaxislength=4.5,
        zorder=zorder,
    )


def _draw_waypoints(ax: Axes, plan: PlanFile, with_eta: bool = True, muted: bool = False) -> None:
    """Waypoints numerados (la base, con una B). La etiqueta se aparta del centro de la ruta."""
    pts = [(w.x, w.y) for w in plan.waypoints]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    edge = PLAN_LIGHT if muted else INK
    base_etas = [w.eta_s for w in plan.waypoints if w.id == "BASE"]
    for i, w in enumerate(plan.waypoints[:-1]):  # el último es la vuelta a la base
        base = w.id == "BASE"
        ax.scatter(
            [w.x], [w.y], s=300, marker="s" if base else "o", facecolor=SURFACE,
            edgecolor=edge, linewidth=1.6, zorder=6,
        )  # fmt: skip
        ax.text(w.x, w.y, "B" if base else str(i), ha="center", va="center", fontsize=9,
                fontweight="bold", color=edge if muted else INK, zorder=7)  # fmt: skip
        dx, dy = w.x - cx, w.y - cy
        norm = math.hypot(dx, dy) or 1.0
        text = w.id if not with_eta else (
            f"BASE\nsalida {_clock(base_etas[0])}\nllegada {_clock(base_etas[-1])}"
            if base else f"{w.id}\n{_clock(w.eta_s)}"
        )  # fmt: skip
        ax.annotate(
            text, (w.x, w.y), xytext=(34 * dx / norm, 34 * dy / norm), textcoords="offset points",
            ha="center", va="center", fontsize=8.5, color=INK_SOFT, zorder=7,
        )  # fmt: skip


def _style_xy(ax: Axes, xs: Sequence[float], ys: Sequence[float]) -> None:
    ax.set_aspect("equal")
    ax.set_xlim(min(xs) - MARGIN_M, max(xs) + MARGIN_M)
    ax.set_ylim(min(ys) - MARGIN_M, max(ys) + MARGIN_M)
    ax.set_xlabel("x (m, east)")
    ax.set_ylabel("y (m, north)")
    ax.grid(True)
    ax.set_axisbelow(True)
    ax.annotate("N", xy=(0.965, 0.93), xytext=(0.965, 0.84), xycoords="axes fraction",
                ha="center", va="center", fontsize=10, fontweight="bold", color=INK_SOFT,
                arrowprops={"arrowstyle": "-|>", "color": INK_SOFT, "lw": 1.4})  # fmt: skip


def _titles(fig: Figure, title: str, subtitle: str) -> None:
    fig.text(0.06, 0.965, title, ha="left", va="top", fontsize=14, fontweight="bold")
    fig.text(0.06, 0.925, subtitle, ha="left", va="top", fontsize=10, color=INK_SOFT)


def _speed_colorbar(fig: Figure, mappable, ax: Axes) -> None:
    bar = fig.colorbar(mappable, ax=ax, shrink=0.75, pad=0.02)
    bar.set_label("ground speed (m/s)", color=INK_SOFT)
    bar.outline.set_edgecolor(GRID)


# --- plan_xy.png ----------------------------------------------------------------------------


def plot_plan(name: str, out_dir: Path) -> Path:
    """Solo lo planificado: waypoints numerados y trayectoria con flechas."""
    plan = PlanFile.model_validate_json((out_dir / "plan.json").read_text("utf-8"))
    traj = plan.trajectory
    fig, ax = plt.subplots(figsize=(10, 7.6))
    fig.subplots_adjust(top=0.86, left=0.08, right=0.97, bottom=0.08)

    ax.plot([s.x for s in traj], [s.y for s in traj], color=PLAN_LIGHT, lw=1.6, zorder=1)
    picked = [
        s for s in traj if s.t >= ARROW_FIRST_S and (s.t - ARROW_FIRST_S) % ARROW_EVERY_S == 0
    ]
    norm = Normalize(0, max(s.speed_mps for s in traj))
    arrows = _arrows(
        ax, [s.x for s in picked], [s.y for s in picked], [s.heading_deg for s in picked],
        [s.speed_mps for s in picked], norm,
    )  # fmt: skip
    _draw_waypoints(ax, plan)
    _style_xy(ax, [w.x for w in plan.waypoints], [w.y for w in plan.waypoints])
    _speed_colorbar(fig, arrows, ax)

    _titles(
        fig,
        f"{name} · flight plan (no disturbances)",
        f"mission {plan.mission_id} · cruise speed {plan.cruise_speed_mps:.0f} m/s · "
        f"altitude {plan.altitude_m:.0f} m · planned duration {plan.duration_s // 60:.0f} min "
        f"{plan.duration_s % 60:.0f} s · "
        f"one arrow every {ARROW_EVERY_S} s",
    )
    path = out_dir / "plan_xy.png"
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    return path


# --- scenario_xy.png ------------------------------------------------------------------------


def _truth_segment(run: RunData, a: float, b: float) -> tuple[list[float], list[float]]:
    pts = [s for s in run.truth.trajectory if a <= s.t <= b]
    return [s.x for s in pts], [s.y for s in pts]


def _callouts(ax: Axes, callouts: list[tuple[Label, float, float]], center: Point) -> None:
    """Etiqueta de cada tramo, hacia fuera de la ruta y sin salirse de los ejes."""
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    for label, mx, my in callouts:
        dx, dy = mx - center[0], my - center[1]
        norm = math.hypot(dx, dy) or 1.0
        tx = min(max(mx + 600 * dx / norm, x0 + 330), x1 - 330)
        ty = min(max(my + 600 * dy / norm, y0 + 90), y1 - 170)
        ax.annotate(
            f"{label.id} · {_label_name(label)}\n{_clock(label.start_s)} – {_clock(label.end_s)}",
            (mx, my), xytext=(tx, ty), textcoords="data",
            ha="center", va="center", fontsize=9, fontweight="bold", color=INK, zorder=8,
            arrowprops={"arrowstyle": "-", "color": INK_SOFT, "lw": 0.9},
        )  # fmt: skip


def plot_xy(name: str, out_dir: Path) -> Path:
    """Plan en tono claro, trayectoria real, puntos de GPS y radar y zonas de anomalía."""
    run = load_run(name, out_dir.parent)
    config = load_scenario(name)
    plan, traj = run.plan, run.truth.trajectory
    fig, ax = plt.subplots(figsize=(10.5, 8))
    fig.subplots_adjust(top=0.86, left=0.08, right=0.97, bottom=0.13)

    ax.plot([p.x for p in plan.trajectory], [p.y for p in plan.trajectory],
            color=PLAN_LIGHT, lw=3.0, zorder=1, solid_capstyle="round")  # fmt: skip
    _draw_waypoints(ax, plan, with_eta=False, muted=True)

    # zonas de anomalía y de fallo: la trayectoria real resaltada en esa ventana y su etiqueta
    pts = [(w.x, w.y) for w in plan.waypoints]
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    callouts: list[tuple[Label, float, float]] = []  # (etiqueta, x, y) del punto medio del tramo
    for label in run.labels:
        xs, ys = _truth_segment(run, label.start_s, label.end_s)
        ax.plot(xs, ys, color=BAND, lw=15, alpha=0.2, solid_capstyle="round", zorder=1)
        callouts.append((label, xs[len(xs) // 2], ys[len(ys) // 2]))

    fixes = run.of_type("PositionUpdated")
    gps = [(e["payload"]["x"], e["payload"]["y"]) for e in fixes if e["payload"]["fix"] != "none"]
    estimated = [
        (e["payload"]["x"], e["payload"]["y"]) for e in fixes if e["payload"]["fix"] == "none"
    ]
    radar = [(e["payload"]["x"], e["payload"]["y"]) for e in run.of_type("TrackUpdated")]
    ax.scatter(*zip(*gps, strict=True), s=7, color=GPS, alpha=0.55, linewidths=0, zorder=2)
    if estimated:  # sin fix: la posición es la estima del dron
        ax.scatter(*zip(*estimated, strict=True), s=22, facecolor="none", edgecolor=GPS,
                   linewidths=0.9, zorder=2)  # fmt: skip
    ax.scatter(*zip(*radar, strict=True), s=16, color=RADAR, marker="D", alpha=0.6,
               linewidths=0, zorder=2)  # fmt: skip

    ax.plot([s.x for s in traj], [s.y for s in traj], color=TRUTH, lw=0.7, alpha=0.5, zorder=3)
    picked = [
        s for s in traj if s.t >= ARROW_FIRST_S and (s.t - ARROW_FIRST_S) % ARROW_EVERY_S == 0
    ]
    norm_speed = Normalize(0, max(s.speed_mps for s in traj))
    arrows = _arrows(
        ax, [s.x for s in picked], [s.y for s in picked], [s.course_deg for s in picked],
        [s.speed_mps for s in picked], norm_speed, zorder=4,
    )  # fmt: skip
    xs_all = [s.x for s in traj] + [w.x for w in plan.waypoints]
    ys_all = [s.y for s in traj] + [w.y for w in plan.waypoints]
    if config.hijack:
        t = config.hijack.target
        ax.scatter([t.x], [t.y], marker="X", s=140, color=INK, zorder=7)
        ax.annotate(
            "hijack destination", (t.x, t.y), xytext=(0, -20), textcoords="offset points",
            ha="center", fontsize=9, color=INK_SOFT,
        )  # fmt: skip
        xs_all.append(t.x)
        ys_all.append(t.y)
    _style_xy(ax, xs_all, ys_all)
    _callouts(ax, callouts, (cx, cy))
    _speed_colorbar(fig, arrows, ax)

    handles = [
        Line2D([], [], color=PLAN_LIGHT, lw=3, label="planned trajectory"),
        Line2D([], [], color=TRUTH, lw=1.2, marker=">", markersize=6,
               label="real trajectory (arrow: heading; colour: speed)"),
        Line2D([], [], color=GPS, lw=0, marker="o", markersize=5, label="GPS (1 Hz)"),
        Line2D([], [], color=RADAR, lw=0, marker="D", markersize=5, label="radar (0.5 Hz)"),
        Line2D([], [], color=BAND, lw=9, alpha=0.25, label="leg with anomaly or fault"),
    ]  # fmt: skip
    if estimated:
        handles.append(
            Line2D([], [], color=GPS, lw=0, marker="o", markersize=6, markerfacecolor="none",
                   label="GPS without fix (estimated position)")
        )  # fmt: skip
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8.5)
    _titles(fig, f"{name} · trayectoria planificada y real", _summary(run))
    path = out_dir / "scenario_xy.png"
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    return path


def _summary(run: RunData) -> str:
    """Una línea con las anomalías del escenario y su ventana."""
    if not run.labels:
        return f"mission {run.plan.mission_id} · no anomalies or faults"
    parts = [
        f"{lb.id} {_label_name(lb)} {_clock(lb.start_s)}–{_clock(lb.end_s)}" for lb in run.labels
    ]
    return f"mission {run.plan.mission_id} · " + " · ".join(parts)


# --- scenario_time.png ----------------------------------------------------------------------


def _with_gaps(series: list[tuple[float, float]], max_gap_s: float) -> tuple[list, list]:
    """Separa en dos listas insertando NaN donde hay un hueco, para que la línea no lo cruce."""
    ts: list[float] = []
    vs: list[float] = []
    for t, v in series:
        if ts and t - ts[-1] > max_gap_s:
            ts.append(ts[-1] + 0.001)
            vs.append(math.nan)
        ts.append(t)
        vs.append(v)
    return ts, vs


def _threshold(ax: Axes, value: float, text: str) -> None:
    """Línea de umbral de una regla; el texto va dentro del eje, a la derecha."""
    ax.axhline(value, color=INK_SOFT, lw=0.8, ls=(0, (4, 3)), zorder=1)
    ax.text(0.995, value, text, transform=ax.get_yaxis_transform(), ha="right", va="bottom",
            fontsize=8, color=INK_SOFT)  # fmt: skip


def plot_time(name: str, out_dir: Path) -> Path:
    """Desviación respecto al plan, distancia GPS–radar y viento, con las ventanas etiquetadas."""
    run = load_run(name, out_dir.parent)
    end = run.truth.duration_s
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(11, 8.6),
                             gridspec_kw={"height_ratios": [3, 2, 2]})  # fmt: skip
    fig.subplots_adjust(top=0.86, left=0.09, right=0.97, bottom=0.08, hspace=0.12)
    dev_ax, disc_ax, wind_ax = axes

    # 1) desviación respecto a la ruta planificada
    dev = truth_deviation(run)
    gps_dev = _with_gaps(reported_deviation(run, "PositionUpdated"), 3.0)
    dev_ax.plot(*gps_dev, color=GPS, lw=1.0, label="GPS (what the drone reports)", zorder=2)
    dev_ax.plot(
        *zip(*dev, strict=True), color=TRUTH, lw=1.8, label="truth (real position)", zorder=3
    )
    rule = f"ROUTE_DEVIATION opens {ROUTE_DEVIATION_OPEN_M:.0f} m, "
    _threshold(dev_ax, ROUTE_DEVIATION_OPEN_M, rule + f"closes {ROUTE_DEVIATION_CLOSE_M:.0f}")
    dev_ax.axhline(ROUTE_DEVIATION_CLOSE_M, color=INK_SOFT, lw=0.8, ls=(0, (4, 3)), zorder=1)
    peak = max(v for _, v in dev)
    if peak > 200:  # un pico grande aplastaría el resto: lineal hasta 100 m y logarítmica desde ahí
        dev_ax.set_yscale("symlog", linthresh=100, linscale=1.0)
        dev_ax.set_yticks([0, 25, 50, 75, 100, 200, 400, 700])
        dev_ax.get_yaxis().set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}"))
        dev_ax.set_ylabel("deviation from the plan (m)\nlinear up to 100, log from there")
    else:
        dev_ax.set_ylabel("deviation from\nthe plan (m)")
    dev_ax.set_ylim(0, peak * (1.25 if peak < 200 else 1.8))
    dev_ax.legend(loc="center right", fontsize=8.5)

    # 2) distancia GPS–radar (media de las 3 últimas)
    disc_ax.plot(*_with_gaps(gps_radar_distance(run), 5.0), color=DISCREPANCY, lw=1.6, zorder=3)
    _threshold(disc_ax, DISCREPANCY_OPEN_M, f"SOURCE_DISCREPANCY opens {DISCREPANCY_OPEN_M:.0f} m")
    _threshold(disc_ax, DISCREPANCY_CLOSE_M, f"closes {DISCREPANCY_CLOSE_M:.0f} m")
    disc_ax.set_ylabel("GPS–radar distance (m)\nmean of 3 measurements")
    disc_ax.set_ylim(bottom=0)

    # 3) viento real y lo que reporta la estación
    wind = run.truth.wind
    wind_ax.plot([w.t for w in wind], [w.speed_mps for w in wind], color=TRUTH, lw=1.8,
                 label="real wind (mean speed)", zorder=3)  # fmt: skip
    met = run.of_type("WindReported")
    wind_ax.scatter([e["sim_time"] for e in met], [e["payload"]["speed_mps"] for e in met],
                    s=14, color=METEO, zorder=4, label="weather station: speed")  # fmt: skip
    wind_ax.scatter([e["sim_time"] for e in met], [e["payload"]["gust_mps"] for e in met],
                    s=18, facecolor="none", edgecolor=METEO, linewidth=1.0, zorder=4,
                    label="weather station: gust")  # fmt: skip
    wind_ax.set_ylabel("wind (m/s)")
    wind_top = max([w.gust_mps for w in wind] + [e["payload"]["gust_mps"] for e in met])
    wind_ax.set_ylim(0, wind_top * 1.3)
    wind_ax.legend(loc="upper right", fontsize=8.5, ncol=3)

    for ax in axes:
        ax.grid(True, axis="y")
        for label in run.labels:
            ax.axvspan(label.start_s, label.end_s, color=BAND, alpha=0.13, lw=0, zorder=0)
    for k, label in enumerate(run.labels):  # alternan de altura para que no se pisen
        dev_ax.text(label.start_s + 1.5, 0.97 - 0.08 * (k % 2), f"{label.id} {_label_name(label)}",
                    transform=dev_ax.get_xaxis_transform(), va="top", ha="left", fontsize=8.5,
                    fontweight="bold", color=INK)  # fmt: skip
    wind_ax.set_xlim(0, end)
    wind_ax.xaxis.set_major_locator(MultipleLocator(60))
    wind_ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _clock(v)))
    wind_ax.set_xlabel("simulation time (shaded zones: anomaly or fault windows)")
    _titles(fig, f"{name} · deviation, discrepancy between sources and wind", _summary(run))
    path = out_dir / "scenario_time.png"
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    return path


PLOTS = {"plan": plot_plan, "xy": plot_xy, "time": plot_time}


def plot_scenario(name: str, only: str | None = None, runs_dir: Path = RUNS_DIR) -> list[Path]:
    out_dir = runs_dir / name
    return [fn(name, out_dir) for key, fn in PLOTS.items() if only in (None, key)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="scenarios with output in runs/")
    parser.add_argument("--all", action="store_true", help="all of those in runs/")
    parser.add_argument("--only", choices=["plan", "xy", "time"], help="a single figure")
    args = parser.parse_args()
    names = (
        sorted(p.name for p in RUNS_DIR.iterdir() if (p / "plan.json").exists())
        if args.all
        else args.names
    )
    if not names:
        parser.error("give one or more scenarios, or --all")
    for name in names:
        for path in plot_scenario(name, args.only):
            print(path)


if __name__ == "__main__":
    main()
