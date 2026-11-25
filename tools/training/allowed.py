"""E7b, paso 2b: las entradas permitidas de cada árbol, con su justificación física.

Cada faceta solo puede usar las características de esta lista: las señales que, por física o por
la definición de la etiqueta, informan de ella. Son **relativas** (al dron, al sensor, al
periodo de la fuente o a la referencia nominal del receptor) salvo donde la magnitud absoluta tiene
sentido por sí misma: un porcentaje de batería, los metros con que se define «desviado», los
metros de precisión que dice el receptor, la latencia y la pérdida de paquetes con que se define
«enlace degradado», y el umbral de 5 m/s de viento «notable» (que es una definición operativa, no
una propiedad del dron).
"""

# ruff: noqa: E501  (las justificaciones son frases)

ALLOWED: dict[str, list[tuple[str, str]]] = {
    "gps.availability": [
        (
            "age_gps_p",
            "sin `PositionUpdated` durante varios periodos del GPS: fuente callada (`no_data`)",
        ),
        (
            "age_gnss_p",
            "el receptor publica con el GPS: si también calla, es la fuente y no el fix",
        ),
        ("gps_fix_3d", "un receptor vivo sin fix 3D es `no_fix`"),
        ("gps_sats", "sin fix no hay satélites"),
        ("gps_hdop", "sin fix el receptor da un `hdop` enorme"),
    ],
    "gps.quality": [
        (
            "gps_hacc_m",
            "precisión horizontal que dice el receptor, en metros: la etiqueta («σ real > 5 m») está en metros",
        ),
        ("gps_hdop", "la geometría de satélites degradada sube el σ de la posición"),
        ("gps_sats", "pocos satélites, peor posición"),
        (
            "innovation_max10_sigma",
            "una posición ruidosa se separa de la estima a bordo (en múltiplos de su σ)",
        ),
    ],
    "gps.integrity": [
        ("cn0_vs_nominal_db", "un emisor de engaño sube el C/N0 sobre el nominal del receptor"),
        ("agc_vs_nominal_db", "y baja el AGC (la mitad de lo que sube el C/N0)"),
        ("cn0_vs_base_db", "lo mismo frente a los primeros 60 s de ese receptor"),
        ("agc_vs_base_db", "ídem para el AGC"),
        ("cn0_vs_slow_db", "y frente a sus últimos 5 minutos (sin el último)"),
        ("agc_vs_slow_db", "ídem para el AGC"),
        (
            "gps_radar_avg_sigma",
            "un GPS arrastrado se separa de lo que ve el radar (en múltiplos del error esperado de ambos)",
        ),
        ("gps_radar_cusum_sigma", "la discrepancia que se acumula con el tiempo, también en σ"),
        (
            "wind_diff_over_limit",
            "el estimador a bordo absorbe la deriva como viento: el estimado se separa del de la estación",
        ),
    ],
    "radar.availability": [
        (
            "age_radar_p",
            "sin trazas durante varios periodos del radar: callado (`no_data`) o fuera de alcance",
        ),
        (
            "radar_range_ratio",
            "distancia del dron al radar entre su alcance: por encima de 1, `out_of_range`",
        ),
    ],
    "link.availability": [
        (
            "link_loss_pct",
            "nuestra estación mide los paquetes de telemetría perdidos: 100 % = enlace caído",
        ),
        ("tele_gap_p", "periodos sin ningún paquete de telemetría del dron"),
        ("age_link_p", "periodos desde el último `LinkStatus`"),
    ],
    "link.quality": [
        ("link_loss_pct", "la etiqueta («degradado») se define por la pérdida de paquetes en %"),
        ("link_latency_ms", "y por la latencia en ms"),
        ("link_latency_vs_base", "la latencia frente a la que tenía ese enlace al empezar"),
        (
            "link_rssi_vs_base_db",
            "la potencia recibida frente a la del principio (la pérdida de paquetes depende del RSSI)",
        ),
        ("link_rssi_dbm", "el RSSI absoluto, que es lo que gobierna la pérdida de paquetes"),
    ],
    "meteo.availability": [
        ("age_meteo_p", "sin `WindReported` durante varios periodos de la estación"),
    ],
    "battery.availability": [
        ("age_battery_p", "sin `BatteryStatus` durante varios periodos de la batería"),
    ],
    "battery.level": [
        ("battery_pct", "los niveles (15 % y 7 %) se definen sobre la carga en porcentaje"),
    ],
    "battery.endurance": [
        (
            "home_time_ratio",
            "tiempo para volver a casa a ritmo de crucero entre el tiempo restante: por encima de 1 no llega",
        ),
        ("battery_pct", "la carga que queda"),
        (
            "wind_est_over_airspeed",
            "un viento de cara frena la vuelta en proporción a la velocidad del dron",
        ),
        (
            "ground_speed_over_cruise",
            "si va más lento que el crucero, el tiempo de vuelta es mayor",
        ),
    ],
    "environment.wind": [
        (
            "wind_est_over_limit",
            "el viento estimado a bordo entre la resistencia declarada del dron: «notable» es 0,4 y `beyond_limit` es 1",
        ),
        ("wind_est_mean5_over_limit", "su media de 5 s, menos ruidosa"),
        (
            "station_wind_over_limit",
            "el de la estación en tierra, independiente del GPS, entre el mismo límite",
        ),
        ("age_meteo_p", "si la estación calla, solo queda la estima de a bordo"),
    ],
    "drone.mode": [
        ("mode_hold", "el autopiloto publica su modo (mantener)"),
        ("mode_return", "(volver)"),
        ("mode_land", "(aterrizar)"),
        ("age_autopilot_p", "sin paquetes del autopiloto no hay modo que leer"),
        ("link_loss_pct", "control ajeno: nuestra estación pierde el enlace mientras otro manda"),
        (
            "radar_dev_sigma",
            "y el radar ve al dron separarse de la ruta (en múltiplos de su error)",
        ),
        ("radar_dev_sigma_max30", "lo máximo que se ha separado en 30 s"),
        (
            "radar_dev_slope_cruise",
            "y a qué ritmo se aleja, en fracción de su velocidad de crucero",
        ),
    ],
    "drone.situation": [
        # la etiqueta es geométrica: distancia a la referencia del modo (25 m desviado, 15 m en ruta)
        ("gps_dev_m", "«desviado» se define a 25 m y «en ruta» a 15 m de la referencia del modo"),
        ("radar_dev_m", "lo mismo con el radar (que es independiente del GPS)"),
        ("gps_dev_sigma", "la desviación del GPS en múltiplos de su error esperado"),
        ("radar_dev_sigma", "la del radar en múltiplos de su error a esa distancia"),
        ("gps_dev_sigma_max30", "lo máximo en 30 s: «volviendo» es haber estado desviado"),
        ("radar_dev_sigma_max30", "ídem con el radar"),
        ("gps_dev_slope_cruise", "si se acerca o se aleja de la ruta, en fracción de su crucero"),
        ("radar_dev_slope_cruise", "ídem con el radar"),
        ("gps_radar_avg_sigma", "qué sensor creer cuando discrepan"),
        ("age_gps_p", "con el GPS caducado solo queda el radar"),
        ("age_radar_p", "y al revés"),
        ("mode_return", "en `failsafe_return` la referencia es el tramo a casa"),
        ("mode_hold", "en `failsafe_hold` es el punto de espera"),
    ],
    "drone.cause": [
        ("link_loss_pct", "control ajeno: se pierde el enlace"),
        ("tele_gap_p", "y la telemetría del dron deja de llegar"),
        ("radar_dev_sigma", "el radar ve al dron fuera de ruta"),
        ("radar_dev_sigma_max30", "lo máximo en 30 s"),
        ("radar_dev_slope_cruise", "y cómo se aleja (en fracción de su crucero)"),
        ("gps_dev_sigma", "desviación del GPS en σ"),
        ("gps_dev_sigma_max30", "lo máximo en 30 s"),
        ("cn0_vs_nominal_db", "posición engañada: C/N0 por encima del nominal"),
        ("agc_vs_nominal_db", "y AGC por debajo"),
        ("cn0_vs_slow_db", "frente a la referencia lenta del receptor"),
        ("agc_vs_slow_db", "ídem"),
        ("gps_radar_avg_sigma", "el GPS se separa del radar"),
        ("gps_radar_cusum_sigma", "y la discrepancia se acumula"),
        ("wind_diff_over_limit", "el viento estimado a bordo se separa del de la estación"),
        ("age_gps_p", "navegación a estima: el GPS calla o no tiene fix"),
        ("gps_fix_3d", "(sin fix)"),
        ("wind_est_over_limit", "viento: el estimado entre el límite del dron"),
        ("wind_est_over_airspeed", "y entre su velocidad máxima respecto al aire"),
        ("station_wind_over_limit", "el de la estación, independiente"),
        (
            "airspeed_over_max",
            "un dron con la velocidad respecto al aire al máximo ya no puede compensar",
        ),
        (
            "speed_gap_over_max",
            "la diferencia aire–suelo en fracción de ese máximo: es el viento que le gana",
        ),
        ("innovation_sigma", "diferencia entre el GPS y la estima en σ"),
    ],
}


def columns(facet: str, features: list[str]) -> list[int]:
    """Índices en `features` de las entradas permitidas de una faceta (falla si una no existe)."""
    return [features.index(name) for name, _ in ALLOWED[facet]]


# Las únicas características absolutas (con unidades del dron o del sensor) que una faceta puede
# usar, y por qué: la etiqueta o la física de esa faceta está definida en esas unidades.
ABSOLUTE_OK = {
    "gps_hacc_m",
    "gps_hdop",
    "gps_sats",
    "gps_fix_3d",  # lo que dice el receptor de sí mismo
    "gps_dev_m",
    "radar_dev_m",  # «desviado» se define a 25 m y «en ruta» a 15 m
    "link_loss_pct",
    "link_latency_ms",
    "link_rssi_dbm",  # «enlace degradado» y la pérdida de paquetes
    "battery_pct",
    "wind_est_mps",
    "station_wind_mps",  # niveles de batería y «notable» a 5 m/s
    "mode_hold",
    "mode_return",
    "mode_land",  # estado de modo, sin unidades
}

# Relativas por construcción (frente a la historia del propio receptor o a un cociente) que no están
# en `RELATIVE` porque ya existían en v1.
RELATIVE_LEGACY = {
    "cn0_vs_base_db", "agc_vs_base_db", "cn0_vs_slow_db", "agc_vs_slow_db",
    "home_time_ratio", "radar_range_ratio",
}  # fmt: skip


# Lista de referencia (no es la de la tabla): la de la situación más las señales de que la causa
# continúa o ha terminado, que es lo que distingue «volviendo» de «desviado». Solo para comparar
# con la regla determinista, que usa esas señales a través de las facetas aprendidas.
SITUATION_WITH_CAUSE_SIGNALS = [name for name, _ in ALLOWED["drone.situation"]] + [
    "wind_est_over_limit", "station_wind_over_limit", "cn0_vs_nominal_db", "agc_vs_nominal_db",
    "link_loss_pct", "gps_fix_3d",
]  # fmt: skip
