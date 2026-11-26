"""Inventario de assets y a cuál pertenece cada tipo de evento del simulador.

Los assets son fijos (`d1`, `radar-1`, `meteo-1`, `gcs-1`); su ficha sale del escenario cargado y
solo lleva lo que se conoce de antemano (nunca viento, fallos ni nada de la verdad).
"""

from dataclasses import dataclass

from poc_contracts.enums import EventType
from poc_contracts.scenario import ScenarioConfig
from poc_contracts.sim_api import AssetInfo, AssetType

DRONE, RADAR, METEO, GROUND = "d1", "radar-1", "meteo-1", "gcs-1"
INSTRUCTOR = "instructor"  # registro aparte de la parte del instructor (no es un asset)

_T = EventType
ASSET_OF_TYPE: dict[EventType, str] = {
    _T.POSITION_UPDATED: DRONE,
    _T.GNSS_STATUS: DRONE,
    _T.AUTOPILOT_STATUS: DRONE,
    _T.BATTERY_STATUS: DRONE,
    _T.MISSION_PLANNED: DRONE,
    _T.MISSION_STARTED: DRONE,
    _T.WAYPOINT_REACHED: DRONE,
    _T.MISSION_COMPLETED: DRONE,
    _T.TRACK_UPDATED: RADAR,
    _T.WIND_REPORTED: METEO,
    _T.LINK_STATUS: GROUND,
}
INSTRUCTOR_TYPES: frozenset[EventType] = frozenset(
    {
        _T.FAULT_INJECTED,
        _T.FAULT_CLEARED,
        _T.INSTRUCTOR_COMMAND,
        _T.EXERCISE_INJECTS,
        _T.INTERACTIVE_MODE_CHANGED,
    }
)
LIFECYCLE_OF_TYPE: dict[EventType, str] = {
    _T.SIMULATION_STARTED: "RunStarted",
    _T.SIMULATION_RESET: "RunReset",
    _T.SIMULATION_FINISHED: "RunFinished",
}
ASSET_IDS: tuple[str, ...] = (DRONE, RADAR, METEO, GROUND)


@dataclass(frozen=True)
class _Spec:
    type: AssetType
    name: str
    subject: str


_SPECS: dict[str, _Spec] = {
    DRONE: _Spec(AssetType.DRONE, "Drone d1", "d1"),
    RADAR: _Spec(AssetType.RADAR, "Radar 1", "d1"),
    METEO: _Spec(AssetType.WEATHER_STATION, "Weather station 1", "zone1"),
    GROUND: _Spec(AssetType.GROUND_STATION, "Ground station 1", "d1"),
}


def message_types(asset_id: str) -> list[str]:
    return [t.value for t, a in ASSET_OF_TYPE.items() if a == asset_id]


def _config(asset_id: str, c: ScenarioConfig) -> dict[str, float | str]:
    s = c.sensors
    if asset_id == DRONE:
        return {
            "max_airspeed_mps": c.drone.max_airspeed_mps,
            "wind_limit_mps": c.drone.wind_limit_mps,
            "cruise_speed_mps": c.drone.cruise_speed_mps,
            "gps_period_s": s.gps.period_s,
            "battery_period_s": s.battery.period_s,
            "gps_sigma_m": s.gps.sigma_m,
            "cn0_nominal_dbhz": s.gps.cn0_nominal_dbhz,
            "agc_nominal_db": s.gps.agc_nominal_db,
            "mission_controller_id": c.mission.controller_id,
        }
    if asset_id == RADAR:
        r = s.radar
        return {
            "x": r.x,
            "y": r.y,
            "period_s": r.period_s,
            "sigma_m": r.sigma_m,
            "sigma_per_km_m": r.sigma_per_km_m,
            "max_range_m": r.max_range_m,
        }
    if asset_id == METEO:
        return {"period_s": s.meteo.period_s}
    # la estación de tierra está en la base y es el controlador de la misión
    return {
        "x": 0.0,
        "y": 0.0,
        "period_s": s.link.period_s,
        "controller_id": c.mission.controller_id,
    }


def subject_of(asset_id: str) -> str:
    return _SPECS[asset_id].subject


def asset_info(asset_id: str, config: ScenarioConfig) -> AssetInfo:
    spec = _SPECS[asset_id]
    return AssetInfo(
        id=asset_id,
        type=spec.type,
        name=spec.name,
        subject=spec.subject,
        message_types=message_types(asset_id),
        config=_config(asset_id, config),
    )
