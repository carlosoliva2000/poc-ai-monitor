"""YAML de escenario (`scenarios/*.yaml`, `contracts/eventos.md` §8.1).

Los modelos validan el diccionario ya leído; este paquete no depende de PyYAML.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .enums import SensorSource

IsoUtcSeconds = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")]
Positive = Annotated[float, Field(gt=0)]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DroneConfig(Config):
    cruise_speed_mps: Positive
    max_accel_mps2: Positive
    max_turn_rate_dps: Positive
    altitude_m: float
    acceptance_radius_m: Positive
    lookahead_m: Positive


class WaypointConfig(Config):
    id: str
    x: float
    y: float


class MissionConfig(Config):
    id: str
    waypoints: list[WaypointConfig] = Field(min_length=1)
    return_to_base: Literal[True]  # por ahora solo se admiten misiones con vuelta a la base


class GpsConfig(Config):
    period_s: Positive
    sigma_m: float = Field(ge=0)
    sats: int
    hdop: float


class RadarConfig(Config):
    id: Literal["radar-1"]  # es el `source` del sobre de `TrackUpdated`
    period_s: Positive
    sigma_m: float = Field(ge=0)


class MeteoConfig(Config):
    id: Literal["meteo-1"]  # es el `source` del sobre de `WindReported`
    period_s: Positive
    sigma_mps: float = Field(ge=0)
    sigma_deg: float = Field(ge=0)


class LinkConfig(Config):
    period_s: Positive
    controller_id: str
    rssi_dbm: float
    latency_ms: float


class BatteryConfig(Config):
    period_s: Positive
    start_pct: float = Field(ge=0, le=100)
    drain_pct_per_min: float = Field(ge=0)


class SensorsConfig(Config):
    gps: GpsConfig
    radar: RadarConfig
    meteo: MeteoConfig
    link: LinkConfig
    battery: BatteryConfig


class WindBase(Config):
    speed_mps: float = Field(ge=0)
    gust_mps: float = Field(ge=0)
    from_deg: float


class WindEpisode(WindBase):
    """Episodio con rampa de subida y bajada de `ramp_s` (la procedencia salta de golpe)."""

    start_s: float = Field(ge=0)
    end_s: float
    ramp_s: Positive

    @model_validator(mode="after")
    def _check_window(self) -> "WindEpisode":
        if self.end_s <= self.start_s:
            raise ValueError("end_s debe ser mayor que start_s")
        return self


class WindConfig(Config):
    base: WindBase
    episodes: list[WindEpisode]


class SpoofingConfig(Config):
    """GPS reportado = real + desfase que crece a `drift_rate_mps` hacia `direction_deg`."""

    start_s: float = Field(ge=0)
    end_s: float
    drift_rate_mps: Positive
    direction_deg: float

    @model_validator(mode="after")
    def _check_window(self) -> "SpoofingConfig":
        if self.end_s <= self.start_s:
            raise ValueError("end_s debe ser mayor que start_s")
        return self


class Point(Config):
    x: float
    y: float


class LinkHint(Config):
    controller_id: str
    rssi_dbm: float
    latency_ms: float


class HijackConfig(Config):
    """Desde `start_s` el objetivo pasa a `target`; en `end_s` (`null`: nunca) vuelve el mando."""

    start_s: float = Field(ge=0)
    end_s: float | None
    target: Point
    link_hint: LinkHint

    @model_validator(mode="after")
    def _check_window(self) -> "HijackConfig":
        if self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError("end_s debe ser mayor que start_s")
        return self


class FaultConfig(Config):
    """Fuente silenciada en `[start_s, end_s)`: solo afecta a lo que se reporta."""

    source: SensorSource
    start_s: float = Field(ge=0)
    end_s: float

    @model_validator(mode="after")
    def _check_window(self) -> "FaultConfig":
        if self.end_s <= self.start_s:
            raise ValueError("end_s debe ser mayor que start_s")
        return self


class ScenarioConfig(Config):
    name: str
    description: str
    seed: int
    t0: IsoUtcSeconds
    max_duration_s: Positive
    drone: DroneConfig
    mission: MissionConfig
    sensors: SensorsConfig
    wind: WindConfig
    spoofing: SpoofingConfig | None
    hijack: HijackConfig | None
    faults: list[FaultConfig]
