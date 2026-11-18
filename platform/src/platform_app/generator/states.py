"""Estado de cada faceta por segundo (`states.jsonl`), a partir de la verdad ampliada.

Reglas de la especificación del núcleo v2 (`contracts/eventos.md` §8.7): `n/a` y `?` explícitos,
calidad por valor físico con umbral operativo, situación del dron respecto a la referencia del modo
(con histéresis) y causa con prioridad y pegajosa. Los umbrales están en el bloque `labeling` del
escenario. Lo escribe el generador: no hay un script aparte que reconstruya la física.
"""

from poc_contracts.scenario import ScenarioConfig
from poc_contracts.states import NOT_APPLICABLE as NA
from poc_contracts.states import NOT_OBSERVABLE as UNKNOWN
from poc_contracts.states import StateRow

from .simulator import Aux

# Prioridad de la causa de una desviación: es una convención nuestra, documentada; el árbol la
# aprende de las etiquetas.
CAUSE_PRIORITY = ["foreign_control", "spoofed_position", "dead_reckoning", "wind"]


def _causes(a: Aux, wind_notable_mps: float) -> list[str]:
    active = []
    if a.hijack:
        active.append("foreign_control")
    if a.spoofing:
        active.append("spoofed_position")
    if a.gps_loss:
        active.append("dead_reckoning")
    if a.wind_speed_mps >= wind_notable_mps:
        active.append("wind")
    return active


def _telemetry(a: Aux, cfg: ScenarioConfig) -> dict[str, str]:
    """Facetas de lo que viaja por el enlace del dron (GPS y batería), tal como serían con el
    enlace conectado."""
    lab = cfg.labeling
    out: dict[str, str] = {}
    out["gps.availability"] = "no_data" if a.gps_mute else "no_fix" if a.gps_loss else "normal"
    if out["gps.availability"] == "normal":
        out["gps.quality"] = "degraded" if a.gps_sigma_m > lab.gps_sigma_bad_m else "good"
        out["gps.integrity"] = "spoofed" if a.spoofing else "reliable"
    else:
        out["gps.quality"] = out["gps.integrity"] = NA
    out["battery.availability"] = "no_data" if a.battery_mute else "normal"
    if a.battery_mute:
        out["battery.level"] = out["battery.endurance"] = NA
    else:
        pct = a.battery_soc
        out["battery.level"] = (
            "critical"
            if pct < lab.battery_critical_pct
            else "low"
            if pct < lab.battery_low_pct
            else "normal"
        )
        out["battery.endurance"] = "sufficient" if a.can_reach_home else "cannot_reach_home"
    return out


def compute_states(
    cfg: ScenarioConfig, aux: dict[int, Aux], times: dict[int, float]
) -> list[StateRow]:
    """Una fila por cada instante de `aux` (`times`: paso → `sim_time`), en orden."""
    lab = cfg.labeling
    wind_limit = cfg.drone.wind_limit_mps
    rows: list[StateRow] = []
    situation, sticky = "on_route", NA
    for n in sorted(aux):
        a = aux[n]
        facets: dict[str, str] = {}
        hidden: dict[str, str] = {}

        # Entidades que dependen del enlace: con el enlace perdido son `?` y se guarda su estado.
        tele = _telemetry(a, cfg)
        for name, value in tele.items():
            if a.link_up:
                facets[name] = value
            else:
                facets[name], hidden[name] = UNKNOWN, value

        # Radar, estación y entorno: independientes del enlace.
        facets["radar.availability"] = (
            "no_data" if a.radar_mute else "normal" if a.radar_in_range else "out_of_range"
        )
        facets["meteo.availability"] = "no_data" if a.meteo_mute else "normal"
        w = a.wind_speed_mps
        facets["environment.wind"] = (
            "beyond_limit"
            if w >= wind_limit
            else "notable"
            if w >= lab.wind_notable_mps
            else "calm"
        )

        # Enlace.
        facets["link.availability"] = "connected" if a.link_up else "lost"
        degraded = (
            a.link_latency_ms > lab.link_latency_bad_ms or a.link_loss_pct > lab.link_loss_bad_pct
        )
        facets["link.quality"] = NA if not a.link_up else "degraded" if degraded else "good"

        # Dron: modo, situación (respecto a la referencia del modo, con histéresis) y causa.
        facets["drone.mode"] = a.mode
        causes = _causes(a, lab.wind_notable_mps)
        d = a.ref_dist_m
        if d > lab.deviated_m:
            if causes:
                situation = "deviated"
                sticky = min(causes, key=CAUSE_PRIORITY.index)
            elif situation in ("deviated", "returning"):
                situation = (
                    "returning"  # ya no hay causa activa y el dron sigue fuera: la causa pega
                )
            else:
                situation, sticky = "deviated", "unexplained"
        elif situation in ("deviated", "returning") and d > lab.returning_m:
            situation = "deviated" if situation == "deviated" and causes else "returning"
        else:
            situation, sticky = "on_route", NA
        facets["drone.situation"] = situation
        facets["drone.cause"] = sticky if situation != "on_route" else NA

        rows.append(StateRow(t=times[n], facets=facets, hidden=hidden))
    return rows
