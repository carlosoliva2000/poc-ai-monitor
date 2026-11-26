# Anexo del guion del vídeo (19/11) · instantes con el monitor de la E7c

Escrito para: quien graba el vídeo. **Los instantes cambian porque el monitor ahora ejecuta las tablas congeladas (k = 5, m = 10) y el catálogo nuevo; no se ha ajustado nada para que cuadren con el guion.** Lo demás del guion (`video-19-11.md`: cómo arrancar, velocidades, pausas, preguntas exactas) sigue valiendo. Medido el 26/11/2026 con `python -m platform_app.run` a 16× (monitor en directo) y con el ensayo de la web (`web/scripts/capture.mjs video1|video2`); en directo los instantes varían unos segundos entre pasadas.

## Arranque (sin cambios)
```bash
uv run --project platform python -m platform_app.app                                         # 8100
uv run --project ai-module-py python -m ai_module.situation --platform http://127.0.0.1:8100 # el monitor
cd web && pnpm dev                                                                            # 3000
```
O, todo junto sin la web: `uv run --project platform python -m platform_app.run --scenario demo --speed 16`.

## Vídeo 1 · `demo`
| Incidente | En el guion | Ahora (en directo) | Qué hacer con la pausa |
|---|---|---|---|
| `Wind beyond limit` | abre T+02:18, recuperación T+02:35, cierra T+03:00 | abre **T+02:19** (baja, «probable»), sube a media y «confirmada» a T+02:20; recuperación **T+02:37**; cierra **T+03:00** | la pausa «WIND abierto» vale (T+02:19–02:20) |
| `GPS spoofing` | abre T+03:20 (dron a 14 m de la ruta), actualiza T+03:31, recuperación T+04:12, cierra T+04:32 | abre **T+03:22** (alta, «confirmada», dron «on route»); evidencias T+03:40 y T+04:04; recuperación **T+04:12**; cierra **T+04:33** | la pausa «lo ve antes de que se desvíe» vale; la desviación del radar se ve hacia T+03:40, no T+03:31 |
| `Command link lost` → `Hijack` | abre T+06:14, renombra T+06:24, recuperación T+06:55, cierra T+07:58 | abre **T+06:12** (media), sube a alta T+06:20, **renombra a Hijack T+06:28** (pide causa y modo confirmados), recuperación **T+06:53**, cierra **T+07:58** | la pausa de la pregunta a T+398 vale: Hijack lleva 26 s abierto; la tarjeta dice 208 m de desviación (en el guion, 288 m); el texto del chat («more than 200 m») sigue siendo cierto |

- **Revisiones de evidencias en `demo`:** 9 en directo (3 en cada incidente: viento T+02:30, 02:42 y 02:51; engaño T+03:40, 04:04 y 04:24; secuestro T+06:16, 06:44 y 07:49); con las tablas del vídeo eran 12. El viento tiene ya una sola recuperación (T+02:37).
- **«Injected vs detected»** (final de `demo`): viento 7 s, engaño 4 s, secuestro 4 s después de empezar (en el guion, 6, 2 y 6).
- **El viento abre «probable» y baja de «Wind beyond limit · low»**: la fila de causa lee «spoofed position» en el primer segundo (la estación del viento aún no ha registrado la ráfaga) y una pasada después ya dice «wind». La tarjeta enseña las dos cosas; es de las tablas (E8), no se ha tocado.
- **La tarjeta ya no habla de «viento por encima del límite 7 s» ni «desvío 29 m»:** las evidencias salen de las tablas aprendidas y se leen como cocientes con los activos («Estimated wind over the drone limit 1.5 > 0.93», «C/N0 vs nominal +7.2 dB»). Hay que decirlo al hablar: «1,5 es una vez y media el límite del dron».
- El informe sale ~4 s después de terminar («3 incidents») y dice lo mismo que antes.

## Vídeo 2 · `nominal` con las dos órdenes
| Qué | En el guion | Ahora |
|---|---|---|
| Orden 1 (19 m/s del norte) | pausa ≈ T+105 | igual: el comando se aplica a T+01:45 |
| `Wind beyond limit` abre | T+01:59–02:03 | **T+01:59** (baja «probable»); media y «confirmada» T+02:00; evidencias T+02:20 |
| Orden 2 (quitar el viento) | pausa ≈ T+148 | igual: se aplica a T+02:27 |
| Recuperación / cierre | T+02:34 / T+02:50 | **T+02:40 / T+02:49** |

`nominal` sin órdenes: ningún incidente (tanto en el replay como en directo).

## Capturas
`results/capturas/e7c/video1/` (13 + `capture_log.json`) y `results/capturas/e7c/video2/` (8 + `capture_log.json`); los registros de salida del script están en `video1.log` y `video2.log`. Las reglas se ven con las tablas congeladas (13 aprendidas y la regla de la situación), con la confianza y la probabilidad de cada fila y el respaldo (variantes e instantes de entrenamiento) al pasar el ratón por la salida.

## Lo que se ve distinto en la web
- Cada fila de «Rules» dice la confianza y la probabilidad de la hoja («spoofed · confirmed (p 0.96)») y el número de variantes y de instantes de entrenamiento.
- Los incidentes nuevos del catálogo (fuente sin datos con su nombre —«Radar silent»—, batería, failsafe, interferencia…) salen con su tarjeta; «Undetermined deviation» enseña «Hypothesis: none» hasta que haya asistente con LLM.
- No hay «Wait for the agent» ni detecciones: el monitor nuevo no las publica.
