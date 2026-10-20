#!/usr/bin/env python3
"""Comprobación rápida del controlador y de los escenarios (hecha por Claude el 16/10/2026).

NO es el generador: es una referencia mínima para que el generador de verdad (platform/) reproduzca
la misma física. Sin ruido de sensores, sin eventos. Uso:
    python3 ref/simcheck_controlador.py scenarios/nominal.yaml scenarios/demo.yaml

Física (2D, paso 0,1 s):
- Velocidad respecto al aire = cruise_speed en la dirección del rumbo (acelera con max_accel).
- Velocidad respecto al suelo = velocidad respecto al aire + viento (el viento se da por procedencia).
- Guiado "punto de mira" sobre el tramo: se proyecta la posición QUE CREE TENER el dron (GPS) sobre el
  tramo pendiente y se apunta a un punto lookahead_m por delante. El rumbo gira hacia él con el giro
  limitado a max_turn_rate. Sin compensación integral del viento: con viento lateral w el error
  estacionario es lookahead * tan(asin(w / v)) (≈ 8 m con 2 m/s; ≈ 50 m con 12 m/s).
- Cambio de waypoint cuando el GPS está a menos de acceptance_radius_m.
- Secuestro: el objetivo pasa a ser `target`; al recuperar el control se vuelve a seguir el tramo pendiente.
- Spoofing: GPS = real + desfase creciente; el controlador usa el GPS, así que el dron se desvía de verdad.

Resultado con los YAML del paquete (desviación máxima de la verdad respecto al plan):
  nominal ≈ 13 m · viento ≈ 52 m · spoofing: verdad ≈ 75 m con el GPS < 10 m hasta el fin del engaño ·
  secuestro ≈ 650–950 m (según duración) y vuelve a la ruta.
"""
import math
import sys

import yaml


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) if l2 else 0.0
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def cross_track(p, route):
    return min(seg_dist(p, route[i], route[i + 1]) for i in range(len(route) - 1))


def wind_vector(t, wind):
    speed, frm = wind["base"]["speed_mps"], wind["base"]["from_deg"]
    for e in wind["episodes"]:
        if e["start_s"] <= t <= e["end_s"]:
            k = min(1.0, (t - e["start_s"]) / e["ramp_s"], (e["end_s"] - t) / e["ramp_s"])
            speed, frm = speed + (e["speed_mps"] - speed) * k, e["from_deg"]
    to = math.radians(frm + 180.0)
    return speed * math.sin(to), speed * math.cos(to)


def simulate(cfg):
    d = cfg["drone"]
    route = [(0.0, 0.0)] + [(w["x"], w["y"]) for w in cfg["mission"]["waypoints"]] + [(0.0, 0.0)]
    x = y = speed = t = 0.0
    heading = math.degrees(math.atan2(route[1][0], route[1][1]))
    i, dt = 1, 0.1
    spoof, hijack = cfg["spoofing"], cfg["hijack"]
    samples = []
    while t < cfg["max_duration_s"] and i < len(route):
        off = (0.0, 0.0)
        if spoof and spoof["start_s"] <= t < spoof["end_s"]:
            k = (t - spoof["start_s"]) * spoof["drift_rate_mps"]
            a = math.radians(spoof["direction_deg"])
            off = (k * math.sin(a), k * math.cos(a))
        gx, gy = x + off[0], y + off[1]  # lo que reporta (y cree) el dron
        hijacked = hijack and hijack["start_s"] <= t < (hijack["end_s"] or float("inf"))
        if hijacked:
            target = (hijack["target"]["x"], hijack["target"]["y"])
        else:
            a, b = route[i - 1], route[i]
            if math.hypot(b[0] - gx, b[1] - gy) < d["acceptance_radius_m"]:
                i += 1
                continue
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            s = (gx - a[0]) * u[0] + (gy - a[1]) * u[1]
            s = min(length, s + d["lookahead_m"])
            target = (a[0] + u[0] * s, a[1] + u[1] * s)
        desired = math.degrees(math.atan2(target[0] - gx, target[1] - gy))
        err = (desired - heading + 540.0) % 360.0 - 180.0
        step = d["max_turn_rate_dps"] * dt
        heading = (heading + max(-step, min(step, err))) % 360.0
        speed = min(d["cruise_speed_mps"], speed + d["max_accel_mps2"] * dt)
        wx, wy = wind_vector(t, cfg["wind"])
        x += (speed * math.sin(math.radians(heading)) + wx) * dt
        y += (speed * math.cos(math.radians(heading)) + wy) * dt
        t += dt
        samples.append((t, cross_track((x, y), route), cross_track((gx, gy), route), math.hypot(off[0], off[1])))
    return t, samples


if __name__ == "__main__":
    for path in sys.argv[1:]:
        cfg = yaml.safe_load(open(path, encoding="utf-8"))
        end, samples = simulate(cfg)
        print(f"{path}: fin en t = {end:.0f} s")
        for a in range(0, int(end) + 1, 25):
            win = [s for s in samples if a <= s[0] < a + 25]
            if win:
                print(f"  {a:4d}-{a + 25:<4d} verdad={max(s[1] for s in win):7.1f} m  "
                      f"gps={max(s[2] for s in win):7.1f} m  desfase_gps={max(s[3] for s in win):5.1f} m")
