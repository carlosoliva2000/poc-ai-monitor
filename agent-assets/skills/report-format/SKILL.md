---
name: report-format
description: Estructura y estilo del informe final del ejercicio. Úsala siempre antes de escribir el informe.
---
# Formato del informe final

Escribe en **Markdown**, en español, para un responsable que no ha visto la simulación. Breve: cabe en una pantalla y media. Tiempos como T+mm:ss.

## Estructura (en este orden)

```markdown
# Informe de la misión <mission_id>

**Escenario:** <nombre> · **Duración:** <mm:ss> · **Misión completada:** sí/no (<motivo>)

## Resumen
3–5 frases: qué pasó, cuántas anomalías hubo, cuál fue la más grave y si el monitor las identificó a tiempo.

## Cronología
| Tiempo | Fuente | Qué pasó |
|---|---|---|
Solo hechos relevantes (despegue, waypoints, inicio y fin de cada anomalía, detecciones, alertas y cierres). Máximo 15 filas.

## Anomalías
Una subsección por alerta del monitor (las sustituidas, juntas con la que las sustituyó):
### <causa en palabras> (<severidad>, confianza <x>)
- **Cuándo:** detección a T+…, alerta a T+… (retraso de diagnóstico: … s de simulación).
- **Qué se vio:** 2–3 frases con cifras y fuentes.
- **Evidencias:** ids principales.
- **Estado:** cerrada a T+… / abierta al final.

## Valoración del monitor
Qué diagnósticos están bien respaldados por los datos, cuáles son dudosos y por qué, y si hubo detecciones sin alerta o alertas sin detección. No tienes la verdad del simulador: valora con los eventos.

## Recomendaciones
2–4 puntos accionables para el responsable del dron o del ejercicio.

## Limitaciones
Datos simulados; el monitor solo veía lo ocurrido hasta cada instante; lo que no se pudo comprobar.
```

## Reglas
- Cada cifra sale de una tool. Si no tienes un dato, escribe «no disponible».
- No copies el JSON de las tools: tradúcelo a frases.
- Sin adornos ni conclusiones que no salgan de los datos.
