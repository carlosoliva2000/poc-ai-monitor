---
name: report-format
description: Estructura y estilo del informe final del ejercicio. Úsala siempre antes de escribir el informe.
---
# Formato del informe final

El informe es un documento en **Markdown**, en español, para un responsable que no ha visto la simulación. Breve: cabe en una pantalla y media. Tiempos como T+mm:ss.

## Quién escribe qué
El informe final lo monta el módulo con estas partes, en este orden:

1. **Cabecera** (módulo): misión, escenario, duración, si se completó, waypoints y número de anomalías.
2. **Resumen** (tú).
3. **Cronología** (módulo): tabla con las detecciones, las alertas y los cierres, con su hora.
4. **Anomalías** (módulo y tú): una subsección por anomalía (cada cadena de alertas que se sustituyen entre sí es **una** anomalía), con la hora y la severidad de su primera alerta, los cambios de la última, las evidencias y el estado, escritos por el módulo. Tú escribes solo el «Qué se vio» de cada una.
5. **Valoración del monitor** (tú).
6. **Recomendaciones** (tú).
7. **Limitaciones** (módulo).

## Lo que escribes tú
Responde **solo** con estos cuatro apartados, con estos títulos exactos y en este orden:

```markdown
## Resumen
3–5 frases: qué pasó, cuántas anomalías hubo, cuál fue la más grave y si el monitor las identificó a tiempo.

## Qué se vio
### A1
2–3 frases con cifras y fuentes (lo que vio el detector y lo que comprobó el monitor). Sin repetir la hora, la severidad ni el estado.
### A2
…

## Valoración del monitor
Con espíritu crítico, en cuatro viñetas: **Respaldo** (qué comprobaciones sostienen cada causa y qué duda queda), **Retrasos**, **Fallbacks y rechazos** (cifras exactas) y **Ayudas** (cuáles tenía activas y cómo pueden influir en el resultado).

## Recomendaciones
1. …
2. …
```

## Reglas
- Cada cifra sale de los datos que te entregan. Si no tienes un dato, escribe «no disponible».
- No escribas horas, severidades, estados ni ids que no estén en los datos; los hechos los pone el módulo.
- No copies el JSON de los datos: tradúcelo a frases.
- Sin adornos ni conclusiones que no salgan de los datos.
