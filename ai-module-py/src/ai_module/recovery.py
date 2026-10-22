"""Criterio de recuperación tras un engaño o una pérdida del GPS (función pura).

Cuando acaba un spoofing o una pérdida de GPS, el GPS vuelve a informar bien y **salta de golpe**
a la posición real, lejos de la ruta: salta `ROUTE_DEVIATION` aunque el dron ya corrija. Es
recuperación solo si se cumplen las dos condiciones de la skill `route-deviation` (paso 0):

1. hay una alerta del GPS (`GPS_SPOOFING`, `GPS_JAMMING` o `SENSOR_FAULT`) abierta o cerrada hace
   60 s de tiempo simulado o menos;
2. la desviación del GPS da un salto brusco: de menos de 15 m a más de 30 m entre dos muestras
   consecutivas (1 s). El dron vuela a unos 15 m/s: el viento y el secuestro alejan al dron de la
   ruta como mucho a ese ritmo (en `demo`, 7 m -> 21 m -> 37 m en el secuestro), mientras que un GPS
   que vuelve a la posición real salta de golpe (6 m -> 74 m).

Esta función **no la ejecuta el monitor** para dar pistas al LLM: la recuperación la concluye el
modelo con la skill y las tools. Solo la usan las pruebas (para comprobar que la skill está bien
planteada sobre los datos) y, como mucho, el modo guiado.
"""

from collections.abc import Sequence

LOW_M = 15.0
HIGH_M = 30.0
JUMP_WITHIN_S = 1.0
RECENT_ALERT_S = 60.0


def has_sudden_jump(deviation: Sequence[tuple[float, float]]) -> bool:
    """`deviation`: pares `(sim_time, desviación del GPS en m)` ordenados por tiempo. Hay salto
    si algún par pasa de < 15 m a > 30 m en 1 s o menos (entre muestras consecutivas)."""
    for i, (t_low, low) in enumerate(deviation):
        if low >= LOW_M:
            continue
        for t_high, high in deviation[i + 1 :]:
            if t_high - t_low > JUMP_WITHIN_S:
                break
            if high > HIGH_M:
                return True
    return False


def gps_alert_is_recent(now: float, active_until: float | None) -> bool:
    """`active_until`: último instante en que hubo una alerta del GPS abierta (`now` si sigue
    abierta, `None` si nunca la hubo)."""
    return active_until is not None and now - active_until <= RECENT_ALERT_S


def is_gps_recovery(
    deviation: Sequence[tuple[float, float]], now: float, gps_alert_active_until: float | None
) -> bool:
    return gps_alert_is_recent(now, gps_alert_active_until) and has_sudden_jump(deviation)
