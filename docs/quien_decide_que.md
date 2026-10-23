# poc-ai-monitor · Quién decide qué

Estado al cerrar la Fase 5 (23/10/2026; **todo en inglés, comportamiento del modelo en inglés sin evaluar**: ver `docs/fases/fase5.md`) sobre el de la Fase 4.3 (22/10/2026): el monitor, con la configuración de la ronda R9 y el prompt de salida original (el de las fases 3, 3.1 y 4; el castellano llano de la 4.1 se revirtió), y los chats a temperatura 0 con hechos interpretados por el código (huella `cd2925fe198331cc` en la 4.3; en la Fase 5, por la traducción, `e28d071e856efb09`) y el modelo `Qwen/Qwen2.5-14B-Instruct-AWQ` en vLLM (sin cambios), y el informe rehecho (los hechos los escribe el código). Sirve para explicar la demo sin vender de más y para saber qué hay que quitar cuando se pruebe un modelo mejor. Detalle y trazas en `docs/fases/fase3.md` (§9 ayudas, §10 conclusiones, §14 pendientes) y en `docs/fases/fase3_1.md` (informe). **Se mantiene al día al cerrar cada fase.**

## 1. Las piezas y qué decide cada una

| Pieza | Qué decide | ¿Determinista? | Dónde vive |
|---|---|---|---|
| **Simulador** (plataforma) | Cómo vuela el dron y qué publica cada fuente. Es la verdad, que nadie de la IA ve. Con «esperar al agente», el reproductor **se pausa con cada aviso del detector, también con los cierres**, y sigue cuando el monitor responde a todos. | Sí (semilla) | `platform/` |
| **Tools de datos** (plataforma) | Nada: **calculan hechos** a partir de los eventos hasta el instante actual (desviaciones, distancia GPS–radar, viento de la ventana y si es notable, si va a favor de la deriva, si GPS y radar discrepan, el mayor salto del GPS). Nunca devuelven eventos posteriores al instante de la invocación. | Sí | `platform/.../tools/` |
| **Detector de reglas** | **Qué es anómalo y cuándo**: abre, actualiza y cierra detecciones con 4 reglas e histéresis (`ROUTE_DEVIATION`, `SOURCE_DISCREPANCY`, `SOURCE_SILENT`, `GPS_DEGRADED`). No sabe de causas. | Sí | `ai-module-py/.../detector` |
| **Agente monitor (LLM)** | **La causa** (en los casos del §2), la severidad, la confianza, si un aviso es una alerta nueva, sustituye a otra o se reconoce, si una alerta se cierra, qué tools y skills usar, qué evidencias citar y **todo el texto** (resumen, explicación, recomendación). **Ese texto puede contradecir sus propios `checks`** (por ejemplo «GPS and radar disagree by 13.8 m» con GPS y radar sin discrepar): nada lo verifica antes de publicarlo; lo vigila la evaluación y la web solo limpia la presentación (ver «Evaluación» y §5). | No | `agent-assets/` + `ai-module-py/.../agent` |
| **Guardrails** | **Vetan** lo que propone el modelo y le dicen qué corregir (los rechazos están en inglés): formato; ids de detección y de alerta (que existan, que sean del lote que se atiende, que no se duplique una alerta ni se cierre con detecciones abiertas; una alerta que sustituye a otra tiene que cambiar la causa o la severidad: si no, «Nothing changes…: use acknowledge_detection»); evidencias que existan, anteriores al instante; que las comprobaciones (`checks`) coincidan con lo que devolvieron las tools y el estado; y la causa solo en **tres casos**: `WIND` exige viento notable a favor de la deriva, `HIJACK` exige haber mirado el enlace y las causas del GPS sobre un `ROUTE_DEVIATION` exigen alerta del GPS reciente y discrepancia o salto. En la recuperación del GPS (§2) **imponen** la causa, el `supersedes` y la severidad `medium` (y esa regla pasa por delante del veto «No cambia nada», para no mandar reconocer una recuperación). | Sí | `ai-module-py/.../agent/guardrails.py` |
| **Orquestación del módulo** | **Que cada aviso tenga respuesta.** Responde **sin LLM** a los cierres que no cambian nada (la detección no tenía alerta, su alerta ya estaba cerrada o a la alerta aún le quedan detecciones abiertas). El reconocimiento lleva `alert_id` solo si la alerta sigue abierta. Si el modelo no concluye: una alerta `UNKNOWN` «sin diagnóstico» (confianza 0,1) si llega una detección nueva o actualizada y no hay ninguna alerta abierta; si la hay, un reconocimiento sin alerta; y en un aviso de cierre de la última detección de una alerta, la cierra. Rellena ids cuando solo hay una opción, corta la invocación si el modelo repite por segunda vez una llamada rechazada (y aplica el fallback) y calcula el valor esperado de `checks.link_anomalous` sobre los eventos de enlace que pidió el modelo, para vetar una declaración distinta. | Sí | `ai-module-py/.../monitor.py` |
| **Informe** | **Los hechos los escribe el código**: cabecera, cronología, T+ de detección, alerta y cierre de cada anomalía (una cadena de `supersedes` es una anomalía, con la hora y la severidad de su primera alerta y las de la última si cambian), estado, evidencias, las cifras del monitor (invocaciones, fallbacks, rechazos, ayudas activas) y las limitaciones. **El LLM solo redacta** el resumen, «qué se vio» de cada anomalía, la valoración del monitor y las recomendaciones; para valorar recibe los retrasos, los fallbacks, los rechazos y las ayudas, y se le pide que sea crítico. Si no concluye, el informe sale con los hechos y esos apartados marcados como no disponibles. | Mixto | `ai-module-py/.../report.py`, `report_facts.py` |
| **Chats** | El LLM responde, **sin tools** y **a temperatura 0** en la demo, con el estado, las alertas (con sus comprobaciones y evidencias, **sin la explicación en prosa del monitor**) y los últimos hechos que consultó el monitor, **cada uno con su sí o no ya calculado** por el código con las reglas del guardrail (viento notable, deriva a favor, GPS y radar discrepan, salto del GPS, enlace anómalo) y sus cifras. **El código decide si algo es «notable» o «a favor»; el chat solo lo cuenta.** El del informe, además, con el informe. | No | `ai-module-py/.../chat.py`, `chat_facts.py` |
| **Evaluación** | Si el diagnóstico es correcto, contrastándolo con las etiquetas del escenario, y **cuántas frases del texto de las alertas contradicen sus `checks`** (tres reglas simples sobre resumen, explicación y recomendación, con patrones en inglés y en castellano; las lista en `eval.md`; solo vigila, no impide nada). No la usa ningún agente. | Sí | `ai-module-py/.../evaluate.py` |

## 2. Quién pone la causa en cada caso

| Caso | Quién avisa | Quién pone la causa | Cómo de acotado está el modelo |
|---|---|---|---|
| **Viento** | Detector (`ROUTE_DEVIATION`) | **Modelo** | Lee los hechos `wind.notable` y `wind.with_drift` (calculados) y decide; el guardrail rechaza `WIND` si los hechos no lo apoyan. |
| **Spoofing** (discrepancia) | Detector (`SOURCE_DISCREPANCY`) | **Modelo** | La skill le pide mirar la calidad del fix del GPS y la geometría. El guardrail comprueba que sus `checks` cuadren con los datos, pero **no tiene veto de causa** sobre una discrepancia: elegir `GPS_SPOOFING` es del modelo. |
| **Recuperación tras spoofing o pérdida de GPS** | Detector (`ROUTE_DEVIATION`) | **Código (guardrail)** | Si hay una alerta del GPS reciente (abierta o cerrada hace 60 s o menos) y los hechos dicen «salto de 30 m o más» o «discrepancia», **solo vale la causa de esa alerta, con `supersedes` si sigue abierta y severidad `medium`** (las tres cosas se comprueban). El modelo suele proponer otra cosa (a veces la severidad de la alerta anterior): el rechazo le dice qué publicar y él solo redacta. |
| **Secuestro** | Detector (`ROUTE_DEVIATION`) | **Modelo** | Una sola alerta: si la detección sube de severidad y el modelo no cambia ni la causa ni la severidad, el guardrail rechaza el `supersedes` y obliga a reconocerla. Tiene que mirar el enlace: el guardrail exige haberlo mirado (`link_checked`) y que declare bien `link_anomalous`, cuyo valor esperado calcula el módulo (si se equivoca, el rechazo le dice el correcto). **No exige que sea anómalo para publicar `HIJACK`**: decidirlo es del modelo. |
| **Fuente callada** | Detector (`SOURCE_SILENT`) | **Modelo** | `SENSOR_FAULT`; sin veto de causa. Bien con el radar; con el GPS durante una pérdida de GPS falla (pendiente F3). |
| **Pérdida de GPS** | Detector (`GPS_DEGRADED`) | **Modelo** | `GPS_JAMMING`; sin veto de causa. Las detecciones que siguen a veces abren otra cadena (pendiente F2). |
| **Cierre** | Detector (`DetectionCleared`) | **Código** si a la alerta le quedan detecciones abiertas (o no tenía alerta o ya estaba cerrada); **modelo** si era la última (cierra o la mantiene). | El guardrail no deja cerrar con detecciones abiertas. El modelo a veces la mantiene abierta queriendo cerrar (pendiente). Si no concluye, el módulo la cierra. Con «esperar al agente», el cierre sale a la hora en que termina la detección. |

**En una frase:** el detector decide *que* algo va mal; las tools calculan *los hechos*; el modelo decide *por qué* (viento, spoofing, secuestro, fallos de sensor) y lo cuenta; los guardrails vetan lo incoherente y, en la recuperación del GPS, deciden ellos; y en el informe los hechos son del código y la narrativa, del modelo.

## 3. Ayudas al modelo (se pueden quitar con uno mejor)

De la más a la menos intrusiva. Todas con interruptor en `agents.yaml` (`monitor.*`; los chats, `chat.tools_enabled`), salvo las marcadas.

| Ayuda | Qué le quita al modelo | Interruptor |
|---|---|---|
| Guardrail de coherencia (incluida la recuperación excluyente) | Equivocarse de causa sin que nadie lo pare; en la recuperación, la decisión | `monitor.coherence_guardrail` |
| `checks` obligatorios antes de la causa | Saltarse comprobaciones del árbol | `monitor.require_checks` |
| Hechos calculados en `get_track_metrics` | Comparar números y ángulos | `monitor.computed_facts` |
| Última iteración solo con las tres respuestas | Encadenar tools de datos sin decidir | `monitor.final_iteration_response_tools_only` |
| `tool_choice: required` | El formato de la llamada | `monitor.tool_choice` |
| Chats sin tools | Elegir qué consultar | `chat.tools_enabled` |
| Hechos de los chats con su sí o no calculado, y alertas sin la prosa del monitor | Comparar números y ángulos (decidir si un viento es notable o va a favor) y repetir un error de la prosa del monitor | (sin interruptor; en git) |
| Informe sin tools (datos inyectados) | Elegir qué consultar | (sin interruptor; en git) |
| Informe: hechos escritos por el código | Copiar bien horas, severidades, estados y evidencias | (sin interruptor; en git) |
| Ids que rellena el módulo | Copiar ids | (sin interruptor; contrato v0.8) |
| Prompts y skills reescritos para este modelo | Interpretar instrucciones largas | (sin interruptor; originales en git) |

**No son ayudas** y se quedan con cualquier modelo: la respuesta garantizada a cada aviso y los fallbacks, los cierres deterministas, el corte temporal, que el modelo nunca vea la verdad, los mensajes de rechazo accionables, `repetition_penalty` y `top_k` explícitos, las trazas y la evaluación contra etiquetas.

## 4. Qué contar al equipo
1. Con un 14B local, **el formato** de las tool calls fue lo primero en fallar; `required` lo resolvió (que haya una llamada bien formada; no que vengan todos los campos obligatorios: eso lo reclaman los guardrails).
2. El modelo **no ejecuta un árbol de decisión largo** leyendo una skill, aunque tenga los números: salta a la conclusión que más se parece a lo que ve.
3. Lo que funcionó fue **calcular los hechos en código, obligar a declarar las comprobaciones y vetar lo incoherente**. Donde la decisión es mecánica (la recuperación), la toma el código y el modelo redacta.
4. Lo que no depende del modelo (contrato, respuesta garantizada, trazas, evaluación) es lo que permitió medir todo esto, y es lo que se lleva tal cual al módulo Java.
5. **En el informe pasa lo mismo:** cuando lo escribía todo el modelo, se equivocaba en las horas (daba la alerta del spoofing a T+03:42 y «media», y el cierre del viento a T+03:12) y valoraba al monitor sin dudas. Ahora las horas, las cadenas y las cifras son del código; el modelo se limita a redactar y, con el prompt nuevo, nombra los retrasos, los rechazos y las ayudas. Sigue siendo un 14B: puede citar mal una cifra en la narrativa, y por eso las del monitor van también en una línea escrita por el módulo.

## 5. El texto de las alertas no está verificado
El resumen, la explicación y la recomendación de una alerta los escribe el modelo, y **el guardrail contrasta sus `checks` con las tools, no su prosa**. Con el 14B, a temperatura 0, la demo de viento (entonces en castellano) repetía siempre «GPS y radar discrepan 13,8 m» y «empuja en dirección contraria a la deriva» contra sus propios `checks` (GPS y radar sin discrepar, deriva a favor). Pedirle que escribiera sin nombres de campo lo agravó (los nombres le servían de ancla) y se revirtió. Hoy:
- **La métrica «frases que contradicen los checks»** de `eval.md` lo vigila (solo vigila).
- **La web** quita de lo que muestra los paréntesis que solo contienen `campo=valor` o `campo: valor`; es un parche de presentación, no arregla las frases falsas. El evento, `eval.md` y el informe conservan el texto original.
- **Los chats** no repiten el problema porque reciben las alertas sin la explicación en prosa y con los hechos ya interpretados por el código (Fase 4.2).
- Soluciones de verdad, sin hacer: `docs/mejoras_futuras.md`, «Texto fiable del monitor».

## 6. Pendientes ligados a esto
- **Texto fiable del monitor** (`docs/mejoras_futuras.md`): explicación estructurada con plantillas, verificar el texto contra los `checks` antes de publicarlo, o un modelo mejor.
- **Liberar al agente** (`docs/mejoras_futuras.md`): con un modelo más moderno (Qwen3 instruct, por ejemplo), apagar las ayudas del §3 de arriba abajo y comparar los `eval.md`.
- **Probar el monitor con modelos de Claude** (`docs/mejoras_futuras.md`, dentro de «Liberar al agente»): `claude-haiku-5-5`, luego `claude-sonnet-5-5` y, solo como techo y avisando, `claude-opus-5-5`, con todas las ayudas apagadas. Exige una excepción explícita a la regla 1 («nada en la nube»), que decide Carlos.
- **`faults`**: F3, las dos cadenas de F2 y las alertas que quedan abiertas: decisiones mecánicas candidatas a regla.
