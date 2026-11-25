"""Enlace de mando y emisores (E7a, paso 5): RSSI, pérdida de paquetes, C/N0 y AGC del receptor.

Modelos sencillos y documentados (valores ⚠️ salvo que se diga lo contrario):
- **RSSI**: pérdidas en espacio libre, `RSSI = RSSI(1 km) − 20·log10(d_km)` con la distancia a la
  base, menos la atenuación de un episodio de degradación del enlace.
- **Pérdida de paquetes**: logística en el RSSI (50 % con `loss_rssi50_dbm`).
- **Emisores** : a la distancia `d` un emisor de potencia `P` (dB a 1 km,
  sobre el ruido) llega con `L = P − 20·log10(d_km)`. Interferencia: el C/N0 baja
  `10·log10(1 + 10^(L/10))` y el AGC baja lo mismo. Engaño: la señal falsa es más fuerte que la
  real: el C/N0 **sube** (como mucho `MAX_SPOOF_CN0_GAIN_DB`) y el AGC **baja** la mitad de esa
  ganancia.
"""

import math

from poc_contracts.run_files import TruthEmitter
from poc_contracts.scenario import EmitterPosition, ScenarioConfig

from .disturbances import is_hijacked

SPOOFER_ID = "spoofer-1"
HIJACKER_ID = "hijacker-1"
MAX_SPOOF_CN0_GAIN_DB = 8.0
MIN_DISTANCE_KM = 0.05


def distance_km(x: float, y: float, ox: float = 0.0, oy: float = 0.0) -> float:
    return max(MIN_DISTANCE_KM, math.hypot(x - ox, y - oy) / 1000.0)


def rssi_dbm(config: ScenarioConfig, x: float, y: float, t: float) -> float:
    """Señal del enlace en la posición (x, y) a la hora `t`, sin ruido."""
    lk = config.sensors.link
    rssi = lk.rssi_dbm - 20.0 * math.log10(distance_km(x, y))
    for e in lk.episodes:
        k = e.level(t)
        if k is not None:
            if e.rssi_dbm is not None:
                rssi -= k * (lk.rssi_dbm - e.rssi_dbm)
            break
    return rssi


def loss_probability(config: ScenarioConfig, rssi: float) -> float:
    """Probabilidad de perder un paquete con esa señal (logística)."""
    lk = config.sensors.link
    z = (rssi - lk.loss_rssi50_dbm) / lk.loss_slope_db
    return 1.0 / (1.0 + math.exp(min(z, 60.0)))


def _db_sum(level_db: float) -> float:
    """`10·log10(1 + 10^(L/10))`: lo que sube el nivel al sumar una señal de `L` dB sobre el
    ruido."""
    return 10.0 * math.log10(1.0 + 10.0 ** (min(level_db, 200.0) / 10.0))


def emitter_effects(
    config: ScenarioConfig, t: float, x: float, y: float
) -> tuple[float, float, tuple[str, ...]]:
    """Variación del C/N0 y del AGC del receptor (dB) en (x, y) y ids de los emisores activos."""
    d_cn0 = d_agc = 0.0
    active: list[str] = []
    for j in config.emitters:
        if j.start_s <= t < j.end_s:
            drop = _db_sum(j.power_db - 20.0 * math.log10(distance_km(x, y, j.x, j.y)))
            d_cn0 -= drop
            d_agc -= drop
            active.append(j.id)
    sp = config.spoofing
    if sp is not None and sp.start_s <= t < sp.end_s:
        em = sp.emitter or EmitterPosition(x=0.0, y=0.0)
        gain = _db_sum(em.power_db - 20.0 * math.log10(distance_km(x, y, em.x, em.y)))
        applied = min(MAX_SPOOF_CN0_GAIN_DB, gain)  # lo que sube el C/N0…
        d_cn0 += applied
        d_agc -= 0.5 * applied  # …y el AGC baja la mitad de eso
        active.append(SPOOFER_ID)
    if is_hijacked(t, config.hijack):
        active.append(HIJACKER_ID)
    return d_cn0, d_agc, tuple(active)


def truth_emitters(config: ScenarioConfig) -> list[TruthEmitter]:
    """Emisores y estación del secuestrador con posición (solo en la verdad)."""
    out = [TruthEmitter(id=j.id, kind="jammer", x=j.x, y=j.y) for j in config.emitters]
    if config.spoofing is not None:
        em = config.spoofing.emitter or EmitterPosition(x=0.0, y=0.0)
        out.append(TruthEmitter(id=SPOOFER_ID, kind="spoofer", x=em.x, y=em.y))
    if config.hijack is not None:
        out.append(
            TruthEmitter(
                id=HIJACKER_ID, kind="hijacker", x=config.hijack.target.x, y=config.hijack.target.y
            )
        )
    return out
