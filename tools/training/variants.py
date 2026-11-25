"""E7b, paso 1: generador de variantes por clase.

    uv run --project platform python tools/training/variants.py [--manifest M] [--out D]

Del manifiesto (`manifests/e7b-v1.yaml`: semilla, cuotas por familia, rangos de parámetros y
combinaciones) salen N escenarios distintos, no la misma ruta con otra semilla: ruta, parámetros
del dron, ruido de las fuentes, radar, estación, enlace y batería se muestrean dentro de sus
rangos, y a cada variante se le ponen una anomalía principal (su familia) y, a veces, una segunda
y una tercera, solapadas o no. Cada variante se genera con el simulador v2 (sin tocarlo) y deja en
`<out>/<dataset>/variants/<nombre>/` sus eventos y `states.jsonl` (comprimidos), el escenario, el
`assets.yaml` (lo que el monitor conoce de antemano: posición y alcance del radar) y `meta.json`.
`index.json` (determinista) lleva la partición entrenamiento/validación/prueba **por variante** y
`timing.json` los tiempos. Todo sale de la semilla maestra con `zlib.crc32` (nunca `hash()`).
"""

import argparse
import copy
import gzip
import json
import math
import random
import shutil
import sys
import time
import zlib
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform" / "src"))

from platform_app.generator.build import generate, plan_for  # noqa: E402
from poc_contracts.scenario import ScenarioConfig  # noqa: E402

DEFAULT_MANIFEST = REPO / "tools" / "training" / "manifests" / "e7b-v1.yaml"
DEFAULT_OUT = REPO / "experiments" / "e7b"
MAX_ATTEMPTS = 12
EDGE_S = 40.0  # una anomalía no empieza ni acaba pegada al principio o al final del vuelo
SOURCES_MUTABLE = ("gps", "radar", "meteo", "battery")
Window = tuple[float, float]


def stable_int(*parts: object) -> int:
    """Entero estable (no depende de `PYTHONHASHSEED`) a partir de varias partes."""
    return zlib.crc32(":".join(str(p) for p in parts).encode())


def uni(rng: random.Random, span: list[float], digits: int = 1) -> float:
    return round(rng.uniform(span[0], span[1]), digits)


def pick(rng: random.Random, spec: list, digits: int = 1) -> float:
    """Un valor uniforme en `[lo, hi]` o, si `spec` es una lista de intervalos, en uno de ellos."""
    if isinstance(spec[0], list):
        spec = rng.choice(spec)
    return round(rng.uniform(spec[0], spec[1]), digits)


def overlaps(a: Window, b: Window) -> bool:
    return a[0] < b[1] and b[0] < a[1]


class Draft:
    """Un escenario en construcción: su YAML como diccionario, el plan y qué ocupa cada recurso."""

    def __init__(self, raw: dict[str, Any], plan: Any, rng: random.Random, ranges: dict) -> None:
        self.raw, self.plan, self.rng, self.r = raw, plan, rng, ranges
        self.flight_s: float = plan.duration_s
        self.used: dict[str, list[Window]] = {}
        self.families: list[dict[str, Any]] = []

    def band(self, name: str) -> list[float]:
        """Rango de la velocidad del viento de un episodio: absoluto (v1) o relativo al dron."""
        w = self.r["wind"]
        if "bands_relative" not in w:
            return w["bands"][name][1:]
        limit, air = self.raw["drone"]["wind_limit_mps"], self.raw["drone"]["max_airspeed_mps"]
        notable_min = (
            w["notable_min_over_limit"] * limit if "notable_min_over_limit" in w
            else min(w["notable_min_mps"], 0.95 * limit)
        )  # fmt: skip
        return {
            "notable": [notable_min, limit],
            "beyond_limit": [limit, air],
            "drifting": [air, w["drifting_max_over_airspeed"] * air],
        }[name]

    def band_weights(self) -> dict[str, float]:
        w = self.r["wind"]
        return (
            w["bands_relative"]
            if "bands_relative" in w
            else {n: b[0] for n, b in w["bands"].items()}
        )

    def free(self, resources: list[str], window: Window) -> bool:
        return not any(overlaps(window, w) for res in resources for w in self.used.get(res, []))

    def take(self, resources: list[str], window: Window) -> None:
        for res in resources:
            self.used.setdefault(res, []).append(window)

    def position(self, t: float) -> tuple[float, float]:
        traj = self.plan.trajectory
        p = traj[max(0, min(len(traj) - 1, int(t)))]
        return p.x, p.y

    def offset(self, t: float, span: list[float]) -> tuple[float, float]:
        """Un punto a `span` metros de donde está el dron (según el plan) en `t`."""
        x, y = self.position(t)
        d, a = self.rng.uniform(*span), self.rng.uniform(0, 2 * math.pi)
        return round(x + d * math.cos(a), 1), round(y + d * math.sin(a), 1)

    def window(self, span: list[float], near: Window | None = None) -> Window:
        """Una ventana de duración `span`; si hay `near`, se solapa con ella."""
        d = uni(self.rng, span)
        if near is not None:
            start = self.rng.uniform(near[0] - 0.5 * d, near[1] - 0.5 * d)
        else:
            start = self.rng.uniform(EDGE_S, max(EDGE_S, self.flight_s - d - EDGE_S))
        start = round(max(10.0, min(start, self.flight_s - 20.0)), 1)
        return start, round(min(start + d, self.flight_s - 5.0), 1)


# --- Familias: cada una anota su anomalía en el borrador y dice qué recursos ocupa -------------


def _wind_episode(d: Draft, window: Window, speed: float) -> dict[str, Any]:
    ramp = min(uni(d.rng, d.r["wind"]["ramp_s"]), (window[1] - window[0]) / 2 - 0.1)
    return {"start_s": window[0], "end_s": window[1], "ramp_s": round(max(ramp, 1.0), 1),
            "speed_mps": speed, "from_deg": round(d.rng.uniform(0, 360), 1)}  # fmt: skip


def f_nominal(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    """Sin anomalía; con un 30 % de probabilidad, un viento notable (5–12 m/s)."""
    if d.rng.random() >= 0.3 or "wind" in d.used and near is None:
        return [], None, {}
    w = d.window(d.r["wind"]["duration_s"], near)
    if not d.free(["wind"], w):
        return [], None, {}
    speed = uni(d.rng, d.band("notable"))
    d.raw["wind"]["episodes"].append(_wind_episode(d, w, speed))
    d.take(["wind"], w)
    return ["wind"], w, {"speed_mps": speed}


def f_wind(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    weights = d.band_weights()
    band = d.rng.choices(list(weights), weights=list(weights.values()))[0]
    w = d.window(d.r["wind"]["duration_s"], near)
    if not d.free(["wind"], w):
        return [], None, {}
    speed = uni(d.rng, d.band(band))
    d.raw["wind"]["episodes"].append(_wind_episode(d, w, speed))
    d.take(["wind"], w)
    return ["wind"], w, {"band": band, "speed_mps": speed}


def f_spoofing(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    r = d.r["spoofing"]
    if d.raw["spoofing"] is not None:
        return [], None, {}
    w = d.window(r["duration_s"], near)
    spoof: dict[str, Any] = {
        "start_s": w[0], "end_s": w[1], "drift_rate_mps": uni(d.rng, r["drift_rate_mps"], 2),
        "direction_deg": round(d.rng.uniform(0, 360), 1),
    }  # fmt: skip
    if d.rng.random() >= r["no_emitter"]:
        x, y = d.offset((w[0] + w[1]) / 2, r["emitter_offset_m"])
        spoof["emitter"] = {"x": x, "y": y, "power_db": uni(d.rng, r["emitter_power_db"])}
    d.raw["spoofing"] = spoof
    return ["spoofing"], w, {"drift_rate_mps": spoof["drift_rate_mps"]}


def f_hijack(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    r = d.r["hijack"]
    if d.raw["hijack"] is not None:
        return [], None, {}
    w = d.window(r["duration_s"], near)
    if not d.free(["link_fault", "link_episode"], w):
        return [], None, {}
    x, y = d.offset(w[0], r["target_offset_m"])
    end = None if d.rng.random() < r["open_ended"] else w[1]
    d.raw["hijack"] = {"start_s": w[0], "end_s": end, "target": {"x": x, "y": y}}
    d.take(["link_fault", "link_episode"], w)
    return ["hijack"], w, {"open_ended": end is None}


def _fault(d: Draft, source: str, mode: str, w: Window) -> None:
    d.raw["faults"].append({"source": source, "mode": mode, "start_s": w[0], "end_s": w[1]})


def f_gps_loss(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    w = d.window(d.r["fault"]["duration_s"], near)
    if not d.free(["gps_fault", "gps_episode"], w):
        return [], None, {}
    _fault(d, "gps", "loss", w)
    d.take(["gps_fault", "gps_episode"], w)
    with_wind = d.rng.random() < 0.5
    if with_wind:  # el viento cambia durante la pérdida: sale la navegación a estima
        start = round(w[0] + d.rng.uniform(0, (w[1] - w[0]) / 2), 1)
        w2 = (start, round(min(start + uni(d.rng, [40, 80]), d.flight_s - 5), 1))
        if d.free(["wind"], w2) and w2[1] > w2[0] + 12:
            change = d.r["wind"].get("loss_change_over_airspeed")
            air = d.raw["drone"]["max_airspeed_mps"]
            speed = uni(d.rng, [change[0] * air, change[1] * air] if change else [8, 14])
            d.raw["wind"]["episodes"].append(_wind_episode(d, w2, speed))
            d.take(["wind"], w2)
    return ["gps_fault"], w, {"wind_change": with_wind}


def _gps_episode(d: Draft, w: Window) -> None:
    r = d.r["gps_degraded"]
    d.raw["sensors"]["gps"]["episodes"].append({
        "start_s": w[0], "end_s": w[1], "ramp_s": min(10.0, (w[1] - w[0]) / 2 - 0.1),
        "sats": int(d.rng.randint(*r["sats"])), "hdop": uni(d.rng, r["hdop"]),
    })  # fmt: skip


def f_gps_degraded(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    w = d.window(d.r["gps_degraded"]["duration_s"], near)
    if not d.free(["gps_fault", "gps_episode"], w):
        return [], None, {}
    _gps_episode(d, w)
    d.take(["gps_episode"], w)
    return ["gps_episode"], w, {}


def f_jamming(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    r = d.r["jamming"]
    w = d.window(r["duration_s"], near)
    if not d.free(["gps_fault", "gps_episode"], w):
        return [], None, {}
    x, y = d.offset((w[0] + w[1]) / 2, r["offset_m"])
    n = len(d.raw["emitters"]) + 1
    emitter = {"id": f"jammer-{n}", "x": x, "y": y, "power_db": uni(d.rng, r["power_db"])}
    d.raw["emitters"].append({**emitter, "start_s": w[0], "end_s": w[1]})
    _gps_episode(d, w)
    d.take(["gps_episode"], w)
    loss = d.rng.random() < r["loss_prob"]
    if loss:
        s = round(w[0] + d.rng.uniform(0.2, 0.5) * (w[1] - w[0]), 1)
        _fault(d, "gps", "loss", (s, round(min(s + uni(d.rng, r["loss_s"]), w[1]), 1)))
        d.take(["gps_fault"], w)
    return ["gps_episode"], w, {"loss": loss}


def f_link_degraded(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    r = d.r["link_degraded"]
    w = d.window(r["duration_s"], near)
    if not d.free(["link_fault", "link_episode"], w):
        return [], None, {}
    ep: dict[str, Any] = {"start_s": w[0], "end_s": w[1], "ramp_s": 5.0}
    which = d.rng.choice(["latency", "rssi", "both"])
    if which in ("latency", "both"):
        ep["latency_ms"] = uni(d.rng, r["latency_ms"])
    if which in ("rssi", "both"):
        ep["rssi_dbm"] = uni(d.rng, r["rssi_dbm"])
    d.raw["sensors"]["link"]["episodes"].append(ep)
    d.take(["link_episode"], w)
    return ["link_episode"], w, {"which": which}


def f_link_mute(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    w = d.window(d.r["fault"]["duration_s"], near)
    if not d.free(["link_fault", "link_episode"], w):
        return [], None, {}
    _fault(d, "link", "mute", w)
    d.take(["link_fault", "link_episode"], w)
    return ["link_fault"], w, {}


def _mute_one(d: Draft, source: str, near: Window | None) -> Window | None:
    w = d.window(d.r["fault"]["duration_s"], near)
    res = [f"{source}_fault"] + (["gps_episode"] if source == "gps" else [])
    if not d.free(res, w):
        return None
    _fault(d, source, "mute", w)
    d.take(res, w)
    return w


def f_source_mute(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    """Una fuente callada y, en el 40 % de los casos, otra distinta en otra ventana."""
    first = d.rng.choice(SOURCES_MUTABLE)
    w = _mute_one(d, first, near)
    if w is None:
        return [], None, {}
    sources = [first]
    if d.rng.random() < 0.4:
        second = d.rng.choice([s for s in SOURCES_MUTABLE if s != first])
        if _mute_one(d, second, None) is not None:
            sources.append(second)
    return [f"{first}_fault"], w, {"sources": sources}


def f_radar_range(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    if d.used.get("radar_range"):
        return [], None, {}
    rx, ry = d.raw["sensors"]["radar"]["x"], d.raw["sensors"]["radar"]["y"]
    far = max(math.hypot(p.x - rx, p.y - ry) for p in d.plan.trajectory)
    max_range = round(max(600.0, d.rng.uniform(0.5, 0.9) * far), 1)
    d.raw["sensors"]["radar"]["max_range_m"] = max_range
    d.used["radar_range"] = [(0.0, d.flight_s)]
    return ["radar_range"], None, {"max_range_m": max_range}


def f_battery(d: Draft, near: Window | None) -> tuple[list[str], Window | None, dict]:
    if d.used.get("battery_cfg"):
        return [], None, {}
    r = d.r["battery"]
    bat = d.raw["sensors"]["battery"]
    bat["capacity_wh"] = uni(d.rng, r["low_capacity_wh"])
    bat["start_pct"] = uni(d.rng, r["low_start_pct"])
    d.used["battery_cfg"] = [(0.0, d.flight_s)]
    return ["battery_cfg"], None, {"capacity_wh": bat["capacity_wh"], "start_pct": bat["start_pct"]}


FAMILIES = {
    "nominal": f_nominal, "wind": f_wind, "spoofing": f_spoofing, "hijack": f_hijack,
    "gps_loss": f_gps_loss, "jamming": f_jamming, "gps_degraded": f_gps_degraded,
    "link_degraded": f_link_degraded, "link_mute": f_link_mute, "source_mute": f_source_mute,
    "radar_range": f_radar_range, "battery": f_battery,
}  # fmt: skip
EXTRAS = [name for name in FAMILIES if name != "nominal"]


# --- Muestreo de una variante -------------------------------------------------------------------


def _route(rng: random.Random, r: dict) -> list[dict[str, Any]]:
    """Waypoints al azar: cada punto a `radius_m` de la base y a `min_leg_m` o más del anterior."""
    wps: list[dict[str, Any]] = []
    prev = (0.0, 0.0)
    for i in range(rng.randint(*r["n_waypoints"])):
        for _ in range(100):
            rad, ang = rng.uniform(*r["radius_m"]), rng.uniform(0, 2 * math.pi)
            p = (round(rad * math.cos(ang), 1), round(rad * math.sin(ang), 1))
            if math.dist(p, prev) >= r["min_leg_m"]:
                break
        wps.append({"id": f"WP{i + 1}", "x": p[0], "y": p[1]})
        prev = p
    return wps


def base_scenario(manifest: dict, name: str, rng: random.Random) -> dict[str, Any]:
    """El escenario sin anomalías: ruta, dron, fuentes, radar, estación, enlace y batería."""
    r = manifest["ranges"]
    gm, white = uni(rng, r["gps"]["gm_sigma_m"], 2), uni(rng, r["gps"]["white_sigma_m"], 2)
    radar_d, radar_a = rng.uniform(*r["radar"]["offset_m"]), rng.uniform(0, 2 * math.pi)
    actions = r["link_loss_action"]
    return {
        "name": name, "description": f"E7b training variant {name}.",
        "seed": stable_int(manifest["seed"], name, "scenario") % 2**31,
        "t0": "2026-10-20T10:00:00Z", "max_duration_s": 1800,
        "drone": {
            "cruise_speed_mps": uni(rng, r["drone"]["cruise_speed_mps"]),
            "max_accel_mps2": uni(rng, r["drone"]["max_accel_mps2"], 2),
            "max_turn_rate_dps": uni(rng, r["drone"]["max_turn_rate_dps"]),
            "altitude_m": 60.0, "acceptance_radius_m": 5.0,
            "lookahead_m": uni(rng, r["drone"]["lookahead_m"]),
            "wind_limit_mps": 12.0, "max_airspeed_mps": 17.0,
            "link_loss_action": rng.choices(list(actions), weights=list(actions.values()))[0],
        },
        "mission": {"id": f"MSN-{name.upper()}", "waypoints": _route(rng, r["route"]),
                    "return_to_base": True},  # fmt: skip
        "sensors": {
            "gps": {"period_s": 1.0, "sigma_m": round(math.hypot(gm, white), 3),
                    "sats": rng.randint(*r["gps"]["sats"]), "hdop": uni(rng, r["gps"]["hdop"], 2),
                    "gm_sigma_m": gm, "gm_tau_s": uni(rng, r["gps"]["gm_tau_s"]),
                    "white_sigma_m": white, "episodes": []},  # fmt: skip
            "radar": {"period_s": 2.0, "sigma_m": 5.0,
                      "x": round(radar_d * math.cos(radar_a), 1),
                      "y": round(radar_d * math.sin(radar_a), 1),
                      "sigma_per_km_m": uni(rng, r["radar"]["sigma_per_km_m"], 2),
                      "max_range_m": uni(rng, r["radar"]["max_range_m"])},  # fmt: skip
            "meteo": {"period_s": 10.0, "sigma_mps": uni(rng, r["meteo"]["sigma_mps"], 2),
                      "sigma_deg": uni(rng, r["meteo"]["sigma_deg"]),
                      "factor": uni(rng, r["meteo"]["factor"], 2),
                      "lag_s": uni(rng, r["meteo"]["lag_s"])},  # fmt: skip
            "link": {"period_s": 5.0, "rssi_dbm": uni(rng, r["link"]["rssi_dbm"]),
                     "latency_ms": uni(rng, r["link"]["latency_ms"]), "episodes": []},  # fmt: skip
            "battery": {"period_s": 10.0, "start_pct": uni(rng, r["battery"]["start_pct"]),
                        "capacity_wh": uni(rng, r["battery"]["capacity_wh"])},  # fmt: skip
        },
        "wind": {"base": {"speed_mps": uni(rng, r["wind"]["base_speed_mps"]),
                          "from_deg": round(rng.uniform(0, 360), 1)}, "episodes": []},  # fmt: skip
        "spoofing": None, "hijack": None, "faults": [], "emitters": [],
    }  # fmt: skip


def base_scenario_v2(manifest: dict, name: str, rng: random.Random) -> dict[str, Any]:
    """El escenario sin anomalías con el dron y los sensores de la variante (paso 2b): velocidad
    máxima respecto al aire, límite de viento y crucero relativos a ella, σ del GPS y del radar, y
    periodos de las fuentes dentro de los rangos del manifiesto. La física no se toca."""
    r = manifest["ranges"]
    air = pick(rng, r["drone"]["max_airspeed_mps"])
    wind_limit = round(air * pick(rng, r["drone"]["wind_limit_over_airspeed"], 3), 2)
    cruise = round(air * pick(rng, r["drone"]["cruise_over_airspeed"], 3), 2)
    gm, white = pick(rng, r["gps"]["gm_sigma_m"], 2), pick(rng, r["gps"]["white_sigma_m"], 2)
    radar_d, radar_a = rng.uniform(*r["radar"]["offset_m"]), rng.uniform(0, 2 * math.pi)
    actions = r["link_loss_action"]
    periods = {k: rng.choice(v) for k, v in r["periods_s"].items()}
    base_wind = round(wind_limit * pick(rng, r["wind"]["base_over_limit"], 3), 1)
    receiver = (  # C/N0 y AGC nominales del receptor (contrato v1.2)
        {"cn0_nominal_dbhz": pick(rng, r["gnss"]["cn0_nominal_dbhz"]),
         "agc_nominal_db": pick(rng, r["gnss"]["agc_nominal_db"], 2)}
        if "gnss" in r else {}
    )  # fmt: skip
    return {
        "name": name, "description": f"E7b training variant {name}.",
        "seed": stable_int(manifest["seed"], name, "scenario") % 2**31,
        "t0": "2026-10-20T10:00:00Z", "max_duration_s": 1800,
        "drone": {
            "cruise_speed_mps": cruise,
            "max_accel_mps2": uni(rng, r["drone"]["max_accel_mps2"], 2),
            "max_turn_rate_dps": uni(rng, r["drone"]["max_turn_rate_dps"]),
            "altitude_m": 60.0, "acceptance_radius_m": 5.0,
            "lookahead_m": uni(rng, r["drone"]["lookahead_m"]),
            "wind_limit_mps": wind_limit, "max_airspeed_mps": air,
            "link_loss_action": rng.choices(list(actions), weights=list(actions.values()))[0],
        },
        "mission": {"id": f"MSN-{name.upper()}", "waypoints": _route(rng, r["route"]),
                    "return_to_base": True},  # fmt: skip
        "sensors": {
            "gps": {"period_s": periods["gps"], "sigma_m": round(math.hypot(gm, white), 3),
                    "sats": rng.randint(*r["gps"]["sats"]), "hdop": uni(rng, r["gps"]["hdop"], 2),
                    "gm_tau_s": uni(rng, r["gps"]["gm_tau_s"]), "gm_sigma_m": gm,
                    "white_sigma_m": white, "episodes": [], **receiver},  # fmt: skip
            "radar": {"period_s": periods["radar"], "sigma_m": pick(rng, r["radar"]["sigma0_m"], 2),
                      "x": round(radar_d * math.cos(radar_a), 1),
                      "y": round(radar_d * math.sin(radar_a), 1),
                      "sigma_per_km_m": pick(rng, r["radar"]["sigma_per_km_m"], 2),
                      "max_range_m": pick(rng, r["radar"]["max_range_m"])},  # fmt: skip
            "meteo": {"period_s": periods["meteo"],
                      "sigma_mps": uni(rng, r["meteo"]["sigma_mps"], 2),
                      "sigma_deg": uni(rng, r["meteo"]["sigma_deg"]),
                      "factor": uni(rng, r["meteo"]["factor"], 2),
                      "lag_s": uni(rng, r["meteo"]["lag_s"])},  # fmt: skip
            "link": {"period_s": periods["link"], "rssi_dbm": uni(rng, r["link"]["rssi_dbm"]),
                     "latency_ms": uni(rng, r["link"]["latency_ms"]), "episodes": []},  # fmt: skip
            "battery": {"period_s": periods["battery"],
                        "start_pct": uni(rng, r["battery"]["start_pct"]),
                        "capacity_wh": uni(rng, r["battery"]["capacity_wh"])},  # fmt: skip
        },
        "wind": {"base": {"speed_mps": base_wind,
                          "from_deg": round(rng.uniform(0, 360), 1)}, "episodes": []},  # fmt: skip
        "spoofing": None, "hijack": None, "faults": [], "emitters": [],
    }  # fmt: skip


def quota_families(manifest: dict, n: int) -> list[str]:
    """Una familia por variante con las cuotas exactas (resto mayor) y un orden estable."""
    quotas = manifest["quotas"]
    exact = {f: q * n for f, q in quotas.items()}
    counts = {f: math.floor(v) for f, v in exact.items()}
    for f in sorted(exact, key=lambda f: (counts[f] - exact[f], f))[: n - sum(counts.values())]:
        counts[f] += 1
    families = [f for f, c in counts.items() for _ in range(c)]
    random.Random(stable_int(manifest["seed"], "quota")).shuffle(families)
    return families


def sample_variant(manifest: dict, index: int, family: str, attempt: int) -> tuple[dict, dict]:
    """El escenario (YAML) y la descripción de la variante `index`, en el intento `attempt`."""
    name = f"v{index:04d}"
    rng = random.Random(stable_int(manifest["seed"], index, attempt))
    cfg = manifest["ranges"]
    while True:  # la ruta se vuelve a muestrear si el vuelo sale demasiado corto o largo
        base = base_scenario_v2 if "max_airspeed_mps" in cfg["drone"] else base_scenario
        raw = base(manifest, name, rng)
        plan, _ = plan_for(ScenarioConfig.model_validate(raw))
        if manifest["min_flight_s"] <= plan.duration_s <= manifest["max_flight_s"]:
            break
    # un vuelo que se queda esperando (`hold`) no dura hasta el límite: el plan más un margen
    raw["max_duration_s"] = round(1.3 * plan.duration_s + 60.0)
    far = max(math.hypot(p.x - raw["sensors"]["radar"]["x"], p.y - raw["sensors"]["radar"]["y"])
              for p in plan.trajectory)  # fmt: skip
    radar = raw["sensors"]["radar"]
    radar["max_range_m"] = round(max(radar["max_range_m"], 1.1 * far), 1)  # la ruta está a la vista
    draft = Draft(raw, plan, rng, cfg)

    combo = manifest["combine"]
    n_extra = 0
    if rng.random() < combo["second"]:
        n_extra = 2 if rng.random() < combo["third"] / combo["second"] else 1
    chain = [family] + [rng.choice([f for f in EXTRAS if f != family]) for _ in range(n_extra)]
    first: Window | None = None
    for fam in chain:
        near = first if first and rng.random() < combo["overlap"] and fam != family else None
        for _ in range(10):
            res, w, params = FAMILIES[fam](draft, near)
            if res or fam == "nominal":
                break
            near = None
        else:
            continue
        if fam == family or res:
            draft.families.append({"family": fam, "window": w, "params": params})
        first = first or w
    meta = {
        "name": name, "index": index, "family": family, "attempt": attempt,
        "anomalies": draft.families, "plan_duration_s": round(plan.duration_s, 1),
        "link_loss_action": raw["drone"]["link_loss_action"],
    }  # fmt: skip
    return raw, meta


def assets_of(raw: dict) -> dict[str, Any]:
    """Lo que el monitor conoce de antemano de sus activos: la base, el radar, el dron, los
    periodos de las fuentes y el receptor (el C/N0 y el AGC nominales son los del simulador)."""
    sensors, drone, radar, gps = (
        raw["sensors"],
        raw["drone"],
        raw["sensors"]["radar"],
        raw["sensors"]["gps"],
    )
    return {
        "base": {"x": 0.0, "y": 0.0},
        "drone": {
            "max_airspeed_mps": drone["max_airspeed_mps"],
            "wind_limit_mps": drone["wind_limit_mps"],
            "cruise_mps": drone["cruise_speed_mps"],
        },  # fmt: skip
        "periods_s": {
            k: sensors[k]["period_s"] for k in ("gps", "radar", "link", "meteo", "battery")
        },
        "gps": {"sigma_m": round(math.hypot(gps["gm_sigma_m"], gps["white_sigma_m"]), 3)},
        "radar": {
            "x": radar["x"],
            "y": radar["y"],
            "max_range_m": radar["max_range_m"],
            "sigma0_m": radar["sigma_m"],
            "sigma_per_km_m": radar["sigma_per_km_m"],
        },  # fmt: skip
        "gnss": {
            "cn0_nominal_dbhz": gps.get("cn0_nominal_dbhz", 45.0),
            "agc_nominal_db": gps.get("agc_nominal_db", 0.0),
        },  # fmt: skip
    }


# --- Generación y escritura ---------------------------------------------------------------------


def _gz(path: Path, text: str) -> None:
    path.write_bytes(gzip.compress(text.encode("utf-8"), compresslevel=6, mtime=0))


def make_variant(job: tuple[dict, int, str, Path]) -> tuple[dict, float]:
    """Muestrea y genera una variante, y escribe sus ficheros. Repite si queda algún segundo de
    `unexplained` (un escenario mal escrito) o no valida."""
    manifest, index, family, out = job
    t0 = time.perf_counter()
    discarded: list[dict[str, Any]] = []
    for attempt in range(MAX_ATTEMPTS):
        try:
            raw, meta = sample_variant(manifest, index, family, attempt)
            run = generate(ScenarioConfig.model_validate(raw))
        except ValueError as exc:  # no valida: otro intento
            discarded.append({"attempt": attempt, "reason": str(exc).splitlines()[0][:120]})
            continue
        unexplained = sum(r.facets["drone.cause"] == "unexplained" for r in run.states)
        if unexplained == 0:
            break
        discarded.append({"attempt": attempt, "reason": f"{unexplained} s unexplained"})
    else:
        raise RuntimeError(f"variant {index} ({family}): no valid sample in {MAX_ATTEMPTS} tries")
    folder = out / "variants" / meta["name"]
    folder.mkdir(parents=True)
    (folder / "scenario.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    (folder / "assets.yaml").write_text(yaml.safe_dump(assets_of(raw), sort_keys=False), "utf-8")
    _gz(folder / "events.jsonl.gz", "".join(e.model_dump_json() + "\n" for e in run.events))
    _gz(folder / "states.jsonl.gz", "".join(s.model_dump_json() + "\n" for s in run.states))
    meta |= {"duration_s": run.truth.duration_s, "discarded": discarded}
    (folder / "meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return meta, round(time.perf_counter() - t0, 3)


def assign_splits(manifest: dict, metas: list[dict]) -> dict[str, str]:
    """Partición por variante, estratificada por familia, con un orden estable por nombre."""
    split = manifest["split"]
    out: dict[str, str] = {}
    for family in sorted({m["family"] for m in metas}):
        names = sorted(
            (m["name"] for m in metas if m["family"] == family),
            key=lambda n: stable_int(manifest["seed"], "split", n),
        )
        n_train = round(split["train"] * len(names))
        n_val = round(split["validation"] * len(names))
        for i, name in enumerate(names):
            out[name] = "train" if i < n_train else "validation" if i < n_train + n_val else "test"
    return out


def build(manifest: dict, out_root: Path, workers: int, n: int | None = None) -> Path:
    n = n or manifest["n_variants"]
    out = out_root / manifest["dataset"]
    shutil.rmtree(out, ignore_errors=True)
    (out / "variants").mkdir(parents=True)
    families = quota_families(manifest, n)
    jobs = [(manifest, i, fam, out) for i, fam in enumerate(families)]
    if workers > 1:
        with Pool(workers) as pool:
            results = pool.map(make_variant, jobs, chunksize=8)
    else:
        results = [make_variant(j) for j in jobs]
    metas = [m for m, _ in results]
    splits = assign_splits(manifest, metas)
    index = [{**m, "split": splits[m["name"]]} for m in metas]
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    timing = {m["name"]: t for m, t in results}
    (out / "timing.json").write_text(json.dumps(timing, indent=1) + "\n", encoding="utf-8")
    (out / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--n", type=int, default=None, help="menos variantes (pruebas)")
    args = parser.parse_args(argv)
    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    out = build(copy.deepcopy(manifest), args.out, args.workers, args.n)
    print(f"{out}: {time.perf_counter() - t0:.1f} s en total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
