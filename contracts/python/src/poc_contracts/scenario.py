"""YAML de escenario (`scenarios/*.yaml`, `contracts/eventos.md` §8.1).

Los modelos validan el diccionario ya leído; este paquete no depende de PyYAML.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .commands import ScheduledCommand
from .enums import FaultMode, SensorSource

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


class SensorEpisode(Config):
    """Episodio de degradación de una fuente (E6): de `start_s` a `end_s`, con rampa de subida y
    bajada de `ramp_s` (0: el valor cambia de golpe). Los valores objetivo que no se den se quedan
    en los nominales. Con `labeled: false` es ruido normal del vuelo: no da etiqueta (la evaluación
    lo cuenta aparte)."""

    start_s: float = Field(ge=0)
    end_s: float
    ramp_s: float = Field(default=0.0, ge=0)
    labeled: bool = True

    @model_validator(mode="after")
    def _check_window(self) -> "SensorEpisode":
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be greater than start_s")
        return self

    def level(self, t: float) -> float | None:
        """Cuánto del valor objetivo se aplica en `t` (0 a 1), o `None` fuera del episodio. La
        misma cuenta que los episodios de viento."""
        if not self.start_s <= t <= self.end_s:
            return None
        if self.ramp_s == 0:
            return 1.0
        return min(1.0, (t - self.start_s) / self.ramp_s, (self.end_s - t) / self.ramp_s)


def _check_no_overlap(episodes: "list[SensorEpisode]") -> None:
    ordered = sorted(episodes, key=lambda e: e.start_s)
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b.start_s < a.end_s:
            raise ValueError("episodes of the same source must not overlap")


class GpsEpisode(SensorEpisode):
    """Degradación del GPS con fix 3D (menos satélites, peor `hdop`). La pérdida total del fix es
    el fallo `loss`, que manda si coincide con un episodio."""

    sats: int | None = Field(default=None, ge=4)  # con menos de 4 no hay fix 3D: es `loss`
    hdop: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_target(self) -> "GpsEpisode":
        if self.sats is None and self.hdop is None:
            raise ValueError("a gps episode needs sats, hdop or both")
        return self


class LinkEpisode(SensorEpisode):
    """Degradación del enlace (más latencia, menos RSSI) con el mismo controlador: cambiar de
    controlador es un secuestro (`hijack`), que manda si coincide con un episodio."""

    latency_ms: float | None = Field(default=None, ge=0)
    rssi_dbm: float | None = None

    @model_validator(mode="after")
    def _check_target(self) -> "LinkEpisode":
        if self.latency_ms is None and self.rssi_dbm is None:
            raise ValueError("a link episode needs latency_ms, rssi_dbm or both")
        return self


class GpsConfig(Config):
    period_s: Positive
    sigma_m: float = Field(ge=0)
    sats: int
    hdop: float
    episodes: list[GpsEpisode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_episodes(self) -> "GpsConfig":
        _check_no_overlap(list(self.episodes))
        return self


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
    episodes: list[LinkEpisode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_episodes(self) -> "LinkConfig":
        _check_no_overlap(list(self.episodes))
        return self


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
            raise ValueError("end_s must be greater than start_s")
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
            raise ValueError("end_s must be greater than start_s")
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
            raise ValueError("end_s must be greater than start_s")
        return self


class FaultConfig(Config):
    """Fallo en `[start_s, end_s)`: `mute` (la fuente no se publica) o `loss` (solo GPS)."""

    source: SensorSource
    mode: FaultMode
    start_s: float = Field(ge=0)
    end_s: float

    @model_validator(mode="after")
    def _check_window(self) -> "FaultConfig":
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be greater than start_s")
        if self.mode == FaultMode.LOSS and self.source != SensorSource.GPS:
            raise ValueError("`loss` only exists for the GPS")
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
    commands: list[ScheduledCommand] = []  # opcional (v0.18): comandos del instructor programados
