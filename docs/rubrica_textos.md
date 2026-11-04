# poc-ai-monitor · Rúbrica de los textos de los agentes

Fase 14.2. Es para que **Claude en el chat** y, más adelante, **un modelo de Claude como juez (E5)** valoren los textos de la misma manera. Sirve para lo que la medida automática (`tools/experiments/text_metrics.py`) no ve: conclusiones blandas, relleno, recomendaciones sin acción, críticas sin respaldo. Los textos están en inglés (los escribe el modelo); esta guía, en castellano.

## Qué se valora
Todo texto que escribe un modelo para una persona: `summary`, `explanation` y `recommendation` de las alertas, el motivo de un cierre o de un reconocimiento, las respuestas de los chats, y el informe de misión (resumen, «qué se vio» y recomendaciones). **La autoevaluación del monitor (anexo del informe) se valora aparte**: es técnica a propósito y los criterios 3 y 4 no se le aplican igual.

## Cómo se aplica
1. Antes de leer el texto, lee **los hechos** que tenía el modelo: la alerta (causa, severidad, fase, checks), el resultado de `get_track_metrics` (la ventana y `now`) y las detecciones. Sin ellos no se puede juzgar el criterio 1.
2. Cada criterio se marca **cumple / no cumple** (y una frase de motivo con la cita). No hay nota media: un texto con un fallo del criterio 1 no se salva por ser concreto.
3. Orden de prioridad: **correcto → concreto → útil → crítico con respaldo**. Si hay un error de contenido, es lo primero que se dice.
4. Se cita siempre la frase que falla. «Suena robótico» no es un hallazgo.

## 1. Correcto
Las cifras, las direcciones, las causas y las conclusiones coinciden con los hechos y con lo que el propio sistema publicó. Mira tres cosas: **de dónde viene el viento y hacia dónde va** (no confundirlos), **«ahora» frente a la ventana** (una cifra de la ventana no es el presente) y **que el texto no contradiga sus `checks`, su severidad o su fase**.

No cumple:
- `e13-textos.md:87` (Qwen3-30B-A3B-2507, cierre de A1): «wind is light (2.3 m/s, from 336°)». 2,3 m/s es una muestra suelta; la media del episodio era 7,2 m/s.
- `e13-textos.md:107` (Ministral 3 14B, cierre de A1): «The wind is notable (7.2 m/s from 171.3°)». 171,3° es hacia donde sopla; viene de unos 351°.
- `e14-1-textos.md:233` (`actual`, recuperación del spoofing): «At T+03:42, GPS and radar disagree by 9.9 m… This suggests GPS spoofing.» 9,9 m es la distancia de **ahora**: coinciden, y el engaño ha terminado.

Cumple:
- `e14-1-textos.md:375` (Qwen3-32B, misma recuperación): «At T+03:42, the GPS position (gps-000222) shows a sudden jump from 2098.2,1072.0 to 2055.2,1003.5 meters, indicating a recovery from a spoofing incident. However, the GPS is still 73.9 meters off the planned route.»
- `e14-1-textos.md:39` (`actual`, A1): «At T+01:46, GPS shows 30.5 m deviation from route. Wind reported at T+01:45 (met-0010) is from N (342°), pushing S (146°)… Wind aligns with drift direction (4.9°). GPS and radar agree (distance 5.7 m).»

## 2. Concreto
Dice algo de **este caso**: cifras con su unidad, ids de eventos, tiempos T+mm:ss, fuentes. Un dato correcto pero irrelevante para la causa es relleno y tampoco cumple.

No cumple:
- `e14-1-textos.md:43` (`actual`, recomendación de A1): «Monitor drone's position and ensure it stays on course. Wind conditions may affect navigation accuracy.» Vale para cualquier vuelo.
- `e14-1-textos.md:181` (`actual`, explicación de A2): «…Wind is pushing the drone (wind from 299.1°, gusts up to 4.3 m/s).» Dato de viento que no explica un engaño del GPS.
- `e13-textos.md:179`: «Wind is pushing the drone, but it is not notable.» Relleno: afirma y niega a la vez.

Cumple:
- `e14-1-textos.md:39` (arriba): hora, id, cifras y dirección, todo del caso.
- `e14-1-textos.md:1874` (gpt-oss-20b, F3): «GPS has not reported for 5s (det-0008)…» Dice cuánto, qué detección y qué fuente.

## 3. Útil para el operador
El responsable del dron, que no ve los datos ni las tools, sabe **qué hacer ahora y por qué**. La recomendación nombra una acción sobre el dron, el radar, el enlace, la ruta o el GPS, y la justifica con la causa o los datos. Una fórmula de seguridad que valdría para cualquier alerta («asegura canales seguros») no cumple; tampoco «investiga más» sin decir qué mirar.

No cumple:
- `e14-1-textos.md:223` (`actual`, A2): «Investigate GPS spoofing immediately. Verify the authenticity of GPS signals and ensure secure communication channels.»
- `e13-textos.md:532` (`actual`, chat del monitor sobre el enlace en un secuestro): «There is no indication of a major disruption, but the change in the controller and fluctuating latency could suggest potential issues that need further investigation.» Con el controlador cambiado a `UNK-4F2A`, no dice qué hacer.

Cumple:
- `e14-1-textos.md:337` (Qwen3-32B, A2): «Do not trust the GPS data. Use the radar as a reference for the drone's actual position and notify the person in charge immediately.»
- `e14-1-textos.md:1746` (`actual`, F2): «Do not trust the GPS. Use radar as reference. Monitor for further degradation.»

## 4. Crítico solo con respaldo
Una duda, una crítica o una valoración se escribe **solo si un dato la sostiene**: dos fuentes que se contradicen, una fuente que falta, una causa que cambió, una anomalía abierta. Una duda inventada para sonar prudente, o una conclusión contraria a los datos («estaba mal») sin dato, no cumple. Y al revés: no concluir «todo fue bien» si los datos dicen otra cosa.

No cumple:
- `e13-textos.md:656` (informe antiguo, A1): «Supported by GPS and radar agreeing on the deviation and notable wind conditions, though wind alignment with drift introduces some uncertainty.» La deriva iba a favor del viento (4,9°): la duda no tiene dato.
- `e14-1-textos.md:904` (gpt-oss-20b, anexo): «the monitor’s severity decreased from high to medium between the first and second alerts, suggesting uncertainty in the spoofing assessment.» La bajada la impuso el guardrail de la recuperación, no una duda del monitor.

Cumple:
- `e14-1-textos.md:1874` (gpt-oss-20b, F3): «Recent GPS alert ai-0006 indicates GPS_JAMMING; however, this silent source is treated as a separate fault. No radar or wind evidence contradicts a sensor failure.» Distingue dos cosas y dice qué datos no la contradicen (aunque filtre el nombre de la causa: eso lo mide `enum_names`).
- `e14-1-textos.md:1061` (`actual`, anexo): «Review the severity change in A2 (from high to medium) and ensure consistency… when the GPS/radar discrepancy trend contradicts the severity adjustment.» Critica un hecho real del diseño (la severidad de la recuperación), que la 14.2 resuelve con la fase de la alerta.

## Qué ve la medida y qué no
La medida automática ve nombres internos, frases copiadas, ids inexistentes, cifras y direcciones que no cuadran, «ahora» mezclado con la ventana, viento en el cierre de una causa sin relación, recomendaciones genéricas y sin acción, tipo de cada anomalía en el resumen y jerga del monitor en las recomendaciones. **No ve** conclusiones blandas o contrarias a los datos sin cifra (el chat que dice «no hay indicios» en pleno secuestro), críticas sin respaldo sin cifra, ni la calidad de la redacción: eso es la rúbrica.
