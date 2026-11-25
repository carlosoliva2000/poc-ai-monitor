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
    wind_limit_mps: Positive = 12.0
    """Viento máximo con el que mantiene la ruta: resistencia al viento de la ficha del DJI Matrice
    300 RTK, 12 m/s (https://www.dji.com/matrice-300/info)."""
    max_airspeed_mps: Positive = 17.0
    """Velocidad máxima respecto al aire con posicionamiento: modo P del Matrice 300 RTK, 17 m/s
    (en modo S, 23 m/s; https://www.dji.com/matrice-300/info). Separada de la de crucero: si el
    viento la supera, el dron deriva."""
    lateral_ki_per_s: float = Field(default=0.05, ge=0)
    """Ganancia integral del error lateral (1/s) del guiado de multirrotor ⚠️."""
    link_loss_timeout_s: Positive = 10.0
    """Failsafe de enlace: segundos sin enlace antes de actuar (PX4 `COM_DL_LOSS_T`: 10 s)."""
    link_loss_action: Literal["continue", "hold", "return", "land"] = "continue"
    """Qué hace al saltar el failsafe del enlace: seguir el plan (por defecto, como `NAV_DLL_ACT`
    = 0 de PX4), mantener la posición, volver a casa o aterrizar."""
    land_duration_s: Positive = 20.0
    """Lo que tarda en aterrizar (⚠️: 60 m a 3 m/s); termina el vuelo con `reason: landed`."""
    estimator_position_gain: float = Field(default=0.6, ge=0, le=1)
    """Estimador a bordo (filtro complementario): cuánto de la innovación del GPS corrige la
    posición en cada medida ⚠️."""
    estimator_wind_gain: float = Field(default=0.5, ge=0)
    """Y cuánto (m/s por m de innovación) corrige el viento estimado ⚠️."""


class WaypointConfig(Config):
    id: str
    x: float
    y: float


class MissionConfig(Config):
    id: str
    controller_id: str = "GCS-1"
    """Controlador de la misión (`MissionPlanned.mission_controller_id`)."""
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
    gm_sigma_m: float = Field(default=1.5, ge=0)
    """Receptor realista: σ del error de posición con memoria
    (Gauss-Markov de primer orden) en cada eje ⚠️."""
    gm_tau_s: Positive = 90.0
    """Constante de tiempo de ese error (⚠️ 60–120 s)."""
    white_sigma_m: float = Field(default=0.3, ge=0)
    """σ del ruido blanco pequeño que se suma en cada eje ⚠️."""

    @model_validator(mode="after")
    def _check_episodes(self) -> "GpsConfig":
        _check_no_overlap(list(self.episodes))
        return self


class RadarConfig(Config):
    period_s: Positive
    sigma_m: float = Field(ge=0)
    x: float = 0.0
    y: float = 0.0
    """Posición del radar (en el mapa)."""
    sigma_per_km_m: float = Field(default=2.0, ge=0)
    """σ(distancia) = `sigma_m` + `sigma_per_km_m` · distancia en km ⚠️."""
    max_range_m: Positive = 6000.0
    """Alcance máximo: más lejos no hay traza (⚠️)."""


class MeteoConfig(Config):
    period_s: Positive
    sigma_mps: float = Field(ge=0)
    sigma_deg: float = Field(ge=0)
    factor: Positive = 0.8
    """Estación en tierra: viento medido = viento en el dron ×
    `factor` ⚠️ (0,7–0,9)."""
    lag_s: float = Field(default=30.0, ge=0)
    """Retraso: media móvil del viento de los últimos `lag_s` segundos ⚠️."""


class LinkConfig(Config):
    period_s: Positive
    rssi_dbm: float
    """RSSI nominal: el de 1 km de la base (cae 20·log10(d))."""
    latency_ms: float
    rssi_floor_dbm: float = -95.0
    """Por debajo de esta señal no hay enlace (el failsafe empieza a contar) ⚠️."""
    loss_rssi50_dbm: float = -90.0
    """Señal con la que se pierde el 50 % de los paquetes (logística en el RSSI) ⚠️."""
    loss_slope_db: Positive = 2.5
    episodes: list[LinkEpisode] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_episodes(self) -> "LinkConfig":
        _check_no_overlap(list(self.episodes))
        return self


class BatteryConfig(Config):
    period_s: Positive
    start_pct: float = Field(ge=0, le=100)
    capacity_wh: Positive = 450.0
    """Energía de la batería (⚠️, un cuadricóptero de ~5 kg)."""
    hover_power_w: Positive = 400.0
    """Potencia en estacionario (⚠️); la curva en U del resto sale de Zeng et al."""
    efficiency: float = Field(default=0.75, gt=0, le=1)
    """Eficiencia eléctrica y del motor (⚠️ 0,7–0,8)."""
    return_reserve: float = Field(default=0.1, ge=0)
    """Reserva sobre la energía para volver a casa para decir que «no llega» ⚠️."""
    failsafe_return_pct: float = Field(default=7.0, ge=0)
    """Carga por debajo de la cual vuelve a casa (PX4 `BAT_CRIT_THR`: 7 %)."""
    failsafe_land_pct: float = Field(default=5.0, ge=0)
    """Y por debajo de la cual aterriza (PX4 `BAT_EMERGEN_THR`: 5 %). Con el 15 % (`BAT_LOW_THR`)
    solo hay aviso: no cambia de modo."""
    endurance_action: Literal["none", "return"] = "return"
    """Qué hace al no llegar a casa con la energía que queda."""


class SensorsConfig(Config):
    gps: GpsConfig
    radar: RadarConfig
    meteo: MeteoConfig
    link: LinkConfig
    battery: BatteryConfig


class WindBase(Config):
    speed_mps: float = Field(ge=0)
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


class EmitterPosition(Config):
    x: float
    y: float
    power_db: float = 12.0
    """Nivel a 1 km de distancia, en dB sobre el ruido (cae 20·log10(d))."""


class JammerConfig(Config):
    """Emisor de interferencia con posición: baja el C/N0 y el AGC del
    receptor según su distancia. Solo en la verdad y en la vista del instructor."""

    id: str
    x: float
    y: float
    power_db: float = 25.0
    start_s: float = Field(ge=0)
    end_s: float

    @model_validator(mode="after")
    def _check_window(self) -> "JammerConfig":
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be greater than start_s")
        return self


class SpoofingConfig(Config):
    """GPS reportado = real + desfase que crece a `drift_rate_mps` hacia `direction_deg`."""

    emitter: EmitterPosition | None = None
    """Posición del emisor de engaño (por defecto, la base): sube el C/N0 y baja el AGC."""

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


class HijackConfig(Config):
    """Desde `start_s` el objetivo pasa a `target`; en `end_s` (`null`: nunca) vuelve el mando."""

    start_s: float = Field(ge=0)
    end_s: float | None
    target: Point
    """`target` es la posición de la estación del secuestrador."""

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


class LabelingConfig(Config):
    """Umbrales operativos de las etiquetas por faceta (`states.jsonl`). Convención nuestra, no del
    simulador; valores de partida ⚠️."""

    wind_notable_mps: Positive = 5.0  # viento medio por encima del cual es «notable»
    gps_sigma_bad_m: Positive = 5.0  # σ real de la posición del GPS: por encima, «degradada»
    link_latency_bad_ms: Positive = 100.0  # latencia del enlace: por encima, «degradada»
    link_loss_bad_pct: Positive = 20.0  # paquetes perdidos: por encima, «degradada»
    deviated_m: Positive = 25.0  # distancia a la referencia del modo para «desviado»
    returning_m: Positive = 15.0  # y para volver a «en ruta» (histéresis)
    battery_low_pct: Positive = 15.0
    battery_critical_pct: Positive = 7.0


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
    emitters: list[JammerConfig] = Field(default_factory=list)
    labeling: LabelingConfig = Field(default_factory=LabelingConfig)
    commands: list[ScheduledCommand] = []  # opcional (v0.18): comandos del instructor programados
